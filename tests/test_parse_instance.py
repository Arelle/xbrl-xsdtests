from __future__ import annotations

from pathlib import Path

import pytest

from conftest import REPO_ROOT
from xbrl_xsdtests import sources
from xbrl_xsdtests.model import (
    ExtractedType,
    ExtractedValue,
    InstanceTestRef,
    ReasonCode,
    SkipRecord,
    SourceSet,
    TestGroupRef,
)
from xbrl_xsdtests.parse import (
    InstanceExtractor,
    SchemaExtractor,
)

_SOURCE = SourceSet(member="x/meta/T.testSet", contributor="NIST", xsd_version="1.0")
_XSI = 'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"'

# Synthetic instance fixtures: member -> raw XML.
FIXTURES: dict[str, str] = {
    "x/data/plain.xml": '<e xmlns="urn:t">42</e>',
    "x/data/nil.xml": f'<e xmlns="urn:t" {_XSI} xsi:nil="true"/>',
    "x/data/empty.xml": '<e xmlns="urn:t"></e>',
    "x/data/qname.xml": '<e xmlns="urn:t" xmlns:p="urn:p">p:foo</e>',
    "x/data/whitespace.xml": '<e xmlns="urn:t">  hi\t\n </e>',
    "x/data/malformed.xml": '<e xmlns="urn:t">oops',
    # Several occurrences of the same tested element under a container wrapper.
    "x/data/repeated.xml": (
        '<root xmlns="urn:t">\n'
        "  <bar>a</bar>\n  <bar>b</bar>\n  <bar>c</bar>\n"
        "</root>"
    ),
    # Microsoft msData shape: <simpleTest> (tested type) *and* <comp_foo> (a different
    # type) both carry a value -> the document mixes value-bearing element types.
    "x/data/ms-wrapper.xml": (
        f"<root {_XSI}>\n"
        "  <complexTest><!-- value=_foo --><comp_foo>_foo</comp_foo></complexTest>\n"
        "  <simpleTest>_foo</simpleTest>\n"
        "</root>"
    ),
    # Same wrapper but only the tested probe is present (single value-bearing type).
    "x/data/ms-wrapper-qname.xml": (
        '<root xmlns:p="urn:p">\n'
        "  <simpleTest>p:foo</simpleTest>\n"
        "</root>"
    ),
    # A value leaf of the tested type carrying xsi:type: the effective type (and thus
    # the document's validity) is decided by the type override, which the re-based fact
    # cannot reproduce, so the instance is skipped even though the text is well-formed.
    "x/data/xsi-type.xml": f'<e xmlns="urn:t" {_XSI} xsi:type="Other">42</e>',
}

# The default single-leaf fixtures all use element <e> typed by the tested type.
_E_IDENTITIES = {"e": "local:tType"}
_E_TARGET = "local:tType"


def _ref(member: str) -> InstanceTestRef:
    group = TestGroupRef(source=_SOURCE, name="g", schema_member="x/data/g.xsd")
    return InstanceTestRef(group=group, name=member, instance_member=member, validity="valid")


@pytest.fixture(scope="module")
def extractor(tmp_path_factory: pytest.TempPathFactory) -> InstanceExtractor:
    root = tmp_path_factory.mktemp("instances")
    for name, xml in FIXTURES.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(xml, encoding="utf-8")
    return InstanceExtractor(root)


class TestSingleValue:
    def test_plain_value(self, extractor: InstanceExtractor) -> None:
        result = extractor.extract(_ref("x/data/plain.xml"), _E_IDENTITIES, _E_TARGET)
        assert result == [ExtractedValue(text="42", is_nil=False, extra_nsmap={})]

    def test_nil_value(self, extractor: InstanceExtractor) -> None:
        result = extractor.extract(_ref("x/data/nil.xml"), _E_IDENTITIES, _E_TARGET)
        assert isinstance(result, list) and len(result) == 1
        assert result[0].is_nil is True
        assert result[0].text is None

    def test_empty_non_nil_is_empty_string(self, extractor: InstanceExtractor) -> None:
        result = extractor.extract(_ref("x/data/empty.xml"), _E_IDENTITIES, _E_TARGET)
        assert isinstance(result, list) and len(result) == 1
        assert result[0].is_nil is False
        assert result[0].text == ""

    def test_qname_prefix_captured(self, extractor: InstanceExtractor) -> None:
        result = extractor.extract(_ref("x/data/qname.xml"), _E_IDENTITIES, _E_TARGET)
        assert isinstance(result, list) and len(result) == 1
        assert result[0].text == "p:foo"
        assert result[0].extra_nsmap == {"p": "urn:p"}

    def test_whitespace_preserved_verbatim(self, extractor: InstanceExtractor) -> None:
        result = extractor.extract(_ref("x/data/whitespace.xml"), _E_IDENTITIES, _E_TARGET)
        assert isinstance(result, list) and len(result) == 1
        assert result[0].text == "  hi\t\n "

    def test_malformed_instance_skips(self, extractor: InstanceExtractor) -> None:
        result = extractor.extract(_ref("x/data/malformed.xml"), _E_IDENTITIES, _E_TARGET)
        assert isinstance(result, SkipRecord)
        assert result.reason is ReasonCode.UNPARSEABLE
        assert result.instance == "x/data/malformed.xml"


class TestMultipleOccurrences:
    def test_every_occurrence_is_returned_in_document_order(self, extractor: InstanceExtractor) -> None:
        result = extractor.extract(
            _ref("x/data/repeated.xml"), {"bar": "local:st"}, "local:st"
        )
        assert isinstance(result, list)
        assert [v.text for v in result] == ["a", "b", "c"]

    def test_single_probe_among_wrapper_descends_correctly(self, extractor: InstanceExtractor) -> None:
        result = extractor.extract(
            _ref("x/data/ms-wrapper-qname.xml"), {"simpleTest": "local:st"}, "local:st"
        )
        assert isinstance(result, list) and len(result) == 1
        assert result[0].text == "p:foo"
        assert result[0].extra_nsmap == {"p": "urn:p"}


class TestMixedAndMissing:
    def test_mixed_value_types_skips(self, extractor: InstanceExtractor) -> None:
        result = extractor.extract(
            _ref("x/data/ms-wrapper.xml"),
            {"comp_foo": "xsd:Name", "simpleTest": "local:st"},
            "local:st",
        )
        assert isinstance(result, SkipRecord)
        assert result.reason is ReasonCode.MIXED_VALUE_TYPES

    def test_no_value_element_of_tested_type_skips(self, extractor: InstanceExtractor) -> None:
        result = extractor.extract(_ref("x/data/plain.xml"), {"x": "local:tType"}, "local:tType")
        assert isinstance(result, SkipRecord)
        assert result.reason is ReasonCode.VALUE_NOT_FOUND

    def test_xsi_type_override_skips(self, extractor: InstanceExtractor) -> None:
        result = extractor.extract(_ref("x/data/xsi-type.xml"), _E_IDENTITIES, _E_TARGET)
        assert isinstance(result, SkipRecord)
        assert result.reason is ReasonCode.XSI_TYPE_OVERRIDE


class TestRealMsWrapperInstance:
    def test_name002_is_mixed_value_and_skipped(self) -> None:
        root = REPO_ROOT
        schema_member = "msData/datatypes/Name.xsd"
        instance_member = "msData/datatypes/Name002.xml"
        group = TestGroupRef(source=_SOURCE, name="Name002", schema_member=schema_member)
        ref = InstanceTestRef(
            group=group, name="Name002", instance_member=instance_member, validity="valid"
        )
        t = SchemaExtractor(root).extract(group)
        assert isinstance(t, ExtractedType)
        result = InstanceExtractor(root).extract(ref, dict(t.element_identities), t.target_identity)
        assert isinstance(result, SkipRecord)
        assert result.reason is ReasonCode.MIXED_VALUE_TYPES


class TestRealXsiTypeInstance:
    def test_sun_st_name_negative_is_xsi_type_override(self) -> None:
        root = REPO_ROOT
        schema_member = "sunData/SType/ST_name/ST_name00101m/ST_name00101m.xsd"
        base = "sunData/SType/ST_name/ST_name00101m"
        group = TestGroupRef(source=_SOURCE, name="ST_name00101m", schema_member=schema_member)
        t = SchemaExtractor(root).extract(group)
        assert isinstance(t, ExtractedType)
        extractor = InstanceExtractor(root)
        positive = InstanceTestRef(
            group=group, name="p", instance_member=f"{base}/ST_name00101m1_p.xml", validity="valid"
        )
        negative = InstanceTestRef(
            group=group, name="n", instance_member=f"{base}/ST_name00101m1_n.xml", validity="invalid"
        )
        positive_result = extractor.extract(positive, dict(t.element_identities), t.target_identity)
        negative_result = extractor.extract(negative, dict(t.element_identities), t.target_identity)
        assert isinstance(positive_result, list) and [v.text for v in positive_result] == ["2"]
        assert isinstance(negative_result, SkipRecord)
        assert negative_result.reason is ReasonCode.XSI_TYPE_OVERRIDE


class TestRealQNameInstance:
    def test_prefixed_qname_from_disk(self) -> None:
        root = REPO_ROOT
        schema_member = (
            "nistData/atomic/QName/Schema+Instance/"
            "NISTSchema-SV-IV-atomic-QName-enumeration-1.xsd"
        )
        instance_member = (
            "nistData/atomic/QName/Schema+Instance/"
            "NISTXML-SV-IV-atomic-QName-enumeration-1-5.xml"
        )
        group = TestGroupRef(source=_SOURCE, name="QName", schema_member=schema_member)
        ref = InstanceTestRef(
            group=group, name="QName-1-5", instance_member=instance_member, validity="valid"
        )
        t = SchemaExtractor(root).extract(group)
        assert isinstance(t, ExtractedType)
        result = InstanceExtractor(root).extract(ref, dict(t.element_identities), t.target_identity)
        assert isinstance(result, list) and len(result) == 1
        assert result[0].text == "_:cengine"
        assert result[0].is_nil is False
        assert result[0].extra_nsmap == {"_": "http://www.nist.gov/xsdNS"}
