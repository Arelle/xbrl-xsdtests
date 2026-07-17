"""
See COPYRIGHT.md for copyright information.

TestSetParser, SchemaExtractor, InstanceExtractor (stdlib ElementTree-based).

The parsers are namespace-aware (not prefix-based): XSTS schema documents use a
mix of conventions (some bind the XSD namespace to ``xs:``, others make it the
default namespace), so everything is matched by ``{namespace}localName``.
"""

from __future__ import annotations

import posixpath
from collections.abc import Iterator
from pathlib import Path

from xbrl_xsdtests import xmlutil as etree
from xbrl_xsdtests.xmlutil import nsmap

from xbrl_xsdtests import typemap
from xbrl_xsdtests.model import (
    ExtractedType,
    ExtractedValue,
    FacetSet,
    InstanceTestRef,
    ReasonCode,
    SkipRecord,
    SourceSet,
    TestGroupRef,
)

TS_NS = "http://www.w3.org/XML/2004/xml-schema-test-suite/"
XLINK_NS = "http://www.w3.org/1999/xlink"
XSD_NS = "http://www.w3.org/2001/XMLSchema"
XSI_NS = "http://www.w3.org/2001/XMLSchema-instance"

_NIL_TRUE = frozenset({"true", "1"})

_VALIDITIES = frozenset({"valid", "invalid"})
# Facets whose order is semantically relevant and which are kept verbatim/ordered.
_ENUMERATION = "enumeration"
_PATTERN = "pattern"


def _resolve_member(base_member: str, href: str) -> str:
    """Resolve an ``xlink:href`` relative to the repo-relative path of its testSet member."""
    return posixpath.normpath(posixpath.join(posixpath.dirname(base_member), href))


def _resolve_qname(element: etree.Element, qname: str) -> tuple[str | None, str]:
    """Resolve a possibly-prefixed QName string against an element's namespace map."""
    element_nsmap = nsmap(element)
    if ":" in qname:
        prefix, local = qname.split(":", 1)
        return element_nsmap.get(prefix), local
    return element_nsmap.get(None), qname


def _local_name(element: etree.Element) -> str:
    return etree.localname(element)


_XSD_1_1 = "1.1"


def _select_expected(instance_test: etree.Element) -> etree.Element | None:
    """Pick the first ``<expected>`` not tagged ``version="1.1"``.

    Some testGroups (e.g. Microsoft's ``DataTypes_w3c``) carry multiple
    version-tagged ``<expected>`` siblings whose outcome differs by XSD version,
    e.g. ``float018_1917.i``::

        <expected validity="valid" version="1.1"/>
        <expected validity="invalid" version="1.0"/>

    This generator only targets XSD 1.0 outcomes (v1 non-goal), so a 1.1-tagged
    outcome is skipped in favor of the next sibling. Note ``version`` is
    overloaded elsewhere in the corpus for unrelated dimensions (e.g. the
    Microsoft regex tests use ``version="Unicode_4.0.0"``/``"Unicode_6.0.0"`` for
    the Unicode database version) — only the literal ``"1.1"`` tag is treated as
    an XSD-version marker; anything else is picked by document
    order.
    """
    for candidate in instance_test.findall(f"{{{TS_NS}}}expected"):
        if candidate.get("version") == _XSD_1_1:
            continue
        return candidate
    return None


class TestSetParser:
    """Streams a testSet member, yielding one ``InstanceTestRef`` per ``instanceTest``.

    Groups with no ``instanceTest`` (e.g. schemaTest-only legality checks) yield an
    informational ``SkipRecord`` with reason ``schema-test-only`` instead.
    """

    __test__ = False  # not a pytest test class despite the "Test" prefix

    def __init__(self, root: Path) -> None:
        self._root = root

    def iter_instance_tests(self, source: SourceSet) -> Iterator[InstanceTestRef | SkipRecord]:
        with (self._root / source.member).open("rb") as fh:
            for _event, group in etree.iterparse(fh, events=("end",), tag=f"{{{TS_NS}}}testGroup"):
                yield from self._handle_group(source, group)
                group.clear()

    def _handle_group(self, source: SourceSet, group: etree.Element) -> Iterator[InstanceTestRef | SkipRecord]:
        group_name = group.get("name") or ""
        schema_member = self._schema_member(source, group)
        group_ref = TestGroupRef(source=source, name=group_name, schema_member=schema_member or "")
        instance_tests = group.findall(f"{{{TS_NS}}}instanceTest")
        if not instance_tests:
            yield SkipRecord(
                source=source.contributor,
                group=group_name,
                instance=None,
                reason=ReasonCode.SCHEMA_TEST_ONLY,
                detail="testGroup has no instanceTest",
            )
            return
        for instance_test in instance_tests:
            ref = self._instance_ref(source, group_ref, instance_test)
            if ref is not None:
                yield ref

    def _schema_member(self, source: SourceSet, group: etree.Element) -> str | None:
        document = group.find(f"{{{TS_NS}}}schemaTest/{{{TS_NS}}}schemaDocument")
        if document is None:
            document = group.find(f".//{{{TS_NS}}}schemaDocument")
        if document is None:
            return None
        href = document.get(f"{{{XLINK_NS}}}href")
        return _resolve_member(source.member, href) if href else None

    def _instance_ref(
        self, source: SourceSet, group_ref: TestGroupRef, instance_test: etree.Element
    ) -> InstanceTestRef | None:
        document = instance_test.find(f"{{{TS_NS}}}instanceDocument")
        href = document.get(f"{{{XLINK_NS}}}href") if document is not None else None
        expected = _select_expected(instance_test)
        validity = expected.get("validity") if expected is not None else None
        if not href or validity not in _VALIDITIES:
            return None
        return InstanceTestRef(
            group=group_ref,
            name=instance_test.get("name") or "",
            instance_member=_resolve_member(source.member, href),
            validity=validity,  # type: ignore[arg-type]
        )


class SchemaExtractor:
    """Extracts the tested simple type from a testGroup ``.xsd``.

    Returns an ``ExtractedType`` for a translatable restriction of a built-in xsd
    primitive, otherwise a ``SkipRecord`` with the appropriate reason code.
    """

    def __init__(self, root: Path) -> None:
        self._root = root

    def extract(self, ref: TestGroupRef) -> ExtractedType | SkipRecord:
        category_skip = self._category_skip(ref)
        if category_skip is not None:
            return category_skip
        try:
            schema_root = self._parse(ref.schema_member)
        except (etree.XMLSyntaxError, OSError) as exc:
            return self._skip(ref, ReasonCode.UNPARSEABLE, f"failed to parse schema: {exc}")
        if schema_root.find(f"{{{XSD_NS}}}import") is not None or schema_root.find(f"{{{XSD_NS}}}include") is not None:
            return self._skip(ref, ReasonCode.HAS_DEPENDENCY, "schema has import/include")
        simple_types = {
            st.get("name"): st
            for st in schema_root.findall(f"{{{XSD_NS}}}simpleType")
            if st.get("name")
        }
        target = self._target_simple_type(schema_root, simple_types)
        if target is None:
            return self._skip(ref, ReasonCode.NON_BUILTIN_BASE, "no element references a local simpleType")
        _value_element, simple_type = target
        target_identity = f"local:{simple_type.get('name')}"
        element_identities = self._element_identities(schema_root, simple_types)
        return self._classify(ref, target_identity, element_identities, simple_type, simple_types)

    def _parse(self, schema_member: str) -> etree.Element:
        with (self._root / schema_member).open("rb") as fh:
            return etree.parse(fh, track_ns=True).getroot()

    def _category_skip(self, ref: TestGroupRef) -> SkipRecord | None:
        member = ref.schema_member
        if "/list/" in member:
            return self._skip(ref, ReasonCode.UNSUPPORTED_LIST, "list category (member path)")
        if "/union/" in member:
            return self._skip(ref, ReasonCode.UNSUPPORTED_UNION, "union category (member path)")
        return None

    def _target_simple_type(
        self, root: etree.Element, simple_types: dict[str, etree.Element]
    ) -> tuple[str | None, etree.Element] | None:
        """Find the first element declaring a local simpleType-typed value.

        Returns ``(elementName, simpleType)`` — the element's ``name`` is the
        localName of the value-bearing element in the instance (the instance root
        for root-typed sources like NIST, or a nested probe like Microsoft's
        ``<simpleTest>``). The name is ``None`` for an anonymous/ref-only element.
        """
        for element in root.findall(f"{{{XSD_NS}}}element"):
            type_attr = element.get("type")
            if not type_attr:
                continue
            _uri, local = _resolve_qname(element, type_attr)
            if local in simple_types:
                return element.get("name"), simple_types[local]
        return None

    @staticmethod
    def _element_identity(
        element: etree.Element, simple_types: dict[str, etree.Element]
    ) -> str | None:
        """Type-identity token of a value-bearing element declaration, else ``None``.

        ``xsd:<builtin>`` (typed by a built-in primitive), ``local:<name>`` (typed by
        a local named simpleType), or ``inline:<name>`` (anonymous inline simpleType).
        Returns ``None`` for complex-typed, externally-typed, or ref-only declarations,
        which carry no simple value of their own.
        """
        type_attr = element.get("type")
        if type_attr:
            uri, local = _resolve_qname(element, type_attr)
            if uri == XSD_NS:
                return f"xsd:{local}"
            if local in simple_types:
                return f"local:{local}"
            return None
        if element.find(f"{{{XSD_NS}}}simpleType") is not None:
            return f"inline:{element.get('name')}"
        return None

    @classmethod
    def _element_identities(
        cls, root: etree.Element, simple_types: dict[str, etree.Element]
    ) -> tuple[tuple[str, str], ...]:
        """Map every named element declaration (global and local) to its identity."""
        identities: dict[str, str] = {}
        for element in root.iter(f"{{{XSD_NS}}}element"):
            name = element.get("name")
            if not name:
                continue
            identity = cls._element_identity(element, simple_types)
            if identity is not None:
                identities[name] = identity
        return tuple(sorted(identities.items()))

    def _classify(
        self,
        ref: TestGroupRef,
        target_identity: str,
        element_identities: tuple[tuple[str, str], ...],
        simple_type: etree.Element,
        simple_types: dict[str, etree.Element],
    ) -> ExtractedType | SkipRecord:
        construct_skip = self._construct_skip(ref, simple_type)
        if construct_skip is not None:
            return construct_skip
        restriction = simple_type.find(f"{{{XSD_NS}}}restriction")
        if restriction is None:
            return self._skip(ref, ReasonCode.NON_BUILTIN_BASE, "simpleType has no restriction")
        base = restriction.get("base")
        if not base:
            return self._skip(ref, ReasonCode.NON_BUILTIN_BASE, "restriction has no base")
        base_uri, base_local = _resolve_qname(restriction, base)
        if base_uri != XSD_NS:
            return self._non_builtin_base(ref, base_local, simple_types)
        item_type = typemap.xbrli_item_type(base_local)
        if item_type is None:
            return self._skip(ref, ReasonCode.NO_XBRLI_ITEMTYPE, f"xsd:{base_local} has no xbrli item type")
        return self._build_type(restriction, base_local, item_type, target_identity, element_identities)

    def _construct_skip(self, ref: TestGroupRef, simple_type: etree.Element) -> SkipRecord | None:
        if simple_type.find(f"{{{XSD_NS}}}union") is not None:
            return self._skip(ref, ReasonCode.UNSUPPORTED_UNION, "xs:union construct")
        if simple_type.find(f"{{{XSD_NS}}}list") is not None:
            return self._skip(ref, ReasonCode.UNSUPPORTED_LIST, "xs:list construct")
        return None

    def _non_builtin_base(
        self, ref: TestGroupRef, base_local: str, simple_types: dict[str, etree.Element]
    ) -> SkipRecord:
        base_type = simple_types.get(base_local)
        if base_type is not None:
            if base_type.find(f"{{{XSD_NS}}}union") is not None:
                return self._skip(ref, ReasonCode.UNSUPPORTED_UNION, "restriction of local union type")
            if base_type.find(f"{{{XSD_NS}}}list") is not None:
                return self._skip(ref, ReasonCode.UNSUPPORTED_LIST, "restriction of local list type")
            return self._skip(ref, ReasonCode.HAS_DEPENDENCY, f"restriction of local type {base_local}")
        return self._skip(ref, ReasonCode.NON_BUILTIN_BASE, f"restriction base {base_local} is not an xsd primitive")

    def _build_type(
        self,
        restriction: etree.Element,
        base_local: str,
        item_type: str,
        target_identity: str,
        element_identities: tuple[tuple[str, str], ...],
    ) -> ExtractedType:
        facets: list[tuple[str, str]] = []
        enumerations: list[str] = []
        patterns: list[str] = []
        facet_xml: list[str] = []
        for child in restriction:
            if not isinstance(child.tag, str):  # comments / PIs
                continue
            local = _local_name(child)
            if local == "annotation":
                continue
            value = child.get("value", "")
            if local == _ENUMERATION:
                enumerations.append(value)
            elif local == _PATTERN:
                patterns.append(value)
            else:
                facets.append((local, value))
            facet_xml.append(etree.tostring(child, encoding="unicode").strip())
        facet_set = FacetSet(
            base_xsd=base_local,
            facets=tuple(sorted(facets)),
            enumerations=tuple(enumerations),
            patterns=tuple(patterns),
        )
        return ExtractedType(
            base_xsd=base_local,
            xbrli_item_type=item_type,
            numeric=typemap.is_numeric(base_local),
            facet_set=facet_set,
            facet_xml=tuple(facet_xml),
            target_identity=target_identity,
            element_identities=element_identities,
        )

    @staticmethod
    def _skip(ref: TestGroupRef, reason: ReasonCode, detail: str) -> SkipRecord:
        return SkipRecord(
            source=ref.source.contributor,
            group=ref.name,
            instance=None,
            reason=reason,
            detail=detail,
        )


class InstanceExtractor:
    """Extracts the literal value(s) from an instance ``.xml``.

    Captures each value-bearing leaf element's text verbatim (no whitespace
    normalization — Arelle applies the type's whitespace facet), nil status, and the
    prefixed namespace declarations in scope (needed so QName-valued facts keep a
    resolvable prefix). The default namespace and the XSD-instance namespace are
    dropped since neither is relevant on the re-based fact.

    The value element is *not* always the instance root: NIST/Sun instances make the
    typed element the root, but Microsoft's ``msData`` instances wrap it in a generic
    ``<root>`` container with named probes (``<simpleTest>``, ``<complexTest>``) and
    may repeat the probe many times. We therefore walk every leaf element (one with
    no child elements) and classify it via the schema's element-identity map:

    * if every leaf maps to the tested type (``target_identity``), each leaf's value
      is returned — one per occurrence, in document order — so the emitted instance
      carries every tested value as a fact and reproduces the source document's
      validity (a document is invalid iff some fact is invalid);
    * if the document mixes value-bearing element types (a leaf maps to a *different*
      declared type, or to an element the schema does not declare), it cannot be
      faithfully reduced to this one concept and a ``mixed-value-types`` skip is
      returned rather than a partial/biased single fact;
    * if no leaf maps to the tested type (e.g. ``substitutionGroup``/``xsi:type``
      substitution tests carrying the head element under another name), a
      ``value-not-found`` skip is returned;
    * if a value leaf of the tested type carries an ``xsi:type`` attribute, its
      effective type — and therefore the document's validity — is decided by that
      type override (often the whole point of the source test, e.g. a negative test
      that names a non-existent or incompatible type). The re-based fact drops the
      override, so an ``xsi-type-override`` skip is returned rather than emitting a
      fact whose validity would no longer match the source.
    """

    def __init__(self, root: Path) -> None:
        self._root = root

    def extract(
        self,
        ref: InstanceTestRef,
        element_identities: dict[str, str],
        target_identity: str,
    ) -> list[ExtractedValue] | SkipRecord:
        try:
            root = self._parse(ref.instance_member)
        except (etree.XMLSyntaxError, KeyError, OSError) as exc:
            return self._skip(ref, ReasonCode.UNPARSEABLE, f"failed to parse instance: {exc}")
        target_leaves: list[etree.Element] = []
        other_identities: set[str] = set()
        has_unrecognized = False
        for leaf in self._leaves(root):
            identity = element_identities.get(_local_name(leaf))
            if identity is None:
                has_unrecognized = True
            elif identity == target_identity:
                target_leaves.append(leaf)
            else:
                other_identities.add(identity)
        if not target_leaves:
            return self._skip(
                ref, ReasonCode.VALUE_NOT_FOUND, "no value element of the tested type in instance"
            )
        if other_identities or has_unrecognized:
            detail = "instance mixes value-bearing element types: " + ", ".join(
                sorted(other_identities) or ["undeclared element"]
            )
            return self._skip(ref, ReasonCode.MIXED_VALUE_TYPES, detail)
        if any(leaf.get(f"{{{XSI_NS}}}type") is not None for leaf in target_leaves):
            return self._skip(
                ref,
                ReasonCode.XSI_TYPE_OVERRIDE,
                "value element carries xsi:type; the effective type (and thus validity) "
                "is governed by the type override, which the re-based fact cannot reproduce",
            )
        return [self._value_of(leaf) for leaf in target_leaves]

    @staticmethod
    def _leaves(root: etree.Element) -> Iterator[etree.Element]:
        """Yield every element with no element children (comments/PIs ignored)."""
        for element in root.iter():
            if not isinstance(element.tag, str):
                continue
            if not any(isinstance(child.tag, str) for child in element):
                yield element

    @staticmethod
    def _value_of(element: etree.Element) -> ExtractedValue:
        is_nil = element.get(f"{{{XSI_NS}}}nil") in _NIL_TRUE
        text = None if is_nil else (element.text if element.text is not None else "")
        element_nsmap = nsmap(element)
        extra_nsmap = {
            prefix: uri
            for prefix, uri in element_nsmap.items()
            if prefix is not None and uri != XSI_NS
        }
        return ExtractedValue(text=text, is_nil=is_nil, extra_nsmap=extra_nsmap)

    @staticmethod
    def _skip(ref: InstanceTestRef, reason: ReasonCode, detail: str) -> SkipRecord:
        return SkipRecord(
            source=ref.group.source.contributor,
            group=ref.group.name,
            instance=ref.name,
            reason=reason,
            detail=detail,
        )

    def _parse(self, instance_member: str) -> etree.Element:
        with (self._root / instance_member).open("rb") as fh:
            return etree.parse(fh, track_ns=True).getroot()
