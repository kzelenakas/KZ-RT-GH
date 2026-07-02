# Builds the frontend and starts the QC app at http://localhost:8000
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
npm --prefix frontend run build
backend\.venv\Scripts\python.exe -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000
