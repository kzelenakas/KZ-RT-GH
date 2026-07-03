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


# --- numeric_range: triggers when present AND out of [min, max] (or non-numeric) ---

def test_numeric_range_min_only():
    logic = {"type": "numeric_range", "field": "subject.DwellingCount", "min": 1}
    assert OPERATORS["numeric_range"](logic, make_report(**{"subject.DwellingCount": "0"})).triggered is True
    assert OPERATORS["numeric_range"](logic, make_report(**{"subject.DwellingCount": "1"})).triggered is False
    assert OPERATORS["numeric_range"](logic, make_report()).triggered is False


def test_numeric_range_max_only():
    logic = {"type": "numeric_range", "field": "subject.OpinionOfValueAmount", "max": 1000000000}
    assert OPERATORS["numeric_range"](logic, make_report(**{"subject.OpinionOfValueAmount": "1000000001"})).triggered is True
    assert OPERATORS["numeric_range"](logic, make_report(**{"subject.OpinionOfValueAmount": "500000"})).triggered is False


def test_numeric_range_non_numeric_value_triggers():
    logic = {"type": "numeric_range", "field": "subject.DwellingCount", "min": 1}
    assert OPERATORS["numeric_range"](logic, make_report(**{"subject.DwellingCount": "not-a-number"})).triggered is True


# --- conditional: gates a `then` operator behind an OR-of-AND-groups condition set ---

def _cond_logic(if_any, then_field="subject.PropertyEstateType"):
    return {
        "type": "conditional",
        "if_any": if_any,
        "then": {"type": "field_present", "field": then_field},
    }


def test_conditional_or_group_either_branch_fires():
    logic = _cond_logic([
        [{"field": "subject.PropertyInProjectIndicator", "equals": "false"}],
        [{"field": "subject.ProjectLegalStructureType", "equals": "Condominium"}],
    ])
    # branch 1 true, PET missing -> fires
    r1 = OPERATORS["conditional"](logic, make_report(**{"subject.PropertyInProjectIndicator": "false"}))
    assert r1.triggered is True
    assert r1.values == {"subject.PropertyEstateType": None}
    # branch 2 true (different field), PET missing -> fires
    r2 = OPERATORS["conditional"](logic, make_report(**{"subject.ProjectLegalStructureType": "Condominium"}))
    assert r2.triggered is True
    # neither branch true -> does not fire even though PET missing
    r3 = OPERATORS["conditional"](logic, make_report(**{"subject.PropertyInProjectIndicator": "true"}))
    assert r3.triggered is False


def test_conditional_and_group_requires_every_condition():
    logic = _cond_logic([
        [{"field": "subject.PropertyEstateType", "equals": "Leasehold"},
         {"field": "subject.LandOwnedInCommonIndicator", "equals": "false"}],
    ], then_field="subject.PropertyGroundLeaseAnnualAmount")
    # only one of two AND conditions true -> does not fire
    partial = OPERATORS["conditional"](logic, make_report(**{
        "subject.PropertyEstateType": "Leasehold",
        "subject.LandOwnedInCommonIndicator": "true",
    }))
    assert partial.triggered is False
    # both true, then-field missing -> fires
    full = OPERATORS["conditional"](logic, make_report(**{
        "subject.PropertyEstateType": "Leasehold",
        "subject.LandOwnedInCommonIndicator": "false",
    }))
    assert full.triggered is True


def test_conditional_condition_true_but_then_field_present_does_not_fire():
    logic = _cond_logic([[{"field": "subject.PropertyInProjectIndicator", "equals": "false"}]])
    result = OPERATORS["conditional"](logic, make_report(**{
        "subject.PropertyInProjectIndicator": "false",
        "subject.PropertyEstateType": "FeeSimple",
    }))
    assert result.triggered is False


def test_conditional_missing_condition_field_is_treated_as_false_not_error():
    logic = _cond_logic([[{"field": "subject.PropertyInProjectIndicator", "equals": "false"}]])
    result = OPERATORS["conditional"](logic, make_report())
    assert result.triggered is False


def test_conditional_not_equals_and_in_comparators():
    ne_logic = _cond_logic([[{"field": "subject.SaleType", "not_equals": "Other"}]])
    assert OPERATORS["conditional"](ne_logic, make_report(**{"subject.SaleType": "Standard"})).triggered is True
    assert OPERATORS["conditional"](ne_logic, make_report(**{"subject.SaleType": "Other", "subject.PropertyEstateType": "x"})).triggered is False

    in_logic = _cond_logic([[{"field": "subject.PartyRoleType", "in": ["Lender", "ManagementCompany"]}]],
                            then_field="subject.FullName")
    assert OPERATORS["conditional"](in_logic, make_report(**{"subject.PartyRoleType": "Lender"})).triggered is True
    assert OPERATORS["conditional"](in_logic, make_report(**{"subject.PartyRoleType": "Appraiser"})).triggered is False


def test_conditional_then_type_unsupported_raises():
    logic = {
        "type": "conditional",
        "if_any": [[{"field": "subject.X", "equals": "true"}]],
        "then": {"type": "not_a_real_operator", "field": "subject.Y"},
    }
    with pytest.raises(ValueError):
        OPERATORS["conditional"](logic, make_report(**{"subject.X": "true"}))
