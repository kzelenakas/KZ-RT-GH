"""AI rule type: engine integration with injected backends (no network)."""

import pytest

from app.models import NormalizedField, NormalizedReport, RuleDefinition
from app.rules import evaluate
from app.rules.ai_backends import AIResult, StubBackend, _parse_ai_json, build_backend


class FiringBackend:
    name = "fake"

    def __init__(self):
        self.calls = []

    def evaluate(self, prompt, context):
        self.calls.append((prompt, context))
        return AIResult(triggered=True, rationale="Commentary appears boilerplate.")


class ExplodingBackend:
    name = "boom"

    def evaluate(self, prompt, context):
        raise ConnectionError("model unavailable")


REPORT = NormalizedReport(
    schema_version="TEST",
    fields={"doc:X/MarketCommentary": NormalizedField(value="The market is stable.", section="Market")},
)


def ai_rule(**overrides) -> RuleDefinition:
    base = {
        "rule_id": "AI-DEMO-1",
        "category": "Market Analysis",
        "description": "Flag boilerplate market commentary.",
        "severity": "Advisory",
        "logic": {
            "type": "ai",
            "prompt": "Does this market commentary read as generic boilerplate?",
            "fields": ["doc:X/MarketCommentary"],
        },
        "messages": {"appraiser": "Commentary looks generic.", "reviewer": "Boilerplate commentary detected."},
    }
    base.update(overrides)
    return RuleDefinition.model_validate(base)


def test_ai_rule_fires_with_rationale_and_context():
    backend = FiringBackend()
    result = evaluate(REPORT, [ai_rule()], ai_backend=backend)
    assert len(result.findings) == 1
    finding = result.findings[0]
    assert finding.values["ai_rationale"] == "Commentary appears boilerplate."
    assert finding.values["doc:X/MarketCommentary"] == "The market is stable."
    assert finding.field_path == "doc:X/MarketCommentary"
    assert finding.section == "Market"
    prompt, context = backend.calls[0]
    assert "boilerplate" in prompt
    assert context == {"doc:X/MarketCommentary": "The market is stable."}


def test_stub_backend_never_fires():
    result = evaluate(REPORT, [ai_rule()], ai_backend=StubBackend())
    assert result.findings == [] and result.rule_errors == []


def test_ai_backend_failure_recorded_not_raised():
    result = evaluate(REPORT, [ai_rule()], ai_backend=ExplodingBackend())
    assert result.findings == []
    assert result.rule_errors[0].error_type == "ai_error"
    assert "model unavailable" in result.rule_errors[0].detail


def test_ai_rule_without_backend_records_error():
    result = evaluate(REPORT, [ai_rule()], ai_backend=None)
    assert result.rule_errors[0].error_type == "ai_error"


def test_ai_rule_without_prompt_records_error():
    rule = ai_rule(logic={"type": "ai", "fields": []})
    result = evaluate(REPORT, [rule], ai_backend=StubBackend())
    assert result.rule_errors[0].error_type == "ai_error"


def test_parse_ai_json_tolerates_wrapping_text():
    result = _parse_ai_json('Sure! {"triggered": true, "explanation": "Generic."} Hope that helps.')
    assert result.triggered is True and result.rationale == "Generic."
    with pytest.raises(ValueError):
        _parse_ai_json("no json here")


def test_build_backend_validation():
    assert build_backend("stub").name == "stub"
    assert build_backend("gemini", gemini_api_key="k").name == "gemini"
    with pytest.raises(ValueError):
        build_backend("gemini")
    with pytest.raises(ValueError):
        build_backend("vertex")
    with pytest.raises(ValueError):
        build_backend("skynet")


def test_glba_guardrail_blocks_gemini_on_real_data(monkeypatch, tmp_path):
    monkeypatch.setenv("QC_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("QC_DATA_CLASS", "real")
    monkeypatch.setenv("QC_AI_BACKEND", "gemini")
    monkeypatch.setenv("QC_GEMINI_API_KEY", "test-key")
    import importlib

    import app.config
    importlib.reload(app.config)
    from app.main import create_app
    with pytest.raises(RuntimeError, match="GLBA"):
        create_app()
    # restore config for later tests
    monkeypatch.delenv("QC_DATA_CLASS")
    monkeypatch.delenv("QC_AI_BACKEND")
    monkeypatch.delenv("QC_GEMINI_API_KEY")
    importlib.reload(app.config)
