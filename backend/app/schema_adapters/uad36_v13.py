from __future__ import annotations

import json
from pathlib import Path

from lxml import etree

from app.models import NormalizedField, NormalizedReport, RawReport, StructuralError
from app.schema_adapters.xsd_validator import validate_xml

# ASSUMPTION (Phase 1/2): the subject property is the FIRST <PROPERTY> under
# VALUATION_ANALYSIS/PROPERTIES in document order. Verified true for all three
# official GSE sample files (SF1, SF3, Condo2). A later phase replaces this with
# xlink-relationship-based subject/comparable classification (Appendix G-1).

# Field extraction is data-driven: schemas/uad36_field_manifest.json (generated
# from Appendix H-1 by app.rules.h1_import) lists every field the ruleset
# references — key, scope ("subject" -> resolved under the subject PROPERTY;
# "doc" -> resolved anywhere in the document), xpath directory, element name,
# display label, and report section. Swapping in a new schema version means a
# new manifest + (if structure changed) a new adapter class. Engine, API,
# persistence, and UI never change.


def _local_steps(path: str) -> list[str]:
    return [s for s in path.split("/") if s]


def _find_first(node, steps: list[str]):
    current = node
    for step in steps:
        if current is None:
            return None
        current = next(
            (child for child in current if etree.iselement(child) and etree.QName(child).localname == step),
            None,
        )
    return current


class UAD36v13Adapter:
    schema_version = "GSE_UAD_3.6.0_v1.3"

    def __init__(self, xsd_path: str, manifest_path: str):
        self._xsd_path = xsd_path
        manifest = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
        self._fields: list[dict] = manifest["fields"]

    def validate(self, raw: RawReport) -> list[StructuralError]:
        return validate_xml(raw.xml_bytes, self._xsd_path)

    def normalize(self, raw: RawReport) -> NormalizedReport:
        try:
            doc = etree.fromstring(raw.xml_bytes)
        except etree.XMLSyntaxError:
            doc = None  # validate() already reported the parse failure
        subject = self._subject_node(doc) if doc is not None else None

        fields: dict[str, NormalizedField] = {}
        for entry in self._fields:
            value = None
            if doc is not None:
                element = self._resolve(doc, subject, entry)
                if element is not None and element.text is not None:
                    value = element.text
            fields[entry["key"]] = NormalizedField(
                value=value,
                xpath=f"{entry['xpath_dir']}{entry['element']}",
                label=entry["label"],
                section=entry["section"],
            )
        return NormalizedReport(schema_version=self.schema_version, fields=fields)

    @staticmethod
    def _subject_node(doc):
        nodes = doc.xpath(
            "//*[local-name()='VALUATION_ANALYSIS']/*[local-name()='PROPERTIES']/*[local-name()='PROPERTY'][1]"
        )
        return nodes[0] if nodes else None

    @staticmethod
    def _resolve(doc, subject, entry: dict):
        steps = _local_steps(entry["xpath_dir"]) + [entry["element"]]
        if entry["scope"] == "subject" and "PROPERTY" in steps:
            if subject is None:
                return None
            rel = steps[steps.index("PROPERTY") + 1:]
            return _find_first(subject, rel)
        # doc scope (or subject-scoped paths outside PROPERTY): first match anywhere
        xpath = "//" + "/".join(f"*[local-name()='{s}']" for s in steps)
        found = doc.xpath(xpath)
        return found[0] if found else None
