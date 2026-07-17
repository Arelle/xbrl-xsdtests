"""
See COPYRIGHT.md for copyright information.

Arelle-coupled validation smoke test for the XSTS value/facet generator.

This is the **only** test in the generator project that imports Arelle's runtime.
It emits the fixed four-type slice (decimal/minExclusive, string/enumeration,
token/pattern, QName), each with a valid and an invalid instance, then runs Arelle
in-process over every instance and asserts:

    valid   => zero error/warning messages
    invalid => exactly one ``xmlSchema:valueError``

If the xbrli import URL regresses (the ``anyType`` collapse), the valid cases
emit a storm of incidental errors and this test fails loudly.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

arelle = pytest.importorskip("arelle", reason="arelle not installed (install with: pip install -e .[arelle])")
from arelle.api.Session import Session  # noqa: E402
from arelle.RuntimeOptions import RuntimeOptions  # noqa: E402
from xbrl_xsdtests.dedup import TaxonomyDedup
from xbrl_xsdtests.emit import (
    InstanceEmitter,
    TaxonomyEmitter,
)
from xbrl_xsdtests.model import (
    ExtractedValue,
    InstanceTestRef,
    SourceSet,
    TestGroupRef,
)
from xbrl_xsdtests.parse import SchemaExtractor

VALUE_ERROR = "xmlSchema:valueError"
_SOURCE = SourceSet(member="x/m.testSet", contributor="NIST", xsd_version="1.0")


def _schema(body: str) -> str:
    return (
        '<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema" '
        'xmlns="urn:t" targetNamespace="urn:t">' + body + "</xs:schema>"
    )


def _simple_type(base: str, facet: str = "") -> str:
    return (
        '<xs:element name="t" type="tType"/>'
        '<xs:simpleType name="tType">'
        f'<xs:restriction base="{base}">{facet}</xs:restriction>'
        "</xs:simpleType>"
    )


# label -> (schema body, valid value, invalid value)
CASES: dict[str, tuple[str, str, str]] = {
    "decimal": (
        _simple_type("xs:decimal", '<xs:minExclusive value="-999"/>'),
        "-998",
        "-1000",
    ),
    "string": (
        _simple_type(
            "xs:string",
            '<xs:enumeration value="alpha"/><xs:enumeration value="beta"/>',
        ),
        "alpha",
        "delta",
    ),
    "token": (
        _simple_type("xs:token", '<xs:pattern value="[a-z]+"/>'),
        "abc",
        "ABC",
    ),
    "qname": (
        _simple_type("xs:QName"),
        "xbrli:pure",  # xbrli prefix is declared structurally on every instance root
        "undeclaredprefix:foo",
    ),
}


def _extractor(tmp: Path) -> SchemaExtractor:
    for label, (body, _v, _i) in CASES.items():
        path = tmp / f"{label}.xsd"
        path.write_text(_schema(body), encoding="utf-8")
    return SchemaExtractor(tmp)


def _ref(label: str, validity: str) -> InstanceTestRef:
    group = TestGroupRef(source=_SOURCE, name=f"{label}-{validity}", schema_member=f"{label}.xsd")
    return InstanceTestRef(
        group=group,
        name=f"{label}-{validity}",
        instance_member=f"{label}/{validity}.xml",
        validity=validity,  # type: ignore[arg-type]
    )


def _emit_slice(tmp: Path, out: Path) -> dict[tuple[str, str], Path]:
    """Emit the four-type slice (valid + invalid each); return label/validity -> path."""
    extractor = _extractor(tmp)
    dedup = TaxonomyDedup()
    taxonomy_emitter = TaxonomyEmitter()
    instance_emitter = InstanceEmitter()
    paths: dict[tuple[str, str], Path] = {}
    for label, (_body, valid_value, invalid_value) in CASES.items():
        group = TestGroupRef(source=_SOURCE, name=label, schema_member=f"{label}.xsd")
        extracted = extractor.extract(group)
        key, is_new = dedup.get_or_register(extracted)  # type: ignore[arg-type]
        if is_new:
            taxonomy_emitter.emit(key, extracted, out)  # type: ignore[arg-type]
        for validity, value in (("valid", valid_value), ("invalid", invalid_value)):
            ref = _ref(label, validity)
            extracted_value = ExtractedValue(text=value, is_nil=False, extra_nsmap={})
            paths[(label, validity)] = instance_emitter.emit(ref, [extracted_value], key, extracted, out)  # type: ignore[arg-type]
    return paths


def _validate(instance_path: Path) -> list[str]:
    """Run Arelle in-process over one instance; return error/warning message codes."""
    options = RuntimeOptions(
        entrypointFile=str(instance_path),
        validate=True,
        keepOpen=True,
        internetConnectivity="offline",
        baseTaxonomyValidationMode="none",
        logFile="logToBuffer",
    )
    with Session() as session:
        session.run(options)
        logs = json.loads(session.get_logs("json"))
    return [
        entry["code"]
        for entry in logs["log"]
        if entry.get("level", "").lower() in ("error", "warning", "critical")
    ]


@pytest.fixture(scope="module")
def emitted(tmp_path_factory: pytest.TempPathFactory) -> dict[tuple[str, str], Path]:
    tmp = tmp_path_factory.mktemp("xsts_smoke_schemas")
    out = tmp_path_factory.mktemp("xsts_smoke")
    return _emit_slice(tmp, out)


@pytest.mark.parametrize("label", sorted(CASES))
class TestValueContract:
    def test_valid_value_has_no_errors(self, emitted: dict[tuple[str, str], Path], label: str) -> None:
        codes = _validate(emitted[(label, "valid")])
        assert codes == [], f"{label} valid instance produced unexpected messages: {codes}"

    def test_invalid_value_is_exactly_value_error(
        self, emitted: dict[tuple[str, str], Path], label: str
    ) -> None:
        codes = _validate(emitted[(label, "invalid")])
        assert codes == [VALUE_ERROR], f"{label} invalid instance produced: {codes}"
