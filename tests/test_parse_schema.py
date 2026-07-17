from __future__ import annotations

import os
from pathlib import Path

import pytest

from xbrl_xsdtests.model import (
    ExtractedType,
    ReasonCode,
    SkipRecord,
    SourceSet,
    TestGroupRef,
)
from xbrl_xsdtests.parse import SchemaExtractor

_SOURCE = SourceSet(member="x/meta/T.testSet", contributor="NIST", xsd_version="1.0")


def _schema(body: str, *, default_xsd: bool = False) -> str:
    if default_xsd:
        return (
            '<schema xmlns="http://www.w3.org/2001/XMLSchema" '
            'xmlns:t="urn:t" targetNamespace="urn:t">' + body + "</schema>"
        )
    return (
        '<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema" '
        'xmlns="urn:t" targetNamespace="urn:t">' + body + "</xs:schema>"
    )


# Representative fixtures: (member_path, schema_xml).
FIXTURES: dict[str, str] = {
    "x/data/decimal.xsd": _schema(
        '<xs:element name="t" type="tType"/>'
        '<xs:simpleType name="tType">'
        '<xs:restriction base="xs:decimal"><xs:minExclusive value="-999"/></xs:restriction>'
        "</xs:simpleType>"
    ),
    "x/data/string-enum.xsd": _schema(
        '<xs:element name="t" type="tType"/>'
        '<xs:simpleType name="tType">'
        '<xs:restriction base="xs:string">'
        '<xs:enumeration value="alpha"/><xs:enumeration value="beta"/>'
        "</xs:restriction></xs:simpleType>"
    ),
    "x/data/token-pattern.xsd": _schema(
        '<xs:element name="t" type="tType"/>'
        '<xs:simpleType name="tType">'
        '<xs:restriction base="xs:token"><xs:pattern value="[a-z]+"/></xs:restriction>'
        "</xs:simpleType>"
    ),
    "x/data/multi-pattern.xsd": _schema(
        '<xs:element name="t" type="tType"/>'
        '<xs:simpleType name="tType">'
        '<xs:restriction base="xs:string">'
        '<xs:pattern value="[a-z]+"/><xs:pattern value="[0-9]+"/>'
        "</xs:restriction></xs:simpleType>"
    ),
    "x/data/qname.xsd": _schema(
        '<xs:element name="helper" type="xs:string"/>'
        '<xs:element name="t" type="tType"/>'
        '<xs:simpleType name="tType">'
        '<xs:restriction base="xs:QName"><xs:enumeration value="p:foo"/></xs:restriction>'
        "</xs:simpleType>"
    ),
    # Microsoft msData shape: a generic <root> wrapper with a complexType probe
    # (comp/comp_foo) and a simpleType probe (simpleTest). Only simpleTest carries a
    # local simpleType restriction, so it is the value-bearing element.
    "x/data/ms-wrapper.xsd": _schema(
        '<xs:element name="complexTest" type="complexfooType"/>'
        '<xs:element name="simpleTest" type="simplefooType"/>'
        '<xs:complexType name="complexfooType"><xs:sequence>'
        '<xs:element name="comp_foo" type="xs:Name"/>'
        "</xs:sequence></xs:complexType>"
        '<xs:simpleType name="simplefooType">'
        '<xs:restriction base="xs:Name"/></xs:simpleType>'
        '<xs:element name="root"><xs:complexType><xs:sequence>'
        '<xs:element ref="complexTest"/><xs:element ref="simpleTest"/>'
        "</xs:sequence></xs:complexType></xs:element>"
    ),
    "x/data/id.xsd": _schema(
        '<xs:element name="t" type="tType"/>'
        '<xs:simpleType name="tType">'
        '<xs:restriction base="xs:ID"><xs:length value="1"/></xs:restriction>'
        "</xs:simpleType>"
    ),
    # default-XSD-namespace style list construct (no /list/ path marker).
    "x/data/listtype.xsd": _schema(
        '<element name="t" type="t:tType"/>'
        '<simpleType name="tType">'
        '<restriction base="t:itemList"><length value="1"/></restriction></simpleType>'
        '<simpleType name="itemList"><list itemType="t:base"/></simpleType>',
        default_xsd=True,
    ),
    "x/data/uniontype.xsd": _schema(
        '<xs:element name="t" type="tType"/>'
        '<xs:simpleType name="tType">'
        '<xs:restriction base="memberUnion"><xs:enumeration value="1"/></xs:restriction>'
        "</xs:simpleType>"
        '<xs:simpleType name="memberUnion"><xs:union memberTypes="xs:anyURI xs:float"/></xs:simpleType>'
    ),
    "x/data/import.xsd": _schema(
        '<xs:import namespace="urn:other" schemaLocation="other.xsd"/>'
        '<xs:element name="t" type="tType"/>'
        '<xs:simpleType name="tType">'
        '<xs:restriction base="xs:string"><xs:length value="1"/></xs:restriction>'
        "</xs:simpleType>"
    ),
    "x/data/foreign-base.xsd": (
        '<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema" '
        'xmlns="urn:t" xmlns:other="urn:other" targetNamespace="urn:t">'
        '<xs:element name="t" type="tType"/>'
        '<xs:simpleType name="tType">'
        '<xs:restriction base="other:weird"><xs:length value="1"/></xs:restriction>'
        "</xs:simpleType></xs:schema>"
    ),
    # path-based skip: a perfectly translatable decimal body, but under /list/.
    "x/nistData/list/decimal.xsd": _schema(
        '<xs:element name="t" type="tType"/>'
        '<xs:simpleType name="tType">'
        '<xs:restriction base="xs:decimal"><xs:minExclusive value="0"/></xs:restriction>'
        "</xs:simpleType>"
    ),
}


@pytest.fixture(scope="module")
def extractor(tmp_path_factory: pytest.TempPathFactory) -> SchemaExtractor:
    root = tmp_path_factory.mktemp("schemas")
    for name, xml in FIXTURES.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(xml, encoding="utf-8")
    return SchemaExtractor(root)


def _extract(extractor: SchemaExtractor, member: str) -> ExtractedType | SkipRecord:
    return extractor.extract(TestGroupRef(source=_SOURCE, name=member, schema_member=member))


class TestTranslatableTypes:
    def test_decimal_min_exclusive(self, extractor: SchemaExtractor) -> None:
        result = _extract(extractor, "x/data/decimal.xsd")
        assert isinstance(result, ExtractedType)
        assert result.base_xsd == "decimal"
        assert result.xbrli_item_type == "decimalItemType"
        assert result.numeric is True
        assert result.facet_set.facets == (("minExclusive", "-999"),)
        assert result.facet_set.enumerations == ()
        assert any("minExclusive" in x for x in result.facet_xml)

    def test_string_enumeration(self, extractor: SchemaExtractor) -> None:
        result = _extract(extractor, "x/data/string-enum.xsd")
        assert isinstance(result, ExtractedType)
        assert result.base_xsd == "string"
        assert result.xbrli_item_type == "stringItemType"
        assert result.numeric is False
        assert result.facet_set.enumerations == ("alpha", "beta")
        assert result.facet_set.facets == ()

    def test_token_pattern(self, extractor: SchemaExtractor) -> None:
        result = _extract(extractor, "x/data/token-pattern.xsd")
        assert isinstance(result, ExtractedType)
        assert result.base_xsd == "token"
        assert result.xbrli_item_type == "tokenItemType"
        assert result.facet_set.patterns == ("[a-z]+",)

    def test_multi_pattern_order_preserved(self, extractor: SchemaExtractor) -> None:
        result = _extract(extractor, "x/data/multi-pattern.xsd")
        assert isinstance(result, ExtractedType)
        assert result.facet_set.patterns == ("[a-z]+", "[0-9]+")

    def test_qname_picks_local_simpletype_element(self, extractor: SchemaExtractor) -> None:
        result = _extract(extractor, "x/data/qname.xsd")
        assert isinstance(result, ExtractedType)
        assert result.base_xsd == "QName"
        assert result.xbrli_item_type == "QNameItemType"
        assert result.numeric is False
        assert result.facet_set.enumerations == ("p:foo",)

    def test_root_typed_element_carries_target_identity(self, extractor: SchemaExtractor) -> None:
        result = _extract(extractor, "x/data/decimal.xsd")
        assert isinstance(result, ExtractedType)
        assert result.target_identity == "local:tType"
        assert result.element_identities == (("t", "local:tType"),)

    def test_qname_decoy_elements_are_mapped_but_not_the_target(self, extractor: SchemaExtractor) -> None:
        result = _extract(extractor, "x/data/qname.xsd")
        assert isinstance(result, ExtractedType)
        assert result.target_identity == "local:tType"
        assert dict(result.element_identities) == {"helper": "xsd:string", "t": "local:tType"}

    def test_ms_wrapper_maps_every_value_bearing_element(self, extractor: SchemaExtractor) -> None:
        result = _extract(extractor, "x/data/ms-wrapper.xsd")
        assert isinstance(result, ExtractedType)
        assert result.base_xsd == "Name"
        assert result.target_identity == "local:simplefooType"
        assert dict(result.element_identities) == {
            "comp_foo": "xsd:Name",
            "simpleTest": "local:simplefooType",
        }


class TestSkips:
    def test_id_has_no_item_type(self, extractor: SchemaExtractor) -> None:
        result = _extract(extractor, "x/data/id.xsd")
        assert isinstance(result, SkipRecord)
        assert result.reason is ReasonCode.NO_XBRLI_ITEMTYPE

    def test_list_construct(self, extractor: SchemaExtractor) -> None:
        result = _extract(extractor, "x/data/listtype.xsd")
        assert isinstance(result, SkipRecord)
        assert result.reason is ReasonCode.UNSUPPORTED_LIST

    def test_union_construct(self, extractor: SchemaExtractor) -> None:
        result = _extract(extractor, "x/data/uniontype.xsd")
        assert isinstance(result, SkipRecord)
        assert result.reason is ReasonCode.UNSUPPORTED_UNION

    def test_import_is_dependency(self, extractor: SchemaExtractor) -> None:
        result = _extract(extractor, "x/data/import.xsd")
        assert isinstance(result, SkipRecord)
        assert result.reason is ReasonCode.HAS_DEPENDENCY

    def test_foreign_namespace_base(self, extractor: SchemaExtractor) -> None:
        result = _extract(extractor, "x/data/foreign-base.xsd")
        assert isinstance(result, SkipRecord)
        assert result.reason is ReasonCode.NON_BUILTIN_BASE

    def test_path_based_list_skip_wins(self, extractor: SchemaExtractor) -> None:
        result = _extract(extractor, "x/nistData/list/decimal.xsd")
        assert isinstance(result, SkipRecord)
        assert result.reason is ReasonCode.UNSUPPORTED_LIST
