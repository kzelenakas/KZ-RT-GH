from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class Severity(str, Enum):
    HARD_STOP = "HardStop"
    WARNING = "Warning"
    ADVISORY = "Advisory"


class Finding(BaseModel):
    rule_id: str
    category: str
    severity: Severity
    message_appraiser: str
    message_reviewer: str
    field_path: str = ""
    xpath: str | None = None
    section: str | None = None
    values: dict[str, str | None] = Field(default_factory=dict)
    citation: str | None = None


class RuleError(BaseModel):
    """A rule that could not execute. Recorded, never fatal to the run."""

    rule_id: str
    error_type: str
    detail: str


class RunResult(BaseModel):
    findings: list[Finding] = Field(default_factory=list)
    rule_errors: list[RuleError] = Field(default_factory=list)
