from pathlib import Path

from app.rules.h1_import import convert_row, import_h1
from tests.conftest import REPO_ROOT

H1_CSV = REPO_ROOT / "QC_rules" / "Appendix H-1 - Compliance Rules - UAD Compliance Rules v1.4.csv"


def base_row(**overrides) -> dict:
    row = {
        "Unique ID": "0100.0009",
        "Primary Data Element": "CityName",
        "Message ID": "UAD1002",
        "Message Text": "Provide the city name.",
        "Rule Logic": "If CityName is not provided",
        "Severity": "Fatal",
        "Property Affected": "Subject",
        "Report Section": "Subject Property",
        "Report Subsection": "{No Subsection}",
        "Report Label / Value": "Physical Address",
        "Data Point Name / Value": "CityName",
        "xPath": "../VALUATION_ANALYSIS/PROPERTIES/PROPERTY/ADDRESS/",
        "Date Format": "",
        "Min Value": "",
        "Max Value": "",
    }
    row.update(overrides)
    return row


def test_simple_not_provided_becomes_field_present():
    rule, manifest = convert_row(base_row())
    assert rule["enabled"] is True
    assert rule["logic"] == {
        "type": "field_present",
        "field": "subject:VALUATION_ANALYSIS/PROPERTIES/PROPERTY/ADDRESS/CityName",
    }
    assert rule["severity"] == "HardStop"
    assert rule["citation"] == "UAD 3.6 Appendix H-1 v1.4, Unique ID 0100.0009, Message ID UAD1002"
    assert manifest["section"] == "Subject Property"


def test_instance_quantifier_is_not_converted():
    rule, manifest = convert_row(base_row(
        **{"Rule Logic": 'If ImprovementType is not "Dwelling" in at least one instance of IMPROVEMENT_DETAIL',
           "Min Value": "1"}
    ))
    assert rule["enabled"] is False
    assert rule["logic"]["type"] == "needs_encoding"
    assert "at least one instance" in rule["logic"]["source_logic"]
    assert manifest is None


def test_comparable_scope_is_not_converted():
    rule, manifest = convert_row(base_row(**{"Property Affected": "Sales Comparable #n"}))
    assert rule["enabled"] is False
    assert rule["logic"]["type"] == "needs_encoding"
    assert manifest is None


def test_zip_format_rule_becomes_regex():
    rule, _ = convert_row(base_row(
        **{"Primary Data Element": "PostalCode",
           "Rule Logic": "If PostalCode is not in the required format (5 digits, or 5 digits, a hyphen, and 4 digits)"}
    ))
    assert rule["logic"]["type"] == "regex_match"
    assert rule["logic"]["pattern"] == r"\d{5}(-\d{4})?"


def test_state_code_rule_becomes_field_in_set():
    rule, _ = convert_row(base_row(
        **{"Primary Data Element": "StateCode",
           "Rule Logic": "If StateCode is not a valid 2-character US State or Territory Code"}
    ))
    assert rule["logic"]["type"] == "field_in_set"
    assert "VA" in rule["logic"]["allowed"]


def test_date_format_rule_becomes_regex():
    rule, _ = convert_row(base_row(
        **{"Primary Data Element": "AppraisalEffectiveDate",
           "Rule Logic": "If AppraisalEffectiveDate is not in the required format",
           "Date Format": "CCYY-MM-DD"}
    ))
    assert rule["logic"] == {
        "type": "regex_match",
        "field": "subject:VALUATION_ANALYSIS/PROPERTIES/PROPERTY/ADDRESS/AppraisalEffectiveDate",
        "pattern": r"\d{4}-\d{2}-\d{2}",
    }


def test_full_import_counts():
    if not H1_CSV.exists():
        import pytest
        pytest.skip("H-1 csv not present")
    ruleset, manifest = import_h1(H1_CSV)
    assert len(ruleset["rules"]) == 729
    executable = [r for r in ruleset["rules"] if r["enabled"]]
    assert len(executable) == 163
    assert all(r["logic"]["type"] != "needs_encoding" for r in executable)
    disabled = [r for r in ruleset["rules"] if not r["enabled"]]
    assert all(r["logic"]["type"] == "needs_encoding" for r in disabled)
    # nothing dropped, nothing invented: every disabled rule keeps its source text
    assert all(r["logic"]["source_logic"] for r in disabled)
    assert len(manifest["fields"]) == 163


# --- numeric_range: "If <own element> < / > N", nothing else in the text ---

def test_numeric_lt_becomes_numeric_range_min():
    rule, manifest = convert_row(base_row(
        **{"Primary Data Element": "DwellingCount", "Rule Logic": "If DwellingCount < 1"}
    ))
    assert rule["enabled"] is True
    assert rule["logic"] == {
        "type": "numeric_range",
        "field": "subject:VALUATION_ANALYSIS/PROPERTIES/PROPERTY/ADDRESS/DwellingCount",
        "min": 1,
    }
    assert manifest is not None


def test_numeric_gt_becomes_numeric_range_max_with_comma_thousands():
    rule, _ = convert_row(base_row(
        **{"Primary Data Element": "OpinionOfValueAmount",
           "Rule Logic": "If OpinionOfValueAmount > 1,000,000,000"}
    ))
    assert rule["logic"]["type"] == "numeric_range"
    assert rule["logic"]["max"] == 1000000000


def test_numeric_comparison_against_another_field_is_not_converted():
    # "If DwellingCount > LivingUnitExcludingADUCount" — not a literal number, stays needs_encoding.
    rule, manifest = convert_row(base_row(
        **{"Primary Data Element": "DwellingCount",
           "Rule Logic": "If DwellingCount > LivingUnitExcludingADUCount"}
    ))
    assert rule["logic"]["type"] == "needs_encoding"
    assert manifest is None


# --- conditional: "If <condition(s)>, and <element> is not provided" ---

def test_single_condition_becomes_conditional():
    index = {"CostApproachIndicator": "subject:VALUATION_ANALYSIS/PROPERTIES/PROPERTY/APPROACH/CostApproachIndicator"}
    rule, manifest = convert_row(base_row(
        **{"Primary Data Element": "SiteEstimatedValueAmount",
           "Rule Logic": 'If CostApproachIndicator = "true", and SiteEstimatedValueAmount is not provided'}
    ), index)
    assert rule["enabled"] is True
    assert rule["logic"] == {
        "type": "conditional",
        "if_any": [[{"field": index["CostApproachIndicator"], "equals": "true"}]],
        "then": {
            "type": "field_present",
            "field": "subject:VALUATION_ANALYSIS/PROPERTIES/PROPERTY/ADDRESS/SiteEstimatedValueAmount",
        },
    }
    assert manifest is not None


def test_and_chain_condition_becomes_single_and_group():
    index = {
        "PropertyEstateType": "subject:.../PropertyEstateType",
        "LandOwnedInCommonIndicator": "subject:.../LandOwnedInCommonIndicator",
    }
    rule, _ = convert_row(base_row(
        **{"Primary Data Element": "PropertyGroundLeaseAnnualAmount",
           "Rule Logic": 'If PropertyEstateType = "Leasehold" and LandOwnedInCommonIndicator = "false", '
                         'and PropertyGroundLeaseAnnualAmount is not provided'}
    ), index)
    assert rule["logic"]["type"] == "conditional"
    assert rule["logic"]["if_any"] == [[
        {"field": index["PropertyEstateType"], "equals": "Leasehold"},
        {"field": index["LandOwnedInCommonIndicator"], "equals": "false"},
    ]]


def test_or_group_condition_becomes_two_and_groups():
    index = {
        "PropertyInProjectIndicator": "subject:.../PropertyInProjectIndicator",
        "ProjectLegalStructureType": "subject:.../ProjectLegalStructureType",
    }
    rule, _ = convert_row(base_row(
        **{"Primary Data Element": "PropertyEstateType",
           "Rule Logic": 'If (PropertyInProjectIndicator = "false" or ProjectLegalStructureType = "Condominium"), '
                         'and PropertyEstateType is not provided'}
    ), index)
    assert rule["logic"]["if_any"] == [
        [{"field": index["PropertyInProjectIndicator"], "equals": "false"}],
        [{"field": index["ProjectLegalStructureType"], "equals": "Condominium"}],
    ]


def test_same_field_or_shorthand_expands_to_two_groups():
    index = {"PropertyEstateType": "subject:.../PropertyEstateType"}
    rule, _ = convert_row(base_row(
        **{"Primary Data Element": "CommunityLandTrustIndicator",
           "Rule Logic": 'If PropertyEstateType = "Leasehold" or "Other", '
                         'and CommunityLandTrustIndicator is not provided'}
    ), index)
    assert rule["logic"]["if_any"] == [
        [{"field": index["PropertyEstateType"], "equals": "Leasehold"}],
        [{"field": index["PropertyEstateType"], "equals": "Other"}],
    ]


def test_mixed_and_or_condition_distributes_correctly():
    index = {
        "NewConstructionIndicator": "subject:.../NewConstructionIndicator",
        "PropertyValuationConditionalConclusionType": "doc:.../PropertyValuationConditionalConclusionType",
    }
    rule, _ = convert_row(base_row(
        **{"Primary Data Element": "PropertyAsIsConditionRatingCode",
           "Rule Logic": 'If NewConstructionIndicator = "false" and '
                         '(PropertyValuationConditionalConclusionType = "SubjectToCompletionPerPlans" or "SubjectToRepair") '
                         'and PropertyAsIsConditionRatingCode is not provided'}
    ), index)
    assert rule["logic"]["if_any"] == [
        [{"field": index["NewConstructionIndicator"], "equals": "false"},
         {"field": index["PropertyValuationConditionalConclusionType"], "equals": "SubjectToCompletionPerPlans"}],
        [{"field": index["NewConstructionIndicator"], "equals": "false"},
         {"field": index["PropertyValuationConditionalConclusionType"], "equals": "SubjectToRepair"}],
    ]


def test_condition_with_instance_of_is_not_converted():
    rule, manifest = convert_row(base_row(
        **{"Primary Data Element": "ManufacturedHomeManufactureDate",
           "Rule Logic": 'If ImprovementType = "Dwelling" and there are no instances of X, '
                         'and ManufacturedHomeManufactureDate is not provided'}
    ), {"ImprovementType": "subject:.../ImprovementType"})
    assert rule["logic"]["type"] == "needs_encoding"
    assert manifest is None


def test_condition_field_unresolvable_falls_back_to_needs_encoding():
    # element_index has no entry for CostApproachIndicator -> can't build the field key -> stays needs_encoding.
    rule, manifest = convert_row(base_row(
        **{"Primary Data Element": "SiteEstimatedValueAmount",
           "Rule Logic": 'If CostApproachIndicator = "true", and SiteEstimatedValueAmount is not provided'}
    ), element_index={})
    assert rule["logic"]["type"] == "needs_encoding"
    assert manifest is None


def test_condition_field_not_in_element_index_without_index_arg_defaults_safe():
    # convert_row(row) with no element_index arg at all — old call signature still works.
    rule, manifest = convert_row(base_row(
        **{"Primary Data Element": "SiteEstimatedValueAmount",
           "Rule Logic": 'If CostApproachIndicator = "true", and SiteEstimatedValueAmount is not provided'}
    ))
    assert rule["logic"]["type"] == "needs_encoding"


def test_full_import_new_rule_counts_by_type():
    if not H1_CSV.exists():
        import pytest
        pytest.skip("H-1 csv not present")
    ruleset, _ = import_h1(H1_CSV)
    from collections import Counter
    counts = Counter(r["logic"]["type"] for r in ruleset["rules"])
    assert counts["field_present"] == 62
    assert counts["regex_match"] == 13
    assert counts["field_in_set"] == 1
    assert counts["numeric_range"] == 4
    assert counts["conditional"] == 83
    assert counts["needs_encoding"] == 566
    assert sum(counts.values()) == 729


def test_full_import_known_unresolvable_conditions_stay_needs_encoding():
    # UAD1229/UAD1231 reference SiteValueIndicator, which is never itself a Primary
    # Data Element anywhere in H-1 — no xPath to resolve it from, so it must not be
    # guessed at even though the rest of the condition parses cleanly.
    if not H1_CSV.exists():
        import pytest
        pytest.skip("H-1 csv not present")
    ruleset, _ = import_h1(H1_CSV)
    by_id = {r["rule_id"]: r for r in ruleset["rules"]}
    for rid in ("UAD1229", "UAD1231", "UAD1110", "UAD1119", "UAD1136", "UAD1343", "UAD1425"):
        assert by_id[rid]["logic"]["type"] == "needs_encoding", rid
