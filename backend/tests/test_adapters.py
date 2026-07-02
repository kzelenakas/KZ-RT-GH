import zipfile

import pytest

from app.models import RawReport
from app.schema_adapters import PlaceholderAdapter, UAD36v13Adapter, get_default_adapter
from tests.conftest import SAMPLES_DIR, XSD_PATH

needs_official_files = pytest.mark.skipif(
    not (SAMPLES_DIR.exists() and XSD_PATH.exists()), reason="official GSE files not present"
)


def sf1_raw() -> RawReport:
    with zipfile.ZipFile(SAMPLES_DIR / "SF1_Appraisal_v1.4.zip") as zf:
        xml = zf.read("SF1_Appraisal_v1.4.xml")
    return RawReport(source_filename="SF1_Appraisal_v1.4.zip", xml_bytes=xml)


def test_placeholder_adapter_satisfies_contract():
    adapter = PlaceholderAdapter()
    raw = RawReport(source_filename="x.xml", xml_bytes=b"<x/>")
    assert adapter.validate(raw) == []
    report = adapter.normalize(raw)
    assert report.schema_version == "PLACEHOLDER-0.1"
    assert "placeholder.sample_text_field" in report.fields


@needs_official_files
def test_uad_adapter_extracts_subject_address_from_sf1():
    report = UAD36v13Adapter(str(XSD_PATH)).normalize(sf1_raw())
    assert report.schema_version == "GSE_UAD_3.6.0_v1.3"
    assert report.fields["subject.AddressLineText"].value == "123 Falling Tree Ct"
    assert report.fields["subject.CityName"].value == "Treeville"
    assert report.fields["subject.StateCode"].value == "VA"
    assert report.fields["subject.PostalCode"].value == "12345"
    assert report.fields["subject.CountyName"].value == "Arboreal"
    assert report.fields["subject.CityName"].section == "Subject Property"
    assert "ADDRESS" in report.fields["subject.CityName"].xpath


@needs_official_files
def test_uad_adapter_handles_missing_address_gracefully():
    raw = RawReport(source_filename="t.xml", xml_bytes=b'<?xml version="1.0"?><MESSAGE xmlns="http://www.mismo.org/residential/2009/schemas"/>')
    report = UAD36v13Adapter(str(XSD_PATH)).normalize(raw)
    assert report.fields["subject.CityName"].value is None  # triggers field_present rules downstream


@needs_official_files
def test_default_adapter_is_uad36():
    assert get_default_adapter().schema_version == "GSE_UAD_3.6.0_v1.3"
