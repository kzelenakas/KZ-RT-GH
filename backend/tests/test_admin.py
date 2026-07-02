"""Admin: rules CRUD, on/off, profiles, import/export, needs_encoding queue."""

import pytest
from fastapi.testclient import TestClient

from tests.conftest import SAMPLES_DIR, XSD_PATH

needs_official_files = pytest.mark.skipif(
    not (SAMPLES_DIR.exists() and XSD_PATH.exists()), reason="official GSE files not present"
)

ADMIN = {"X-QC-Role": "admin"}


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("QC_DATA_DIR", str(tmp_path))
    import importlib

    import app.config
    importlib.reload(app.config)
    from app.main import create_app
    return TestClient(create_app())


def test_admin_requires_role(client):
    assert client.get("/api/admin/rules").status_code == 403
    assert client.get("/api/admin/rules", headers={"X-QC-Role": "reviewer"}).status_code == 403


def test_rules_seeded_from_h1_file(client):
    rules = client.get("/api/admin/rules", headers=ADMIN).json()
    assert len(rules) == 729
    queue = client.get("/api/admin/rules?status=needs_encoding", headers=ADMIN).json()
    assert len(queue) == 653
    assert all(r["logic"]["type"] == "needs_encoding" for r in queue)


def test_toggle_rule_changes_active_set_and_version(client):
    meta1 = client.get("/api/meta").json()
    assert meta1["active_rule_count"] == 76
    toggled = client.post("/api/admin/rules/UAD1002/toggle", json={"enabled": False}, headers=ADMIN).json()
    assert toggled["enabled"] is False
    meta2 = client.get("/api/meta").json()
    assert meta2["active_rule_count"] == 75
    assert meta2["ruleset_version"] != meta1["ruleset_version"]


def test_edit_rule_message(client):
    rule = client.get("/api/admin/rules/UAD1002", headers=ADMIN).json()
    rule["messages"]["appraiser"] = "Coaching: add the subject city before delivery."
    updated = client.put("/api/admin/rules/UAD1002", json=rule, headers=ADMIN).json()
    assert updated["messages"]["appraiser"].startswith("Coaching:")
    # h1 extras preserved through the round-trip
    assert updated["h1"]["unique_id"] == "0100.0009"


def test_create_custom_rule_and_archive(client):
    new_rule = {
        "rule_id": "TF-CUSTOM-1",
        "category": "True Footage Internal",
        "description": "Subject county must be provided (internal standard).",
        "severity": "Advisory",
        "enabled": True,
        "logic": {"type": "field_present", "field": "subject:VALUATION_ANALYSIS/PROPERTIES/PROPERTY/ADDRESS/CountyName"},
        "messages": {"appraiser": "Add the county.", "reviewer": "CountyName missing (internal)."},
    }
    created = client.put("/api/admin/rules/TF-CUSTOM-1", json=new_rule, headers=ADMIN).json()
    assert created["rule_id"] == "TF-CUSTOM-1"
    assert created.get("citation") is None  # never fabricated
    assert client.post("/api/admin/rules/TF-CUSTOM-1/archive", headers=ADMIN).json() == {"archived": "TF-CUSTOM-1"}
    assert client.get("/api/admin/rules/TF-CUSTOM-1", headers=ADMIN).status_code == 404


def test_invalid_rule_rejected(client):
    bad = {"rule_id": "BAD-1", "category": "X"}  # missing severity
    assert client.put("/api/admin/rules/BAD-1", json=bad, headers=ADMIN).status_code == 422


def test_export_import_roundtrip(client):
    exported = client.get("/api/admin/export", headers=ADMIN).json()
    assert len(exported["rules"]) == 729
    result = client.post("/api/admin/import", json={"ruleset": exported}, headers=ADMIN).json()
    assert result["imported"] == 729


@needs_official_files
def test_profile_disables_rules_per_run(client):
    import io
    import zipfile

    from lxml import etree

    client.post("/api/admin/profiles", json={
        "name": "LenderX", "description": "Client waives city check",
        "disabled_rule_ids": ["UAD1002"],
    }, headers=ADMIN)

    with zipfile.ZipFile(SAMPLES_DIR / "SF1_Appraisal_v1.4.zip") as zf:
        xml_bytes = zf.read("SF1_Appraisal_v1.4.xml")
    ns = {"m": "http://www.mismo.org/residential/2009/schemas"}
    doc = etree.fromstring(xml_bytes)
    address = doc.xpath("//m:VALUATION_ANALYSIS/m:PROPERTIES/m:PROPERTY[1]/m:ADDRESS", namespaces=ns)[0]
    address.find("m:CityName", ns).text = ""

    def zipped() -> io.BytesIO:
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("broken.xml", etree.tostring(doc))
        buf.seek(0)
        return buf

    default_run = client.post("/api/runs", files={"file": ("b.zip", zipped(), "application/zip")}).json()
    assert any(f["rule_id"] == "UAD1002" for f in default_run["findings"])

    profile_run = client.post(
        "/api/runs?profile=LenderX", files={"file": ("b.zip", zipped(), "application/zip")},
    ).json()
    assert not any(f["rule_id"] == "UAD1002" for f in profile_run["findings"])
    assert profile_run["ruleset_version"].endswith("+LenderX")
    assert profile_run["ruleset_version"] != default_run["ruleset_version"]
