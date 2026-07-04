"""CandidateRulesRepository: bulk insert, list/filter, get, review status transitions."""

from app.persistence import CandidateRulesRepository, init_db

VALID_DEFINITION = {
    "rule_id": "CR-0001",
    "category": "Site",
    "description": "Narrative does not analyze impact of adjacent external land use noted in map/aerial imagery.",
    "severity": "Advisory",
    "enabled": False,
    "logic": {"type": "ai", "prompt": "Does the narrative analyze the impact of the noted external factor on marketability/value?",
              "fields": ["subject:VALUATION_ANALYSIS/NEIGHBORHOOD/CommentText"]},
    "citation": "True Footage client revision pattern, 12 occurrences, date range not available in source export",
    "messages": {"appraiser": "Coaching text.", "reviewer": "Audit text."},
}


def _repo(tmp_path):
    sessions = init_db(f"sqlite:///{tmp_path}/test.db")
    return CandidateRulesRepository(sessions)


def test_bulk_insert_and_list(tmp_path):
    repo = _repo(tmp_path)
    inserted = repo.bulk_insert([{
        "definition": VALID_DEFINITION,
        "theme_id": "site-external-factor-not-analyzed",
        "occurrence_count": 12,
        "date_range_start": None,
        "date_range_end": None,
        "redundancy_verdict": "new",
        "redundancy_notes": "No matching field/logic found in the existing rule set.",
    }])
    assert inserted == 1
    items = repo.list_candidates("all")
    assert len(items) == 1
    assert items[0]["rule_id"] == "CR-0001"
    assert items[0]["occurrence_count"] == 12
    assert items[0]["review_status"] == "pending"


def test_bulk_insert_skips_existing_rule_id(tmp_path):
    repo = _repo(tmp_path)
    row = {
        "definition": VALID_DEFINITION, "theme_id": "t1", "occurrence_count": 5,
        "date_range_start": None, "date_range_end": None,
        "redundancy_verdict": "new", "redundancy_notes": "",
    }
    assert repo.bulk_insert([row]) == 1
    assert repo.bulk_insert([row]) == 0  # already exists, not re-inserted


def test_list_candidates_filters_by_status(tmp_path):
    repo = _repo(tmp_path)
    repo.bulk_insert([{
        "definition": VALID_DEFINITION, "theme_id": "t1", "occurrence_count": 5,
        "date_range_start": None, "date_range_end": None,
        "redundancy_verdict": "new", "redundancy_notes": "",
    }])
    assert len(repo.list_candidates("pending")) == 1
    assert len(repo.list_candidates("approved")) == 0


def test_mark_reviewed_updates_status_and_reviewer(tmp_path):
    repo = _repo(tmp_path)
    repo.bulk_insert([{
        "definition": VALID_DEFINITION, "theme_id": "t1", "occurrence_count": 5,
        "date_range_start": None, "date_range_end": None,
        "redundancy_verdict": "new", "redundancy_notes": "",
    }])
    updated = repo.mark_reviewed("CR-0001", "approved", "kevin.zelenakas")
    assert updated["review_status"] == "approved"
    assert updated["reviewed_by"] == "kevin.zelenakas"
    assert updated["reviewed_at"] is not None


def test_mark_reviewed_returns_none_for_unknown_id(tmp_path):
    repo = _repo(tmp_path)
    assert repo.mark_reviewed("CR-9999", "approved", "kevin.zelenakas") is None


def test_get_candidate_returns_none_for_unknown_id(tmp_path):
    repo = _repo(tmp_path)
    assert repo.get_candidate("CR-9999") is None
