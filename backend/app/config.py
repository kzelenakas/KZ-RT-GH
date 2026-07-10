from __future__ import annotations

import os
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_DIR.parent

# collateral_risk_engine/ lives at the repo root, a sibling of backend/, not inside it.
# It has no packaging metadata (no pyproject.toml/setup.py), and the app only ever runs
# with backend/ on sys.path (uvicorn's --app-dir backend, see dev.ps1 and Dockerfile) --
# the repo root is never added automatically. Insert it here so `import
# collateral_risk_engine` works from app.api.runs. Guarded against duplicate inserts
# since this module gets importlib.reload()-ed per test (backend/tests/test_api.py's
# client fixture).
_repo_root_str = str(REPO_ROOT)
if _repo_root_str not in sys.path:
    sys.path.insert(0, _repo_root_str)

XSD_PATH = Path(os.environ.get(
    "QC_XSD_PATH",
    str(REPO_ROOT / "GSE_UAD_3.6.0_v1.3_schema" / "Combined" / "GSE_UAD_3.6.0_v1.3.xsd"),
))
RULES_PATH = Path(os.environ.get("QC_RULES_PATH", str(REPO_ROOT / "rules" / "h1_rules.json")))
MANIFEST_PATH = Path(os.environ.get(
    "QC_MANIFEST_PATH", str(REPO_ROOT / "schemas" / "uad36_field_manifest.json"),
))
DATA_DIR = Path(os.environ.get("QC_DATA_DIR", str(BACKEND_DIR / "data")))
# Postgres in production (Cloud SQL): postgresql+psycopg://user:pass@host/db
# or unix socket: postgresql+psycopg://user:pass@/db?host=/cloudsql/PROJECT:REGION:INSTANCE
DB_URL = os.environ.get("QC_DB_URL", f"sqlite:///{DATA_DIR / 'qc.sqlite3'}")
# Originals of uploaded reports are retained here (mount a GCS bucket via
# Cloud Storage FUSE volume on Cloud Run to make this durable in production).
FILES_DIR = Path(os.environ.get("QC_FILES_DIR", str(DATA_DIR / "files")))
FRONTEND_DIST = REPO_ROOT / "frontend" / "dist"

# --- AI rule processing -----------------------------------------------------
# QC_AI_BACKEND: stub (default, offline) | gemini (dev key, SAMPLE DATA ONLY) | vertex
# QC_DATA_CLASS: sample (default) | real  -- GLBA guardrail: 'real' blocks gemini.
AI_BACKEND = os.environ.get("QC_AI_BACKEND", "stub")
DATA_CLASS = os.environ.get("QC_DATA_CLASS", "sample")
GEMINI_API_KEY = os.environ.get("QC_GEMINI_API_KEY", "")
VERTEX_PROJECT = os.environ.get("QC_VERTEX_PROJECT", "")
VERTEX_LOCATION = os.environ.get("QC_VERTEX_LOCATION", "us-central1")
AI_MODEL = os.environ.get("QC_AI_MODEL", "gemini-2.0-flash")
