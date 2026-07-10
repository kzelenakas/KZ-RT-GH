# Collateral Risk Media Checks — Phase 2/3 (Photo Quality & Photo People/Privacy) — Design

**Date:** 2026-07-10
**Status:** Draft — built same session per Kevin's explicit go-ahead (see decisions below)
**Relates to:** `docs/superpowers/specs/2026-07-10-collateral-risk-media-checks-design.md` (Phase 1,
location/adverse-influence proximity — shipped, uncommitted), `docs/HANDOFF-collateral-risk-geo.md`
**Scope:** Phase 2 (photo quality flags) and Phase 3 (photo people-detection redaction prompt).

## Why this spec exists now

The Phase 1 plan and design doc both explicitly gated Phase 2/3 behind Kevin reviewing Phase 1
results, and Phase 3 additionally behind "explicit sign-off on backend before any code is written"
given it touches photos of people. Both gates were cleared this session:

- Phase 1 status reviewed with Kevin directly (uncommitted work, two rule bugs, Dockerfile gap —
  all fixed this session, see updated `docs/HANDOFF-collateral-risk-geo.md`).
- Kevin's explicit instruction on Phase 3: **"implement both. This is meant to prompt the appraiser
  to redact or blur photos."** — i.e. detection exists to trigger a human redaction step, not to
  store, transmit, or expose identities anywhere. This directly shapes the design below.

## Scope honesty (read this before enabling anything)

Two very different problems got bundled under "Phase 2/3" in the original ask:

1. **Photo people/privacy detection** (Phase 3) — well-scoped, buildable locally today: does this
   photo contain a detected face? Prompts redaction. Built for real this session.
2. **Photo condition/damage detection** (Phase 2) — the original ask ("property condition/damage
   visible in photos") is a genuinely hard computer-vision problem (roof damage, water staining,
   structural cracks, deferred maintenance) that needs either a specialized trained model or a
   vision-capable LLM call. Neither exists in this project, and building/training a real damage
   classifier is not something to fabricate in one session — doing so risks exactly the kind of
   overclaimed, unreliable finding that would actively hurt collateral-risk review quality (USPAP
   priority #1).

   **What Phase 2 actually ships this session is narrower and honestly named: photo *quality* checks**
   (too dark / too blurry to be evaluated), using classical, local, deterministic image processing
   — no ML model, no external API, no claim of detecting damage or condition. This is real signal
   (an unusable photo is a real QC problem — appraiser should retake it) but it is **not** damage
   detection. Rule descriptions say exactly this. True condition/damage detection is flagged below
   as a follow-on that needs either (a) a trained model Kevin sources/approves, or (b) explicit
   sign-off to send real property photos to an external vision API (mirrors the existing GLBA
   guardrail in `backend/app/main.py` blocking the Gemini dev-key backend for `QC_DATA_CLASS=real`).

## Decisions made

| Decision | Choice | Why |
|---|---|---|
| Face-detection backend | OpenCV Haar cascade (`haarcascade_frontalface_default.xml`), bundled with the already-installed `opencv-python-headless` dependency | Fully local, no network call, no new heavy dependency (already in the sandbox), no third party ever sees a property photo. Matches Phase 1's "no third-party sees real photos" default. |
| What "detection" means for redaction | Bounding-box face detection only — no face recognition, no identity matching, no storage of biometric templates. Detects presence of a face-shaped region, nothing more. | Kevin's stated purpose is a redact/blur *prompt*, not identification. Minimizes privacy surface to exactly what's needed. |
| Photos-of-photos (framed picture on a wall) | Not special-cased — a face in a framed photo triggers the same detector the same way a live photo would. This is correct for the stated purpose: both need redaction consideration before delivery. | Haar cascade detects face-shaped pixel patterns regardless of whether the "camera" is photographing a person or a photo of a person — this is a feature here, not a bug. |
| Does the tool auto-redact/blur? | **No.** Detection produces a finding (photo flagged, "contains a detected face — review before delivery"). Actual blurring/redaction stays a manual appraiser action outside the tool. | Matches the tool's foundational, repeatedly-stated design principle (root `README.md`): **read-only**, never edits/rewrites/repairs anything it reviews — only flags. Auto-redacting would silently modify the photo, which is exactly what this tool promises never to do. An optional "generate a redacted preview" convenience export is a plausible future add-on, not built here — see open questions. |
| Photo condition/damage detection (original Phase 2 ask) | **Not built.** Replaced with honestly-scoped "photo quality" checks (blur, darkness) using classical CV, no model. | See "Scope honesty" above — building a fake damage detector would be worse than not building one. |
| Where the new logic lives | `collateral_risk_engine/photo.py` (new), mirrors `poi.py`'s pattern (pure functions, one purpose, local import from `operators.py` so callers that never trigger a photo rule don't pay for `cv2`/`PIL` imports) | Same package-boundary discipline as Phase 1. |
| Rule status on ship | `enabled: false`, same as every other new candidate rule in this ruleset | Consistent with the project's repeated, explicit rule (root `README.md`): never ship a new rule live without Kevin's review of wording/thresholds, regardless of whether the underlying feature was approved. Feature approval and rule-wording approval are different gates. |
| Severity | Advisory | A flag for appraiser/reviewer action, not an automated valuation or compliance conclusion — same framing as every Phase 1 rule. |

## Data flow (new plumbing required)

Today, `backend/app/ingest/extractor.py` only reads image **filenames** out of the delivery zip
(`RawReport.image_filenames`) — it discards the actual photo bytes. Neither photo phase can work
without the bytes, so this phase adds that plumbing:

```
Zip upload → extractor.extract()
                 ├─ xml_bytes (existing)
                 ├─ image_filenames (existing)
                 └─ images: dict[str, bytes]  (NEW — actual photo bytes, Images/ folder only)
                                ↓
                 collateral_risk_engine.evaluate(xml_bytes)         (existing, Phase 1)
                 collateral_risk_engine.evaluate_photos(images)     (NEW — Phase 2/3)
                                ↓
                      merged Findings → RunResult (existing display/export/persistence)
```

- **`backend/app/models/report.py`**: `RawReport` gets `images: dict[str, bytes] = {}` (filename →
  raw bytes, `Images/` folder only, same filter `extractor.py` already applies for
  `image_filenames`).
- **`backend/app/ingest/extractor.py`**: `_extract_zip` reads each image's bytes via `zf.read(name)`
  alongside the existing filename collection — no new zip-parsing logic, just retaining what's
  already being read past.
- **`collateral_risk_engine/photo.py`** (new, pure functions):
  - `detect_faces(image_bytes: bytes) -> list[dict]` — OpenCV Haar cascade, returns one dict per
    detected face region (`{x, y, w, h}` in pixels), empty list if none/undecodable.
  - `assess_quality(image_bytes: bytes) -> dict` — returns `{is_dark: bool, is_blurry: bool,
    mean_brightness: float, laplacian_variance: float}` via classical thresholds (documented in
    the module, tunable, no ML).
- **`collateral_risk_engine/operators.py`**: two new operators, `photo_face_detected` and
  `photo_quality_flag`, following the existing `Finding` contract (`triggered`, `values`). Both
  take a single image's bytes (the photo-evaluation loop in `engine.py` calls the operator once per
  photo, unlike the XML operators which see the whole document once).
- **`collateral_risk_engine/engine.py`**: new `evaluate_photos(images: dict[str, bytes], rules=None)
  -> list[dict]` — loops rules with `logic.type` in `{photo_face_detected, photo_quality_flag}`
  across every image, same `enabled` check as `evaluate()`, one finding per (rule, photo) hit with
  the photo filename in `values["photo"]`.
- **`collateral_risk_engine/rules.json`**: 3 new entries — `CR-105` (photo contains a detected
  face), `CR-106` (photo too dark to evaluate), `CR-107` (photo too blurry to evaluate). All
  `enabled: false`, `severity: Advisory`, `citation: null` (not fabricated).
- **`backend/app` wiring**: `runs.py`'s `create_run()` calls `collateral_risk_engine.evaluate_photos
  (raw.images)` alongside the existing `evaluate(raw.xml_bytes)` call, same never-kill-the-run
  try/except, merges into `result.findings`.

## USPAP / privacy framing

- Read-only principle holds: photo findings are flags, never automatic edits to the delivery.
- No biometric data (face embeddings, identity matches) is ever computed, stored, or transmitted —
  only "a face-shaped region exists at these pixel coordinates in this photo," discarded after the
  finding is produced.
- No property photo is ever sent to a third party for either phase — both run entirely inside the
  existing backend process using already-vendored, offline libraries.

## Open questions (block "enabled: true", do not block building)

1. **Auto-blur/redact convenience feature.** Kevin's phrasing ("prompt the appraiser to redact or
   blur") is satisfied by the flag alone, but a "generate a redacted preview image" button is a
   plausible fast-follow. Not built this session — would need its own read-only-principle review
   (it would be *generating* a new derived image, not editing the original, so likely fine, but
   Kevin should confirm before it's built).
2. **True photo condition/damage detection** (the original Phase 2 ask) is unbuilt. Needs Kevin to
   either source/approve a trained model, or explicitly sign off on sending real property photos to
   an external vision API (GLBA-guardrail decision, mirrors `QC_DATA_CLASS=real` gating already in
   `backend/app/main.py`). Flagging this clearly rather than silently shipping a feature that
   doesn't do what its name implies.
3. **Face-detection accuracy on real property photos** hasn't been validated against real-world
   interior/exterior appraisal photography (angle, lighting, distance) — only against synthetic
   test fixtures in this sandbox (no real face images available here). Kevin should run this against
   a batch of real (but appropriately handled) sample photos before enabling `CR-105`.
4. **Photo quality thresholds** (darkness/blur cutoffs in `photo.py`) are first-pass defaults, not
   tuned against this project's actual photo corpus — expect to revisit after Phase 2 runs against
   real volume, same caveat Phase 1 gave its flat 300 ft threshold.

## Success criteria

- [ ] `RawReport.images` carries real photo bytes from zip uploads.
- [ ] `detect_faces` and `assess_quality` implemented and unit-tested in `collateral_risk_engine`.
- [ ] `photo_face_detected` and `photo_quality_flag` operators implemented and unit-tested.
- [ ] 3 new rules present in `rules.json`, `enabled: false`, no fabricated citations.
- [ ] `collateral_risk_engine.evaluate_photos()` implemented and unit-tested.
- [ ] `backend/app` `/api/runs` calls `evaluate_photos()` and merges findings, wrapped in the same
      never-kill-the-run guard as the Phase 1 wiring.
- [ ] Kevin reviews and enables the rules he approves from Admin, same workflow as Phase 1.
