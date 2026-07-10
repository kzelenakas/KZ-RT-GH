# Handoff — Collateral Risk Media Checks (Phase 1: Location/Adverse-Influence Proximity)

**Last updated:** 2026-07-10 (session 2)
**Status:** Tasks 1–6 done. **Nothing is committed to git yet** — a stale `.git/index.lock`
(dated Jul 9, no live git process) blocks `git add`/`git commit` from this app's sandboxed Bash
tool across two sessions now. This needs to happen from Kevin's own terminal — see "First thing
to do" below. Full test suite has been run; two real rule-encoding bugs were found and are NOT
yet fixed (see "Not done").

## What this is

Adds proximity-to-adverse-influence checks (airports, highways, high-voltage transmission lines,
commercial/industrial land use) to `collateral_risk_engine`, computed live per subject coordinate
against the public Overpass API (OpenStreetMap) — no national dataset stored locally, since scope
is national and the subject's address/coordinates are confirmed not NPI/confidential.

- Spec: `docs/superpowers/specs/2026-07-10-collateral-risk-media-checks-design.md`
- Plan: `docs/superpowers/plans/2026-07-10-collateral-risk-media-checks-plan.md`

Photo condition/damage detection and photo people/privacy detection (the other two asks from the
original request) are explicitly **not** in this phase — separate specs, separate CV-backend risk
review, per the design doc.

## Done (uncommitted — review before committing)

| File | Change |
|---|---|
| `collateral_risk_engine/poi.py` | New. Haversine distance + live Overpass API lookup (`nearest_distance_ft`), one query per category (`airport`, `highway`, `high_voltage`, `commercial_industrial`), network call injectable for tests. |
| `collateral_risk_engine/operators.py` | New `geo_proximity` operator, registered in `OPERATORS`. Resolves subject lat/long via the existing `resolve.py` helpers, calls `poi.nearest_distance_ft`, compares to `threshold_ft`. |
| `collateral_risk_engine/engine.py` | Bug fix: `evaluate()` did not previously check `rule.get("enabled")` at all — every rule with a registered operator ran regardless of its `enabled` flag. Added the check. This is a real behavior change for the existing 100-rule set too (any of them ever toggled `enabled: false` would previously have still fired) — worth confirming this is the intended semantics before merging. |
| `collateral_risk_engine/rules.json` | 4 new entries: `CR-101` (airport), `CR-102` (highway), `CR-103` (high-voltage), `CR-104` (commercial/industrial). All `enabled: false`, severity `Advisory`, `threshold_ft: 300`, `citation: null` — not in the approved `Collateral_Risk_Rules_100_2026-07-10.xlsx`, need Kevin's sign-off before enabling. |
| `collateral_risk_engine/test_geo_proximity.py` | New. Runnable script (matches `test_engine.py`'s pattern, no pytest required) — haversine sanity check, injected-fetch hit/miss, operator trigger/no-trigger, missing-coordinates case. |

## Important: verify these files before trusting them further

Mid-session, the sandbox's mounted view of these files (read via the Bash tool) lagged behind or
returned **torn/truncated reads** for files edited in place (`rules.json`, `operators.py`,
`engine.py`) — while newly-created files (`poi.py`, `test_geo_proximity.py`) synced immediately and
correctly. The Read tool (which reflects the real file) showed correct content throughout, and I
verified the logic by reconstructing the exact file contents in an isolated directory and running
the tests there — that passed cleanly. But I was never able to get a clean Bash-tool read of the
live `rules.json` to confirm byte-for-byte, and a `git status` check in the same Bash session
showed ~89 modified files repo-wide, including files this session never touched (Dockerfile,
`.gitignore`, XSD schema files, several `backend/app/*.py` files) — almost certainly a pre-existing
condition (prior uncommitted work, or a line-ending/mount artifact) and **not** something to
attribute to this session's changes, but it means git status/diff run via Bash in this project
isn't fully trustworthy either right now.

**First thing to do in the new session:** from a normal terminal (PowerShell, per this project's
own `docs/ROADMAP.md` convention — not this app's sandboxed Bash tool), run from the **repo root**
(`Revisions/`, not `collateral_risk_engine/` — see correction below):

```powershell
cd Revisions
python -c "import json; d = json.load(open('collateral_risk_engine/rules.json')); print(len(d['rules']), 'rules,', [r['rule_id'] for r in d['rules'][-4:]])"
python -m collateral_risk_engine.test_engine
python -m collateral_risk_engine.test_geo_proximity
```

Expect: rule count with `CR-101`–`104` at the end, and both scripts printing `OK`.

**Correction (found 2026-07-10, session 2):** the original version of this block had you `cd
collateral_risk_engine` then `python test_engine.py` directly — that fails with
`ModuleNotFoundError: No module named 'collateral_risk_engine'`, because running the script that
way puts `collateral_risk_engine/` itself on `sys.path`, and `test_engine.py`/`test_geo_proximity.py`
both do `from collateral_risk_engine import ...` (they need the *parent* of that folder on the
path). Confirmed fix: run from the repo root using `python -m collateral_risk_engine.<module>`
instead of `cd`-ing in and running the file directly. Both scripts printed `OK` this way; the
CR-033 rule showing up in `test_engine.py`'s finding list is the known inverted-logic bug (see
below), not a new problem.

## Session 2 — Tasks 5 & 6 (done)

- **Task 5 — wired into `backend/app`.** `backend/app/config.py` gets a guarded, idempotent
  `sys.path.insert(0, REPO_ROOT)` (the package has no packaging metadata and uvicorn runs with
  `--app-dir backend`, so the repo root was never importable otherwise). `backend/app/api/runs.py`'s
  `create_run()` now calls `collateral_risk_engine.evaluate(raw.xml_bytes)` after the existing H-1
  evaluation, adapts each finding dict into the backend `Finding` model (severity `Fatal`→`HardStop`,
  `Advisory`→`Advisory`, unrecognized falls back to `Advisory` — flagged below), and merges into
  `result.findings` only — `result.trace` is deliberately untouched (the rules-log CSV export has an
  existing test pinned to exactly 729 H-1-only rows). The whole call is wrapped in the same
  never-kill-the-run try/except pattern used for AI rules; failures record a `RuleError` instead of
  raising. New test: `backend/tests/test_collateral_risk_integration.py` (monkeypatches the Overpass
  fetch — zero real network calls in tests). Independently spec-reviewed and code-quality-reviewed;
  both passed.
- **Task 6 — ran the full suite.** `backend/tests/`: **133 total, 127 passed, 5 failed, 1 skipped.**
  All 5 failures are pre-existing / unrelated to the new wiring (confirmed by checking which files
  actually import `collateral_risk_engine` — only `runs.py`, `config.py`, and the new test do; the
  admin/meta/rules_repo code paths never touch it and fail identically with or without this change).
  No fixes were needed or made to the wiring itself.

## Not done / needs Kevin

- **Nothing committed.** `.git/index.lock` is stale (0 bytes, dated Jul 9 19:03, no live git
  process) and can't be removed from this app's sandbox (`rm`/`os.remove`/`sudo -n` all fail —
  no-new-privileges blocks sudo, and the file shows the same torn-read symptom as other mid-edit
  files in this sandbox: a bare `ls` on it inconsistently reports both "exists" and "no such file").
  **From Kevin's own terminal:**
  ```
  cd Revisions
  rm .git/index.lock
  git add backend/app/config.py backend/app/api/runs.py backend/tests/test_collateral_risk_integration.py
  git status   # confirm ONLY those 3 files are staged — do not git add -A
  git commit -m "Wire collateral_risk_engine into runs.py"
  ```
  Then separately review/commit the 5 collateral_risk_engine files + docs from session 1
  (`poi.py`, `operators.py`, `engine.py`, `rules.json`, `test_geo_proximity.py` + this handoff +
  the spec/plan docs) if not already done.
- **Two real rule-encoding bugs found, not fixed (out of scope for the wiring task, and not mine to
  silently patch):**
  - `CR-033` ("C6 condition rating without a 'subject to repairs' scope indicator") uses
    `field_in_set` with `allowed: ["C6"]`, which triggers when the value is **not** C6 — inverted
    from what the description wants. Fires on almost every report (confirmed: fires on the official
    `SF1_Appraisal_v1.4.zip` sample, whose subject is C4).
  - `CR-018` ("Reconciliation section present but no narrative...") checks for
    `VALUATION_RECONCILIATION_SUMMARY_DETAIL/ValuationCommentText` directly, but the SF1 sample has
    zero nodes there even with a fully populated reconciliation section — the narrative likely lives
    under a `VALUATION_COMMENTARY` category entry instead, same pattern `CR-041`/`CR-047` already use
    via `commentary_category_present`.
  - Both are `severity: "Fatal"` (→ `HardStop`) and now genuinely fire once the wiring is live —
    that's why `test_api.py::test_upload_sample_zip_end_to_end` and `::test_run_history_and_detail`
    currently fail. This is real signal working as designed, not a wiring bug — but it means those
    two tests will keep failing until `rules.json` is corrected. Decide whether to fix the rule logic
    or temporarily set both to `enabled: false` pending a fix.
- **Separately, pre-existing H-1 ruleset drift** (unrelated to this feature): `skipped` count in the
  rules-log is 566 vs. tests expecting `>=600`; `active_rule_count` is 163 vs. an expected 76;
  `needs_encoding` queue is 566 vs. an expected 653. All three are the same underlying drift,
  confirmed to have zero collateral_risk_engine involvement. Separate cleanup task.
- **Dockerfile doesn't `COPY collateral_risk_engine/`** into the production image. Since `runs.py`
  now does a hard top-level `import collateral_risk_engine`, **the built container will fail to
  start** until this is added. Real gap, not fixed (deploy/packaging decision, out of scope here).
- Rule IDs `CR-101`–`104` are still provisional — confirm no collision before committing (still
  clean as of this session).
- The ~90 files `git status` shows as modified repo-wide: confirmed this session (via
  `git diff --ignore-all-space`) to be **CRLF line-ending noise only, zero content changes** — not
  a real problem, just noisy `git status` output. Safe to ignore when scoping the commit.

## Notes for next session (superseded by Session 3 below for Phase 2/3 status)

- Kevin's explicit calls this round, for context: national scope → no stored dataset, live Overpass
  queries instead; subject address/coordinates are not NPI (see memory:
  `subject-address-not-npi.md`); flat 300 ft threshold across all 4 categories (a known v1
  simplification, noted in the spec's open questions).
- Photo condition/damage and photo people/privacy detection are still fully unscoped — no design
  work done on them yet. Don't start those without a fresh brainstorming pass; they carry a real
  CV-backend privacy decision the location work didn't need.

## Session 3 (2026-07-10) — Phase 1 closed out, Phase 2/3 built

Kevin cleared both gates directly this session: reviewed the Phase 1 status above and said "close
out Phase 1 first," then on Phase 3 said **"implement both. This is meant to prompt the appraiser
to redact or blur photos."**

### Phase 1 — fixed

| File | Change |
|---|---|
| `collateral_risk_engine/rules.json` | `CR-033` was inverted (`field_in_set` with `allowed: ["C6"]` triggers when NOT C6 — fired on almost every report). Rewritten as `conditional` + `commentary_category_present`: triggers only when condition **is** C6 **and** no `PropertyValuationConditionalConclusionType=SubjectToRepair` is present under `VALUATION_RECONCILIATION_SUMMARY/VALUATION_CONDITIONS/VALUATION_CONDITION`. Field path confirmed against the UAD 3.6 XSD and the real `SF1_Appraisal_v1.4.xml` (which has exactly this element, value `SubjectToRepair`, sibling of `VALUATION_RECONCILIATION_SUMMARY_DETAIL`). `CR-018` pointed at a field that never exists (`VALUATION_RECONCILIATION_SUMMARY_DETAIL/ValuationCommentText`) — repointed to the real reconciliation-narrative field, `VALUATION_RECONCILIATION_DETAIL/ValuationReconciliationSummaryCommentDescription` (confirmed present and populated in the sample; MISMO XSD documents it as exactly "a free-form text field used to describe or reconcile the different property valuation methods"). |
| `Dockerfile` | Added `COPY collateral_risk_engine collateral_risk_engine` to the runtime stage — it was missing, so the built container would have crashed on `import collateral_risk_engine` in `runs.py`/`config.py`. |

**Verification note — sandbox bash-mount bug, not a code problem.** This session's Bash tool shows
a persistent stale/torn view of every file edited in place this session (`rules.json`, `Dockerfile`,
`operators.py`, `engine.py`, `__init__.py`) — `wc -c`/`json.load` see content frozen mid-write, while
the Read tool (which reflects the real file) is correct throughout. Same symptom the Session 2
handoff above already documented for `rules.json`/`operators.py`/`engine.py`, now also hit on
`__init__.py` and confirmed to affect full-file rewrites too, not just patches. Worked around by
reconstructing the exact (Read-confirmed) file contents in an isolated directory
(`outputs/cr_verify/`) and running real Python there:
- CR-033/CR-018 fixes: verified against the real SF1 sample (no false trigger) and 4 synthetic edge
  cases (C6-with-repair, C6-without-repair, C4, blank narrative) — all passed as expected.
- Phase 2/3 wiring (below): verified end-to-end (`evaluate_photos`, both operators, the `enabled`
  honesty check) — all passed as expected.

**From your own terminal**, confirm cleanly (same pattern as Session 2's correction — run from repo
root, `python -m`, not `cd` + direct script run):
```powershell
cd Revisions
python -c "import json; d=json.load(open('collateral_risk_engine/rules.json')); print(len(d['rules']), 'rules'); print([r['rule_id'] for r in d['rules'][-7:]])"
python -m collateral_risk_engine.test_engine
python -m collateral_risk_engine.test_geo_proximity
python -m collateral_risk_engine.test_photo
```
Expect: 107 rules, last 7 IDs `CR-101`–`CR-107`, and all three scripts printing `OK`. **Correction:**
`test_engine.py`'s fixture doc uses condition `C9` and has no C6 condition or reconciliation-narrative
field — it never exercises CR-033/CR-018, so its `OK` output does not confirm those fixes (an earlier
version of this doc claimed it did; that was wrong). The real check is in `backend/tests/test_api.py`:
`test_upload_sample_zip_end_to_end` and `test_run_history_and_detail` both assert
`payload["counts"]["HardStop"] == 0` against the real SF1 sample — that's the exact assertion that was
failing before this session's fix (CR-033 fired Fatal on nearly every report including SF1; CR-018
fired Fatal because its field never existed). Run:
```powershell
cd Revisions\backend
pytest tests/test_api.py::test_upload_sample_zip_end_to_end tests/test_api.py::test_run_history_and_detail -v
```
Both should now pass with `HardStop == 0`.

### Phase 2/3 — built this session

Design doc: `docs/superpowers/specs/2026-07-10-collateral-risk-photo-checks-design.md` — **read the
"Scope honesty" section before enabling anything.** Short version: Phase 3 (photo people/privacy) is
built for real — local OpenCV face detection, flags a photo so the appraiser redacts/blurs it, never
auto-edits anything. Phase 2 (photo condition/damage) as originally asked is genuinely a hard CV
problem needing a model decision that wasn't made; what actually shipped is honestly-scoped **photo
quality** checks (too dark / too blurry to evaluate), not damage detection. Don't let the rule
category name ("Photo Quality") get conflated with real condition/damage detection when presenting
this to anyone.

| File | Change |
|---|---|
| `collateral_risk_engine/photo.py` | New. `detect_faces()` (OpenCV Haar cascade, bounding boxes only, no recognition), `assess_quality()` (classical blur/darkness heuristics, no ML). |
| `collateral_risk_engine/operators.py` | Two new operators: `photo_face_detected`, `photo_quality_flag`. |
| `collateral_risk_engine/engine.py` | New `evaluate_photos(images, rules=None)` — same shape/honesty as `evaluate()`, loops (rule × photo) instead of (rule × document). |
| `collateral_risk_engine/__init__.py` | Exports `evaluate_photos`. |
| `collateral_risk_engine/rules.json` | 3 new entries: `CR-105` (face detected — redact/blur prompt), `CR-106` (too dark), `CR-107` (too blurry). All `enabled: false`, `severity: Advisory`, `citation: null` — same not-yet-approved status as every other new rule this project has shipped. |
| `collateral_risk_engine/test_photo.py` | New. Runnable script, same pattern as `test_geo_proximity.py`. **Honesty note:** the real face-detection true-positive path is verified via a mocked/injected result, not a real face photo — none is available in this sandbox. Everything else (quality thresholds, no-face case, undecodable-bytes safety, `enabled` honesty) is verified against real synthetic images and real code. |
| `backend/app/models/report.py` | `RawReport` gets `images: dict[str, bytes]` (filename → raw bytes) alongside the existing `image_filenames` (names only). |
| `backend/app/ingest/extractor.py` | `_extract_zip` now reads and keeps the actual photo bytes (was discarding them, keeping only filenames). |
| `backend/app/api/runs.py` | `create_run()` calls `collateral_risk_engine.evaluate_photos(raw.images)` after the existing XML-rules call, same never-kill-the-run try/except, merges into `result.findings`. |
| `collateral_risk_engine/requirements.txt`, `backend/requirements.txt` | Added `opencv-python-headless>=4.10` and `numpy>=1.26` to both — missed originally, caused `ModuleNotFoundError: No module named 'numpy'` when Kevin ran `test_photo.py`. Duplicated across both files matching the existing `lxml` pattern (Dockerfile only installs `backend/requirements.txt`). |

**Not done / needs Kevin:**
- **Face-detection accuracy is unvalidated against real property photos** — only synthetic fixtures
  and a mocked true-positive exist in this sandbox. Run a batch of real (appropriately handled) photos
  through it before enabling `CR-105`.
- **Photo quality thresholds** (`DARK_BRIGHTNESS_THRESHOLD=40`, `BLUR_VARIANCE_THRESHOLD=100` in
  `photo.py`) are first-pass defaults, untuned against this project's real photo corpus.
- **True photo condition/damage detection is still unbuilt** — needs Kevin to source/approve a
  trained model, or explicitly sign off on sending real property photos to an external vision API
  (same GLBA-guardrail decision as `QC_DATA_CLASS=real` in `backend/app/main.py`). Don't let anyone
  assume `CR-106`/`CR-107` cover this — they don't.
- **Auto-blur/redact convenience feature** (generate a redacted preview image) is a plausible
  fast-follow on `CR-105` but wasn't built — needs its own read-only-principle check-in with Kevin
  first (see design doc open question 1).
- No integration test added yet for the `runs.py` photo-wiring specifically (Phase 1's
  `test_collateral_risk_integration.py` pattern would be the template) — the isolated end-to-end
  verification above covers `evaluate_photos()` itself but not the FastAPI route.

### Commit — same git-lock situation as Session 2

Still can't commit from this sandbox (same stale `.git/index.lock` issue documented above, plus the
bash-mount torn-read bug on top of it now). **From your own terminal:**
```powershell
cd Revisions
rm .git/index.lock   # if still stale/present
git status           # review everything before staging -- do not git add -A
git add collateral_risk_engine/rules.json Dockerfile
git add collateral_risk_engine/photo.py collateral_risk_engine/operators.py collateral_risk_engine/engine.py collateral_risk_engine/__init__.py collateral_risk_engine/test_photo.py
git add collateral_risk_engine/requirements.txt backend/requirements.txt
git add backend/app/models/report.py backend/app/ingest/extractor.py backend/app/api/runs.py
git add docs/superpowers/specs/2026-07-10-collateral-risk-photo-checks-design.md docs/HANDOFF-collateral-risk-geo.md
git status           # confirm only the above are staged
git commit -m "Fix CR-033/CR-018 rule bugs, add Dockerfile COPY, build Phase 2/3 photo checks"
```
Then separately handle Session 1/2's still-uncommitted files if not already done (see the file list
higher up in this doc).
