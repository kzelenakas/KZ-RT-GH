from __future__ import annotations

from typing import Protocol, runtime_checkable

from app.models import NormalizedReport, RawReport, StructuralError


@runtime_checkable
class SchemaAdapter(Protocol):
    """Contract for mapping one schema version into the normalized model.

    To integrate a new UAD schema version: implement this protocol in a new
    module, set a unique schema_version string, and return it from
    get_default_adapter() (or extend the registry). UI, engine, persistence,
    and exports never change.
    """

    schema_version: str

    def validate(self, raw: RawReport) -> list[StructuralError]: ...

    def normalize(self, raw: RawReport) -> NormalizedReport: ...
