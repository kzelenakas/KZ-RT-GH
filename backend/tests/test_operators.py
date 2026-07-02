import pytest

from app.models import NormalizedField, NormalizedReport
from app.rules.operators import OPERATORS


def make_report(**values) -> NormalizedReport:
    return NormalizedReport(
        schema_version="TEST",
        fields={k: NormalizedField(value=v) for k, v in values.items()},
    )


# --- field_present: triggers when the field is missing or blank ---

@pytest.mark.parametrize("report,expected", [
    (make_report(**{"subject.CityName": "Treeville"}), False),
    (make_report(**{"subject.CityName": ""}), True),
    (make_report(**{"subject.CityName": "   "}), True),
    (make_report(**{"subject.CityName": None}), True),
    (make_report(), True),  # field entirely absent
])
def test_field_present(report, expected):
    result = OPERATORS["field_present"]({"type": "field_present", "field": "subject.CityName"}, report)
    assert result.triggered is expected


# --- regex_match: triggers when present AND not matching; absent = no trigger ---

@pytest.mark.parametrize("value,expected", [
    ("12345", False),
    ("12345-6789", False),
    ("1234", True),
    ("123456", True),
    ("12345-67", True),
])
def test_regex_match(value, expected):
    logic = {"type": "regex_match", "field": "subject.PostalCode", "pattern": r"\d{5}(-\d{4})?"}
    result = OPERATORS["regex_match"](logic, make_report(**{"subject.PostalCode": value}))
    assert result.triggered is expected
    assert result.values == {"subject.PostalCode": value}


def test_regex_match_absent_field_does_not_trigger():
    logic = {"type": "regex_match", "field": "subject.PostalCode", "pattern": r"\d{5}"}
    assert OPERATORS["regex_match"](logic, make_report()).triggered is False


# --- field_in_set: triggers when present AND value not in allowed set ---

def test_field_in_set():
    logic = {"type": "field_in_set", "field": "subject.StateCode", "allowed": ["VA", "MD"]}
    assert OPERATORS["field_in_set"](logic, make_report(**{"subject.StateCode": "VA"})).triggered is False
    assert OPERATORS["field_in_set"](logic, make_report(**{"subject.StateCode": "ZZ"})).triggered is True
    assert OPERATORS["field_in_set"](logic, make_report()).triggered is False
