# Integration guide — for the developer who didn't build this

Two things change over the app's life: the **UAD schema version** and the **rule set**.
Both are pluggable by design. UI, persistence, exports, and the run pipeline never
change when they do.

## Architecture in one line

```
Upload → Ingest (zip/xml) → SchemaAdapter.validate + .normalize → RuleEngine.evaluate → Findings → Persist/UI/Export
```

- Engine (`backend/app/rules/engine.py`) is pure: `evaluate(NormalizedReport, rules, ai_backend) -> RunResult`.
- The engine only ever reads `NormalizedReport.fields` — a flat `dict[field_key -> {value, xpath, label, section}]`.

## Contract 1: Schema Adapter

`backend/app/schema_adapters/base.py`:

```python
class SchemaAdapter(Protocol):
    schema_version: str
    def validate(self, raw: RawReport) -> list[StructuralError]: ...
    def normalize(self, raw: RawReport) -> NormalizedReport: ...
```

The active adapter is `UAD36v13Adapter` (`uad36_v13.py`). It is **data-driven**:

- **XSD validation** against `GSE_UAD_3.6.0_v1.3_schema/Combined/GSE_UAD_3.6.0_v1.3.xsd`
  (path: `QC_XSD_PATH`).
- **Field extraction** from `schemas/uad36_field_manifest.json` (path: `QC_MANIFEST_PATH`),
  generated from Appendix H-1. Each entry: `key`, `scope` (`subject` = resolved under the
  subject PROPERTY node; `doc` = first match anywhere), `xpath_dir`, `element`, `label`, `section`.

**Field key convention** (rules and manifest must agree):
`{scope}:{xpath-without-leading-../}{ElementName}`, e.g.
`subject:VALUATION_ANALYSIS/PROPERTIES/PROPERTY/ADDRESS/CityName`.

**Known assumption (labeled in code):** subject property = first `<PROPERTY>` under
`VALUATION_ANALYSIS/PROPERTIES` (true in all official GSE samples). Replace with
xlink-based classification (Appendix G-1) when comparable-scoped rules are encoded.

**To integrate a new schema version (e.g. v1.4):**
1. Drop the new XSD set next to the old one; point `QC_XSD_PATH` at it.
2. Regenerate the manifest: update the CSV path in `backend/app/rules/h1_import.py`
   if H-1 moved, then `python -m app.rules.h1_import` (from `backend/`).
3. If container structure changed, subclass/copy the adapter with a new
   `schema_version` string and register it in `schema_adapters/__init__.py:get_default_adapter`.
4. Every run records `schema_version`, so old runs remain traceable.

## Contract 2: Rule definitions

Stored in the DB (admin-managed), seeded once from `rules/h1_rules.json`. Shape:

```json
{
  "rule_id": "UAD1002",              // stable unique id (H-1 Message ID)
  "category": "Subject Property",    // grouping; categories are data
  "description": "…",
  "severity": "HardStop | Warning | Advisory",   // H-1 Fatal -> HardStop
  "enabled": true,
  "logic": { "type": "…", …type-specific… },
  "citation": "UAD 3.6 Appendix H-1 v1.4, Unique ID 0100.0009, Message ID UAD1002",  // optional, NEVER fabricated
  "messages": { "appraiser": "coaching …", "reviewer": "audit …" },   // one supplied -> used for both
  "…any unknown keys are preserved…": {}
}
```

Logic types implemented (`backend/app/rules/operators.py` + engine):

| type | fires when | keys |
|------|-----------|------|
| `field_present` | field missing/blank | `field` |
| `regex_match` | present AND not fullmatch | `field`, `pattern` |
| `field_in_set` | present AND value not allowed | `field`, `allowed` |
| `numeric_range` | present AND non-numeric or out of bounds | `field`, `min?`, `max?` |
| `conditional` | at least one `if_any` AND-group is true, AND the `then` operator triggers | `if_any` (list of AND-groups of `{field, equals\|not_equals\|in}`), `then` (nested operator dict, e.g. `{"type":"field_present","field":...}`) |
| `ai` | AI backend says triggered | `prompt`, `fields` |
| `needs_encoding` | never (rule stays disabled) | `source_logic` (original H-1 text) |

Unknown `logic.type` on an enabled rule → recorded as a `rule_error`, run continues.

**`conditional` example** (H-1 UAD1021 — "if not in a project, or the project is a
condo, Property Rights Appraised is required"):
```json
{
  "type": "conditional",
  "if_any": [
    [{"field": "subject:.../PropertyInProjectIndicator", "equals": "false"}],
    [{"field": "subject:.../ProjectLegalStructureType", "equals": "Condominium"}]
  ],
  "then": {"type": "field_present", "field": "subject:.../PropertyEstateType"}
}
```
A missing condition field is treated as not-equal (never raises). `if_any` is OR
between groups, each group is AND between its conditions — this covers every
condition shape H-1 actually uses (single condition, AND chain, OR chain, one level
of parenthesized mixed AND/OR, and the "Field = "V1" or "V2"" same-field shorthand).

**The needs_encoding queue:** 566 of the 729 H-1 rules still have logic that isn't
auto-convertible as of 2026-07-03 (down from 653 — see `backend/app/rules/h1_import.py`
for the exact conversion rules, including the new `numeric_range`/`conditional`
patterns). They're imported disabled with the exact source text preserved
(Admin → "Needs encoding" tab). What's left mostly needs capability the engine
doesn't have yet: comparable-scoped rules (~139, need per-instance iteration —
Stage H1), cross-field/date-relative comparisons ("X < TodaysDate", "X > OtherField"),
uniqueness-across-array checks, count-matching, and arithmetic-sum checks. A few
individual rules were deliberately left disabled because a referenced condition
field is itself never a Primary Data Element anywhere in H-1 (no xPath to resolve
it from — e.g. `SiteValueIndicator` in UAD1229/UAD1231) or is ambiguous (used with
two different xPaths elsewhere, e.g. `SaleType` in UAD1136) — these are not guessed
at. Encode remaining rules by editing the rule's logic to one of the implemented
types (or `ai`), then enabling it. Each save freezes a new ruleset snapshot; every
run records the snapshot version it ran under.

## AI backends (`backend/app/rules/ai_backends.py`)

`stub` (default, offline) / `gemini` (developer key — SAMPLE DATA ONLY, GLBA guardrail
blocks it when `QC_DATA_CLASS=real`) / `vertex` (company GCP, real-data path).
Selected via `QC_AI_BACKEND`. The engine treats the backend as an injected interface;
add a new provider by implementing `evaluate(prompt, context) -> AIResult` and
registering it in `build_backend`.

## Versioning on every run/export

- `schema_version` — from the active adapter.
- `ruleset_version` — `db-v{snapshot}-{hash12}` (+`+ProfileName` when a client profile
  was applied). Snapshots live in the `ruleset_versions` table and are immutable.

## Environment variables

| Var | Default | Purpose |
|-----|---------|---------|
| `QC_XSD_PATH` | repo GSE v1.3 combined XSD | structural validation schema |
| `QC_MANIFEST_PATH` | `schemas/uad36_field_manifest.json` | adapter field map |
| `QC_RULES_PATH` | `rules/h1_rules.json` | first-boot rule seed |
| `QC_DB_URL` | SQLite in `backend/data` | Postgres in prod |
| `QC_DATA_DIR` | `backend/data` | SQLite + files root |
| `QC_FILES_DIR` | `{QC_DATA_DIR}/files` | retained upload originals |
| `QC_AI_BACKEND` | `stub` | stub / gemini / vertex |
| `QC_DATA_CLASS` | `sample` | `real` enables GLBA guardrail |
| `QC_GEMINI_API_KEY` | — | gemini backend |
| `QC_VERTEX_PROJECT` / `QC_VERTEX_LOCATION` / `QC_AI_MODEL` | — / us-central1 / gemini-2.0-flash | vertex backend |

## Tests

`backend\.venv\Scripts\python.exe -m pytest backend/tests -v` — 80+ tests covering
ingest, XSD validation, operators, engine, H-1 import, adapters, persistence,
review workflow, admin CRUD/profiles, exports, and AI rule handling.
