from __future__ import annotations

from typing import Sequence

from app.models import Finding, NormalizedReport, RuleDefinition, RuleError, RunResult
from app.rules.operators import OPERATORS

# PURE: no DB, no HTTP, no file I/O in this module. Input -> output only.


def evaluate(report: NormalizedReport, rules: Sequence[RuleDefinition]) -> RunResult:
    findings: list[Finding] = []
    errors: list[RuleError] = []
    for rule in rules:
        if not rule.enabled:
            continue
        logic_type = str(rule.logic.get("type", ""))
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
        field_path = str(rule.logic.get("field", ""))
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
