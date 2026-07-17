from __future__ import annotations

import pytest

from xbrl_xsdtests import typemap

# The 36 NIST atomic types that map to an xbrli:*ItemType.
EXPECTED_MAPPING = {
    "decimal": "decimalItemType",
    "float": "floatItemType",
    "double": "doubleItemType",
    "integer": "integerItemType",
    "nonPositiveInteger": "nonPositiveIntegerItemType",
    "negativeInteger": "negativeIntegerItemType",
    "long": "longItemType",
    "int": "intItemType",
    "short": "shortItemType",
    "byte": "byteItemType",
    "nonNegativeInteger": "nonNegativeIntegerItemType",
    "unsignedLong": "unsignedLongItemType",
    "unsignedInt": "unsignedIntItemType",
    "unsignedShort": "unsignedShortItemType",
    "unsignedByte": "unsignedByteItemType",
    "positiveInteger": "positiveIntegerItemType",
    "string": "stringItemType",
    "normalizedString": "normalizedStringItemType",
    "token": "tokenItemType",
    "language": "languageItemType",
    "Name": "NameItemType",
    "NCName": "NCNameItemType",
    "boolean": "booleanItemType",
    "hexBinary": "hexBinaryItemType",
    "base64Binary": "base64BinaryItemType",
    "anyURI": "anyURIItemType",
    "QName": "QNameItemType",
    "duration": "durationItemType",
    "dateTime": "dateTimeItemType",
    "time": "timeItemType",
    "date": "dateItemType",
    "gYearMonth": "gYearMonthItemType",
    "gYear": "gYearItemType",
    "gMonthDay": "gMonthDayItemType",
    "gDay": "gDayItemType",
    "gMonth": "gMonthItemType",
}

# NIST atomic types with no xbrli item type -> must skip.
NO_ITEM_TYPE = ["ID", "IDREF", "NMTOKEN", "ENTITY"]

NUMERIC_TYPES = {
    "decimal", "float", "double", "integer",
    "nonPositiveInteger", "negativeInteger",
    "long", "int", "short", "byte",
    "nonNegativeInteger", "unsignedLong", "unsignedInt",
    "unsignedShort", "unsignedByte", "positiveInteger",
}


class TestXbrliItemType:
    @pytest.mark.parametrize(("local", "expected"), sorted(EXPECTED_MAPPING.items()))
    def test_maps_to_expected_item_type(self, local: str, expected: str) -> None:
        assert typemap.xbrli_item_type(local) == expected

    def test_all_36_atomic_types_map(self) -> None:
        assert len(EXPECTED_MAPPING) == 36
        assert all(typemap.xbrli_item_type(local) is not None for local in EXPECTED_MAPPING)

    @pytest.mark.parametrize("local", NO_ITEM_TYPE)
    def test_unmapped_types_return_none(self, local: str) -> None:
        assert typemap.xbrli_item_type(local) is None

    def test_unknown_type_returns_none(self) -> None:
        assert typemap.xbrli_item_type("notARealType") is None


class TestIsNumeric:
    def test_numeric_set(self) -> None:
        numeric = {local for local in EXPECTED_MAPPING if typemap.is_numeric(local)}
        assert numeric == NUMERIC_TYPES

    @pytest.mark.parametrize("local", sorted(NUMERIC_TYPES))
    def test_numeric_types(self, local: str) -> None:
        assert typemap.is_numeric(local) is True

    @pytest.mark.parametrize("local", ["string", "boolean", "QName", "date", "anyURI"])
    def test_non_numeric_types(self, local: str) -> None:
        assert typemap.is_numeric(local) is False
