"""Redundancy check: candidate rule vs. the live rule set, deterministic (no LLM)."""

from app.revision_mining.redundancy_check import check_redundancy

EXISTING_RULES = [
    {
        "rule_id": "UAD1001",
        "description": "Subject property physical address line must be provided.",
        "logic": {"type": "field_present", "field": "subject:VALUATION_ANALYSIS/PROPERTIES/PROPERTY/ADDRESS/AddressLineText"},
    },
    {
        "rule_id": "UAD1099",
        "description": "Comparable sale adjustments must be supported by market data.",
        "logic": {"type": "needs_encoding", "source_logic": "..."},
    },
]


def test_exact_duplicate_same_field_and_logic_type():
    candidate = {
        "description": "Subject address line is required.",
        "logic": {"type": "field_present", "field": "subject:VALUATION_ANALYSIS/PROPERTIES/PROPERTY/ADDRESS/AddressLineText"},
    }
    result = check_redundancy(candidate, EXISTING_RULES)
    assert result["verdict"] == "exact_duplicate"
    assert "UAD1001" in result["notes"]


def test_overlaps_similar_description_no_field_match():
    candidate = {
        "description": "Comparable sale adjustments must be supported by market data and cited.",
        "logic": {"type": "ai", "prompt": "Are adjustments supported?", "fields": []},
    }
    result = check_redundancy(candidate, EXISTING_RULES)
    assert result["verdict"] == "overlaps"
    assert "UAD1099" in result["notes"]


def test_new_no_overlap():
    candidate = {
        "description": "Narrative does not analyze impact of adjacency to a house of worship noted in aerial imagery.",
        "logic": {"type": "ai", "prompt": "Does the narrative analyze this external factor?", "fields": ["subject:VALUATION_ANALYSIS/NEIGHBORHOOD/CommentText"]},
    }
    result = check_redundancy(candidate, EXISTING_RULES)
    assert result["verdict"] == "new"
