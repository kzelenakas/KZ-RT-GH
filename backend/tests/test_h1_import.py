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
    assert len(executable) == 76
    assert all(r["logic"]["type"] != "needs_encoding" for r in executable)
    disabled = [r for r in ruleset["rules"] if not r["enabled"]]
    assert all(r["logic"]["type"] == "needs_encoding" for r in disabled)
    # nothing dropped, nothing invented: every disabled rule keeps its source text
    assert all(r["logic"]["source_logic"] for r in disabled)
    assert len(manifest["fields"]) == 73
