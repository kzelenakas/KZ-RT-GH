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
                value = self._resolve_value(doc, subject, entry)
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
    def _split_attribute(steps: list[str]) -> tuple[list[str], str | None]:
        """H-1 xpaths address XML attributes as '.../@' + name (e.g.
        MESSAGE/@MISMOReferenceModelIdentifier). Split node steps from the
        attribute name."""
        node_steps: list[str] = []
        for i, step in enumerate(steps):
            if step == "@":
                return node_steps, (steps[i + 1] if i + 1 < len(steps) else None)
            if step.startswith("@"):
                return node_steps, step[1:]
            node_steps.append(step)
        return node_steps, None

    @classmethod
    def _resolve_value(cls, doc, subject, entry: dict) -> str | None:
        steps = _local_steps(entry["xpath_dir"]) + [entry["element"]]
        node_steps, attribute = cls._split_attribute(steps)
        if entry["scope"] == "subject" and "PROPERTY" in node_steps:
            if subject is None:
                return None
            rel = node_steps[node_steps.index("PROPERTY") + 1:]
            node = _find_first(subject, rel)
        elif node_steps:
            # doc scope (or subject-scoped paths outside PROPERTY): first match
            # anywhere. The document root itself (e.g. MESSAGE) is matched too.
            xpath = "//" + "/".join(f"*[local-name()='{s}']" for s in node_steps)
            found = doc.xpath(xpath)
            node = found[0] if found else None
            if node is None and etree.QName(doc).localname == node_steps[0]:
                node = _find_first(doc, node_steps[1:]) if len(node_steps) > 1 else doc
        else:
            node = doc
        if node is None:
            return None
        if attribute:
            return node.get(attribute)
        return node.text
