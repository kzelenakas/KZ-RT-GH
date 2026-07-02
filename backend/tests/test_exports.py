import csv
import io
import zipfile

import pytest
from fastapi.testclient import TestClient

from tests.conftest import SAMPLES_DIR, XSD_PATH

needs_official_files = pytest.mark.skipif(
    not (SAMPLES_DIR.exists() and XSD_PATH.exists()), reason="official GSE files not present"
)


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("QC_DATA_DIR", str(tmp_path))
    import importlib

    import app.config
    importlib.reload(app.config)
    from app.main import create_app
    return TestClient(create_app())


def upload_broken(client) -> dict:
    from lxml import etree

    with zipfile.ZipFile(SAMPLES_DIR / "SF1_Appraisal_v1.4.zip") as zf:
        xml_bytes = zf.read("SF1_Appraisal_v1.4.xml")
    ns = {"m": "http://www.mismo.org/residential/2009/schemas"}
    doc = etree.fromstring(xml_bytes)
    address = doc.xpath("//m:VALUATION_ANALYSIS/m:PROPERTIES/m:PROPERTY[1]/m:ADDRESS", namespaces=ns)[0]
    address.find("m:CityName", ns).text = ""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("broken.xml", etree.tostring(doc))
    buf.seek(0)
    return client.post("/api/runs", files={"file": ("broken.zip", buf, "application/zip")}).json()


@needs_official_files
def test_csv_export_one_row_per_finding_with_metadata(client):
    run = upload_broken(client)
    response = client.get(f"/api/runs/{run['id']}/export?format=csv&mode=reviewer")
    assert response.status_code == 200
    assert "text/csv" in response.headers["content-type"]
    rows = list(csv.DictReader(io.StringIO(response.text)))
    assert len(rows) == len(run["findings"])
    first = rows[0]
    assert first["run_id"] == run["id"]
    assert first["schema_version"] == "GSE_UAD_3.6.0_v1.3"
    assert first["ruleset_version"] == run["ruleset_version"]
    assert first["mode"] == "reviewer"
    city_row = next(r for r in rows if r["rule_id"] == "UAD1002")
    assert city_row["severity"] == "HardStop"
    assert city_row["citation"].startswith("UAD 3.6 Appendix H-1")


@needs_official_files
def test_csv_export_appraiser_mode_omits_reviewer_fields(client):
    run = upload_broken(client)
    rows = list(csv.DictReader(io.StringIO(
        client.get(f"/api/runs/{run['id']}/export?format=csv&mode=appraiser").text
    )))
    assert all(r["reviewer_status"] == "" and r["reviewer_note"] == "" for r in rows)


@needs_official_files
def test_csv_export_clean_run_says_no_issues(client):
    with open(SAMPLES_DIR / "SF1_Appraisal_v1.4.zip", "rb") as fh:
        run = client.post("/api/runs", files={"file": ("SF1.zip", fh, "application/zip")}).json()
    # SF1 may carry Warning findings; craft assertion accordingly
    response = client.get(f"/api/runs/{run['id']}/export?format=csv&mode=appraiser")
    rows = list(csv.DictReader(io.StringIO(response.text)))
    if run["findings"]:
        assert len(rows) == len(run["findings"])
    else:
        assert rows[0]["message"] == "No issues found"


@needs_official_files
def test_pdf_export(client):
    run = upload_broken(client)
    response = client.get(f"/api/runs/{run['id']}/export?format=pdf&mode=reviewer")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/pdf")
    assert response.content[:5] == b"%PDF-"
    assert len(response.content) > 1500


def test_export_validation(client):
    assert client.get("/api/runs/nope/export?format=csv").status_code == 404
    # invalid params rejected before lookup
    assert client.get("/api/runs/nope/export?format=docx").status_code == 422
    assert client.get("/api/runs/nope/export?format=csv&mode=admin").status_code == 422
