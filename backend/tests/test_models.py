from app.models import (
    Finding, NormalizedField, NormalizedReport, RuleDefinition, RunResult, Severity,
)


def test_severity_values():
    assert Severity.HARD_STOP.value == "HardStop"
    assert Severity("Warning") is Severity.WARNING


def test_rule_definition_preserves_unknown_fields():
    rule = RuleDefinition.model_validate({
        "rule_id": "X-1",
        "category": "Test",
        "severity": "Warning",
        "logic": {"type": "field_present", "field": "a.b"},
        "future_field": {"anything": [1, 2]},
        "messages": {"appraiser": "hi", "tone": "gentle"},
    })
    dumped = rule.model_dump()
    assert dumped["future_field"] == {"anything": [1, 2]}
    assert dumped["messages"]["tone"] == "gentle"
    assert rule.enabled is True
    assert rule.citation is None


def test_normalized_report_lookup():
    rep = NormalizedReport(
        schema_version="TEST-1",
        fields={"subject.CityName": NormalizedField(value="Treeville", xpath="/x", label="City", section="Subject")},
    )
    assert rep.fields["subject.CityName"].value == "Treeville"
    assert rep.fields.get("missing") is None


def test_run_result_shape():
    rr = RunResult(findings=[], rule_errors=[])
    assert rr.findings == [] and rr.rule_errors == []
