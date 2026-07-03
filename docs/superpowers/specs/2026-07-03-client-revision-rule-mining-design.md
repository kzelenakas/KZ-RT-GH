# Client Revision Rule Mining — Design

**Date:** 2026-07-03
**Status:** Draft — awaiting user review
**Source input:** `RRR Export for QC tool.xlsx` (True Footage Dropbox — kevin.zelenakas), 3 sheets
**Relates to:** `ROADMAP.md` Stage F4 ("Trend review — revision-pattern analysis feeds coaching, proves ROI")
**Scope:** Subsystems 1–4 only (mine → classify → author → redundancy-check). Subsystem 5
(repeatable engine/app, scheduled re-runs, trend dashboard) is a follow-on spec once this
pipeline has run once successfully.

## Decisions Made During Brainstorming

| Decision | Choice | Notes |
|----------|--------|-------|
| AI routing for theme mining | Claude Code (this session), not a script with a raw Anthropic API key | The installed `revision-request-parser` skill's categorization step uses `scripts/config.json` with a consumer API key — that bypasses the GLBA guardrail this project already committed to ("borrower data can only route through company-controlled Vertex AI, never a consumer API," per `ROADMAP.md` Stage E). Kevin explicitly chose to process via this chat session instead. |
| Candidate rule storage | New `candidate_rules` table in the same DB as the live `rules` table | Reuses existing persistence layer, engine, and versioning. Not a separate standalone file/DB. |
| Frequency threshold | 3+ occurrences to become a draft candidate rule | Matches the existing `revision-pattern` skill's threshold for flagging a recurring (non-idiosyncratic) issue. |
| Draft rule enablement | All candidate rules start `enabled: false`, severity defaults to `Advisory` | No candidate rule fires against a real report until a human reviews and toggles it on in Admin — mirrors the existing `needs_encoding` review workflow. |
| Rule ID namespace | `CR-####` prefix | Avoids collision with the existing `UAD####` (H-1-sourced) IDs; makes provenance obvious at a glance. |
| Citation field | `"True Footage client revision pattern, N occurrences, [date range]"` | Never a fabricated GSE citation — this is an honestly-sourced internal citation, distinct from H-1's GSE citations. |

## Data Found During Investigation

- Source file has 3 sheets: `APR-preClean-split-C` (1,918 rows), `Copy of Q1-Master` and
  `Copy of CQ2-Master` (2,776 non-blank rows each) — the two "Master" sheets are **byte-identical**
  (verified by content hash). Effective unique data = `APR-preClean-split-C` + one Master copy
  ≈ 4,694 rows.
- Each row is a single free-text `REVISION REQUEST` cell — no appraiser/date/category columns.
  Often multiple bundled action items per cell, inconsistent formatting, some rows contain
  borrower names / owner-of-record details (confirmed PII present).
- This shape matches the installed `revision-request-parser` skill's model (clean → split →
  categorize), not the `revision-pattern` skill's clean-CSV model.
- The live 729-rule set (`rules/h1_rules.json`) uses UAD-schema-section categories (Site, Sales
  Comparison Approach, Assignment Information, etc.) and 5 logic types today: `field_present` (62),
  `regex_match` (13), `field_in_set` (1), `numeric_range` (4), `conditional` (83). `ai` logic type
  is implemented in the engine but has **zero live rules** currently — this project will be the
  first to use it.
- The parser skill's 14-category taxonomy (Subject Identification, Contract Analysis, ... Reconciliation)
  is client-revision-oriented and complements, rather than replaces, the rule set's UAD-section
  categories — used for theme grouping, not as the rule's `category` field.

## Pipeline

### Stage 1 — Preprocess (local, deterministic, zero LLM calls)

- Load `APR-preClean-split-C` + one copy of the Master sheet (dedupe the identical second copy).
- Reuse `revision-request-parser`'s clean + split logic (`scripts/process_revisions.py --no-categorize`
  path, or port the relevant functions directly) to strip email/tracking boilerplate and split
  bundled multi-item cells into atomic action items. Addresses are protected from being split
  (per that skill's existing rule).
- Output: a local intermediate file (atomic action items, no LLM involvement, nothing transmitted
  anywhere). This step never sees a network call.

### Stage 2 — Theme mining (Claude Code, batched fan-out)

- Split atomic items into batches (~150–250 items each, sized to stay well within a single
  agent turn's comfortable context).
- Spawn parallel subagents (fan-out pattern), each given one batch. Each subagent's job: cluster
  its batch into candidate themes and return **abstracted pattern descriptions only** — e.g.
  "narrative does not analyze adjacency to a external land use (house of worship, commercial,
  etc.) noted in map/aerial imagery" — with a count and the likely UAD section. **No borrower
  names, addresses, or order numbers are to appear in a subagent's output**; that's the PII
  containment boundary — raw text is read once per batch, never re-emitted verbatim.
- A merge pass consolidates all batch outputs into one ranked master theme list (dedup near-
  duplicate themes across batches via semantic similarity, not just string match).

### Stage 3 — Rule-ability classification (per theme, threshold: 3+ occurrences)

For each theme above the frequency bar, classify:
- **Deterministic (XML rule)** — maps to a specific field in `schemas/uad36_field_manifest.json`
  with a check expressible as `field_present` / `regex_match` / `field_in_set` / `numeric_range` /
  `conditional`. The field key is verified against the manifest before authoring — never invented.
- **AI rule** — requires judgment on narrative/analysis quality that no discrete field captures
  (e.g. "did the report analyze the impact of X on marketability/value" — this is exactly the
  shape of theme seen repeatedly in the sample rows). Authored as `logic.type: "ai"` with a
  `prompt` and target `fields`.
- **Not yet buildable** — needs engine capability that doesn't exist yet (comparable-scoped
  iteration, cross-field date comparisons, etc. — the same gaps already logged in `INTEGRATION.md`'s
  needs_encoding notes). These are recorded with a reason, not forced into a bad rule, and roll
  up into the Stage H backlog already in `ROADMAP.md`.

### Stage 4 — Rule authoring → `candidate_rules` table

- Each theme that classifies as Deterministic or AI becomes one draft row, same JSON shape as
  `h1_rules.json` entries (`rule_id`, `category`, `description`, `severity`, `logic`, `citation`,
  `messages`), plus new bookkeeping fields: `source: "client_revision"`, `occurrence_count`,
  `first_seen`/`last_seen` (from the export's implicit date range if determinable), `theme_id`.
- `enabled: false`, `severity: "Advisory"` by default (per decision table above) — a human
  changes both when promoting a rule.
- Coaching (`messages.appraiser`) and audit (`messages.reviewer`) text both drafted, in the
  same "what/why/how" tone as existing rules.

### Stage 5 — Redundancy check (separate pass/agent)

- A second pass compares every draft candidate against the full live rule set (`h1_rules.json` +
  `seed_rules.json`, all 729+ rules including the disabled `needs_encoding` ones) on two axes:
  field-key overlap and description/semantic similarity.
- Each candidate gets tagged: `exact_duplicate` (an equivalent live rule already exists — excluded
  from promotion, logged for visibility only), `overlaps` (partially covered by an existing rule —
  flagged for merge/human decision), or `new` (no existing coverage).

## Data Model

New table `candidate_rules` (same DB as `rules`, via existing SQLAlchemy `persistence/` layer).
Column names below are placeholders illustrating structure, not real data:

```
id, rule_id (e.g. "CR-0001"), category, description, severity, enabled,
logic (JSON), citation, messages (JSON),
source ("client_revision"), theme_id, occurrence_count,
date_range_start, date_range_end,
redundancy_verdict (exact_duplicate | overlaps | new), redundancy_notes,
review_status (pending | approved | rejected | edited), reviewed_by, reviewed_at,
created_at
```

Admin UI gets a new tab (styled like the existing "Needs encoding" tab): list candidates sorted
by occurrence count, show theme text + redundancy verdict + proposed rule JSON, with
Approve (copies into live `rules` table, still `enabled: false` until separately toggled on) /
Reject / Edit actions.

## Testing

- Port/adapt clean+split functions with unit tests against synthetic examples matching the
  observed real-row patterns (bundled-item splitting, boilerplate stripping) — no PII in test
  fixtures.
- Pipeline-level test: run against a small fixed synthetic batch, assert no `HardStop` severity
  is ever auto-generated, no `field` key is referenced that's absent from the manifest, and an
  intentionally-duplicated theme gets caught by the redundancy check.
- Defense-in-depth PII scan: before any `candidate_rules` insert, scan the `description`/`citation`/
  `messages` text for name-like patterns as a guard against a theme description accidentally
  carrying PII forward from Stage 2.

## Explicitly Deferred (Subsystem 5 — separate future spec)

- Wrapping Stages 1–5 into a repeatable job (CLI command or Admin "Run revision mining" button)
  that accepts a new export file, re-runs the pipeline, and dedupes against previously-seen themes
  across runs.
- Trend dashboard tying candidate-rule generation back into `ROADMAP.md` Stage F4 (which rules
  fire most, which themes are increasing) — ties revision-pattern output to the QC app's own
  finding data over time.
