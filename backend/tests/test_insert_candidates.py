"""insert_candidates: reads mined-theme JSON, scans PII, tags redundancy, bulk-inserts."""

import json

import pytest

from app.persistence import CandidateRulesRepository, RulesRepository, init_db
from app.revision_mining.insert_candidates import insert_candidates

EXISTING_RULE = {
    "rule_id": "UAD1001",
    "category": "Subject Property",
    "description": "Subject property physical address line must be provided.",
    "severity": "HardStop",
    "enabled": True,
    "logic": {"type": "field_present", "field": "subject:VALUATION_ANALYSIS/PROPERTIES/PROPERTY/ADDRESS/AddressLineText"},
    "citation": "UAD 3.6 Appendix H-1 v1.4, Unique ID 0100.0007, Message ID UAD1001",
    "messages": {"reviewer": "Provide the address line for the subject property physical address."},
}


@pytest.fixture
def db_url(tmp_path):
    return f"sqlite:///{tmp_path}/test.db"


def _write_candidates_file(tmp_path, candidates):
    path = tmp_path / "candidates.json"
    path.write_text(json.dumps(candidates), encoding="utf-8")
    return path


def test_insert_candidates_tags_exact_duplicate_and_new(tmp_path, db_url):
    sessions = init_db(db_url)
    RulesRepository(sessions).upsert_rule(EXISTING_RULE)

    candidates = [
        {
            "theme_id": "dup-address-theme",
            "occurrence_count": 4,
            "definition": {
                "rule_id": "CR-0001", "category": "Subject Property",
                "description": "Subject address line is required.",
                "severity": "Advisory", "enabled": False,
                "logic": {"type": "field_present", "field": "subject:VALUATION_ANALYSIS/PROPERTIES/PROPERTY/ADDRESS/AddressLineText"},
                "citation": "True Footage client revision pattern, 4 occurrences, date range not available in source export",
                "messages": {"appraiser": "x", "reviewer": "x"},
            },
        },
        {
            "theme_id": "new-theme",
            "occurrence_count": 9,
            "definition": {
                "rule_id": "CR-0002", "category": "Site",
                "description": "Narrative does not analyze impact of adjacency to a house of worship.",
                "severity": "Advisory", "enabled": False,
                "logic": {"type": "ai", "prompt": "Does the narrative analyze this factor?",
                          "fields": ["subject:VALUATION_ANALYSIS/NEIGHBORHOOD/CommentText"]},
                "citation": "True Footage client revision pattern, 9 occurrences, date range not available in source export",
                "messages": {"appraiser": "x", "reviewer": "x"},
            },
        },
    ]
    candidates_path = _write_candidates_file(tmp_path, candidates)

    result = insert_candidates(candidates_path, db_url=db_url)

    assert result["inserted"] == 2
    assert result["exact_duplicate"] == 1
    assert result["new"] == 1


def test_insert_candidates_flags_and_excludes_suspected_pii(tmp_path, db_url):
    sessions = init_db(db_url)
    candidates = [{
        "theme_id": "pii-leak-theme",
        "occurrence_count": 3,
        "definition": {
            "rule_id": "CR-0003", "category": "Subject Property",
            # Simulates a mining-step mistake: a name leaked into the description.
            "description": "Add Timothy James Henson as owner of public record per revision request.",
            "severity": "Advisory", "enabled": False,
            "logic": {"type": "field_present", "field": "subject:VALUATION_ANALYSIS/PROPERTIES/PROPERTY/OWNER/OwnerName"},
            "citation": "True Footage client revision pattern, 3 occurrences, date range not available in source export",
            "messages": {"appraiser": "x", "reviewer": "x"},
        },
    }]
    candidates_path = _write_candidates_file(tmp_path, candidates)

    result = insert_candidates(candidates_path, db_url=db_url)

    assert result["inserted"] == 0
    assert result["pii_flagged"] == 1
    assert CandidateRulesRepository(sessions).list_candidates("all") == []
