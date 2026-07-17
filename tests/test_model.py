from __future__ import annotations

import dataclasses

import pytest

from xbrl_xsdtests import model
from xbrl_xsdtests.model import (
    ExtractedType,
    ExtractedValue,
    FacetSet,
    InstanceTestRef,
    ReasonCode,
    SkipRecord,
    SourceSet,
    TestGroupRef,
    TypeKey,
    Variation,
)


def _facet_set(**overrides: object) -> FacetSet:
    kwargs: dict[str, object] = {
        "base_xsd": "decimal",
        "facets": (("minExclusive", "-999"),),
        "enumerations": (),
        "patterns": (),
    }
    kwargs.update(overrides)
    return FacetSet(**kwargs)  # type: ignore[arg-type]


def _source() -> SourceSet:
    return SourceSet(member="nistMeta/NIST.testSet", contributor="NIST", xsd_version="1.0")


def _group() -> TestGroupRef:
    return TestGroupRef(source=_source(), name="g1", schema_member="nistData/atomic/decimal/d.xsd")


class TestFacetSet:
    def test_equal_signatures_are_equal_and_hash_equal(self) -> None:
        a = _facet_set()
        b = _facet_set()
        assert a == b
        assert hash(a) == hash(b)

    def test_different_facets_differ(self) -> None:
        assert _facet_set() != _facet_set(facets=(("minExclusive", "0"),))

    def test_hashable_for_dedup(self) -> None:
        assert {_facet_set(), _facet_set(), _facet_set(patterns=("[0-9]+",))} == {
            _facet_set(),
            _facet_set(patterns=("[0-9]+",)),
        }

    def test_frozen(self) -> None:
        with pytest.raises(dataclasses.FrozenInstanceError):
            _facet_set().base_xsd = "string"  # type: ignore[misc]


class TestTypeKey:
    def test_equality_and_hashing(self) -> None:
        assert TypeKey("decimal") == TypeKey("decimal")
        assert hash(TypeKey("decimal")) == hash(TypeKey("decimal"))
        assert TypeKey("decimal") != TypeKey("string")

    def test_usable_as_dict_key(self) -> None:
        mapping = {TypeKey("decimal"): 1, TypeKey("string"): 2}
        assert mapping[TypeKey("decimal")] == 1

    def test_frozen(self) -> None:
        with pytest.raises(dataclasses.FrozenInstanceError):
            TypeKey("decimal").value = "string"  # type: ignore[misc]


class TestExtractedType:
    def test_hashable_for_dedup(self) -> None:
        t = ExtractedType(
            base_xsd="decimal",
            xbrli_item_type="decimalItemType",
            numeric=True,
            facet_set=_facet_set(),
            facet_xml=('<xsd:minExclusive value="-999"/>',),
        )
        assert hash(t) == hash(t)


class TestExtractedValue:
    def test_plain_value(self) -> None:
        v = ExtractedValue(text="42", is_nil=False, extra_nsmap={})
        assert v.text == "42"
        assert v.is_nil is False

    def test_nil_value(self) -> None:
        v = ExtractedValue(text=None, is_nil=True, extra_nsmap={})
        assert v.text is None
        assert v.is_nil is True

    def test_qname_nsmap_captured(self) -> None:
        v = ExtractedValue(text="p:foo", is_nil=False, extra_nsmap={"p": "http://example.com/ns"})
        assert v.extra_nsmap == {"p": "http://example.com/ns"}


class TestRefs:
    def test_source_set(self) -> None:
        s = _source()
        assert s.contributor == "NIST"
        assert s.xsd_version == "1.0"

    def test_instance_test_ref(self) -> None:
        ref = InstanceTestRef(
            group=_group(),
            name="d-001",
            instance_member="nistData/atomic/decimal/d-001.xml",
            validity="invalid",
        )
        assert ref.validity == "invalid"
        assert ref.group.source.contributor == "NIST"


class TestVariation:
    def test_invalid_carries_expected_error(self) -> None:
        v = Variation(id="d-001", instance_href="decimal/d-001.xbrl", expected_error="xmlSchema:valueError")
        assert v.expected_error == "xmlSchema:valueError"

    def test_valid_has_no_expected_error(self) -> None:
        assert Variation(id="d-002", instance_href="decimal/d-002.xbrl", expected_error=None).expected_error is None


class TestReasonCodeAndSkipRecord:
    def test_reason_codes_match_design_appendix_b(self) -> None:
        assert {rc.value for rc in ReasonCode} == {
            "unsupported-list",
            "unsupported-union",
            "no-xbrli-itemtype",
            "non-builtin-base",
            "has-dependency",
            "schema-test-only",
            "unparseable",
            "value-not-found",
            "mixed-value-types",
            "xsi-type-override",
        }

    def test_skip_record_construction(self) -> None:
        rec = SkipRecord(
            source="NIST",
            group="list-g1",
            instance=None,
            reason=ReasonCode.UNSUPPORTED_LIST,
            detail="xs:list not supported",
        )
        assert rec.reason is ReasonCode.UNSUPPORTED_LIST
        assert rec.instance is None


def test_all_models_importable() -> None:
    for name in (
        "SourceSet",
        "TestGroupRef",
        "InstanceTestRef",
        "FacetSet",
        "ExtractedType",
        "ExtractedValue",
        "TypeKey",
        "Variation",
        "SkipRecord",
        "ReasonCode",
    ):
        assert hasattr(model, name)
