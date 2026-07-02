from app.models import NormalizedField, NormalizedReport, RuleDefinition, Severity
from app.rules import evaluate


def make_rule(**overrides) -> RuleDefinition:
    base = {
        "rule_id": "T-1",
        "category": "Test Category",
        "description": "Field must be present.",
        "severity": "HardStop",
        "logic": {"type": "field_present", "field": "subject.CityName"},
        "messages": {"appraiser": "Coach: add the city.", "reviewer": "Audit: CityName missing."},
    }
    base.update(overrides)
    return RuleDefinition.model_validate(base)


EMPTY = NormalizedReport(schema_version="TEST", fields={})
FILLED = NormalizedReport(
    schema_version="TEST",
    fields={"subject.CityName": NormalizedField(value="Treeville", xpath="/m/ADDRESS/CityName", section="Subject Property")},
)


def test_triggered_rule_produces_finding_with_location():
    result = evaluate(EMPTY, [make_rule()])
    assert len(result.findings) == 1
    f = result.findings[0]
    assert f.rule_id == "T-1"
    assert f.severity is Severity.HARD_STOP
    assert f.message_appraiser == "Coach: add the city."
    assert f.message_reviewer == "Audit: CityName missing."
    assert f.field_path == "subject.CityName"
    assert result.rule_errors == []


def test_finding_carries_xpath_and_section_from_normalized_field():
    rule = make_rule(logic={"type": "field_in_set", "field": "subject.CityName", "allowed": ["Elsewhere"]})
    result = evaluate(FILLED, [rule])
    assert result.findings[0].xpath == "/m/ADDRESS/CityName"
    assert result.findings[0].section == "Subject Property"
    assert result.findings[0].values == {"subject.CityName": "Treeville"}


def test_clean_pass():
    result = evaluate(FILLED, [make_rule()])
    assert result.findings == [] and result.rule_errors == []


def test_disabled_rule_is_skipped():
    result = evaluate(EMPTY, [make_rule(enabled=False)])
    assert result.findings == [] and result.rule_errors == []


def test_unknown_logic_type_records_error_and_continues():
    rules = [make_rule(rule_id="BAD", logic={"type": "quantum_check"}), make_rule(rule_id="GOOD")]
    result = evaluate(EMPTY, rules)
    assert [e.rule_id for e in result.rule_errors] == ["BAD"]
    assert result.rule_errors[0].error_type == "unsupported_logic"
    assert [f.rule_id for f in result.findings] == ["GOOD"]


def test_operator_exception_recorded_not_raised():
    # regex_match without 'pattern' raises KeyError inside the operator
    bad = make_rule(rule_id="BOOM", logic={"type": "regex_match", "field": "subject.CityName"})
    result = evaluate(FILLED, [bad])
    assert result.rule_errors[0].error_type == "execution_error"
    assert result.findings == []


def test_message_fallback_single_variant_used_for_both():
    rule = make_rule(messages={"reviewer": "Only audit text."})
    result = evaluate(EMPTY, [rule])
    assert result.findings[0].message_appraiser == "Only audit text."
    assert result.findings[0].message_reviewer == "Only audit text."


def test_message_fallback_to_description():
    rule = make_rule(messages={})
    result = evaluate(EMPTY, [rule])
    assert result.findings[0].message_appraiser == "Field must be present."
