# UAD 3.6 QC — Master Roadmap & Checklist

Status legend: ✅ done · 🔲 your action · ⏭ future phase

## Build phases (all code work done)

- ✅ **Phase 1 — End-to-end skeleton.** Upload → XSD validation → normalize → rules → findings UI. SQLite persistence, run history, no auto-delete.
- ✅ **Phase 2 — Real schema + rules.** Official GSE UAD 3.6 v1.3 XSD validation; all 729 Appendix H-1 v1.4 rules imported (76 auto-encoded and running; 653 preserved verbatim in the "needs encoding" queue). Manifest-driven adapter.
- ✅ **Phase 3 — Two modes + reviewer workflow.** Appraiser fix-it checklist with saved checkboxes; reviewer verdicts (Hard Stop: Resolved/Fail · Warning: Pass/Fail/Conditional-pass-with-comment · Advisory: Acknowledge); run sign-off (signed off / returned / reopen); append-only audit log.
- ✅ **Phase 4 — Admin mode.** Rules database with on/off toggles, plain-language editor, search, needs-encoding queue, client ruleset profiles, JSON import/export, frozen ruleset snapshot per change.
- ✅ **Phase 5 — Exports.** PDF (formatted QC report) + CSV (one row per finding), both carrying full run metadata (file, hash, timestamp, schema version, ruleset version, mode, reviewer, counts).
- ✅ **Phase 6 — AI rules.** `ai` logic type with pluggable backends (stub / Gemini dev key / Vertex AI) and a hard GLBA guardrail: dev-key Gemini cannot run when data class is `real`.
- ✅ **Phase 7 — GCP packaging.** Dockerfile, Cloud Run deploy script (Cloud SQL Postgres + GCS file retention + IAP-ready), step-by-step non-developer deploy guide.

## Your checklist — local demo (today)

- 🔲 Run `.\dev.ps1`, open http://localhost:8000
- 🔲 Upload `Sample reports\SF1_Appraisal_v1.4.zip` — expect green clean pass + 1 Warning
- 🔲 Toggle Appraiser / QD Reviewer / Admin and click around
- 🔲 Export PDF + CSV from a run

## Your checklist — GCP beta (when IT provides the project)

- 🔲 Ask IT for a company GCP project with billing + Owner/Editor role (GLBA requirement — decided in spec)
- 🔲 Install gcloud CLI and `gcloud auth login`
- 🔲 Run `.\infra\deploy-gcp.ps1 -ProjectId "..."` (see docs/GCP_DEPLOY.md)
- 🔲 Enable IAP and allowlist your account (docs/GCP_DEPLOY.md §IAP)
- 🔲 Set a $25/month budget alert
- 🔲 Upload a sample through the cloud URL end-to-end
- 🔲 Only after IAP works: upload a real report

## Future phases (post-beta, needs decisions/funding)

- ⏭ Encode the 653 `needs_encoding` H-1 rules in batches (Admin queue; AI-assisted drafting possible)
- ⏭ Comparable-scoped rules (~135 of the 729) — needs per-instance iteration + xlink subject/comp classification (Appendix G-1)
- ⏭ Author appraiser-coaching message variants (H-1 ships one message; the contract already supports two)
- ⏭ Batch reviewer view across many reports; PDF/image checks; real SSO user accounts
- ⏭ Upgrade to UAD 3.6 v1.4 XSD when published (procedure in docs/INTEGRATION.md)
