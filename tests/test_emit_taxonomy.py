from __future__ import annotations

from pathlib import Path

import pytest

from xbrl_xsdtests.dedup import TaxonomyDedup
from xbrl_xsdtests.emit import (
    XBRLI_SCHEMA_LOCATION,
    TaxonomyEmitter,
    taxonomy_filename,
)
from xbrl_xsdtests.model import SourceSet, TestGroupRef
from xbrl_xsdtests.parse import SchemaExtractor

GOLDEN_DIR = Path(__file__).parent / "golden"
_SOURCE = SourceSet(member="x/m.testSet", contributor="NIST", xsd_version="1.0")


def _schema(body: str) -> str:
    return (
        '<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema" '
        'xmlns="urn:t" targetNamespace="urn:t">' + body + "</xs:schema>"
    )


# label -> (schema body, expected golden filename)
CASES: dict[str, tuple[str, str]] = {
    "decimal": (
        '<xs:element name="t" type="tType"/>'
        '<xs:simpleType name="tType">'
        '<xs:restriction base="xs:decimal"><xs:minExclusive value="-999"/></xs:restriction>'
        "</xs:simpleType>",
        "gen-decimal__minExclusive_-999.xsd",
    ),
    "string-enum": (
        '<xs:element name="t" type="tType"/>'
        '<xs:simpleType name="tType">'
        '<xs:restriction base="xs:string">'
        '<xs:enumeration value="alpha"/><xs:enumeration value="beta"/>'
        "</xs:restriction></xs:simpleType>",
        "gen-string-b42bdb1f.xsd",
    ),
    "token-pattern": (
        '<xs:element name="t" type="tType"/>'
        '<xs:simpleType name="tType">'
        '<xs:restriction base="xs:token"><xs:pattern value="[a-z]+"/></xs:restriction>'
        "</xs:simpleType>",
        "gen-token-0c469a7c.xsd",
    ),
    "qname": (
        '<xs:element name="t" type="tType"/>'
        '<xs:simpleType name="tType">'
        '<xs:restriction base="xs:QName"><xs:enumeration value="p:foo"/></xs:restriction>'
        "</xs:simpleType>",
        "gen-QName-3411eea3.xsd",
    ),
}


@pytest.fixture(scope="module")
def extractor(tmp_path_factory: pytest.TempPathFactory) -> SchemaExtractor:
    root = tmp_path_factory.mktemp("taxonomy_schemas")
    for label, (body, _golden) in CASES.items():
        (root / f"{label}.xsd").write_text(_schema(body), encoding="utf-8")
    return SchemaExtractor(root)


def _emit(extractor: SchemaExtractor, label: str, out: Path) -> Path:
    body, _golden = CASES[label]
    t = extractor.extract(TestGroupRef(source=_SOURCE, name=label, schema_member=f"{label}.xsd"))
    key, _is_new = TaxonomyDedup().get_or_register(t)
    return TaxonomyEmitter().emit(key, t, out)


class TestGoldenFiles:
    @pytest.mark.parametrize("label", sorted(CASES))
    def test_matches_golden(self, extractor: SchemaExtractor, tmp_path: Path, label: str) -> None:
        path = _emit(extractor, label, tmp_path)
        expected_name = CASES[label][1]
        assert path.name == expected_name
        golden = (GOLDEN_DIR / expected_name).read_text(encoding="utf-8")
        assert path.read_text(encoding="utf-8") == golden


class TestXbrliImportUrl:
    @pytest.mark.parametrize("label", sorted(CASES))
    def test_no_instance_path_segment(self, extractor: SchemaExtractor, tmp_path: Path, label: str) -> None:
        content = _emit(extractor, label, tmp_path).read_text(encoding="utf-8")
        assert XBRLI_SCHEMA_LOCATION == "http://www.xbrl.org/2003/xbrl-instance-2003-12-31.xsd"
        assert f'schemaLocation="{XBRLI_SCHEMA_LOCATION}"' in content
        assert "/instance/" not in content


class TestOnePerKey:
    def test_written_to_taxonomies_subdir(self, extractor: SchemaExtractor, tmp_path: Path) -> None:
        path = _emit(extractor, "decimal", tmp_path)
        assert path.parent == tmp_path / "taxonomies"

    def test_equivalent_types_share_filename(self, extractor: SchemaExtractor, tmp_path: Path) -> None:
        # Same logical type extracted twice -> same dedup key -> same taxonomy filename.
        t = extractor.extract(TestGroupRef(source=_SOURCE, name="decimal", schema_member="decimal.xsd"))
        dedup = TaxonomyDedup()
        key1, _ = dedup.get_or_register(t)
        key2, _ = dedup.get_or_register(t)
        assert taxonomy_filename(key1) == taxonomy_filename(key2)

    def test_distinct_types_differ(self, extractor: SchemaExtractor, tmp_path: Path) -> None:
        decimal = _emit(extractor, "decimal", tmp_path)
        token = _emit(extractor, "token-pattern", tmp_path)
        assert decimal.name != token.name
