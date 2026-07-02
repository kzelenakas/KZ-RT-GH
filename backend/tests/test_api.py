import pytest
from fastapi.testclient import TestClient

from tests.conftest import SAMPLES_DIR, XSD_PATH

needs_official_files = pytest.mark.skipif(
    not (SAMPLES_DIR.exists() and XSD_PATH.exists()), reason="official GSE files not present"
)


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("QC_DATA_DIR", str(tmp_path))
    # config reads env at import; rebuild it and the app fresh per test
    import importlib

    import app.config
    importlib.reload(app.config)
    from app.main import create_app
    return TestClient(create_app())


@needs_official_files
def test_upload_sample_zip_end_to_end(client):
    zpath = SAMPLES_DIR / "SF1_Appraisal_v1.4.zip"
    with open(zpath, "rb") as fh:
        response = client.post("/api/runs", files={"file": ("SF1_Appraisal_v1.4.zip", fh, "application/zip")})
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["schema_version"] == "GSE_UAD_3.6.0_v1.3"
    assert payload["ruleset_version"].startswith("H1-v1.4-")
    assert set(payload["counts"]) == {"HardStop", "Warning", "Advisory"}
    # SF1 is a complete official sample: all executable Fatal (HardStop) rules pass.
    # Warning-level findings (e.g. optional geocoding fields) are legitimate output.
    assert payload["counts"]["HardStop"] == 0, [
        f["rule_id"] for f in payload["findings"] if f["severity"] == "HardStop"
    ]
    assert payload["rule_errors"] == []
    assert len(payload["file_hash"]) == 64  # sha256 hex


@needs_official_files
def test_upload_broken_report_produces_findings(client):
    """Blank the subject CityName and corrupt the PostalCode in-memory, re-zip, upload."""
    import io
    import zipfile

    from lxml import etree

    with zipfile.ZipFile(SAMPLES_DIR / "SF1_Appraisal_v1.4.zip") as zf:
        xml_bytes = zf.read("SF1_Appraisal_v1.4.xml")
    ns = {"m": "http://www.mismo.org/residential/2009/schemas"}
    doc = etree.fromstring(xml_bytes)
    address = doc.xpath("//m:VALUATION_ANALYSIS/m:PROPERTIES/m:PROPERTY[1]/m:ADDRESS", namespaces=ns)[0]
    address.find("m:CityName", ns).text = ""  # fires UAD1002 (field_present)
    address.find("m:PostalCode", ns).text = "1234"  # fires UAD1005 (zip format)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("broken.xml", etree.tostring(doc))
    buf.seek(0)

    response = client.post("/api/runs", files={"file": ("broken.zip", buf, "application/zip")})
    assert response.status_code == 200
    payload = response.json()
    fired = {f["rule_id"] for f in payload["findings"] if f["severity"] == "HardStop"}
    assert {"UAD1002", "UAD1005"} <= fired
    city = next(f for f in payload["findings"] if f["rule_id"] == "UAD1002")
    assert city["severity"] == "HardStop"
    assert city["citation"].startswith("UAD 3.6 Appendix H-1")
    assert "CityName" in city["xpath"]


def test_upload_garbage_returns_422(client):
    response = client.post("/api/runs", files={"file": ("x.docx", b"hello", "application/octet-stream")})
    assert response.status_code == 422


@needs_official_files
def test_run_history_and_detail(client):
    with open(SAMPLES_DIR / "SF1_Appraisal_v1.4.zip", "rb") as fh:
        run_id = client.post("/api/runs", files={"file": ("SF1.zip", fh, "application/zip")}).json()["id"]
    listing = client.get("/api/runs").json()
    assert listing[0]["id"] == run_id
    detail = client.get(f"/api/runs/{run_id}").json()
    assert detail["counts"]["HardStop"] == 0
    assert client.get("/api/runs/does-not-exist").status_code == 404


@needs_official_files
def test_meta(client):
    meta = client.get("/api/meta").json()
    assert meta["schema_version"] == "GSE_UAD_3.6.0_v1.3"
    assert meta["rule_count"] == 729
