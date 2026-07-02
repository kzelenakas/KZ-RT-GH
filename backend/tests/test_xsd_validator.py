import zipfile

import pytest

from app.schema_adapters.xsd_validator import validate_xml
from tests.conftest import SAMPLES_DIR, TINY_XML, XSD_PATH

needs_official_files = pytest.mark.skipif(
    not XSD_PATH.exists(), reason="official GSE XSD not present"
)


def test_unparseable_xml_returns_parse_error():
    errors = validate_xml(b"<not-closed", str(XSD_PATH))
    assert len(errors) == 1
    assert errors[0].code == "XML_PARSE"


@needs_official_files
def test_minimal_xml_fails_schema():
    # TINY_XML is an empty MESSAGE: structurally wrong per the real XSD.
    errors = validate_xml(TINY_XML, str(XSD_PATH))
    assert errors, "empty MESSAGE should produce XSD violations"
    assert all(e.code == "XSD" for e in errors)
    assert all(e.location for e in errors)


@needs_official_files
@pytest.mark.skipif(not SAMPLES_DIR.exists(), reason="GSE samples not present")
def test_official_sample_validates_without_crashing():
    zpath = SAMPLES_DIR / "SF1_Appraisal_v1.4.zip"
    with zipfile.ZipFile(zpath) as zf:
        xml_bytes = zf.read("SF1_Appraisal_v1.4.xml")
    errors = validate_xml(xml_bytes, str(XSD_PATH))
    # Samples are v1.4 against the v1.3 XSD: some errors are legitimate output.
    # We only assert the validator completes and returns StructuralError objects.
    assert isinstance(errors, list)
