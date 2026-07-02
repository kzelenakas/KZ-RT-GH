from __future__ import annotations

from typing import Sequence

from app.models import Finding, NormalizedReport, RuleDefinition, RuleError, RunResult
from app.rules.operators import OperatorResult, OPERATORS

# PURE aside from the injected AI backend: no DB, no file I/O in this module.
# The backend is an interface (see ai_backends.py); tests inject fakes.


def _run_ai_rule(rule: RuleDefinition, report: NormalizedReport, ai_backend) -> OperatorResult:
    if ai_backend is None:
        raise RuntimeError("No AI backend configured for logic type 'ai'")
    prompt = str(rule.logic.get("prompt", "")).strip()
    if not prompt:
        raise ValueError("AI rule has no prompt")
    field_keys = list(rule.logic.get("fields", []))
    context = {}
    for key in field_keys:
        field = report.fields.get(key)
        context[key] = field.value if field else None
    result = ai_backend.evaluate(prompt, context)
    values = dict(context)
    if result.triggered and result.rationale:
        values["ai_rationale"] = result.rationale
    return OperatorResult(triggered=result.triggered, values=values)


def evaluate(
    report: NormalizedReport,
    rules: Sequence[RuleDefinition],
    ai_backend=None,
) -> RunResult:
    findings: list[Finding] = []
    errors: list[RuleError] = []
    for rule in rules:
        if not rule.enabled:
            continue
        logic_type = str(rule.logic.get("type", ""))
        if logic_type == "ai":
            try:
                result = _run_ai_rule(rule, report, ai_backend)
            except Exception as exc:  # noqa: BLE001 - AI failure must never kill the run
                errors.append(RuleError(
                    rule_id=rule.rule_id,
                    error_type="ai_error",
                    detail=f"{type(exc).__name__}: {exc}",
                ))
                continue
        else:
            operator = OPERATORS.get(logic_type)
            if operator is None:
                errors.append(RuleError(
                    rule_id=rule.rule_id,
                    error_type="unsupported_logic",
                    detail=f"Unknown logic type: {logic_type!r}",
                ))
                continue
            try:
                result = operator(rule.logic, report)
            except Exception as exc:  # noqa: BLE001 - a broken rule must never kill the run
                errors.append(RuleError(
                    rule_id=rule.rule_id,
                    error_type="execution_error",
                    detail=f"{type(exc).__name__}: {exc}",
                ))
                continue
        if not result.triggered:
            continue
        field_path = str(rule.logic.get("field") or next(iter(rule.logic.get("fields", [])), ""))
        normalized_field = report.fields.get(field_path)
        appraiser = rule.messages.appraiser or rule.messages.reviewer or rule.description
        reviewer = rule.messages.reviewer or rule.messages.appraiser or rule.description
        findings.append(Finding(
            rule_id=rule.rule_id,
            category=rule.category,
            severity=rule.severity,
            message_appraiser=appraiser,
            message_reviewer=reviewer,
            field_path=field_path,
            xpath=normalized_field.xpath if normalized_field else None,
            section=normalized_field.section if normalized_field else None,
            values=result.values,
            citation=rule.citation,
        ))
    return RunResult(findings=findings, rule_errors=errors)
