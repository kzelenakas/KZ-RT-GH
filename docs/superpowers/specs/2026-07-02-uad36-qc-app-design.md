# UAD 3.6 QC Application — Design

**Date:** 2026-07-02
**Status:** Draft — awaiting user review
**Source spec:** `README.md` (project root)

## Decisions Made During Brainstorming

| Decision | Choice | Notes |
|----------|--------|-------|
| Beta users | Kevin only + c-suite demo | No real accounts. In-app role switcher (Appraiser / Reviewer / Admin). |
| Beta data | Real reports on **company-controlled GCP** | GLBA NPI stays under True Footage governance. Requires company IT to provision the GCP project before real data flows. |
| Access gate | **Google IAP** in front of the app | Only allowlisted True Footage Google accounts reach the app. No auth code in the app itself. |
| AI in beta | Live AI rules, pluggable backend | Kevin's Gemini API key for dev/testing on **sample data only** (free-tier keys allow Google to train on inputs — never real reports). **Vertex AI on company GCP** for real reports. One config switch. Consumer Gemini Pro subscription is not usable programmatically. |
| Sample file | Kevin will provide one real UAD 3.6 delivery zip | Dropped in `samples/`, PII-scrubbed. Build starts on fabricated samples; ingest re-validated against the real file when it arrives. |
| GCP shape | **Cloud Run + Cloud SQL (Postgres) + Cloud Storage** | ⚠️ ASSUMED (user was away when asked). Scales to zero when idle (~$12–20/mo, mostly the database). Swappable before build if Kevin prefers a single VM. |

## UPDATE (same day): Deferred Inputs Have Arrived

The README's "deferred inputs — do not invent them" constraint is now largely satisfied. Kevin dropped the official GSE artifacts into the repo:

| Artifact | Location | What it gives us |
|----------|----------|------------------|
| **UAD 3.6 XSD schema v1.3** | `GSE_UAD_3.6.0_v1.3_schema/Combined/GSE_UAD_3.6.0_v1.3.xsd` (+ Individual variants) | Real structural validation — validate any UAD 3.6 XML directly against the official XSD (lxml). No placeholder schema validation needed. |
| **Appendix A-1 URAR Delivery Specification** | `GSE_UAD_3.6.0_v1.3_schema/appendix-a-1-urar-delivery-specification.xlsx` | Field dictionary / XPath mapping — the source for the Schema Adapter's normalized field paths, labels, and report-section references. |
| **Appendix H-1 UAD Compliance Rules v1.4** | `QC_rules/Appendix H-1 - Compliance Rules - UAD Compliance Rules v1.4.csv` | **729 real GSE rules** (597 Fatal, 132 Warning) with Unique ID, Message ID/Text, natural-language Rule Logic, Severity, Report Section/Subsection, XPath, format constraints. This becomes the seed ruleset. |
| **3 official sample reports** | `Sample reports/SF1_… SF3_… Condo2_Appraisal_v1.4.zip` | Real delivery zips (XML + PDF + `Images/` — structure matches the README's assumption exactly). Test fixtures for ingest + end-to-end. GSE-published samples, no real borrower PII. |
| Reference PDFs (Appendix C-1, E, E-1, F-1, G-1) | `GSE_UAD_3.6.0_v1.3_schema/` | Human-readable reference for report locations, display labels, and codes. |

**Impact on this design (architecture unchanged — contracts absorb the real inputs as intended):**

- **Structural validation** = XSD validation against the official schema. `schema_version` recorded as `GSE_UAD_3.6.0_v1.3`.
- **Schema Adapter** `UAD36v13Adapter` is built for real, driven by the A-1 spec. The `PlaceholderAdapter` survives only as a test fixture proving the contract is pluggable.
- **Seed ruleset** = H-1 import pipeline (CSV → rule JSON → DB), ruleset version `H-1 v1.4`. Severity mapping: Fatal → HardStop, Warning → Warning (Advisory tier stays available for future/custom rules).
- **H-1 Rule Logic is natural language.** Conversion strategy: auto-convert the mechanical majority ("X is not provided" → `field_present`, format text + Date/Number Format columns → `regex_match`/`numeric_range`, valid-code checks → `field_in_set` from the XSD enumerations); rules whose logic can't be auto-converted are imported with logic type `needs_encoding` — they appear in Admin flagged as not-yet-executable and get encoded in batches during build. Nothing is silently dropped or fabricated.
- **Messages:** H-1 supplies one message text per rule → used for both variants (per the contract). Coaching variants can be authored later in Admin, and may be AI-assist-drafted for human review.
- **Sample file question is moot** — three official samples already in `samples/` scope.

## Architecture Overview

```
Browser ──▶ IAP ──▶ Cloud Run container
                      ├─ FastAPI backend (serves API + built React frontend)
                      │
        ┌─────────────┼──────────────┐
        ▼             ▼              ▼
   Cloud SQL     Cloud Storage   Vertex AI / Gemini API
   (runs, findings,  (uploaded zips,   (AI rule backend,
    rules, audit)     extracted files)   pluggable)
```

**Local development:** same code runs with SQLite + local file storage + stub/Gemini AI backend. No GCP needed until deploy phase.

**Pipeline (unchanged from README):**
`Ingest → Schema Adapter → Rule Engine → Findings → UI / Export / Persistence`

## Repository Layout

```
Revisions/
  backend/
    app/
      ingest/            # zip/XML/PDF extraction, file typing
      schema_adapters/   # adapter interface + placeholder adapter + registry
      rules/             # rule engine (pure), rule loader, logic operators, AI backends
      models/            # pydantic domain models (NormalizedReport, Finding, ...)
      persistence/       # SQLAlchemy models + repositories
      exports/           # PDF (WeasyPrint) + CSV generation
      api/               # FastAPI routers
    tests/
  frontend/              # React + Vite + TypeScript + Tailwind
  rules/                 # seed/exported rule definition JSON files (versioned)
  schemas/               # schema definition/mapping files (versioned)
  samples/               # sample delivery zips (fabricated now, real one later)
  infra/                 # Dockerfile, deploy scripts, GCP setup
  docs/
    ROADMAP.md           # master phase checklist for Kevin
    INTEGRATION.md       # how to drop in real schema + rules (for future devs)
```

## Contract 1: Schema Adapter

Python interface. One adapter per schema version, selected via registry.

```python
class SchemaAdapter(Protocol):
    schema_version: str                                  # e.g. "PLACEHOLDER-0.1"
    def validate(self, raw: RawReport) -> list[StructuralError]: ...
    def normalize(self, raw: RawReport) -> NormalizedReport: ...
```

- `RawReport` = extracted contents of the delivery (XML tree, PDF ref, image manifest).
- `StructuralError` = code, human message, location. Rendered in their own UI section above rule findings.
- `NormalizedReport` = flat map of **field path → {value, source location (XPath / section ref), label}** plus report metadata. This is the only thing the rule engine ever reads.
- Ships with `PlaceholderAdapter` exposing 2–3 obviously fake fields (e.g. `placeholder.sample_text_field`) — every one marked `PLACEHOLDER` in code and UI.
- Real schema later = write one new adapter class + mapping file in `schemas/`, register it. UI, persistence, exports untouched.

## Contract 2: Rule Definitions & Engine

Rules are **data, stored in the database**, managed via Admin mode, import/exportable as JSON. Every save produces a frozen, hashed **ruleset version snapshot**; each run records the exact snapshot it ran against (reproducibility requirement).

```json
{
  "rule_id": "PLACEHOLDER-001",
  "category": "Placeholder Category",
  "description": "What is checked",
  "severity": "Warning",
  "enabled": true,
  "logic": { "type": "field_present", "field": "placeholder.sample_text_field" },
  "citation": null,
  "messages": { "appraiser": "coaching text", "reviewer": "audit text" }
}
```

- **Severity canon:** `HardStop` / `Warning` / `Advisory`. The README's alternate labels (Critical/Warning/Minor) are display labels mapped onto the same three levels — labels configurable, not a fourth level.
- **Logic types (declarative, v1):** `field_present`, `field_equals`, `field_in_set`, `numeric_range`, `regex_match`, `cross_field` (two fields + operator), `conditional` (if X then require Y), `ai` (prompt + output contract, runs through the AI backend).
- **Forward compatibility:** unknown top-level keys are preserved untouched. Unknown `logic.type` → rule is skipped and logged as a rule-execution error (`unsupported_logic`); the run continues.
- **Engine purity:** `evaluate(normalized_report, ruleset) -> RunResult(findings, rule_errors)`. No DB, no HTTP, no UI inside the engine. AI calls go through an injected backend interface so the engine stays testable with a stub.
- Per-rule exceptions are caught, recorded as rule-execution errors, and never halt the run.

### AI Backend Interface

```python
class AIBackend(Protocol):
    def evaluate(self, prompt: str, context: dict) -> AIResult: ...
```

Implementations: `StubBackend` (tests/offline), `GeminiAPIBackend` (dev, sample data only), `VertexAIBackend` (production, real reports). Selected by config; guardrail setting blocks `GeminiAPIBackend` when a run is flagged as real data.

## Findings & Reviewer Workflow

Finding fields: severity, category, rule_id, both message variants, offending value(s), location (field path + section ref), citation (shown only when supplied — never fabricated).

- Grouped by category, severity-sorted within, top-line counts. Clean pass → explicit "No issues found" + run metadata.
- **Appraiser mode:** coaching messages, Fix-it checklist (Hard Stops + Warnings only) with per-item checkboxes. Checkbox state persists and is visible to the reviewer.
- **Reviewer mode:** audit messages, per-finding note, verification per finding —
  - Hard Stop: *Resolved* / *Fail (return to appraiser)*
  - Warning: *Pass* / *Fail (return)* / *Conditional pass* (+ required comment)
  - Advisory: informational, acknowledgeable
  - Run-level sign-off state: `in_review` → `signed_off` | `returned`.
- **Mode is a render switch on one run payload.** Reviewer mutations gated server-side by role (role switcher header in beta; IAP identity later).

## Persistence (Postgres / SQLite)

Tables: `runs`, `structural_errors`, `findings` (incl. appraiser checkbox + reviewer status/note), `rule_errors`, `rules`, `ruleset_versions` (frozen snapshots), `ruleset_profiles` (client-based rule on/off + overrides), `audit_log` (reviewer actions, timestamps).

- **Nothing auto-deletes.** No hard-delete endpoints for runs. Rules are soft-deleted (disabled + archived).
- Every run stores: filename, SHA-256 hash, timestamps, schema version, ruleset version hash, profile, full findings, reviewer actions.
- Uploaded originals kept in Cloud Storage (prod) / `data/files` (dev), keyed by run id.

## API Surface (sketch)

```
POST /api/runs                      upload single file or zip (multi supported)
GET  /api/runs                      history w/ filter + search
GET  /api/runs/{id}                 full run payload (both message variants included)
POST /api/runs/{id}/findings/{fid}/check      appraiser checkbox
POST /api/runs/{id}/findings/{fid}/review     reviewer verdict + note
POST /api/runs/{id}/sign-off
GET  /api/runs/{id}/export?format=pdf|csv
GET/POST/PUT /api/admin/rules       CRUD + enable/disable
POST /api/admin/rules/import        JSON ruleset in
GET  /api/admin/rules/export        JSON ruleset out
GET/POST/PUT /api/admin/profiles    ruleset profiles
GET  /api/meta                      schema + ruleset versions
```

## Frontend

React + Vite + TypeScript + Tailwind. Pages: **Upload**, **Run detail** (mode switcher: Appraiser / Reviewer), **Batch view** (reviewer, multi-report), **History** (filter/search), **Admin** (rules table, plain-language rule editor form, profiles). Visual design pass happens at build time with the ui-ux-pro-max skill — direction: clean professional dashboard, unmistakable severity color coding, built for non-technical users, accessible.

## Exports

- **CSV:** one row per finding, stdlib writer.
- **PDF:** HTML template → WeasyPrint.
- Both carry full run metadata: filename, timestamp, schema version, ruleset version, profile, mode, reviewer, severity counts.

## Error Handling & Logging

- Structural errors: own section, never mixed with findings.
- Rule errors: captured per rule, run continues, stored + surfaced in Admin.
- App logs structured JSON → Cloud Logging in prod.

## Testing

- **Engine:** pytest golden tests — fixed normalized report + fixed ruleset → exact expected findings. Stub AI backend.
- **Adapters/Ingest:** fixture zips (valid, missing XML, corrupt zip, unexpected extras).
- **API:** httpx test client, including mode gating (reviewer endpoints reject appraiser role).
- **Frontend:** light component tests + one Playwright end-to-end (upload → findings → export).

## Build Phases (roadmap summary — full checklist in docs/ROADMAP.md at build time)

1. **Skeleton end-to-end (local):** contracts, pure engine, ingest (zip → XML/PDF/Images), **real XSD structural validation**, minimal adapter + handful of rules, minimal UI. Official GSE sample zip flows upload → findings.
2. **Real schema + ruleset:** `UAD36v13Adapter` from Appendix A-1, H-1 import pipeline (729 rules; auto-convert mechanical logic, flag the rest `needs_encoding`), engine runs seed ruleset against all three sample reports.
3. **Both modes:** findings UI, fix-it checklist, reviewer verification + sign-off.
4. **Admin mode:** rules CRUD, on/off, profiles, import/export, ruleset versioning, `needs_encoding` queue.
5. **Exports + history:** PDF, CSV, run history with filter/search, audit log.
6. **AI rule type:** backend interface, stub + Gemini + Vertex implementations, 1–2 live demo rules (e.g. boilerplate-commentary flag).
7. **GCP deploy:** Docker, Cloud Run, Cloud SQL, Cloud Storage, IAP — with step-by-step instructions written for a non-developer, plus master checklist.

Budget check: idle cost ~$12–20/mo → $300 covers the beta period comfortably, AI demo rules cost cents per run.

## Out of Scope (beta)

Real user accounts, SSO, notifications/email, editing reports (tool is read-only by definition), mobile app, multi-tenant isolation beyond ruleset profiles.
