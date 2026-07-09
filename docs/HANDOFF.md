# Handoff — Client Revision Rule Mining

**Last updated:** 2026-07-04
**Status:** Tasks 1–11 done and committed. Task 12 (real-data run) not started.

## What this is

Pipeline that mines client revision-request text (`RRR Export for QC tool.xlsx`, True Footage
Dropbox) into candidate QC rules, redundancy-checked against the live 729-rule set, reviewable
in Admin before promotion. Design + plan docs:

- Spec: `docs/superpowers/specs/2026-07-03-client-revision-rule-mining-design.md`
- Plan: `docs/superpowers/plans/2026-07-03-client-revision-rule-mining.md`

## Done (committed to `main`, NOT pushed to origin — 14 commits ahead)

| Task | What |
|---|---|
| 1 | `openpyxl` dependency |
| 2 | `backend/app/revision_mining/clean_split.py` — ported clean/split text preprocessing (no LLM, no network) |
| 3 | `backend/app/revision_mining/preprocess.py` — xlsx sheet-dedup + atomic item extraction |
| 4 | `CandidateRuleRow` table (`backend/app/persistence/tables.py`) |
| 5 | `CandidateRulesRepository` (`backend/app/persistence/candidate_rules_repo.py`) |
| 6 | `backend/app/revision_mining/redundancy_check.py` — deterministic exact_duplicate/overlaps/new verdict |
| 7 | Wired `candidate_rules_repo` into `backend/app/main.py` |
| 8 | Admin API: `GET/POST /api/admin/candidate-rules*` (list/get/approve/reject) in `backend/app/api/admin.py` |
| 9 | `backend/app/revision_mining/insert_candidates.py` — bulk-insert script with PII defense-in-depth scan + redundancy tagging |
| 10 | Frontend API client additions in `frontend/src/adminApi.ts` |
| 11 | "Client revisions" tab + `CandidateRulesPanel` in `frontend/src/AdminPanel.tsx` |

127 backend tests passing. Frontend type-checks clean (`npx tsc -b`, no errors).

## Not done: Task 12 — run the pipeline against the real export

This is operational, not code (see plan doc Task 12 for exact steps):

1. `extract_atomic_items()` against the real xlsx (local only — result contains PII, never commit/paste it).
2. Batch items (~150–250 each), dispatch subagents to mine themes — abstracted output only, no names/addresses/order numbers.
3. Classify each theme: Deterministic (verify field key exists in `schemas/uad36_field_manifest.json`) / AI / Not-yet-buildable.
4. Author draft candidate JSON (`CR-####` ids, `enabled: false`, `Advisory` severity default).
5. Run `python -m app.revision_mining.insert_candidates --input <file>`.
6. Spot-check in Admin → Client revisions tab.

**Not started this session because:** cost climbed to $61.39 by end of session — Task 12 is a
separate, likely-costly phase (real data volume + many subagent dispatches) better started fresh.

## Known pre-existing issues (NOT caused by this work — verified via `git stash` before/after)

- `backend/tests/test_admin.py::test_rules_seeded_from_h1_file` — expects `queue == 653`, actual `566`
- `backend/tests/test_admin.py::test_toggle_rule_changes_active_set_and_version` — same root cause
- `backend/tests/test_api.py::test_rules_log_written_and_downloadable` — expects `>= 600`

Likely stale since the "Encode H-1 conditional rules" commit (`b764654`) changed live rule counts
but these test assertions weren't updated. Not touched — out of scope for this plan.

## Notes for next session

- Branch strategy this session: directly on `main` (Kevin's explicit call, matches existing workflow).
- Nothing pushed to `origin/main` yet — 14 local commits ahead as of this handoff.
- GateGuard fact-forcing hook fires before every Bash/Edit/Write call — expect the same overhead
  next session unless Kevin changes it via his own launch config (not something Claude should
  disable itself — auto-mode classifier blocks that as a safety-weakening action).
- PII handling: the real RRR export contains borrower names (confirmed, e.g. an owner-of-record
  correction row). Theme mining routes through Claude Code directly (Kevin's explicit choice, not
  the `revision-request-parser` skill's consumer-API script) — keep all mined output abstracted,
  no PII in anything that reaches `candidate_rules`.
