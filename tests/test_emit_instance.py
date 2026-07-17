from __future__ import annotations

from pathlib import Path

import pytest
from xbrl_xsdtests import xmlutil as etree

from xbrl_xsdtests.emit import (
    InstanceEmitter,
    taxonomy_filename,
)
from xbrl_xsdtests.model import (
    ExtractedType,
    ExtractedValue,
    FacetSet,
    InstanceTestRef,
    SourceSet,
    TestGroupRef,
    TypeKey,
)

GOLDEN_DIR = Path(__file__).parent / "golden"


def _type(base: str, item: str, numeric: bool) -> ExtractedType:
    return ExtractedType(
        base_xsd=base,
        xbrli_item_type=item,
        numeric=numeric,
        facet_set=FacetSet(base_xsd=base, facets=(), enumerations=(), patterns=()),
        facet_xml=(),
    )


def _ref(group: str, name: str) -> InstanceTestRef:
    source = SourceSet(member="x/m.testSet", contributor="NIST", xsd_version="1.0")
    group_ref = TestGroupRef(source=source, name=group, schema_member="x/s.xsd")
    return InstanceTestRef(group=group_ref, name=name, instance_member="x/i.xml", validity="valid")


# label -> (ref, value, key, type, golden filename)
CASES = {
    "numeric": (
        _ref("atomic-decimal-minExclusive", "NISTXML-d-1-1"),
        ExtractedValue(text="-998", is_nil=False, extra_nsmap={}),
        TypeKey("decimal__minExclusive_-999"),
        _type("decimal", "decimalItemType", True),
        "instance-numeric.xbrl",
    ),
    "nonnumeric": (
        _ref("atomic-string-enum", "NISTXML-s-1-1"),
        ExtractedValue(text="alpha", is_nil=False, extra_nsmap={}),
        TypeKey("string-b42bdb1f"),
        _type("string", "stringItemType", False),
        "instance-nonnumeric.xbrl",
    ),
    "nil": (
        _ref("atomic-decimal-minExclusive", "NISTXML-d-9-9"),
        ExtractedValue(text=None, is_nil=True, extra_nsmap={}),
        TypeKey("decimal__minExclusive_-999"),
        _type("decimal", "decimalItemType", True),
        "instance-nil.xbrl",
    ),
    "qname": (
        _ref("atomic-QName-enum", "NISTXML-q-1-5"),
        ExtractedValue(text="_:cengine", is_nil=False, extra_nsmap={"_": "http://www.nist.gov/xsdNS"}),
        TypeKey("QName-3411eea3"),
        _type("QName", "QNameItemType", False),
        "instance-qname.xbrl",
    ),
}


def _emit(label: str, out: Path) -> Path:
    ref, value, key, t, _golden = CASES[label]
    return InstanceEmitter().emit(ref, [value], key, t, out)


class TestGoldenFiles:
    @pytest.mark.parametrize("label", sorted(CASES))
    def test_matches_golden(self, tmp_path: Path, label: str) -> None:
        path = _emit(label, tmp_path)
        golden = (GOLDEN_DIR / CASES[label][4]).read_text(encoding="utf-8")
        assert path.read_text(encoding="utf-8") == golden

    @pytest.mark.parametrize("label", sorted(CASES))
    def test_well_formed_xml(self, tmp_path: Path, label: str) -> None:
        path = _emit(label, tmp_path)
        etree.parse(str(path))  # raises if not well-formed


class TestNumericVsNonNumeric:
    def test_numeric_has_unit_and_decimals(self, tmp_path: Path) -> None:
        content = _emit("numeric", tmp_path).read_text(encoding="utf-8")
        assert "<xbrli:unit" in content
        assert 'unitRef="u"' in content
        assert 'decimals="INF"' in content

    def test_non_numeric_has_no_unit_or_decimals(self, tmp_path: Path) -> None:
        content = _emit("nonnumeric", tmp_path).read_text(encoding="utf-8")
        assert "<xbrli:unit" not in content
        assert "unitRef" not in content
        assert "decimals" not in content


class TestNil:
    def test_nil_sets_xsi_nil_and_omits_decimals(self, tmp_path: Path) -> None:
        content = _emit("nil", tmp_path).read_text(encoding="utf-8")
        assert 'xsi:nil="true"' in content
        assert "decimals" not in content
        # numeric nil still carries unitRef (unit allowed; only decimals forbidden)
        assert 'unitRef="u"' in content


class TestMultipleOccurrences:
    def test_each_value_becomes_a_fact_sharing_one_context(self, tmp_path: Path) -> None:
        ref = _ref("atomic-string-enum", "NISTXML-multi")
        values = [
            ExtractedValue(text="a", is_nil=False, extra_nsmap={}),
            ExtractedValue(text="b", is_nil=False, extra_nsmap={}),
            ExtractedValue(text="c", is_nil=False, extra_nsmap={}),
        ]
        path = InstanceEmitter().emit(
            ref, values, TypeKey("string"), _type("string", "stringItemType", False), tmp_path
        )
        root = etree.parse(str(path)).getroot()
        facts = root.findall("{http://arelle.org/xsts-value-suite/string}t")
        assert [f.text for f in facts] == ["a", "b", "c"]
        assert {f.get("contextRef") for f in facts} == {"c"}
        # one shared context, no duplicated context elements
        assert len(root.findall("{http://www.xbrl.org/2003/instance}context")) == 1

    def test_numeric_occurrences_share_one_unit(self, tmp_path: Path) -> None:
        ref = _ref("atomic-decimal", "NISTXML-multi")
        values = [
            ExtractedValue(text="1", is_nil=False, extra_nsmap={}),
            ExtractedValue(text="2", is_nil=False, extra_nsmap={}),
        ]
        path = InstanceEmitter().emit(
            ref, values, TypeKey("decimal"), _type("decimal", "decimalItemType", True), tmp_path
        )
        root = etree.parse(str(path)).getroot()
        facts = root.findall("{http://arelle.org/xsts-value-suite/decimal}t")
        assert [f.text for f in facts] == ["1", "2"]
        assert {f.get("unitRef") for f in facts} == {"u"}
        assert len(root.findall("{http://www.xbrl.org/2003/instance}unit")) == 1


class TestSchemaRefResolves:
    @pytest.mark.parametrize("label", sorted(CASES))
    def test_schema_ref_points_to_existing_relative_taxonomy(self, tmp_path: Path, label: str) -> None:
        path = _emit(label, tmp_path)
        _ref, _value, key, _t, _golden = CASES[label]
        root = etree.parse(str(path)).getroot()
        href = root.find("{http://www.xbrl.org/2003/linkbase}schemaRef").get(
            "{http://www.w3.org/1999/xlink}href"
        )
        resolved = (path.parent / href).resolve()
        assert resolved == (tmp_path / "taxonomies" / taxonomy_filename(key)).resolve()
        assert resolved.name == f"gen-{key.value}.xsd"

    def test_value_escaping(self, tmp_path: Path) -> None:
        ref = _ref("g", "n")
        value = ExtractedValue(text="a < b & c", is_nil=False, extra_nsmap={})
        path = InstanceEmitter().emit(ref, [value], TypeKey("string"), _type("string", "stringItemType", False), tmp_path)
        root = etree.parse(str(path)).getroot()
        fact = root.find("{http://arelle.org/xsts-value-suite/string}t")
        assert fact.text == "a < b & c"
        assert "&amp;" in path.read_text(encoding="utf-8")
