from __future__ import annotations

from functools import lru_cache

from lxml import etree

from app.models import StructuralError


@lru_cache(maxsize=4)
def _load_schema(xsd_path: str) -> etree.XMLSchema:
    # ~1.7MB schema; compiled once per process.
    return etree.XMLSchema(etree.parse(xsd_path))


def validate_xml(xml_bytes: bytes, xsd_path: str) -> list[StructuralError]:
    try:
        doc = etree.fromstring(xml_bytes)
    except etree.XMLSyntaxError as exc:
        return [StructuralError(code="XML_PARSE", message=str(exc), location=f"line {exc.lineno}")]
    schema = _load_schema(xsd_path)
    schema.validate(doc)
    return [
        StructuralError(code="XSD", message=e.message, location=f"line {e.line}")
        for e in schema.error_log
    ]
