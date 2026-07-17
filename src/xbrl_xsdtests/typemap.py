"""
See COPYRIGHT.md for copyright information.

xsd base type -> xbrli item type mapping and numeric classification.

The mapping covers all XSD primitive/derived types that have a corresponding
``xbrli:*ItemType`` in the XBRL 2.1 specification.
"""

from __future__ import annotations

# The 36 xsd atomic types that have a matching xbrli:*ItemType.
_BASE_XBRLI_TYPES: frozenset[str] = frozenset({
    "decimalItemType",
    "floatItemType",
    "doubleItemType",
    "integerItemType",
    "nonPositiveIntegerItemType",
    "negativeIntegerItemType",
    "longItemType",
    "intItemType",
    "shortItemType",
    "byteItemType",
    "nonNegativeIntegerItemType",
    "unsignedLongItemType",
    "unsignedIntItemType",
    "unsignedShortItemType",
    "unsignedByteItemType",
    "positiveIntegerItemType",
    "stringItemType",
    "normalizedStringItemType",
    "tokenItemType",
    "languageItemType",
    "NameItemType",
    "NCNameItemType",
    "booleanItemType",
    "hexBinaryItemType",
    "base64BinaryItemType",
    "anyURIItemType",
    "QNameItemType",
    "durationItemType",
    "dateTimeItemType",
    "timeItemType",
    "dateItemType",
    "gYearMonthItemType",
    "gYearItemType",
    "gMonthDayItemType",
    "gDayItemType",
    "gMonthItemType",
})

# XSD types classified as numeric per XBRL 2.1 §4.8.1.
_NUMERIC_XSD_TYPES: frozenset[str] = frozenset({
    "decimal",
    "float",
    "double",
    "integer",
    "nonPositiveInteger",
    "negativeInteger",
    "long",
    "int",
    "short",
    "byte",
    "nonNegativeInteger",
    "unsignedLong",
    "unsignedInt",
    "unsignedShort",
    "unsignedByte",
    "positiveInteger",
})


def xbrli_item_type(xsd_local: str) -> str | None:
    """Return the matching ``xbrli:*ItemType`` localName, or ``None`` if the xsd
    primitive has no XBRL item type (e.g. ``ID``, ``NMTOKEN``) and must be skipped.
    """
    candidate = f"{xsd_local}ItemType"
    return candidate if candidate in _BASE_XBRLI_TYPES else None


def is_numeric(xsd_local: str) -> bool:
    """Whether the xsd primitive is numeric (drives unit/decimals emission)."""
    return xsd_local in _NUMERIC_XSD_TYPES
