from __future__ import annotations

import re

from xbrl_xsdtests.dedup import TaxonomyDedup
from xbrl_xsdtests.model import ExtractedType, FacetSet

_SAFE_NAME = re.compile(r"^[A-Za-z0-9._-]+$")


def _type(
    base: str = "decimal",
    *,
    facets: tuple[tuple[str, str], ...] = (),
    enumerations: tuple[str, ...] = (),
    patterns: tuple[str, ...] = (),
    facet_xml: tuple[str, ...] = (),
) -> ExtractedType:
    facet_set = FacetSet(
        base_xsd=base,
        facets=tuple(sorted(facets)),
        enumerations=enumerations,
        patterns=patterns,
    )
    return ExtractedType(
        base_xsd=base,
        xbrli_item_type=f"{base}ItemType",
        numeric=base in {"decimal", "integer", "float", "double"},
        facet_set=facet_set,
        facet_xml=facet_xml,
    )


class TestCanonicalKeys:
    def test_builtin_no_facets_keys_on_localname(self) -> None:
        dedup = TaxonomyDedup()
        assert dedup.key_for(_type("string")).value == "string"
        assert dedup.key_for(_type("decimal")).value == "decimal"

    def test_readable_slug_for_simple_facet(self) -> None:
        dedup = TaxonomyDedup()
        key = dedup.key_for(_type("decimal", facets=(("minExclusive", "-999"),)))
        assert key.value == "decimal__minExclusive_-999"

    def test_identical_facet_sets_same_key(self) -> None:
        dedup = TaxonomyDedup()
        a = _type("decimal", facets=(("minExclusive", "-999"),), facet_xml=('<xs:minExclusive value="-999"/>',))
        # same facet_set, but different verbatim facet_xml serialization
        b = _type("decimal", facets=(("minExclusive", "-999"),), facet_xml=('<minExclusive value="-999"/>',))
        assert dedup.key_for(a) == dedup.key_for(b)

    def test_different_facets_different_keys(self) -> None:
        dedup = TaxonomyDedup()
        k1 = dedup.key_for(_type("decimal", facets=(("minExclusive", "-999"),)))
        k2 = dedup.key_for(_type("decimal", facets=(("minExclusive", "0"),)))
        assert k1 != k2

    def test_enumeration_order_is_significant(self) -> None:
        dedup = TaxonomyDedup()
        k1 = dedup.key_for(_type("string", enumerations=("a", "b")))
        k2 = dedup.key_for(_type("string", enumerations=("b", "a")))
        assert k1 != k2

    def test_different_bases_differ(self) -> None:
        dedup = TaxonomyDedup()
        assert dedup.key_for(_type("string")) != dedup.key_for(_type("token"))


class TestStability:
    def test_keys_stable_across_instances(self) -> None:
        t = _type("decimal", facets=(("minExclusive", "-999"), ("maxInclusive", "5")))
        assert TaxonomyDedup().key_for(t) == TaxonomyDedup().key_for(t)

    def test_enumeration_key_stable(self) -> None:
        t = _type("string", enumerations=("alpha", "beta"))
        assert TaxonomyDedup().key_for(t).value == TaxonomyDedup().key_for(t).value


class TestFilesystemSafety:
    def test_pattern_value_produces_safe_name(self) -> None:
        dedup = TaxonomyDedup()
        key = dedup.key_for(_type("token", patterns=("[a-z]+/\\d{3}",)))
        assert _SAFE_NAME.match(key.value)

    def test_long_and_odd_values_truncated_and_safe(self) -> None:
        dedup = TaxonomyDedup()
        odd = "x " * 200 + "weird/<>:|chars"
        key = dedup.key_for(_type("string", facets=(("pattern_like", odd),)))
        assert _SAFE_NAME.match(key.value)
        assert len(key.value) <= 100

    def test_enumeration_with_unsafe_values_safe(self) -> None:
        dedup = TaxonomyDedup()
        key = dedup.key_for(_type("QName", enumerations=("p:foo", "http://x/y?z=1")))
        assert _SAFE_NAME.match(key.value)


class TestRegistration:
    def test_get_or_register_collapses_equivalents(self) -> None:
        dedup = TaxonomyDedup()
        a = _type("decimal", facets=(("minExclusive", "-999"),), facet_xml=('<xs:minExclusive value="-999"/>',))
        b = _type("decimal", facets=(("minExclusive", "-999"),), facet_xml=('<minExclusive value="-999"/>',))
        key1, new1 = dedup.get_or_register(a)
        key2, new2 = dedup.get_or_register(b)
        assert new1 is True
        assert new2 is False
        assert key1 == key2

    def test_get_or_register_distinct_types(self) -> None:
        dedup = TaxonomyDedup()
        _, new1 = dedup.get_or_register(_type("string", enumerations=("a",)))
        key2, new2 = dedup.get_or_register(_type("string", enumerations=("b",)))
        assert new1 is True
        assert new2 is True
        assert key2.value.startswith("string-")
