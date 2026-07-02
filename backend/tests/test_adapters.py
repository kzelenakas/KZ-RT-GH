import zipfile

import pytest

from app.models import RawReport
from app.schema_adapters import PlaceholderAdapter, UAD36v13Adapter, get_default_adapter
from tests.conftest import MANIFEST_PATH, SAMPLES_DIR, SUBJECT_ADDRESS, XSD_PATH

needs_official_files = pytest.mark.skipif(
    not (SAMPLES_DIR.exists() and XSD_PATH.exists() and MANIFEST_PATH.exists()),
    reason="official GSE files / generated manifest not present",
)


def sf1_raw() -> RawReport:
    with zipfile.ZipFile(SAMPLES_DIR / "SF1_Appraisal_v1.4.zip") as zf:
        xml = zf.read("SF1_Appraisal_v1.4.xml")
    return RawReport(source_filename="SF1_Appraisal_v1.4.zip", xml_bytes=xml)


def make_adapter() -> UAD36v13Adapter:
    return UAD36v13Adapter(str(XSD_PATH), str(MANIFEST_PATH))


def test_placeholder_adapter_satisfies_contract():
    adapter = PlaceholderAdapter()
    raw = RawReport(source_filename="x.xml", xml_bytes=b"<x/>")
    assert adapter.validate(raw) == []
    report = adapter.normalize(raw)
    assert report.schema_version == "PLACEHOLDER-0.1"
    assert "placeholder.sample_text_field" in report.fields


@needs_official_files
def test_uad_adapter_extracts_subject_address_from_sf1():
    report = make_adapter().normalize(sf1_raw())
    assert report.schema_version == "GSE_UAD_3.6.0_v1.3"
    assert report.fields[f"{SUBJECT_ADDRESS}/AddressLineText"].value == "123 Falling Tree Ct"
    assert report.fields[f"{SUBJECT_ADDRESS}/CityName"].value == "Treeville"
    assert report.fields[f"{SUBJECT_ADDRESS}/StateCode"].value == "VA"
    assert report.fields[f"{SUBJECT_ADDRESS}/PostalCode"].value == "12345"
    assert report.fields[f"{SUBJECT_ADDRESS}/CountyName"].value == "Arboreal"
    city = report.fields[f"{SUBJECT_ADDRESS}/CityName"]
    assert city.section == "Subject Property"
    assert "ADDRESS" in city.xpath


@needs_official_files
def test_uad_adapter_extracts_all_manifest_fields():
    report = make_adapter().normalize(sf1_raw())
    # every manifest entry appears in the normalized model (value may be None)
    import json

    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    assert set(report.fields) == {e["key"] for e in manifest["fields"]}
    populated = sum(1 for f in report.fields.values() if f.value not in (None, ""))
    assert populated > 20  # SF1 is a complete official sample


@needs_official_files
def test_uad_adapter_reads_xml_attributes():
    # H-1 references some data points as XML attributes, e.g.
    # MESSAGE/@MISMOReferenceModelIdentifier. SF1 carries "3.6.0366".
    report = make_adapter().normalize(sf1_raw())
    key = "doc:MESSAGE/@MISMOReferenceModelIdentifier"
    if key in report.fields:  # present only if the manifest includes it
        assert report.fields[key].value == "3.6.0366"


@needs_official_files
def test_uad_adapter_handles_missing_content_gracefully():
    raw = RawReport(
        source_filename="t.xml",
        xml_bytes=b'<?xml version="1.0"?><MESSAGE xmlns="http://www.mismo.org/residential/2009/schemas"/>',
    )
    report = make_adapter().normalize(raw)
    assert report.fields[f"{SUBJECT_ADDRESS}/CityName"].value is None


@needs_official_files
def test_default_adapter_is_uad36():
    assert get_default_adapter().schema_version == "GSE_UAD_3.6.0_v1.3"
