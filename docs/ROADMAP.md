# UAD 3.6 QC — Master Roadmap, Checklist & Step-by-Step Instructions

**Where you are:** the app is fully built and tested (81 automated tests passing). Everything below
is what happens *from here*: demo it, deploy it to company GCP, put real reports through it, and
grow the rule set. Every step is written to be followed exactly — no developer experience assumed.

All commands run in **PowerShell**, from the project folder:
`C:\Users\kzele\Claude Cowork\Projects\Revisions`
(Open it in PowerShell: right-click the folder in File Explorer → "Open in Terminal".)

---

## STAGE A — Run it locally (today, ~5 minutes)

**Goal:** see the whole thing work on your own PC. This is also your c-suite demo environment.

- [ ] **A1. Start the app.**
  ```powershell
  .\dev.ps1
  ```
  First line builds the screen layouts (~10 seconds), then the window stays busy — that means
  the server is running. Leave it open.
- [ ] **A2. Open the app.** Browser → http://localhost:8000
- [ ] **A3. Upload a sample.** Click the file chooser → pick
  `Sample reports\SF1_Appraisal_v1.4.zip`. Expect: metadata bar (schema + ruleset versions),
  three count boxes, green **"No issues found"**.
- [ ] **A4. See a failure.** Upload `SF3` and `Condo2` too (also clean). To see findings fire,
  go to **Admin** → search `UAD1008` (latitude) → toggle it ON → re-upload SF1 if the sample
  lacks that field, or simpler: ask me to generate a "broken" demo zip — say the word.
- [ ] **A5. Tour the three modes** (buttons top-right):
  - **Appraiser** — coaching view; findings have checkboxes (fix-it checklist).
  - **QD Reviewer** — same findings with citations, verdict buttons, note field,
    sign-off bar (Sign off / Return to appraiser), rule-error panel.
  - **Admin** — 729 rules; tabs All / Enabled / **Needs encoding** (the 566 waiting for logic);
    search box; ON/OFF toggles; Edit forms; **Client profiles** tab; Export/Import rules buttons.
- [ ] **A6. Export.** With a run open, click **PDF** and **CSV** in the metadata bar. Open both —
  metadata (file, hash, timestamp, schema version, ruleset version, mode, reviewer, counts) is on every export.
- [ ] **A7. Stop the app** when done: press `Ctrl+C` in the PowerShell window.

**If the app errors after any future code update:** delete the folder `backend\data` and restart —
the local dev database rebuilds itself (rules re-seed automatically). Nothing important lives there.

---

## STAGE B — C-suite demo (before the meeting, ~30 minutes prep)

**Goal:** a demo that lands the pitch: *real GSE schema, real GSE rules, working QC pipeline, $12–20/month to run*.

- [ ] **B1. Rehearse the flow once:** upload → clean pass → switch modes → Admin queue → export PDF.
- [ ] **B2. Prepare one "dirty" report** so findings fire live (a sample zip with a blanked city +
  bad ZIP code — ask me to generate `samples\SF1_broken_demo.zip` for you).
- [ ] **B3. Talking points that matter to executives:**
  - Runs the **official GSE rule set** (Appendix H-1, 729 rules) against the **official UAD 3.6 schema** — not homemade rules.
  - **163 rules live today; 566 queued** with GSE's exact wording preserved — the growth path is data entry + review, not a rebuild.
    (2026-07-03: added a `conditional` logic type — "if FieldA = X, require FieldB present" — which auto-encoded 83
    more rules plus 4 simple numeric-bound rules, up from the original 76.)
  - One codebase, three audiences (appraiser self-check / QD audit / admin) — the appraiser fixes issues **before** delivery.
  - Client-specific rulesets (profiles) already work — lender customization is a selling point.
  - Every run records the exact schema + ruleset version — **reproducible and audit-defensible**.
  - AI rules are architected in with a **GLBA guardrail** — borrower data can only route through company-controlled Vertex AI, never a consumer API.
  - Beta hosting cost: **$12–20/month**. The $300 budget covers a year.
- [ ] **B4. The ask:** company GCP project from IT (Stage C prerequisite) + headcount/time to encode the remaining rules (Stage F).

---

## STAGE C — Deploy to company GCP (~1 hour total, mostly waiting)

**Goal:** the app running at a private URL, behind Google login, on company infrastructure.

### C-0. Prerequisite — the ask to IT (do this first; it gates everything)

- [x] **C0.1.** Email IT/security. Request:
  1. A **GCP project** (suggest name `uad36-qc-beta`) with **billing enabled**.
  2. Your company Google account granted the **Editor** role (or Owner) on that project.
  3. Mention: the app will hold GLBA-protected borrower data, which is *why* it must be
     company-controlled — this was the design decision, it's a feature not a favor.
- [x] **C0.2.** Write down the **Project ID** they give you. *(Done: `uad36-qc-beta`.)*

### C-1. One-time PC setup (~15 min)

- [x] **C1.1.** Install the Google Cloud CLI: https://cloud.google.com/sdk/docs/install →
  Windows installer → accept all defaults → let it restart the terminal.
- [x] **C1.2.** Log in (browser window opens; use your **company** Google account):
  ```powershell
  gcloud auth login
  ```

### C-2. Deploy (~20 min, one command)

- [x] **C2.1.** From the project folder:
  ```powershell
  .\infra\deploy-gcp.ps1 -ProjectId "PASTE-PROJECT-ID-HERE"
  ```
  The script: enables GCP services → creates the Postgres database (smallest tier) →
  creates the file-retention bucket → builds the app in the cloud → deploys to Cloud Run.
  *(2026-07-02: first run failed silently on DB creation — POSTGRES_16 needs
  `--edition=enterprise` for db-f1-micro. Script fixed; DB created manually; service healthy.)*
- [x] **C2.2.** ⚠️ The script prints a **generated database password** — save it in your
  password manager immediately. You'll need it for future redeploys.
- [x] **C2.3.** Copy the **service URL** it prints at the end.
  *(Done: `https://uad36-qc-620834509337.us-central1.run.app`.)*

### C-3. Turn on the login wall (IAP) (~15 min, point-and-click)

*(2026-07-02: C3.1–C3.4 done via CLI instead of console — `gcloud run services update
uad36-qc --iap` + `gcloud iap web add-iam-policy-binding`. To add a teammate later:)*
```powershell
gcloud iap web add-iam-policy-binding --resource-type=cloud-run --service=uad36-qc `
  --region=us-central1 --member="user:TEAMMATE@truefootage.tech" `
  --role="roles/iap.httpsResourceAccessor" --project=uad36-qc-beta
```

- [x] **C3.1.** IAP enabled on the service (CLI).
- [x] **C3.2.** OAuth consent screen — not required with Cloud Run's built-in IAP integration.
- [x] **C3.3.** IAP toggle ON (`run.googleapis.com/iap-enabled: true` verified).
- [x] **C3.4.** kevin.zelenakas@truefootage.tech granted **IAP-secured Web App User**.
- [x] **C3.5.** Open the service URL → Google sign-in (company account) → the app. **That's the beta, live.**
  *(Verified 2026-07-03: sign-in works, app loads, drag-and-drop upload works on revision uad36-qc-00003-spt.)*

### C-4. Budget guardrails (~5 min)

- [x] **C4.1.** Budget created via CLI: **$25/month**, alerts at 50% / 90% / 100%,
  scoped to `uad36-qc-beta`. *(Alerts go to billing-account admins by default.)*
- [ ] **C4.2.** Expected spend: Cloud SQL ~$9–12/mo, Cloud Run ~$0–3/mo (sleeps when idle),
  storage pennies. Anything above $25 = something's wrong; email me the billing screenshot.

### C-5. Cloud smoke test (~5 min)

- [ ] **C5.1.** Upload `SF1_Appraisal_v1.4.zip` through the cloud URL → clean pass.
- [ ] **C5.2.** Export PDF + CSV from the cloud.
- [ ] **C5.3.** Admin tab loads, shows 729 rules.
- [ ] **C5.4.** Close the browser, reopen, check Run history — the run is still there
  (that's Postgres persistence working).

---

## STAGE D — First real reports (only after Stage C complete)

**Goal:** real appraisal files through the tool, safely.

- [ ] **D1. Gate check — all must be true before any real report is uploaded:**
  - [ ] IAP is ON and only allowlisted company accounts can reach the URL (test in an
    incognito window with a personal account — it must be refused).
  - [ ] The GCP project is company-controlled (Stage C0).
  - [ ] AI backend is `stub` or `vertex` — **never** `gemini` for real data. (The deploy script
    set `QC_DATA_CLASS=real`, so the app physically refuses to start with the gemini key. Built-in.)
- [ ] **D2.** Upload one real delivery zip. Reviewer mode → work the findings → sign off.
- [ ] **D3.** Compare findings against your manual QC of the same report. Log misses/false
  positives — those feed Stage F encoding priorities.
- [ ] **D4.** Onboard 1–2 QD teammates: add them in IAP (C3.4), send them the URL, 15-minute walkthrough.

---

## STAGE E — Turn on live AI rules (optional, after D)

**Goal:** 1–2 AI-powered rules (e.g. boilerplate-commentary detection) for the wow factor.

### E-1. Local testing with YOUR Gemini API key (sample data only)

- [ ] **E1.1.** In PowerShell (local only — never on the cloud service):
  ```powershell
  $env:QC_AI_BACKEND = "gemini"
  $env:QC_GEMINI_API_KEY = "your-key-here"
  .\dev.ps1
  ```
- [ ] **E1.2.** Admin → create a rule with logic type `ai`, e.g.:
  ```json
  { "type": "ai",
    "prompt": "Does this market commentary read as generic boilerplate rather than market-specific analysis?",
    "fields": ["doc:VALUATION_ANALYSIS/MARKET/..."] }
  ```
  (Ask me to draft the exact field keys + prompt when you're ready — 10-minute job.)
- [ ] **E1.3.** Upload a **GSE sample** (never a real report with your personal key — free-tier
  Gemini can train on inputs; the samples are Fannie/Freddie-published fiction).

### E-2. Production AI on company GCP (Vertex — the real-data-safe path)

- [ ] **E2.1.**
  ```powershell
  gcloud services enable aiplatform.googleapis.com
  gcloud run services update uad36-qc --region us-central1 --set-env-vars "QC_AI_BACKEND=vertex,QC_VERTEX_PROJECT=YOUR-PROJECT-ID,QC_DATA_CLASS=real"
  ```
- [ ] **E2.2.** Cost check after a week of use: Vertex charges cents per analyzed report;
  it shows on the same billing page as C4.

---

## STAGE F — Grow the rule set (ongoing; this is where the product value compounds)

**Goal:** work the 566-rule "Needs encoding" queue down, add coaching messages, build client profiles.

- [ ] **F1. Weekly encoding session (suggest: your 12–3p deep-work block).**
  Admin → **Needs encoding** tab → pick 10–20 rules → for each:
  1. Read the preserved GSE logic text (it's in the Description).
  2. Edit → change `logic` from `needs_encoding` to a real type
     (`field_present` / `regex_match` / `field_in_set` / `numeric_range` / `conditional` / `ai` —
     cheat sheet in `docs\INTEGRATION.md`).
  3. Save (auto-freezes a new ruleset version) → toggle ON → verify against a sample upload.
  *Shortcut: paste a batch of rule IDs to me and I'll draft the logic conversions for your review.*
- [ ] **F2. Author appraiser-coaching messages.** H-1 ships one audit-tone message per rule;
  the appraiser variant falls back to it. Edit rules to add plain-language coaching text
  (your voice — the "what/why/how" format you already use). Prioritize the rules that fire most.
- [ ] **F3. Client profiles.** Admin → Client profiles → create one per lender with their waived
  rules. Pick the profile at upload time (`?profile=Name` — profile picker UI is a fast follow, ask).
- [ ] **F4. Trend review (monthly).** Export CSVs across runs → your revision-pattern analysis →
  which rules fire most, which appraisers repeat — feeds coaching, proves ROI to leadership.

---

## STAGE G — Routine operations (as needed)

- [ ] **G1. Update the cloud app after any code change:**
  ```powershell
  gcloud run deploy uad36-qc --source . --region us-central1
  ```
  Database (runs, findings, reviewer actions, rules) survives every redeploy — it lives in Cloud SQL.
- [ ] **G2. Back up the rules** after big encoding sessions: Admin → **Export rules** →
  save the JSON somewhere safe (Drive). Restore any time via **Import rules**.
- [ ] **G3. Database backups:** Cloud SQL takes daily automatic backups by default — verify once:
  Console → SQL → your instance → Backups.
- [ ] **G4. Nothing is ever auto-deleted** (by design). If storage cost ever matters, that's a
  conscious future decision, not a setting to flip casually.

---

## STAGE H — Post-beta / funded phase (needs decisions + budget; not started)

- [ ] **H1.** Comparable-scoped rules (~135 of the 729) — needs per-instance iteration in the
  engine + xlink-based subject/comp classification (Appendix G-1). Removes the
  "subject = first PROPERTY" assumption.
- [ ] **H2.** Batch reviewer dashboard across many reports (queue view, assignment).
- [ ] **H3.** Real user accounts / Google Workspace SSO inside the app (replaces the role switcher).
- [ ] **H4.** UAD 3.6 **v1.4 XSD** upgrade when GSEs publish it (procedure: `docs\INTEGRATION.md` —
  the samples already reference v1.4, so this closes the version gap).
- [ ] **H5.** PDF/image analysis rules (photo presence, sketch checks) via Vertex multimodal.
- [ ] **H6.** True Footage internal rule pack (your QC standards beyond H-1) — the admin
  tooling for this already exists.

---

## Quick reference card

| I want to… | Do this |
|---|---|
| Run the app locally | `.\dev.ps1` → http://localhost:8000 |
| Run the tests | `backend\.venv\Scripts\python.exe -m pytest backend/tests -q` |
| Deploy/update the cloud app | `gcloud run deploy uad36-qc --source . --region us-central1` |
| Add a user to the beta | IAP console → service → Add principal → *IAP-secured Web App User* |
| Fix a broken local app | Delete `backend\data`, restart |
| Add/edit/toggle rules | Admin tab in the app |
| Back up rules | Admin → Export rules |
| Understand the contracts | `docs\INTEGRATION.md` |
| Deploy details | `docs\GCP_DEPLOY.md` |

**Key files:** app code `backend\` + `frontend\` · rules seed `rules\h1_rules.json` ·
field map `schemas/uad36_field_manifest.json` · official GSE inputs `GSE_UAD_3.6.0_v1.3_schema\`,
`QC_rules\`, `Sample reports\` · design spec `docs\superpowers\specs\2026-07-02-uad36-qc-app-design.md`
