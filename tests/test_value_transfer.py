"""
See COPYRIGHT.md for copyright information.

Whole-suite audit that every emitted fact value actually comes from the source
instance document (no fabricated or corrupted values).

The invariant is deliberately implementation-independent: for every translatable
instanceTest we (1) run the real ``SchemaExtractor`` + ``InstanceExtractor`` exactly
as the generator does, and (2) independently inventory the whitespace-collapsed text
of *every* element in the source instance document. Each non-nil value the extractor
returns (the conservative pipeline returns one per occurrence of the tested element,
and skips documents that mix value-bearing element types) must be non-empty and must
match one of those source texts — otherwise we silently fabricated or corrupted a
value. This also guards the original Microsoft ``msData`` bug, where the value lived
in a ``<root><simpleTest>`` probe but extraction read the ``<root>`` wrapper's
(whitespace-only) text.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import pytest
from xbrl_xsdtests import xmlutil as etree

from conftest import REPO_ROOT
from xbrl_xsdtests import sources
from xbrl_xsdtests.model import (
    ExtractedType,
    SkipRecord,
)
from xbrl_xsdtests.parse import (
    InstanceExtractor,
    SchemaExtractor,
    TestSetParser,
)

_WS = re.compile(r"\s+")
_MAX_REPORTED = 25


def _collapse(text: str) -> str:
    """XSD ``collapse`` whitespace handling (trim + fold internal runs to a space)."""
    return _WS.sub(" ", text).strip()


def _source_value_texts(root: Path, member: str) -> set[str]:
    """Collapsed, non-empty text of every element in the source instance document."""
    with (root / member).open("rb") as fh:
        doc_root = etree.parse(fh).getroot()
    texts: set[str] = set()
    for element in doc_root.iter():
        if not isinstance(element.tag, str):
            continue
        if element.text and element.text.strip():
            texts.add(_collapse(element.text))
    return texts


@dataclass
class _Violation:
    contributor: str
    group: str
    instance: str
    member: str
    extracted: str | None
    source_texts: list[str]


@dataclass
class _ScanResult:
    checked: int
    violations: list[_Violation]


@pytest.fixture(scope="module")
def scan() -> _ScanResult:
    checked = 0
    violations: list[_Violation] = []
    root = REPO_ROOT
    parser = TestSetParser(root)
    schema = SchemaExtractor(root)
    instance = InstanceExtractor(root)
    schema_cache: dict[str, ExtractedType | SkipRecord] = {}
    for source in sources.in_scope_sources():
        for item in parser.iter_instance_tests(source):
            if isinstance(item, SkipRecord):
                continue
            ref = item
            extracted = schema_cache.get(ref.group.schema_member)
            if extracted is None:
                extracted = schema.extract(ref.group)
                schema_cache[ref.group.schema_member] = extracted
            if isinstance(extracted, SkipRecord):
                continue
            values = instance.extract(
                ref, dict(extracted.element_identities), extracted.target_identity
            )
            if isinstance(values, SkipRecord):
                continue
            source_texts = _source_value_texts(root, ref.instance_member)
            for value in values:
                if value.is_nil:
                    continue
                checked += 1
                if not source_texts:
                    continue
                got = _collapse(value.text or "")
                if got == "" or got not in source_texts:
                    violations.append(
                        _Violation(
                            contributor=ref.group.source.contributor,
                            group=ref.group.name,
                            instance=ref.name,
                            member=ref.instance_member,
                            extracted=value.text,
                            source_texts=sorted(source_texts),
                        )
                    )
    return _ScanResult(checked=checked, violations=violations)


def test_scan_covers_the_suite(scan: _ScanResult) -> None:
    assert scan.checked > 5000


def test_every_targeted_value_is_transferred(scan: _ScanResult) -> None:
    if scan.violations:
        shown = scan.violations[:_MAX_REPORTED]
        lines = [
            f"{v.contributor} {v.group}/{v.instance} ({v.member}): "
            f"extracted={v.extracted!r} not among source texts {v.source_texts}"
            for v in shown
        ]
        more = len(scan.violations) - len(shown)
        suffix = f"\n... and {more} more" if more > 0 else ""
        pytest.fail(
            f"{len(scan.violations)} instanceTest(s) dropped/fabricated their value "
            f"out of {scan.checked} checked:\n" + "\n".join(lines) + suffix
        )
