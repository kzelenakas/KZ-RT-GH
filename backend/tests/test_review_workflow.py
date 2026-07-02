"""Reviewer workflow: appraiser checkboxes, reviewer verdicts, sign-off, audit."""

import io
import zipfile

import pytest
from fastapi.testclient import TestClient

from tests.conftest import SAMPLES_DIR, XSD_PATH

needs_official_files = pytest.mark.skipif(
    not (SAMPLES_DIR.exists() and XSD_PATH.exists()), reason="official GSE files not present"
)

REVIEWER = {"X-QC-Role": "reviewer"}
APPRAISER = {"X-QC-Role": "appraiser"}


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("QC_DATA_DIR", str(tmp_path))
    import importlib

    import app.config
    importlib.reload(app.config)
    from app.main import create_app
    return TestClient(create_app())


def broken_zip() -> io.BytesIO:
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
    return buf


@pytest.fixture
def run_with_findings(client):
    response = client.post("/api/runs", files={"file": ("broken.zip", broken_zip(), "application/zip")})
    payload = response.json()
    assert payload["findings"], "expected findings on the broken sample"
    return payload


@needs_official_files
def test_appraiser_checkbox_persists(client, run_with_findings):
    run = run_with_findings
    finding = next(f for f in run["findings"] if f["rule_id"] == "UAD1002")
    assert finding["appraiser_checked"] is False
    updated = client.post(
        f"/api/runs/{run['id']}/findings/{finding['id']}/check",
        json={"checked": True}, headers=APPRAISER,
    ).json()
    updated_finding = next(f for f in updated["findings"] if f["id"] == finding["id"])
    assert updated_finding["appraiser_checked"] is True
    # visible to the reviewer on re-fetch
    refetched = client.get(f"/api/runs/{run['id']}").json()
    assert next(f for f in refetched["findings"] if f["id"] == finding["id"])["appraiser_checked"] is True


@needs_official_files
def test_review_requires_reviewer_role(client, run_with_findings):
    run = run_with_findings
    finding = run["findings"][0]
    response = client.post(
        f"/api/runs/{run['id']}/findings/{finding['id']}/review",
        json={"status": "fail"}, headers=APPRAISER,
    )
    assert response.status_code == 403


@needs_official_files
def test_hardstop_verdicts(client, run_with_findings):
    run = run_with_findings
    hard_stop = next(f for f in run["findings"] if f["severity"] == "HardStop")
    url = f"/api/runs/{run['id']}/findings/{hard_stop['id']}/review"
    # 'pass' is a Warning verdict, not valid for HardStop
    assert client.post(url, json={"status": "pass"}, headers=REVIEWER).status_code == 422
    updated = client.post(url, json={"status": "resolved"}, headers=REVIEWER).json()
    reviewed = next(f for f in updated["findings"] if f["id"] == hard_stop["id"])
    assert reviewed["reviewer_status"] == "resolved"
    assert reviewed["reviewed_at"] is not None


@needs_official_files
def test_conditional_pass_requires_note(client, run_with_findings):
    run = run_with_findings
    warning = next((f for f in run["findings"] if f["severity"] == "Warning"), None)
    if warning is None:
        pytest.skip("no warning finding on this sample")
    url = f"/api/runs/{run['id']}/findings/{warning['id']}/review"
    assert client.post(url, json={"status": "conditional_pass"}, headers=REVIEWER).status_code == 422
    updated = client.post(
        url, json={"status": "conditional_pass", "note": "Addressed in addendum."}, headers=REVIEWER,
    ).json()
    reviewed = next(f for f in updated["findings"] if f["id"] == warning["id"])
    assert reviewed["reviewer_status"] == "conditional_pass"
    assert reviewed["reviewer_note"] == "Addressed in addendum."


@needs_official_files
def test_sign_off_and_audit_trail(client, run_with_findings):
    run = run_with_findings
    assert run["sign_off_state"] == "in_review"
    finding = run["findings"][0]
    client.post(
        f"/api/runs/{run['id']}/findings/{finding['id']}/check",
        json={"checked": True}, headers=APPRAISER,
    )
    signed = client.post(
        f"/api/runs/{run['id']}/sign-off",
        json={"state": "signed_off", "reviewer": "Kevin Z"}, headers=REVIEWER,
    ).json()
    assert signed["sign_off_state"] == "signed_off"
    assert signed["reviewer_name"] == "Kevin Z"

    # appraiser cannot sign off
    assert client.post(
        f"/api/runs/{run['id']}/sign-off", json={"state": "signed_off"}, headers=APPRAISER,
    ).status_code == 403

    audit = client.get(f"/api/runs/{run['id']}/audit", headers=REVIEWER).json()
    actions = [a["action"] for a in audit]
    assert "finding_check" in actions and "sign_off" in actions
    assert all(a["created_at"] for a in audit)
    # audit endpoint is reviewer-only
    assert client.get(f"/api/runs/{run['id']}/audit", headers=APPRAISER).status_code == 403
