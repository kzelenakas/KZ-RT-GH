# One-time-ish deploy script for the UAD 3.6 QC beta on GCP Cloud Run.
# Prereqs: gcloud CLI installed and logged in (gcloud auth login),
#          a GCP project with billing enabled.
# Usage:   .\infra\deploy-gcp.ps1 -ProjectId "your-project-id"

param(
    [Parameter(Mandatory = $true)][string]$ProjectId,
    [string]$Region = "us-central1",
    [string]$Service = "uad36-qc",
    [string]$DbInstance = "uad36-qc-db",
    [string]$DbPassword = ""
)

$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot -Parent)

Write-Host "==> Setting project" -ForegroundColor Cyan
gcloud config set project $ProjectId

Write-Host "==> Enabling required services (one-time, ~2 min)" -ForegroundColor Cyan
gcloud services enable run.googleapis.com cloudbuild.googleapis.com `
    artifactregistry.googleapis.com sqladmin.googleapis.com iap.googleapis.com

Write-Host "==> Creating Cloud SQL Postgres (smallest tier, ~`$10/mo). Skips if it exists." -ForegroundColor Cyan
$exists = gcloud sql instances list --filter="name=$DbInstance" --format="value(name)"
if (-not $exists) {
    if (-not $DbPassword) { $DbPassword = -join ((65..90) + (97..122) + (48..57) | Get-Random -Count 20 | ForEach-Object { [char]$_ }) ; Write-Host "Generated DB password: $DbPassword  (SAVE THIS)" -ForegroundColor Yellow }
    # --edition=enterprise required: POSTGRES_16 defaults to Enterprise Plus,
    # which rejects shared-core tiers like db-f1-micro
    gcloud sql instances create $DbInstance --database-version=POSTGRES_16 `
        --edition=enterprise --tier=db-f1-micro --region=$Region --storage-size=10
    if ($LASTEXITCODE -ne 0) { throw "Cloud SQL instance creation failed - stopping. Nothing was deployed." }
    gcloud sql users set-password postgres --instance=$DbInstance --password=$DbPassword
    if ($LASTEXITCODE -ne 0) { throw "Setting DB password failed - stopping." }
    gcloud sql databases create qc --instance=$DbInstance
    if ($LASTEXITCODE -ne 0) { throw "Creating qc database failed - stopping." }
}

Write-Host "==> Creating GCS bucket for retained report files. Skips if it exists." -ForegroundColor Cyan
$bucket = "$ProjectId-uad36-qc-files"
if (-not (gcloud storage buckets list --filter="name=$bucket" --format="value(name)")) {
    gcloud storage buckets create "gs://$bucket" --location=$Region --uniform-bucket-level-access
}

Write-Host "==> Building container with Cloud Build and deploying to Cloud Run" -ForegroundColor Cyan
$conn = "${ProjectId}:${Region}:${DbInstance}"
gcloud run deploy $Service `
    --source . `
    --region $Region `
    --no-allow-unauthenticated `
    --add-cloudsql-instances $conn `
    --add-volume "name=files,type=cloud-storage,bucket=$bucket" `
    --add-volume-mount "volume=files,mount-path=/data/files" `
    --set-env-vars "QC_DB_URL=postgresql+psycopg://postgres:$DbPassword@/qc?host=/cloudsql/$conn,QC_DATA_CLASS=real,QC_AI_BACKEND=stub,QC_FILES_DIR=/data/files" `
    --memory 1Gi --cpu 1 --min-instances 0 --max-instances 2

Write-Host ""
Write-Host "Deployed. NEXT STEPS (manual, see docs/GCP_DEPLOY.md):" -ForegroundColor Green
Write-Host " 1. Turn on IAP for this Cloud Run service and allowlist company Google accounts."
Write-Host " 2. Vertex AI rules: redeploy with QC_AI_BACKEND=vertex and QC_VERTEX_PROJECT=$ProjectId."
Write-Host " 3. Set a budget alert at `$25/month in Billing > Budgets."
