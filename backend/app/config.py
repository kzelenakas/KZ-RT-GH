from __future__ import annotations

import os
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_DIR.parent

XSD_PATH = Path(os.environ.get(
    "QC_XSD_PATH",
    str(REPO_ROOT / "GSE_UAD_3.6.0_v1.3_schema" / "Combined" / "GSE_UAD_3.6.0_v1.3.xsd"),
))
RULES_PATH = Path(os.environ.get("QC_RULES_PATH", str(REPO_ROOT / "rules" / "h1_rules.json")))
MANIFEST_PATH = Path(os.environ.get(
    "QC_MANIFEST_PATH", str(REPO_ROOT / "schemas" / "uad36_field_manifest.json"),
))
DATA_DIR = Path(os.environ.get("QC_DATA_DIR", str(BACKEND_DIR / "data")))
DB_URL = f"sqlite:///{DATA_DIR / 'qc.sqlite3'}"
FRONTEND_DIST = REPO_ROOT / "frontend" / "dist"
