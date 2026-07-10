"""collateral_risk_engine wired into /api/runs (see app/api/runs.py's
_cr_finding_to_finding + the collateral_risk_engine.evaluate() call in create_run()).

No network call is ever made here -- the geo_proximity operator's Overpass fetch is
monkeypatched, same pattern as collateral_risk_engine/test_geo_proximity.py.

CR-101-104 (the shipped geo_proximity rules in collateral_risk_engine/rules.json) are
enabled: false pending Kevin's sign-off on wording/citation, so these tests don't rely
on them or mutate the shipped defaults -- they monkeypatch
collateral_risk_engine.engine.load_rules to inject a standalone enabled test rule with
the same geo_proximity logic shape instead.
"""
from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from tests.conftest import SAMPLES_DIR, XSD_PATH

needs_official_files = pytest.mark.skipif(
    not (SAMPLES_DIR.exists() and XSD_PATH.exists()), reason="official GSE files not present"
)


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("QC_DATA_DIR", str(tmp_path))
    # config reads env (and sets up sys.path for collateral_risk_engine) at import
    # time; rebuild it and the app fresh per test, same as test_api.py's client fixture.
    import importlib

    import app.config
    importlib.reload(app.config)
    from app.main import create_app
    return TestClient(create_app())


def _fake_fetch_hit(query: str) -> bytes:
    # Same fixture value as collateral_risk_engine/test_geo_proximity.py: a way
    # "center" ~91m (~300ft) north of the SF1 sample's real subject coordinates
    # (25.165173, -51.328125) -- inside the rule's 500m search radius and its 300ft
    # trigger threshold.
    return json.dumps({"elements": [{"type": "way", "center": {"lat": 25.16599, "lon": -51.328125}}]}).encode()


_TEST_GEO_RULE = {
    "rule_id": "CR-TEST-GEO",
    "category": "Site, Zoning & Location Risk",
    "description": "Subject within 300 ft of an airport/aerodrome (test rule)",
    "severity": "Advisory",
    "enabled": True,
    "logic": {
        "type": "geo_proximity",
        "lat_field": "LOCATION_IDENTIFIER/GEOSPATIAL_INFORMATION/LatitudeIdentifier",
        "lon_field": "LOCATION_IDENTIFIER/GEOSPATIAL_INFORMATION/LongitudeIdentifier",
        "category": "airport",
        "threshold_ft": 300,
        "radius_m": 500,
    },
    "citation": "test fixture citation",
}


@needs_official_files
def test_geo_proximity_rule_fires_end_to_end(client, monkeypatch):
    import collateral_risk_engine.engine as cr_engine
    import collateral_risk_engine.poi as poi_module

    monkeypatch.setattr(cr_engine, "load_rules", lambda *a, **k: [_TEST_GEO_RULE])
    monkeypatch.setattr(poi_module, "_http_fetch", _fake_fetch_hit)

    zpath = SAMPLES_DIR / "SF1_Appraisal_v1.4.zip"
    with open(zpath, "rb") as fh:
        response = client.post("/api/runs", files={"file": ("SF1_Appraisal_v1.4.zip", fh, "application/zip")})
    assert response.status_code == 200, response.text
    payload = response.json()

    cr_findings = [f for f in payload["findings"] if f["rule_id"] == "CR-TEST-GEO"]
    assert len(cr_findings) == 1, payload["findings"]
    finding = cr_findings[0]
    assert finding["severity"] == "Advisory"
    assert finding["category"] == "Site, Zoning & Location Risk"
    assert finding["citation"] == "test fixture citation"
    assert finding["message_appraiser"] == "Subject within 300 ft of an airport/aerodrome (test rule)"
    assert finding["message_reviewer"] == "Subject within 300 ft of an airport/aerodrome (test rule)"
    # values must be str|None -- collateral_risk_engine's distance_ft/threshold_ft are
    # float/int on the wire, and Finding.values requires str|None (pydantic v2 does not
    # coerce numbers into str for this field).
    assert finding["values"]["category"] == "airport"
    assert finding["values"]["threshold_ft"] == "300"
    assert isinstance(finding["values"]["distance_ft"], str)
    assert float(finding["values"]["distance_ft"]) <= 300

    # counts (by severity) picks the finding up too.
    assert payload["counts"]["Advisory"] >= 1

    # collateral_risk_engine ran cleanly -- no rule_errors entry from the merge.
    cr_errors = [e for e in payload["rule_errors"] if e["rule_id"] == "collateral_risk_engine"]
    assert cr_errors == []


@needs_official_files
def test_geo_proximity_engine_failure_is_isolated_not_fatal(client, monkeypatch):
    """A broken collateral_risk_engine call (e.g. Overpass unreachable, a malformed
    rule) must not take down the run -- mirrors the AI-rule failure-isolation pattern
    already covered for the H-1 engine by backend/tests/test_ai_rules.py's
    ExplodingBackend case."""
    import collateral_risk_engine

    def _boom(xml_bytes, rules=None):
        raise ConnectionError("Overpass API request failed: simulated network failure")

    monkeypatch.setattr(collateral_risk_engine, "evaluate", _boom)

    zpath = SAMPLES_DIR / "SF1_Appraisal_v1.4.zip"
    with open(zpath, "rb") as fh:
        response = client.post("/api/runs", files={"file": ("SF1_Appraisal_v1.4.zip", fh, "application/zip")})
    assert response.status_code == 200, response.text
    payload = response.json()

    cr_errors = [e for e in payload["rule_errors"] if e["rule_id"] == "collateral_risk_engine"]
    assert len(cr_errors) == 1
    assert cr_errors[0]["error_type"] == "collateral_risk_error"
    assert "simulated network failure" in cr_errors[0]["detail"]
    # the H-1 engine's own findings/trace are unaffected by the collateral-risk failure.
    assert payload["schema_version"] == "GSE_UAD_3.6.0_v1.3"
