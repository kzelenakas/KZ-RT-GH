"""Admin candidate-rule endpoints: list/get/approve/reject."""

import pytest
from fastapi.testclient import TestClient

ADMIN = {"X-QC-Role": "admin"}

CANDIDATE_DEFINITION = {
    "rule_id": "CR-0001",
    "category": "Site",
    "description": "Narrative does not analyze impact of adjacent external land use.",
    "severity": "Advisory",
    "enabled": False,
    "logic": {"type": "ai", "prompt": "Does the narrative analyze this external factor?",
              "fields": ["subject:VALUATION_ANALYSIS/NEIGHBORHOOD/CommentText"]},
    "citation": "True Footage client revision pattern, 12 occurrences, date range not available in source export",
    "messages": {"appraiser": "Coaching text.", "reviewer": "Audit text."},
}


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("QC_DATA_DIR", str(tmp_path))
    import importlib

    import app.config
    importlib.reload(app.config)
    from app.main import create_app
    return TestClient(create_app())


@pytest.fixture
def seeded_candidate(client):
    client.app.state.candidate_rules_repo.bulk_insert([{
        "definition": CANDIDATE_DEFINITION,
        "theme_id": "site-external-factor-not-analyzed",
        "occurrence_count": 12,
        "date_range_start": None,
        "date_range_end": None,
        "redundancy_verdict": "new",
        "redundancy_notes": "No matching field/logic found in the existing rule set.",
    }])
    return client


def test_list_candidate_rules_requires_admin(client):
    assert client.get("/api/admin/candidate-rules").status_code == 403


def test_list_and_get_candidate_rule(seeded_candidate):
    items = seeded_candidate.get("/api/admin/candidate-rules", headers=ADMIN).json()
    assert len(items) == 1
    assert items[0]["rule_id"] == "CR-0001"

    one = seeded_candidate.get("/api/admin/candidate-rules/CR-0001", headers=ADMIN).json()
    assert one["occurrence_count"] == 12

    missing = seeded_candidate.get("/api/admin/candidate-rules/CR-9999", headers=ADMIN)
    assert missing.status_code == 404


def test_approve_promotes_into_live_rules(seeded_candidate):
    result = seeded_candidate.post(
        "/api/admin/candidate-rules/CR-0001/approve",
        json={"reviewer": "kevin.zelenakas"}, headers=ADMIN,
    )
    assert result.status_code == 200
    assert result.json()["review_status"] == "approved"

    promoted = seeded_candidate.get("/api/admin/rules/CR-0001", headers=ADMIN)
    assert promoted.status_code == 200
    assert promoted.json()["enabled"] is False  # still disabled after promotion


def test_approve_blocks_exact_duplicate(client):
    client.app.state.candidate_rules_repo.bulk_insert([{
        "definition": CANDIDATE_DEFINITION,
        "theme_id": "dup-theme", "occurrence_count": 3,
        "date_range_start": None, "date_range_end": None,
        "redundancy_verdict": "exact_duplicate",
        "redundancy_notes": "Matches existing rule UAD1234.",
    }])
    result = client.post(
        "/api/admin/candidate-rules/CR-0001/approve",
        json={"reviewer": "kevin.zelenakas"}, headers=ADMIN,
    )
    assert result.status_code == 409


def test_reject_marks_status(seeded_candidate):
    result = seeded_candidate.post(
        "/api/admin/candidate-rules/CR-0001/reject",
        json={"reviewer": "kevin.zelenakas"}, headers=ADMIN,
    )
    assert result.status_code == 200
    assert result.json()["review_status"] == "rejected"
