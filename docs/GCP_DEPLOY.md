# Deploying the QC app to Google Cloud — step by step (no developer experience needed)

This walks you from "app runs on my PC" to "app runs on company GCP behind a login wall."
Budget guidance is included at each step. Expected steady cost: **$12–20/month**, well inside the $300 beta budget.

## Before you start — one-time setup (~30 minutes)

1. **Get the GCP project from IT.** Real appraisal reports contain GLBA-protected borrower
   data, so the project must be company-controlled (this was decided in the design spec).
   Ask IT for: a GCP project with billing enabled, and the `Owner` or `Editor` role on it
   for your Google account.
2. **Install the Google Cloud CLI.** Download from https://cloud.google.com/sdk/docs/install
   (Windows installer). Accept the defaults.
3. **Log in.** Open PowerShell and run:
   ```powershell
   gcloud auth login
   ```
   A browser window opens — sign in with your company Google account.

## Deploy (~15 minutes, mostly waiting)

From the project folder in PowerShell:

```powershell
.\infra\deploy-gcp.ps1 -ProjectId "YOUR-PROJECT-ID"
```

The script does everything: enables services, creates the Postgres database
(smallest tier), creates the file-retention bucket, builds the app in the cloud,
and deploys it to Cloud Run. **It prints a generated database password — save it
in your password manager.**

When it finishes it prints the service URL. The service is deliberately NOT
public (`--no-allow-unauthenticated`) — nobody can reach it until IAP is on.

## Turn on IAP (the login wall) — one time

IAP means only allowlisted company Google accounts can open the app. No passwords
to manage, no login code in the app.

1. Console → Security → Identity-Aware Proxy: https://console.cloud.google.com/security/iap
2. If prompted, configure the OAuth consent screen (Internal, app name "UAD 3.6 QC").
3. Find the Cloud Run service `uad36-qc` in the list and toggle IAP **on**.
4. Click the service → "Add principal" → enter a coworker's email →
   role **IAP-secured Web App User**. Repeat per person (start with just yourself).

Open the service URL in your browser — you should get a Google sign-in, then the app.

## Turning on live AI rules (optional, after the basics work)

The app deploys with AI rules OFF (`QC_AI_BACKEND=stub`). To turn on Vertex AI
(the only AI path allowed for real reports — see GLBA note below):

```powershell
gcloud run services update uad36-qc --region us-central1 `
  --set-env-vars "QC_AI_BACKEND=vertex,QC_VERTEX_PROJECT=YOUR-PROJECT-ID,QC_DATA_CLASS=real"
gcloud services enable aiplatform.googleapis.com
```

**GLBA guardrail (built into the app):** if anyone sets `QC_AI_BACKEND=gemini`
(the developer-key backend) while `QC_DATA_CLASS=real`, the app refuses to start.
The developer key is for local testing on the GSE sample files only.

## Budget guardrails

1. Console → Billing → Budgets & alerts → Create budget → $25/month with alerts
   at 50/90/100%.
2. Expected costs: Cloud SQL db-f1-micro ~$9–12/mo, Cloud Run ~$0–3/mo (scales to
   zero when idle), storage pennies, Vertex AI cents per analyzed report.

## Updating the app later

Any time the code changes, redeploy with one command:

```powershell
gcloud run deploy uad36-qc --source . --region us-central1
```

Everything in the database (runs, findings, reviewer actions, rules) survives
redeploys — it lives in Cloud SQL, not the container.

## Loading a new schema or rule set (no redeploy of code)

- **New rule set:** Admin mode → Import rules (JSON file). Every change freezes a
  new ruleset version automatically; old runs keep pointing at the version they ran under.
- **New UAD schema version (e.g. v1.4 XSD):** put the new XSD folder in the image
  (or a mounted volume) and set `QC_XSD_PATH` to it, plus a regenerated field
  manifest via `QC_MANIFEST_PATH`. See docs/INTEGRATION.md for the full procedure.
