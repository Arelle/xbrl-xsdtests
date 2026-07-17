"""
See COPYRIGHT.md for copyright information.

Pipeline orchestration.

Single-pass streaming over testGroups: parse -> extract schema/value -> dedup ->
emit taxonomy (once per unique type key) + instance + variation; untranslatable
groups/instances are recorded in the skip manifest. The ``index.xml`` is written
**last** (after every testcase file exists), then an **internal consistency
check** confirms every ``<testcase uri>``, ``<instance>`` href, and ``schemaRef``
href resolves on disk.

The whole module stays **Arelle-runtime-free** (only ``arelle.XbrlConst`` via the
emitters) — the validation smoke check that actually runs Arelle is a separate
pytest.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path

from xbrl_xsdtests import xmlutil as etree

from xbrl_xsdtests import sources
from xbrl_xsdtests.dedup import TaxonomyDedup
from xbrl_xsdtests.emit import (
    CONFORMANCE_NS,
    INDEX_FILENAME,
    LINK_NS,
    XLINK_NS,
    IndexEmitter,
    InstanceEmitter,
    TaxonomyEmitter,
)
from xbrl_xsdtests.manifest import (
    MANIFEST_FILENAME,
    SkipManifest,
)
from xbrl_xsdtests.model import (
    ExtractedType,
    InstanceTestRef,
    SkipRecord,
    SourceSet,
    TestGroupRef,
    TypeKey,
)
from xbrl_xsdtests.parse import (
    InstanceExtractor,
    SchemaExtractor,
    TestSetParser,
)

DEFAULT_VERSION = "1.0"
DEFAULT_OUT = Path("output")


class ConsistencyError(Exception):
    """Raised when an emitted suite references a file that does not exist on disk."""


@dataclass
class GenerateResult:
    out: Path
    index_path: Path
    manifest_path: Path
    groups: int = 0
    taxonomies: int = 0
    instances: int = 0
    testcases: int = 0
    skips: int = 0
    skips_by_reason: dict[str, int] = field(default_factory=dict)


@dataclass
class _GroupBatch:
    """A testGroup and its instanceTests, accumulated from the streaming parser."""

    group: TestGroupRef
    instances: list[InstanceTestRef]


class Generator:
    """Composes the read -> extract -> dedup -> emit pipeline over in-scope sources."""

    def __init__(
        self,
        root: Path,
        out: Path,
        version: str = DEFAULT_VERSION,
        limit: int | None = None,
    ) -> None:
        self._root = root
        self._out = out
        self._version = version
        self._limit = limit
        self._parser = TestSetParser(root)
        self._schema = SchemaExtractor(root)
        self._instance = InstanceExtractor(root)
        self._dedup = TaxonomyDedup()
        self._taxonomy = TaxonomyEmitter()
        self._instances = InstanceEmitter()
        self._index = IndexEmitter()
        self._manifest = SkipManifest()
        self._groups = 0
        self._taxonomies = 0
        self._instance_count = 0

    def run(self) -> GenerateResult:
        self._out.mkdir(parents=True, exist_ok=True)
        for source in self._in_scope():
            if self._limit is not None and self._groups >= self._limit:
                break
            for unit in self._stream_groups(source):
                if self._limit is not None and self._groups >= self._limit:
                    break
                self._groups += 1
                if isinstance(unit, SkipRecord):
                    self._manifest.add(unit)
                    print(f"[SKIP] {self._groups}\t from {source.member}\t - {unit.group}")
                else:
                    self._process_group(unit)
                    print(f"[DONE] {self._groups}\t from {source.member}\t - {unit.group.name}")
        testcase_paths = self._index.write(self._out)
        manifest_path = self._manifest.write(self._out)
        summary = self._manifest.summary()
        result = GenerateResult(
            out=self._out,
            index_path=self._out / INDEX_FILENAME,
            manifest_path=manifest_path,
            groups=self._groups,
            taxonomies=self._taxonomies,
            instances=self._instance_count,
            testcases=len(testcase_paths),
            skips=summary["total"],
            skips_by_reason=summary["by_reason"],
        )
        return result

    def _in_scope(self) -> list[SourceSet]:
        return [s for s in sources.in_scope_sources() if s.xsd_version == self._version]

    def _stream_groups(self, source: SourceSet) -> Iterator[_GroupBatch | SkipRecord]:
        """Group the parser's per-instanceTest stream back into whole testGroups.

        The parser emits all instanceTests of a testGroup contiguously, and a
        standalone ``schema-test-only`` ``SkipRecord`` for groups with none.
        """
        current: TestGroupRef | None = None
        bucket: list[InstanceTestRef] = []
        for item in self._parser.iter_instance_tests(source):
            if isinstance(item, SkipRecord):
                if bucket:
                    yield _GroupBatch(group=current, instances=bucket)  # type: ignore[arg-type]
                    current, bucket = None, []
                yield item
                continue
            if current is not None and item.group != current:
                yield _GroupBatch(group=current, instances=bucket)
                bucket = []
            current = item.group
            bucket.append(item)
        if bucket:
            yield _GroupBatch(group=current, instances=bucket)  # type: ignore[arg-type]

    def _process_group(self, batch: _GroupBatch) -> None:
        extracted = self._schema.extract(batch.group)
        if isinstance(extracted, SkipRecord):
            self._manifest.add(extracted)
            return
        key, is_new = self._dedup.get_or_register(extracted)
        if is_new:
            self._taxonomy.emit(key, extracted, self._out)
            self._taxonomies += 1
        for ref in batch.instances:
            self._process_instance(ref, key, extracted)

    def _process_instance(self, ref: InstanceTestRef, key: TypeKey, t: ExtractedType) -> None:
        values = self._instance.extract(ref, dict(t.element_identities), t.target_identity)
        if isinstance(values, SkipRecord):
            self._manifest.add(values)
            return
        self._instances.emit(ref, values, key, t, self._out)
        self._index.add_variation(t, key, ref)
        self._instance_count += 1


def generate(
    root: Path = sources.DEFAULT_ROOT,
    out: Path = DEFAULT_OUT,
    version: str = DEFAULT_VERSION,
    limit: int | None = None,
    self_test: bool = True,
) -> GenerateResult:
    """Generate the suite into ``out`` and (by default) verify internal consistency."""
    root = Path(root)
    out = Path(out)
    result = Generator(root, out, version=version, limit=limit).run()
    if self_test:
        check_consistency(out)
    return result


def check_consistency(out: Path) -> None:
    """Assert every index/testcase/instance reference resolves on disk (no Arelle).

    Raises ``ConsistencyError`` on the first dangling reference — a "fail loud"
    guard for a generator bug or a removed file.
    """
    index_path = out / INDEX_FILENAME
    if not index_path.is_file():
        raise ConsistencyError(f"missing index: {index_path}")
    index = etree.parse(str(index_path)).getroot()
    for testcase_el in index.findall("{*}testcase"):
        uri = testcase_el.get("uri")
        if not uri:
            raise ConsistencyError(f"<testcase> without uri in {index_path}")
        testcase_path = out / uri
        if not testcase_path.is_file():
            raise ConsistencyError(f"missing testcase file: {testcase_path}")
        _check_testcase(testcase_path)


def _check_testcase(testcase_path: Path) -> None:
    testcase = etree.parse(str(testcase_path)).getroot()
    base = testcase_path.parent
    for instance_el in testcase.findall(f".//{{{CONFORMANCE_NS}}}instance"):
        href = (instance_el.text or "").strip()
        if not href:
            raise ConsistencyError(f"empty <instance> href in {testcase_path}")
        instance_path = base / href
        if not instance_path.is_file():
            raise ConsistencyError(f"missing instance file: {instance_path}")
        _check_schema_ref(instance_path)


def _check_schema_ref(instance_path: Path) -> None:
    instance = etree.parse(str(instance_path)).getroot()
    schema_ref = instance.find(f"{{{LINK_NS}}}schemaRef")
    href = schema_ref.get(f"{{{XLINK_NS}}}href") if schema_ref is not None else None
    if not href:
        raise ConsistencyError(f"missing schemaRef href in {instance_path}")
    taxonomy_path = (instance_path.parent / href).resolve()
    if not taxonomy_path.is_file():
        raise ConsistencyError(f"missing taxonomy file: {taxonomy_path}")


__all__ = [
    "ConsistencyError",
    "GenerateResult",
    "Generator",
    "DEFAULT_OUT",
    "DEFAULT_VERSION",
    "MANIFEST_FILENAME",
    "generate",
    "check_consistency",
]
