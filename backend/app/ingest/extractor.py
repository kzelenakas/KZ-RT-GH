from __future__ import annotations

import io
import zipfile

from app.models import RawReport


class IngestError(Exception):
    """Upload could not be turned into a RawReport."""


def extract(data: bytes, filename: str) -> RawReport:
    name = filename.lower()
    if name.endswith(".xml"):
        return RawReport(source_filename=filename, xml_bytes=data)
    if name.endswith(".zip"):
        return _extract_zip(data, filename)
    raise IngestError(f"Unsupported file type: {filename!r}. Upload a .zip delivery or a .xml report.")


def _extract_zip(data: bytes, filename: str) -> RawReport:
    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as exc:
        raise IngestError(f"Not a valid zip file: {exc}") from exc
    names = [n for n in zf.namelist() if not n.endswith("/")]
    xml_names = sorted(n for n in names if n.lower().endswith(".xml"))
    if not xml_names:
        raise IngestError("No XML report found in zip.")
    pdf_names = sorted(n for n in names if n.lower().endswith(".pdf"))
    image_names = sorted(
        n for n in names
        if n.lower().startswith("images/") and n.lower().endswith((".png", ".jpg", ".jpeg", ".gif"))
    )
    # Actual bytes, not just names -- Phase 2/3 (collateral_risk_engine.evaluate_photos)
    # needs real pixel data. Same source list as image_filenames above.
    images = {name: zf.read(name) for name in image_names}
    return RawReport(
        source_filename=filename,
        xml_bytes=zf.read(xml_names[0]),
        pdf_filename=pdf_names[0] if pdf_names else None,
        image_filenames=image_names,
        images=images,
    )
