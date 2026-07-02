from __future__ import annotations

from app.models import NormalizedField, NormalizedReport, RawReport, StructuralError

# PLACEHOLDER adapter. Not wired to real reports. It exists to prove the
# SchemaAdapter contract is pluggable and to keep engine tests independent
# of the official GSE files.


class PlaceholderAdapter:
    schema_version = "PLACEHOLDER-0.1"

    def validate(self, raw: RawReport) -> list[StructuralError]:
        return []

    def normalize(self, raw: RawReport) -> NormalizedReport:
        return NormalizedReport(
            schema_version=self.schema_version,
            fields={
                "placeholder.sample_text_field": NormalizedField(
                    value="PLACEHOLDER", label="PLACEHOLDER text field", section="PLACEHOLDER"
                ),
                "placeholder.sample_numeric_field": NormalizedField(
                    value="42", label="PLACEHOLDER numeric field", section="PLACEHOLDER"
                ),
            },
        )
