from __future__ import annotations

from lxml import etree

from app.models import NormalizedField, NormalizedReport, RawReport, StructuralError
from app.schema_adapters.xsd_validator import validate_xml

MISMO_NS = {"m": "http://www.mismo.org/residential/2009/schemas"}

# ASSUMPTION (Phase 1): the subject property is the FIRST <PROPERTY> under
# VALUATION_ANALYSIS/PROPERTIES in document order. Verified true for all three
# official GSE sample files (SF1, SF3, Condo2). Phase 2 replaces this with
# xlink-relationship-based subject/comparable classification (Appendix G-1).
SUBJECT_ADDRESS_XPATH = "//m:VALUATION_ANALYSIS/m:PROPERTIES/m:PROPERTY[1]/m:ADDRESS"

# (field_path, element local name, display label, report section)
# Labels/sections come from Appendix H-1 columns "Report Label" / "Report Section".
SUBJECT_ADDRESS_FIELDS = [
    ("subject.AddressLineText", "AddressLineText", "Physical Address", "Subject Property"),
    ("subject.CityName", "CityName", "Physical Address", "Subject Property"),
    ("subject.CountyName", "CountyName", "County", "Subject Property"),
    ("subject.PostalCode", "PostalCode", "Physical Address", "Subject Property"),
    ("subject.StateCode", "StateCode", "Physical Address", "Subject Property"),
]


class UAD36v13Adapter:
    schema_version = "GSE_UAD_3.6.0_v1.3"

    def __init__(self, xsd_path: str):
        self._xsd_path = xsd_path

    def validate(self, raw: RawReport) -> list[StructuralError]:
        return validate_xml(raw.xml_bytes, self._xsd_path)

    def normalize(self, raw: RawReport) -> NormalizedReport:
        fields: dict[str, NormalizedField] = {}
        try:
            doc = etree.fromstring(raw.xml_bytes)
            address_nodes = doc.xpath(SUBJECT_ADDRESS_XPATH, namespaces=MISMO_NS)
            address = address_nodes[0] if address_nodes else None
        except etree.XMLSyntaxError:
            address = None  # validate() already reported the parse failure
        for field_path, local_name, label, section in SUBJECT_ADDRESS_FIELDS:
            value = None
            if address is not None:
                element = address.find(f"m:{local_name}", MISMO_NS)
                if element is not None and element.text is not None:
                    value = element.text
            fields[field_path] = NormalizedField(
                value=value,
                xpath=f"VALUATION_ANALYSIS/PROPERTIES/PROPERTY[1]/ADDRESS/{local_name}",
                label=label,
                section=section,
            )
        return NormalizedReport(schema_version=self.schema_version, fields=fields)
