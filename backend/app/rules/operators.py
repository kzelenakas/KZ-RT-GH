from __future__ import annotations

import re
from typing import Callable

from pydantic import BaseModel, Field

from app.models import NormalizedReport


class OperatorResult(BaseModel):
    triggered: bool
    values: dict[str, str | None] = Field(default_factory=dict)


OperatorFn = Callable[[dict, NormalizedReport], OperatorResult]


def _value(report: NormalizedReport, field_path: str) -> str | None:
    field = report.fields.get(field_path)
    return field.value if field is not None else None


def field_present(logic: dict, report: NormalizedReport) -> OperatorResult:
    value = _value(report, logic["field"])
    missing = value is None or str(value).strip() == ""
    return OperatorResult(triggered=missing, values={logic["field"]: value})


def regex_match(logic: dict, report: NormalizedReport) -> OperatorResult:
    value = _value(report, logic["field"])
    if value is None or str(value).strip() == "":
        # Presence is a separate rule (mirrors H-1, e.g. UAD1004 vs UAD1005).
        return OperatorResult(triggered=False)
    ok = re.fullmatch(logic["pattern"], str(value)) is not None
    return OperatorResult(triggered=not ok, values={logic["field"]: value})


def field_in_set(logic: dict, report: NormalizedReport) -> OperatorResult:
    value = _value(report, logic["field"])
    if value is None or str(value).strip() == "":
        return OperatorResult(triggered=False)
    allowed = set(logic["allowed"])
    return OperatorResult(triggered=str(value) not in allowed, values={logic["field"]: value})


def numeric_range(logic: dict, report: NormalizedReport) -> OperatorResult:
    value = _value(report, logic["field"])
    if value is None or str(value).strip() == "":
        return OperatorResult(triggered=False)
    try:
        number = float(str(value).replace(",", ""))
    except ValueError:
        return OperatorResult(triggered=True, values={logic["field"]: value})
    low, high = logic.get("min"), logic.get("max")
    out_of_range = (low is not None and number < low) or (high is not None and number > high)
    return OperatorResult(triggered=out_of_range, values={logic["field"]: value})


OPERATORS: dict[str, OperatorFn] = {
    "field_present": field_present,
    "regex_match": regex_match,
    "field_in_set": field_in_set,
    "numeric_range": numeric_range,
}


def _condition_true(cond: dict, report: NormalizedReport) -> bool:
    value = _value(report, cond["field"])
    text = "" if value is None else str(value)
    if "equals" in cond:
        return text == cond["equals"]
    if "not_equals" in cond:
        return text != cond["not_equals"]
    if "in" in cond:
        return text in cond["in"]
    raise ValueError(f"conditional condition has no comparator: {cond!r}")


def conditional(logic: dict, report: NormalizedReport) -> OperatorResult:
    """Gate another operator behind an OR-of-AND-groups condition set.

    ``if_any``: list of AND-groups; each group is a list of {field, equals|not_equals|in}
    conditions. The rule fires when at least one group is fully true AND the ``then``
    operator (itself one of the operators above, e.g. field_present) triggers.
    A field missing when evaluating a condition simply makes that condition false —
    it never raises, mirroring how the other operators treat absence.
    """
    groups = logic.get("if_any") or []
    if not any(all(_condition_true(cond, report) for cond in group) for group in groups):
        return OperatorResult(triggered=False)
    then = logic.get("then") or {}
    then_fn = OPERATORS.get(str(then.get("type", "")))
    if then_fn is None:
        raise ValueError(f"conditional.then has unsupported type: {then.get('type')!r}")
    return then_fn(then, report)


OPERATORS["conditional"] = conditional
