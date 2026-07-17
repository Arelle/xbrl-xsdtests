from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path, PurePosixPath

import pytest
from xbrl_xsdtests import xmlutil as etree
from xbrl_xsdtests.xmlutil import nsmap

from xbrl_xsdtests.emit import (
    CONFORMANCE_NS,
    EXPECTED_ERROR,
    INDEX_FILENAME,
    INDEX_NAME,
    XML_SCHEMA_ERROR_NS,
    IndexEmitter,
    variation_id,
)
from xbrl_xsdtests.emit import (
    testcase_uri as _testcase_uri,  # aliased: a "test"-prefixed name confuses pytest collection
)
from xbrl_xsdtests.model import (
    ExtractedType,
    FacetSet,
    InstanceTestRef,
    SourceSet,
    TestGroupRef,
    TypeKey,
)

_SOURCE = SourceSet(member="x/m.testSet", contributor="NIST", xsd_version="1.0")


def _collect_test_case_paths(file_path: str, tree: etree.ElementTree) -> Iterator[str]:
    """Yield testcase URI paths from an index (mimics the Arelle test harness discovery)."""
    root_el = tree.getroot()
    tag = root_el.tag
    assert isinstance(tag, str)
    if tag.split("}")[-1] == "testcase":
        yield file_path
        return
    for testcases_el in root_el.findall("{*}testcases") or [root_el]:
        test_root = testcases_el.get("root", "")
        for tc_el in testcases_el.findall("{*}testcase"):
            uri = (tc_el.get("uri") or "").replace("\\", "/")
            yield str(PurePosixPath(file_path).parent / test_root / uri)


def _type(base: str) -> ExtractedType:
    return ExtractedType(
        base_xsd=base,
        xbrli_item_type=f"{base}ItemType",
        numeric=base == "decimal",
        facet_set=FacetSet(base_xsd=base, facets=(), enumerations=(), patterns=()),
        facet_xml=(),
    )


def _ref(group: str, name: str, validity: str = "valid") -> InstanceTestRef:
    group_ref = TestGroupRef(source=_SOURCE, name=group, schema_member=f"src/{group}/{group}.xsd")
    return InstanceTestRef(
        group=group_ref,
        name=name,
        instance_member=f"src/{group}/{name}.xml",
        validity=validity,  # type: ignore[arg-type]
    )


# (type, key, ref) tuples spanning two type keys (=> two testcase files).
_DECIMAL = _type("decimal")
_STRING = _type("string")
_DECIMAL_KEY = TypeKey("decimal__minExclusive_-999")
_STRING_KEY = TypeKey("string-b42bdb1f")

ENTRIES = [
    (_DECIMAL, _DECIMAL_KEY, _ref("g-decimal", "d-1", "invalid")),
    (_DECIMAL, _DECIMAL_KEY, _ref("g-decimal", "d-2", "valid")),
    (_STRING, _STRING_KEY, _ref("g-string", "s-1", "valid")),
]


def _emit(out: Path, entries=ENTRIES) -> IndexEmitter:
    emitter = IndexEmitter()
    for t, key, ref in entries:
        emitter.add_variation(t, key, ref)
    emitter.write(out)
    return emitter


class TestIndexDiscovery:
    def test_index_lists_exactly_emitted_testcase_files(self, tmp_path: Path) -> None:
        written = IndexEmitter()
        for t, key, ref in ENTRIES:
            written.add_variation(t, key, ref)
        testcase_paths = written.write(tmp_path)

        index = etree.parse(str(tmp_path / INDEX_FILENAME))
        # For an index, the harness helper *yields* child testcase paths.
        discovered = list(_collect_test_case_paths(INDEX_FILENAME, index))

        expected_uris = sorted({_testcase_uri(t, key) for t, key, _ in ENTRIES})
        assert sorted(discovered) == expected_uris
        # Every discovered testcase path resolves to a file that was written.
        assert sorted(str(p.relative_to(tmp_path).as_posix()) for p in testcase_paths) == expected_uris
        for uri in discovered:
            assert (tmp_path / uri).is_file()

    def test_index_root_is_testcases_with_name(self, tmp_path: Path) -> None:
        _emit(tmp_path)
        root = etree.parse(str(tmp_path / INDEX_FILENAME)).getroot()
        assert root.tag == "testcases"
        assert root.get("name") == INDEX_NAME


class TestVariations:
    def test_variation_ids_unique_and_match_refs(self, tmp_path: Path) -> None:
        _emit(tmp_path)
        all_ids: list[str] = []
        for uri in {_testcase_uri(t, key) for t, key, _ in ENTRIES}:
            tree = etree.parse(str(tmp_path / uri))
            all_ids.extend(v.get("id") for v in tree.findall("{*}variation"))
        assert len(all_ids) == len(set(all_ids)) == len(ENTRIES)
        assert set(all_ids) == {variation_id(ref) for _, _, ref in ENTRIES}

    def test_variations_grouped_by_type_key(self, tmp_path: Path) -> None:
        _emit(tmp_path)
        decimal_tree = etree.parse(str(tmp_path / _testcase_uri(_DECIMAL, _DECIMAL_KEY)))
        assert len(decimal_tree.findall("{*}variation")) == 2
        string_tree = etree.parse(str(tmp_path / _testcase_uri(_STRING, _STRING_KEY)))
        assert len(string_tree.findall("{*}variation")) == 1

    def test_instance_href_is_relative_to_testcase(self, tmp_path: Path) -> None:
        _emit(tmp_path)
        uri = _testcase_uri(_STRING, _STRING_KEY)
        tree = etree.parse(str(tmp_path / uri))
        instance = tree.find(f".//{{{CONFORMANCE_NS}}}instance")
        assert instance.get("readMeFirst") == "true"
        href = instance.text
        # Resolves (positionally) next to the testcase file under <key>/<name>.xbrl.
        assert href == f"{_STRING_KEY.value}/{variation_id(_ref('g-string', 's-1'))}.xbrl"
        assert (tmp_path / uri).parent.joinpath(href).parent.name == _STRING_KEY.value


class TestExpectedResult:
    def test_invalid_emits_value_error(self, tmp_path: Path) -> None:
        _emit(tmp_path)
        tree = etree.parse(str(tmp_path / _testcase_uri(_DECIMAL, _DECIMAL_KEY)))
        invalid = next(
            v for v in tree.findall("{*}variation") if v.get("id") == variation_id(_ref("g-decimal", "d-1"))
        )
        error = invalid.find(f"{{{CONFORMANCE_NS}}}result/{{{CONFORMANCE_NS}}}error")
        assert error is not None
        assert error.text == EXPECTED_ERROR

    def test_valid_emits_empty_result(self, tmp_path: Path) -> None:
        _emit(tmp_path)
        tree = etree.parse(str(tmp_path / _testcase_uri(_STRING, _STRING_KEY)))
        result = tree.find(f"{{{CONFORMANCE_NS}}}variation/{{{CONFORMANCE_NS}}}result")
        assert result is not None
        assert len(result) == 0

    def test_xml_schema_prefix_resolves_to_xdt_namespace(self, tmp_path: Path) -> None:
        # The grader builds a QName from the <error> text against the document's
        # nsmap; the prefix must map to the XDT schema-error namespace.
        _emit(tmp_path)
        root = etree.parse(str(tmp_path / _testcase_uri(_DECIMAL, _DECIMAL_KEY)), track_ns=True).getroot()
        assert nsmap(root).get("xmlSchema") == XML_SCHEMA_ERROR_NS
        prefix, _, _ = EXPECTED_ERROR.partition(":")
        assert prefix == "xmlSchema"


class TestWriteOrdering:
    def test_index_written_after_testcases(self, tmp_path: Path) -> None:
        testcase_paths = _emit(tmp_path).write(tmp_path)
        index = tmp_path / INDEX_FILENAME
        assert index.is_file()
        for path in testcase_paths:
            assert path.is_file()
            assert index.stat().st_mtime_ns >= path.stat().st_mtime_ns


class TestProvenanceComments:
    def test_index_has_generation_header_comment(self, tmp_path: Path) -> None:
        _emit(tmp_path)
        text = (tmp_path / INDEX_FILENAME).read_text(encoding="utf-8")
        assert "<!-- Generated by the XSTS value/facet conformance generator" in text

    def test_testcase_has_generation_header_comment(self, tmp_path: Path) -> None:
        _emit(tmp_path)
        text = (tmp_path / _testcase_uri(_STRING, _STRING_KEY)).read_text(encoding="utf-8")
        assert "<!-- Generated by the XSTS value/facet conformance generator" in text
        assert f"taxonomy: taxonomies/gen-{_STRING_KEY.value}.xsd" in text

    def test_each_variation_preceded_by_source_comment(self, tmp_path: Path) -> None:
        _emit(tmp_path)
        ref = _ref("g-string", "s-1")
        text = (tmp_path / _testcase_uri(_STRING, _STRING_KEY)).read_text(encoding="utf-8")
        variation_id_text = variation_id(ref)
        comment_pos = text.index(f"source instance: {ref.instance_member}")
        variation_pos = text.index(f'<variation id="{variation_id_text}"')
        assert comment_pos < variation_pos

    def test_comment_count_matches_variation_count(self, tmp_path: Path) -> None:
        _emit(tmp_path)
        text = (tmp_path / _testcase_uri(_DECIMAL, _DECIMAL_KEY)).read_text(encoding="utf-8")
        root = etree.parse(str(tmp_path / _testcase_uri(_DECIMAL, _DECIMAL_KEY))).getroot()
        variations = root.findall("{*}variation")
        # stdlib ElementTree drops comments on parse; count them in the serialized file.
        provenance_comments = text.count("source instance:")
        assert provenance_comments == len(variations) == 2

    def test_double_dash_in_values_does_not_break_comments(self, tmp_path: Path) -> None:
        # Type keys / source members can contain runs of hyphens; XML comments
        # forbid '--', so the emitter must sanitize without raising.
        emitter = IndexEmitter()
        group = TestGroupRef(source=_SOURCE, name="g---x", schema_member="src/a--b/s---.xsd")
        ref = InstanceTestRef(group=group, name="n--m", instance_member="src/a--b/i---.xml", validity="invalid")  # type: ignore[arg-type]
        emitter.add_variation(_STRING, TypeKey("string--weird---key"), ref)
        emitter.write(tmp_path)
        # Parses cleanly and the source members survive (with separators inserted).
        root = etree.parse(str(tmp_path / "string/string--weird---key-testcase.xml")).getroot()
        assert len(root.findall("{*}variation")) == 1

    def test_comments_do_not_break_harness_discovery(self, tmp_path: Path) -> None:
        # Comments must not interfere with variation discovery/uniqueness.
        _emit(tmp_path)
        root = etree.parse(str(tmp_path / _testcase_uri(_DECIMAL, _DECIMAL_KEY))).getroot()
        ids = [v.get("id") for v in root.findall("{*}variation")]
        assert len(ids) == len(set(ids)) == 2


class TestDuplicateGuards:
    def test_duplicate_variation_raises(self, tmp_path: Path) -> None:
        emitter = IndexEmitter()
        emitter.add_variation(_DECIMAL, _DECIMAL_KEY, _ref("g-decimal", "d-1"))
        with pytest.raises(ValueError, match="duplicate variation id"):
            emitter.add_variation(_DECIMAL, _DECIMAL_KEY, _ref("g-decimal", "d-1"))
