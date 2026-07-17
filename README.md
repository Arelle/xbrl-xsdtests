> **Fork notice** — This repository is a derivative of the
> [W3C XML Schema 1.1 Test Suite](https://github.com/w3c/xsdtests) (`w3c/xsdtests`).
> The original test data (all top-level `*Data`/`*Meta` directories, `suite.xml`, etc.)
> is retained under the [W3C 3-clause BSD test-suite license](https://www.w3.org/copyright/3-clause-bsd-license-2008/).
> The generator code in `src/` and `tests/` is original work licensed under
> [Apache-2.0](LICENSE) (aligned with [Arelle](https://github.com/Arelle/Arelle)).
>
> **Purpose**: convert the datatype-related XSD test cases into an XBRL-flavored
> conformance suite so that XBRL processors (e.g. Arelle) can validate their
> value/facet enforcement against the same ground-truth data the XSD working group
> used.
>
> This project is **not affiliated with or endorsed by W3C**, and does **not**
> constitute an authoritative W3C test suite.

---

# XBRL XSTS value/facet conformance suite generator

> [!WARNING]
> ## Disclaimer
> This codebase — the generator, its tests, and this README — is **entirely
AI-generated**. It has not been comprehensively reviewed by a human against the
XSTS source data or the XBRL 2.1 spec line-by-line.
> As a result, the **generated conformance suite should not be trusted as a
perfectly faithful representation of the underlying XSTS test cases**. Bugs in
translation (e.g. a misapplied facet, an incorrectly re-based type, or a
mis-detected skip condition) are possible and would not necessarily be obvious
from the suite's own output.
>The suite's purpose is narrower than "comprehensive XSD conformance testing":
it exists only to surface **indicators** of gaps in an XBRL processor's
value/facet validation, by reusing XSTS's ground-truth valid/invalid data as a
convenient source. A clean run is **not** proof of full XML Schema datatype
conformance, and a failing run should be treated as a lead to investigate
rather than an authoritative verdict. Treat all results — generation and
validation alike — as suggestive, not certain.

A standalone generator that turns the **W3C XML Schema Test Suite (XSTS)** datatype
tests into an **XBRL-flavored conformance suite**. Each in-scope `instanceTest`
literal becomes a typed XBRL fact, so validating the generated suite drives the
value through Arelle's own value/facet validator
(`arelle/XmlValidate.py::_validateValueStringOrRaise`) rather than libxml2, and
grades it through the existing conformance pipeline.

## How it works

A single-pass streaming pipeline over testGroups:

```
repo root (nistMeta/, msMeta/, sunMeta/, nistData/, msData/, sunData/, ...)
  -> sources      in-scope testSet members (NIST + Microsoft + Sun, XSD 1.0)
  -> parse        testGroup -> instanceTest; schema base + facets + element-type map; instance value(s)/nil/nsmap
  -> dedup        TypeKey canonicalization (base + normalized facets), one taxonomy per type
  -> emit         re-based gen-<key>.xsd + per-instance .xbrl (one fact per occurrence) + native testcases + index.xml
  -> manifest     skip-manifest.json for everything untranslatable
```

Each tested simple type is **re-based** onto the matching `xbrli:*ItemType` via
`complexType/simpleContent/restriction`, so Arelle derives `baseXbrliType`,
`baseXsdType`, and the facets correctly.

A source instance may carry the tested element several times (e.g. Microsoft's
`maxOccurs`-repeated probes); every occurrence is emitted as its own fact of the one
generated concept (sharing a context, and a unit for numeric types), so the emitted
instance is invalid exactly when some occurrence is invalid — reproducing the source
document's whole-document validity. This faithful translation is only sound when
**every** value-bearing leaf in the document maps to the single tested type;
documents that mix value-bearing element types (e.g. Microsoft's `<comp_foo>` complex
probe alongside `<simpleTest>`, or an `<foo>`/`<bar>` pair of different types) cannot
be reduced to one concept and are skipped (`mixed-value-types`). The `xsd:import` of the XBRL instance
schema is pinned to its canonical URL and resolves from Arelle's bundled cache, so
generation and validation are fully offline.

The generator uses only the Python standard library at runtime — Arelle is not required. The single
Arelle-coupled check is a separate pytest (see *Validation smoke test* below) and
requires `pip install ".[dev]"`.

## Generating the suite

```bash
python -m xbrl_xsdtests
```

Output is written to the gitignored `output/` directory and is **not committed**;
regenerate it whenever you want to run the suite.

### CLI options

| Option | Description |
|---|---|
| `--data-root PATH` | Root directory containing XSTS test data (default: repo root) |
| `--out PATH` | Output directory (default: `output/`) |
| `--version VER` | XSD outcome version to select (default: `1.0`) |
| `--limit N` | Only process the first N testGroups (mini-suite) |
| `--no-self-test` | Skip the internal consistency check |
| `--list-sources` | List in-scope testSet members and exit |
| `--count` | Print per-source instanceTest counts and exit |

After emitting, an internal consistency check (pure filesystem/XML, no Arelle)
asserts every `<testcase uri>`, `<instance>` href, and `schemaRef` href resolves on
disk, failing loudly otherwise.

## Output layout

```
output/                         (gitignored)
    index.xml                   native <testcases> index (written last)
    skip-manifest.json          skipped groups/instances + counts by reason
    taxonomies/gen-<key>.xsd    one re-based taxonomy per unique type key
    <category>/<key>-testcase.xml
    <category>/<key>/<variation>.xbrl     one fact per tested-element occurrence
```

Expected results follow the native conformance format: `invalid` instances expect
`<error>xmlSchema:valueError</error>`; `valid` instances expect an empty
`<result/>` (match-all).

## Running the conformance suite

Generate the suite first (above), then run it by name:

```bash
# In the Arelle repo (the generated output must be present at the expected path):
python -m pytest tests/integration_tests/validation/test_conformance_suites.py \
    --name xbrl_xsdtests
```

Because this is a discovery harness, failures are the **signal** (value-validation
gaps), not a build break.

## Validation smoke test

`tests/test_smoke.py` is the only Arelle-coupled test: it emits a fixed four-type slice
(decimal/`minExclusive`, string/`enumeration`, token/`pattern`, QName), runs Arelle
in-process over each instance, and asserts `valid => 0 errors` /
`invalid => exactly xmlSchema:valueError`. It guards against the import-URL
regression that would collapse the concept type to `anyType`.

## Design decisions

### Why re-base onto `xbrli:*ItemType`?

XBRL 2.1 §5.1.1.3 (`xbrl.5.1.1.3:itemType`) requires every item concept's type to
derive from an `xbrli:*ItemType`. The original XSTS `simpleType` restricts `xs:decimal`
(etc.) directly, which gives `baseXbrliType = None` and fires an error storm.
Wrapping the original facets into `complexType/simpleContent/restriction
base="xbrli:decimalItemType"` satisfies this constraint while preserving facet
enforcement: Arelle's `XmlUtil.schemaFacets` traverses
`complexType/simpleContent/restriction` to find facet children, and
`constrainingFacets` walks `typeDerivedFrom` recursively so inherited facets
accumulate.

### Critical: xbrli import URL

The taxonomy `xsd:import` of the XBRL instance schema **must** use
`http://www.xbrl.org/2003/xbrl-instance-2003-12-31.xsd` (no `/instance/` path
segment). The wrong URL fails to resolve (even from cache), collapsing the concept
to `anyType` — silently disabling range/QName checks while still firing
enumeration/pattern checks. This asymmetry makes partial breakage hard to detect,
which is why the smoke test exists.

### Fact construction rules

- **Numeric items** (decimal, float, double, integer family): unit =
  `xbrli:pure` + `decimals="INF"`. No `balance` attribute (only monetary may have
  one).
- **Non-numeric items**: no unit, no decimals.
- **All items**: `substitutionGroup="xbrli:item"`, `periodType="instant"`,
  `nillable="true"`, `abstract="false"`, instant context with dummy entity.
- **Nil values**: `xsi:nil="true"`, no decimals (concept is nillable).
- **QName values**: in-scope namespace declarations copied onto the fact element so
  prefixes resolve.
- Value text preserved verbatim (no whitespace normalization — Arelle applies the
  type's whitespace facet).

### TypeKey dedup canonicalization

- **Built-in type, no facets** → key = base localName (e.g. `string`).
- **Custom restriction** → key = base + canonical facet signature: facets sorted by
  `(localName, value)`; `enumeration`/`pattern` kept in document order (semantically
  relevant); a short stable hash suffix is appended when the slug would collide or
  exceed filesystem name limits.
- Two testGroups with identical key share one `gen-<key>.xsd` taxonomy; their
  instances all `schemaRef` it.

### Source scope (XSD 1.0 only, v1)

| Source (repo-relative path) | Contributor | instanceTests |
|---|---|---|
| `nistMeta/NISTXMLSchemaDatatypes.testSet` | NIST | ~19,217 |
| `msMeta/Regex_w3c.xml` | Microsoft | ~1,432 |
| `msMeta/DataTypes_w3c.xml` | Microsoft | ~1,187 |
| `msMeta/SimpleType_w3c.xml` | Microsoft | ~110 |
| `sunMeta/SType.testSet` | Sun | ~200 |

36 of 38 NIST atomic types are translatable; `ID` and `NMTOKEN` skip (no
`xbrli:*ItemType`). `xs:list` and `xs:union` categories are skipped entirely.
XSD 1.1 contributors (IBM, Saxon, Oracle, WG) are deferred but the `xsd_version`
dimension is built in for future enablement.

### Non-goals (deferred)

- `schemaTest` emission (facet-definition legality checks).
- XSD 1.1 sources.
- `xs:list` / `xs:union` / typeless translation.
- Expected-failure triage (the suite is intentionally un-triaged — failures are the
  discovery signal).

### Known edge cases

- **Whitespace semantics**: fact text is preserved verbatim; if XSTS expected
  validity relies on whitespace normalization differences between `string`/`token`/
  `normalizedString`, the fact may validate differently than the source intended.
  No triage — surfaces as discovery failures.
- **"Wrong reason" detection**: a partially broken taxonomy (e.g. bad import URL)
  can still fire enumeration/pattern errors (found structurally) while silently
  passing range/QName checks (need resolved `baseXsdType`). The smoke test guards
  against this class of silent regression.

## Skip reasons

Untranslatable testGroups/instances are recorded in `skip-manifest.json` rather
than emitted:

| Reason | Meaning |
|---|---|
| `unsupported-list` | `xs:list` type |
| `unsupported-union` | `xs:union` type |
| `no-xbrli-itemtype` | base maps to no `xbrli:*ItemType` (e.g. `ID`, `NMTOKEN`) |
| `non-builtin-base` | restriction base is not an `xs:` primitive |
| `has-dependency` | schema `import`/`include`, or restriction of a local type |
| `schema-test-only` | testGroup has no `instanceTest` (informational) |
| `unparseable` | malformed schema or instance member |
| `value-not-found` | no element of the tested type appears in the instance (e.g. `substitutionGroup`/`xsi:type` substitution) |
| `mixed-value-types` | the instance mixes value-bearing element types, so it can't be reduced to one concept (e.g. Microsoft `<comp_foo>` + `<simpleTest>`, or `<foo>`/`<bar>` of different types) |
| `xsi-type-override` | a value leaf of the tested type carries `xsi:type`; its effective type (and the document's validity) is decided by the override, which the re-based fact can't reproduce |

## Module map

| Module | Responsibility |
|---|---|
| `sources.py` | in-scope XSTS testSet members + version tags |
| `typemap.py` | xsd base type -> `xbrli:*ItemType` mapping + numeric flag |
| `model.py` | dataclasses (refs, extracted type/value, `TypeKey`, `SkipRecord`) |
| `parse.py` | `TestSetParser`, `SchemaExtractor`, `InstanceExtractor` |
| `dedup.py` | `TaxonomyDedup` — `TypeKey` canonicalization + cache |
| `emit.py` | `TaxonomyEmitter`, `InstanceEmitter`, `IndexEmitter` |
| `manifest.py` | `SkipManifest` writer |
| `generate.py` | pipeline orchestration + consistency check |
| `__main__.py` | CLI entry point |
