from __future__ import annotations

from pathlib import Path

import pytest

from conftest import REPO_ROOT
from xbrl_xsdtests import sources
from xbrl_xsdtests.model import InstanceTestRef, ReasonCode, SkipRecord
from xbrl_xsdtests.parse import TestSetParser

# Authoritative instanceTest counts from parsing the committed test data.
EXPECTED_COUNTS = {
    "nistMeta/NISTXMLSchemaDatatypes.testSet": 19217,
    "msMeta/Regex_w3c.xml": 1432,
    "msMeta/DataTypes_w3c.xml": 1187,
    "msMeta/SimpleType_w3c.xml": 110,
    "sunMeta/SType.testSet": 200,
}


@pytest.fixture(scope="module")
def root() -> Path:
    return REPO_ROOT


def _by_source() -> dict[str, object]:
    return {s.member: s for s in sources.in_scope_sources()}


class TestInstanceTestCounts:
    @pytest.mark.parametrize("member", sorted(EXPECTED_COUNTS))
    def test_counts_match_expected(self, root: Path, member: str) -> None:
        source = _by_source()[member]
        parser = TestSetParser(root)
        instance_tests = [r for r in parser.iter_instance_tests(source) if isinstance(r, InstanceTestRef)]
        assert len(instance_tests) == EXPECTED_COUNTS[member]

    def test_total_in_scope(self, root: Path) -> None:
        parser = TestSetParser(root)
        total = sum(
            1
            for source in sources.in_scope_sources()
            for r in parser.iter_instance_tests(source)
            if isinstance(r, InstanceTestRef)
        )
        assert total == sum(EXPECTED_COUNTS.values())


class TestHrefResolution:
    def test_all_hrefs_resolve_on_disk(self, root: Path) -> None:
        parser = TestSetParser(root)
        for source in sources.in_scope_sources():
            for ref in parser.iter_instance_tests(source):
                if isinstance(ref, InstanceTestRef):
                    assert (root / ref.instance_member).is_file(), ref.instance_member
                    if ref.group.schema_member:
                        assert (root / ref.group.schema_member).is_file(), ref.group.schema_member

    def test_nist_first_instance_fields(self, root: Path) -> None:
        source = _by_source()["nistMeta/NISTXMLSchemaDatatypes.testSet"]
        parser = TestSetParser(root)
        first = next(r for r in parser.iter_instance_tests(source) if isinstance(r, InstanceTestRef))
        assert first.name == "NISTXML-SV-IV-atomic-decimal-minExclusive-1-1"
        assert first.validity == "valid"
        assert first.instance_member == (
            "nistData/atomic/decimal/Schema+Instance/"
            "NISTXML-SV-IV-atomic-decimal-minExclusive-1-1.xml"
        )
        assert first.group.schema_member == (
            "nistData/atomic/decimal/Schema+Instance/"
            "NISTSchema-SV-IV-atomic-decimal-minExclusive-1.xsd"
        )
        assert first.group.source.contributor == "NIST"


class TestVersionedExpected:
    def test_picks_outcome_matching_source_version(self, root: Path) -> None:
        # float018_1917.i carries two version-tagged <expected> siblings:
        #   <expected validity="valid" version="1.1"/>
        #   <expected validity="invalid" version="1.0"/>
        # The in-scope source is tagged xsd_version="1.0", so the 1.0 outcome
        # (invalid) must be picked, not the first-in-document-order 1.1 one.
        source = _by_source()["msMeta/DataTypes_w3c.xml"]
        parser = TestSetParser(root)
        ref = next(
            r
            for r in parser.iter_instance_tests(source)
            if isinstance(r, InstanceTestRef) and r.name == "float018_1917.i"
        )
        assert ref.validity == "invalid"


class TestSchemaTestOnly:
    def test_schema_only_groups_yield_skip_records(self, root: Path) -> None:
        # MS SimpleType has many schemaTest-only groups (stA001..).
        source = _by_source()["msMeta/SimpleType_w3c.xml"]
        parser = TestSetParser(root)
        skips = [r for r in parser.iter_instance_tests(source) if isinstance(r, SkipRecord)]
        assert skips
        assert all(r.reason is ReasonCode.SCHEMA_TEST_ONLY for r in skips)
        assert all(r.instance is None for r in skips)
