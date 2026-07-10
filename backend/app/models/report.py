from __future__ import annotations

from pydantic import BaseModel, Field


class RawReport(BaseModel):
    """Extracted contents of one report delivery. Read-only input to adapters."""

    source_filename: str
    xml_bytes: bytes
    pdf_filename: str | None = None
    image_filenames: list[str] = Field(default_factory=list)
    # filename -> raw photo bytes, Images/ folder only. Phase 2/3
    # (collateral_risk_engine.evaluate_photos) needs actual pixel data, not
    # just names -- image_filenames alone (above) was sufficient for Phase 1.
    images: dict[str, bytes] = Field(default_factory=dict)


class NormalizedField(BaseModel):
    value: str | None = None
    xpath: str | None = None
    label: str | None = None
    section: str | None = None


class NormalizedReport(BaseModel):
    """The only thing the rule engine ever reads."""

    schema_version: str
    fields: dict[str, NormalizedField] = Field(default_factory=dict)


class StructuralError(BaseModel):
    """Schema/structural failure. Rendered separately from rule findings."""

    code: str
    message: str
    location: str | None = None
