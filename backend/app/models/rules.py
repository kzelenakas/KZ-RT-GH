from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from .findings import Severity


class RuleMessages(BaseModel):
    model_config = ConfigDict(extra="allow")

    appraiser: str | None = None
    reviewer: str | None = None


class RuleDefinition(BaseModel):
    """External rule contract. Unknown fields are preserved (forward-compatible)."""

    model_config = ConfigDict(extra="allow")

    rule_id: str
    category: str
    description: str = ""
    severity: Severity
    enabled: bool = True
    logic: dict = Field(default_factory=dict)
    citation: str | None = None
    messages: RuleMessages = Field(default_factory=RuleMessages)
