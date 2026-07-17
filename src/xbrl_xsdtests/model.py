"""
See COPYRIGHT.md for copyright information.

Data models for the XSTS value/facet conformance generator.

``SourceSet`` lives here (rather than in ``sources.py``) because it is a pure data
record that ``TestGroupRef`` references; the ``sources`` module imports it and adds
the ``in_scope_sources()`` selection logic.

Dataclasses are ``frozen``. ``FacetSet``, ``ExtractedType`` and
``TypeKey`` are hashable so they can serve as dedup-cache keys. ``ExtractedValue``
carries a mutable ``extra_nsmap`` dict, so although it is frozen it is not intended
to be hashed.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Literal


@dataclass(frozen=True)
class SourceSet:
    member: str             # repo-relative path, e.g. "nistMeta/NISTXMLSchemaDatatypes.testSet"
    contributor: str        # "NIST" | "Microsoft" | "Sun"
    xsd_version: str        # "1.0" (dimension; 1.1 sets simply not listed yet)


@dataclass(frozen=True)
class TestGroupRef:
    __test__ = False  # not a pytest test class despite the "Test" prefix
    source: SourceSet
    name: str
    schema_member: str      # resolved repo-relative path of the .xsd


@dataclass(frozen=True)
class InstanceTestRef:
    group: TestGroupRef
    name: str               # unique XSTS instance name -> variation id
    instance_member: str    # resolved repo-relative path of the .xml
    validity: Literal["valid", "invalid"]


@dataclass(frozen=True)
class FacetSet:
    # ordered/normalized for canonical hashing; multiple patterns preserved in order
    base_xsd: str                               # e.g. "decimal"
    facets: tuple[tuple[str, str], ...]         # ((localName, value), ...) sorted canonical
    enumerations: tuple[str, ...]               # order-preserving
    patterns: tuple[str, ...]                   # order-preserving


@dataclass(frozen=True)
class ExtractedType:
    base_xsd: str               # built-in primitive localName
    xbrli_item_type: str        # e.g. "decimalItemType"
    numeric: bool
    facet_set: FacetSet
    facet_xml: tuple[str, ...]  # original facet child elements, serialized verbatim
    # Identity token of the tested simple type, ``local:<simpleTypeName>``.
    target_identity: str = ""
    # localName -> type-identity token for every value-bearing element declaration in
    # the schema (global *and* local). Identity tokens are ``xsd:<builtin>`` (element
    # typed by a built-in), ``local:<name>`` (typed by a local named simpleType), or
    # ``inline:<name>`` (anonymous inline simpleType). Container/complex-typed and
    # ref-only declarations are omitted. The instance extractor uses this to confirm
    # that *every* value-bearing leaf in a document maps to ``target_identity`` before
    # emitting each occurrence as a fact; a document mixing value-bearing element types
    # cannot be faithfully reduced to this one concept and is skipped.
    element_identities: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True)
class ExtractedValue:
    text: str | None                            # root text; None => nil
    is_nil: bool
    extra_nsmap: dict[str, str] = field(default_factory=dict)  # prefixes in scope (QName values)


@dataclass(frozen=True)
class TypeKey:
    value: str                  # stable slug, e.g. "decimal__minExclusive_-999..."


@dataclass(frozen=True)
class Variation:
    id: str
    instance_href: str
    expected_error: str | None  # "xmlSchema:valueError" if invalid else None


class ReasonCode(str, Enum):
    """Machine-readable skip reasons."""
    UNSUPPORTED_LIST = "unsupported-list"
    UNSUPPORTED_UNION = "unsupported-union"
    NO_XBRLI_ITEMTYPE = "no-xbrli-itemtype"
    NON_BUILTIN_BASE = "non-builtin-base"
    HAS_DEPENDENCY = "has-dependency"
    SCHEMA_TEST_ONLY = "schema-test-only"
    UNPARSEABLE = "unparseable"
    VALUE_NOT_FOUND = "value-not-found"
    MIXED_VALUE_TYPES = "mixed-value-types"
    XSI_TYPE_OVERRIDE = "xsi-type-override"


@dataclass(frozen=True)
class SkipRecord:
    source: str
    group: str
    instance: str | None
    reason: ReasonCode
    detail: str
