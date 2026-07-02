import io
import sys
import zipfile
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

REPO_ROOT = BACKEND_DIR.parent
SAMPLES_DIR = REPO_ROOT / "Sample reports"
XSD_PATH = REPO_ROOT / "GSE_UAD_3.6.0_v1.3_schema" / "Combined" / "GSE_UAD_3.6.0_v1.3.xsd"
MANIFEST_PATH = REPO_ROOT / "schemas" / "uad36_field_manifest.json"
SUBJECT_ADDRESS = "subject:VALUATION_ANALYSIS/PROPERTIES/PROPERTY/ADDRESS"

TINY_XML = b'<?xml version="1.0" encoding="UTF-8"?><MESSAGE xmlns="http://www.mismo.org/residential/2009/schemas"></MESSAGE>'


@pytest.fixture
def synthetic_zip() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("report.xml", TINY_XML)
        zf.writestr("report.pdf", b"%PDF-1.4 fake")
        zf.writestr("Images/front.png", b"\x89PNG fake")
    return buf.getvalue()
