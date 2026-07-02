import io
import zipfile

import pytest

from app.ingest import IngestError, extract
from tests.conftest import TINY_XML


def test_extract_zip(synthetic_zip):
    raw = extract(synthetic_zip, "delivery.zip")
    assert raw.xml_bytes == TINY_XML
    assert raw.pdf_filename == "report.pdf"
    assert raw.image_filenames == ["Images/front.png"]
    assert raw.source_filename == "delivery.zip"


def test_extract_bare_xml():
    raw = extract(TINY_XML, "report.xml")
    assert raw.xml_bytes == TINY_XML
    assert raw.pdf_filename is None


def test_extract_zip_without_xml_raises():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("only.pdf", b"%PDF")
    with pytest.raises(IngestError, match="No XML"):
        extract(buf.getvalue(), "bad.zip")


def test_extract_corrupt_zip_raises():
    with pytest.raises(IngestError, match="zip"):
        extract(b"this is not a zip", "bad.zip")


def test_extract_unsupported_extension_raises():
    with pytest.raises(IngestError, match="Unsupported"):
        extract(b"x", "report.docx")
