# UAD 3.6 QC App — Phase 1: End-to-End Skeleton Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A locally-running web app where an official GSE sample appraisal zip flows upload → XSD structural validation → normalization → rule evaluation → grouped severity-ranked findings in a browser, persisted to SQLite.

**Architecture:** FastAPI backend with a pure rule engine behind two pluggable contracts (SchemaAdapter, RuleDefinition JSON). The engine never touches DB/HTTP. React (Vite + TS + Tailwind) frontend served as static files by FastAPI. SQLite for dev persistence (schema mirrors the future Postgres).

**Tech Stack:** Python 3.12, FastAPI, lxml (XSD validation), pydantic v2, SQLAlchemy 2, pytest, httpx; Node 20+, Vite, React 18, TypeScript, Tailwind CSS v4.

**Spec:** `docs/superpowers/specs/2026-07-02-uad36-qc-app-design.md` — Phase 1 of 7.

## Global Constraints

- The tool is **read-only** with respect to reports: never modify uploaded files or XML content (in-memory test mutation of fixture copies is fine).
- **Never fabricate citations.** Citations in seed rules quote real Appendix H-1 rows (Unique ID + Message ID). A rule without a citation renders none.
- Severity canon: `HardStop` / `Warning` / `Advisory`. H-1 `Fatal` maps to `HardStop`.
- Rule engine is **pure**: `evaluate(normalized_report, rules) -> RunResult`. No DB, HTTP, or file I/O inside `app/rules/engine.py`.
- Unknown rule fields are **preserved** (pydantic `extra="allow"`); unknown `logic.type` produces a `RuleError("unsupported_logic")`, never a crash, and the run continues.
- Nothing auto-deletes. No DELETE endpoints in Phase 1.
- Every run records `schema_version` and `ruleset_version`.
- All assumptions are labeled in code comments as `ASSUMPTION (Phase 1):` — notably: subject property = first `<PROPERTY>` under `VALUATION_ANALYSIS/PROPERTIES` (true in all three GSE samples; Phase 2 replaces with xlink-based classification per Appendix G-1).
- Official inputs live at repo root: XSD `GSE_UAD_3.6.0_v1.3_schema/Combined/GSE_UAD_3.6.0_v1.3.xsd`, samples in `Sample reports/`. Tests that need samples `skipif` the folder is missing.
- The samples are v1.4, the XSD is v1.3 — **XSD validation errors on the samples are expected legitimate output**, rendered in the structural-errors section. Do not "fix" them; do not assert zero structural errors on samples.
- Dev machine is Windows. All commands below are PowerShell, run from repo root `C:\Users\kzele\Claude Cowork\Projects\Revisions`. Use the venv interpreter explicitly: `backend\.venv\Scripts\python.exe`.
- Commit after every task (conventional commits, no Co-Authored-By trailer).

## File Structure (Phase 1 complete state)

```
backend/
  requirements.txt
  app/
    __init__.py
    config.py                 # paths: XSD, rules file, data dir, DB url
    main.py                   # FastAPI app factory, static mount
    models/
      __init__.py             # re-exports
      report.py               # RawReport, NormalizedField, NormalizedReport, StructuralError
      findings.py             # Severity, Finding, RuleError, RunResult
      rules.py                # RuleMessages, RuleDefinition (extra="allow")
    ingest/
      __init__.py
      extractor.py            # bytes+filename -> RawReport (zip or bare xml)
    schema_adapters/
      __init__.py
      base.py                 # SchemaAdapter protocol + registry
      xsd_validator.py        # lxml validation -> list[StructuralError]
      placeholder.py          # PLACEHOLDER adapter (test fixture proving pluggability)
      uad36_v13.py            # real adapter: subject address fields
    rules/
      __init__.py
      operators.py            # field_present, regex_match, field_in_set + registry
      engine.py               # pure evaluate()
      loader.py               # load_ruleset(path) -> (rules, version)
    persistence/
      __init__.py
      db.py                   # engine/session factory
      tables.py               # RunRow, StructuralErrorRow, FindingRow, RuleErrorRow
      repository.py           # save_run, get_run, list_runs
    api/
      __init__.py
      runs.py                 # POST/GET /api/runs, GET /api/runs/{id}
      meta.py                 # GET /api/meta
  tests/
    conftest.py               # fixtures: sample paths, synthetic zips, tmp db
    test_models.py
    test_extractor.py
    test_xsd_validator.py
    test_operators.py
    test_engine.py
    test_loader.py
    test_adapters.py
    test_repository.py
    test_api.py
rules/
  seed_rules.json             # 4 real H-1 rules, hand-encoded
frontend/                     # Vite React TS app (built -> frontend/dist)
dev.ps1                       # build frontend + run server
docs/DEV.md                   # how to run, for Kevin
```

---

### Task 1: Backend scaffold + domain models

**Files:**
- Create: `backend/requirements.txt`, `backend/app/__init__.py`, `backend/app/models/__init__.py`, `backend/app/models/report.py`, `backend/app/models/findings.py`, `backend/app/models/rules.py`, `.gitignore` (append), `backend/tests/__init__.py` (empty), `backend/tests/test_models.py`

**Interfaces:**
- Produces (everything later tasks import from `app.models`):
  - `Severity(str, Enum)`: `HARD_STOP="HardStop"`, `WARNING="Warning"`, `ADVISORY="Advisory"`
  - `RawReport(source_filename: str, xml_bytes: bytes, pdf_filename: str|None, image_filenames: list[str])`
  - `NormalizedField(value: str|None, xpath: str|None, label: str|None, section: str|None)`
  - `NormalizedReport(schema_version: str, fields: dict[str, NormalizedField])`
  - `StructuralError(code: str, message: str, location: str|None)`
  - `RuleMessages(appraiser: str|None, reviewer: str|None)` — extra allowed
  - `RuleDefinition(rule_id, category, description, severity, enabled, logic: dict, citation, messages)` — extra allowed
  - `Finding(rule_id, category, severity, message_appraiser, message_reviewer, field_path, xpath, section, values: dict, citation)`
  - `RuleError(rule_id, error_type, detail)`
  - `RunResult(findings: list[Finding], rule_errors: list[RuleError])`

- [ ] **Step 1: Create venv and install deps**

`backend/requirements.txt`:
```
fastapi>=0.115
uvicorn[standard]>=0.30
lxml>=5.2
pydantic>=2.7
sqlalchemy>=2.0
python-multipart>=0.0.9
pytest>=8.2
httpx>=0.27
```

Run:
```powershell
python -m venv backend\.venv
backend\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
```
Expected: installs succeed.

Append to `.gitignore` (create if missing):
```
backend/.venv/
backend/data/
__pycache__/
frontend/node_modules/
frontend/dist/
```

- [ ] **Step 2: Write the failing test**

`backend/tests/test_models.py`:
```python
from app.models import (
    Finding, NormalizedField, NormalizedReport, RuleDefinition, RunResult, Severity,
)


def test_severity_values():
    assert Severity.HARD_STOP.value == "HardStop"
    assert Severity("Warning") is Severity.WARNING


def test_rule_definition_preserves_unknown_fields():
    rule = RuleDefinition.model_validate({
        "rule_id": "X-1",
        "category": "Test",
        "severity": "Warning",
        "logic": {"type": "field_present", "field": "a.b"},
        "future_field": {"anything": [1, 2]},
        "messages": {"appraiser": "hi", "tone": "gentle"},
    })
    dumped = rule.model_dump()
    assert dumped["future_field"] == {"anything": [1, 2]}
    assert dumped["messages"]["tone"] == "gentle"
    assert rule.enabled is True
    assert rule.citation is None


def test_normalized_report_lookup():
    rep = NormalizedReport(
        schema_version="TEST-1",
        fields={"subject.CityName": NormalizedField(value="Treeville", xpath="/x", label="City", section="Subject")},
    )
    assert rep.fields["subject.CityName"].value == "Treeville"
    assert rep.fields.get("missing") is None


def test_run_result_shape():
    rr = RunResult(findings=[], rule_errors=[])
    assert rr.findings == [] and rr.rule_errors == []
```

- [ ] **Step 3: Run test to verify it fails**

Run: `backend\.venv\Scripts\python.exe -m pytest backend/tests/test_models.py -v` (from repo root; add `backend` to path via `backend/tests/conftest.py` in Step 4 — first run fails with `ModuleNotFoundError: app`)

- [ ] **Step 4: Implement models**

`backend/tests/conftest.py` (start minimal; grows in later tasks):
```python
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

REPO_ROOT = BACKEND_DIR.parent
SAMPLES_DIR = REPO_ROOT / "Sample reports"
XSD_PATH = REPO_ROOT / "GSE_UAD_3.6.0_v1.3_schema" / "Combined" / "GSE_UAD_3.6.0_v1.3.xsd"
```

`backend/app/__init__.py`: empty file.

`backend/app/models/report.py`:
```python
from __future__ import annotations

from pydantic import BaseModel, Field


class RawReport(BaseModel):
    """Extracted contents of one report delivery. Read-only input to adapters."""

    source_filename: str
    xml_bytes: bytes
    pdf_filename: str | None = None
    image_filenames: list[str] = Field(default_factory=list)


class NormalizedField(BaseModel):
    value: str | None = None
    xpath: str | None = None
    label: str | None = None
    section: str | None = None


class NormalizedReport(BaseModel):
    """The only thing the rule engine ever reads."""

    schema_version: str
    fields: dict[str, NormalizedField] = Field(default_factory=dict)


class StructuralError(BaseModel):
    """Schema/structural failure. Rendered separately from rule findings."""

    code: str
    message: str
    location: str | None = None
```

`backend/app/models/findings.py`:
```python
from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class Severity(str, Enum):
    HARD_STOP = "HardStop"
    WARNING = "Warning"
    ADVISORY = "Advisory"


class Finding(BaseModel):
    rule_id: str
    category: str
    severity: Severity
    message_appraiser: str
    message_reviewer: str
    field_path: str = ""
    xpath: str | None = None
    section: str | None = None
    values: dict[str, str | None] = Field(default_factory=dict)
    citation: str | None = None


class RuleError(BaseModel):
    """A rule that could not execute. Recorded, never fatal to the run."""

    rule_id: str
    error_type: str
    detail: str


class RunResult(BaseModel):
    findings: list[Finding] = Field(default_factory=list)
    rule_errors: list[RuleError] = Field(default_factory=list)
```

`backend/app/models/rules.py`:
```python
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from .findings import Severity


class RuleMessages(BaseModel):
    model_config = ConfigDict(extra="allow")

    appraiser: str | None = None
    reviewer: str | None = None


class RuleDefinition(BaseModel):
    """External rule contract. Unknown fields are preserved (forward-compatible)."""

    model_config = ConfigDict(extra="allow")

    rule_id: str
    category: str
    description: str = ""
    severity: Severity
    enabled: bool = True
    logic: dict = Field(default_factory=dict)
    citation: str | None = None
    messages: RuleMessages = Field(default_factory=RuleMessages)
```

`backend/app/models/__init__.py`:
```python
from .findings import Finding, RuleError, RunResult, Severity
from .report import NormalizedField, NormalizedReport, RawReport, StructuralError
from .rules import RuleDefinition, RuleMessages

__all__ = [
    "Finding", "NormalizedField", "NormalizedReport", "RawReport", "RuleDefinition",
    "RuleError", "RuleMessages", "RunResult", "Severity", "StructuralError",
]
```

- [ ] **Step 5: Run test to verify it passes**

Run: `backend\.venv\Scripts\python.exe -m pytest backend/tests/test_models.py -v`
Expected: 4 PASS

- [ ] **Step 6: Commit**

```powershell
git add backend .gitignore
git commit -m "feat: backend scaffold and domain models"
```

---

### Task 2: Ingest extractor

**Files:**
- Create: `backend/app/ingest/__init__.py`, `backend/app/ingest/extractor.py`
- Test: `backend/tests/test_extractor.py`
- Modify: `backend/tests/conftest.py` (add synthetic zip fixture)

**Interfaces:**
- Consumes: `RawReport` from Task 1
- Produces: `extract(data: bytes, filename: str) -> RawReport`; `class IngestError(Exception)` — both in `app.ingest`

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/conftest.py`:
```python
import io
import zipfile

import pytest

TINY_XML = b'<?xml version="1.0" encoding="UTF-8"?><MESSAGE xmlns="http://www.mismo.org/residential/2009/schemas"></MESSAGE>'


@pytest.fixture
def synthetic_zip() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("report.xml", TINY_XML)
        zf.writestr("report.pdf", b"%PDF-1.4 fake")
        zf.writestr("Images/front.png", b"\x89PNG fake")
    return buf.getvalue()
```

`backend/tests/test_extractor.py`:
```python
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
    import io, zipfile
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
```

Note: `from tests.conftest import TINY_XML` requires `backend/tests/__init__.py` (created empty in Task 1).

- [ ] **Step 2: Run test to verify it fails**

Run: `backend\.venv\Scripts\python.exe -m pytest backend/tests/test_extractor.py -v`
Expected: FAIL `ModuleNotFoundError: app.ingest`

- [ ] **Step 3: Implement**

`backend/app/ingest/extractor.py`:
```python
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
    return RawReport(
        source_filename=filename,
        xml_bytes=zf.read(xml_names[0]),
        pdf_filename=pdf_names[0] if pdf_names else None,
        image_filenames=image_names,
    )
```

`backend/app/ingest/__init__.py`:
```python
from .extractor import IngestError, extract

__all__ = ["IngestError", "extract"]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `backend\.venv\Scripts\python.exe -m pytest backend/tests/test_extractor.py -v`
Expected: 5 PASS

- [ ] **Step 5: Commit**

```powershell
git add backend
git commit -m "feat: ingest extractor for zip and bare xml deliveries"
```

---

### Task 3: XSD structural validator

**Files:**
- Create: `backend/app/schema_adapters/__init__.py` (empty for now), `backend/app/schema_adapters/xsd_validator.py`
- Test: `backend/tests/test_xsd_validator.py`

**Interfaces:**
- Consumes: `StructuralError` from Task 1; XSD at `conftest.XSD_PATH`
- Produces: `validate_xml(xml_bytes: bytes, xsd_path: str) -> list[StructuralError]` in `app.schema_adapters.xsd_validator`

- [ ] **Step 1: Write the failing test**

`backend/tests/test_xsd_validator.py`:
```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `backend\.venv\Scripts\python.exe -m pytest backend/tests/test_xsd_validator.py -v`
Expected: FAIL `ModuleNotFoundError` / import error

- [ ] **Step 3: Implement**

`backend/app/schema_adapters/xsd_validator.py`:
```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `backend\.venv\Scripts\python.exe -m pytest backend/tests/test_xsd_validator.py -v`
Expected: 3 PASS (first XSD compile may take a few seconds)

- [ ] **Step 5: Commit**

```powershell
git add backend
git commit -m "feat: XSD structural validation against official GSE schema"
```

---

### Task 4: Rule operators

**Files:**
- Create: `backend/app/rules/__init__.py` (empty for now), `backend/app/rules/operators.py`
- Test: `backend/tests/test_operators.py`

**Interfaces:**
- Consumes: `NormalizedReport`, `NormalizedField` from Task 1
- Produces in `app.rules.operators`:
  - `class OperatorResult(BaseModel)`: `triggered: bool`, `values: dict[str, str | None]`
  - `OPERATORS: dict[str, Callable[[dict, NormalizedReport], OperatorResult]]` with keys `"field_present"`, `"regex_match"`, `"field_in_set"`

- [ ] **Step 1: Write the failing test**

`backend/tests/test_operators.py`:
```python
import pytest

from app.models import NormalizedField, NormalizedReport
from app.rules.operators import OPERATORS


def make_report(**values) -> NormalizedReport:
    return NormalizedReport(
        schema_version="TEST",
        fields={k: NormalizedField(value=v) for k, v in values.items()},
    )


# --- field_present: triggers when the field is missing or blank ---

@pytest.mark.parametrize("report,expected", [
    (make_report(**{"subject.CityName": "Treeville"}), False),
    (make_report(**{"subject.CityName": ""}), True),
    (make_report(**{"subject.CityName": "   "}), True),
    (make_report(**{"subject.CityName": None}), True),
    (make_report(), True),  # field entirely absent
])
def test_field_present(report, expected):
    result = OPERATORS["field_present"]({"type": "field_present", "field": "subject.CityName"}, report)
    assert result.triggered is expected


# --- regex_match: triggers when present AND not matching; absent = no trigger ---

@pytest.mark.parametrize("value,expected", [
    ("12345", False),
    ("12345-6789", False),
    ("1234", True),
    ("123456", True),
    ("12345-67", True),
])
def test_regex_match(value, expected):
    logic = {"type": "regex_match", "field": "subject.PostalCode", "pattern": r"\d{5}(-\d{4})?"}
    result = OPERATORS["regex_match"](logic, make_report(**{"subject.PostalCode": value}))
    assert result.triggered is expected
    assert result.values == {"subject.PostalCode": value}


def test_regex_match_absent_field_does_not_trigger():
    logic = {"type": "regex_match", "field": "subject.PostalCode", "pattern": r"\d{5}"}
    assert OPERATORS["regex_match"](logic, make_report()).triggered is False


# --- field_in_set: triggers when present AND value not in allowed set ---

def test_field_in_set():
    logic = {"type": "field_in_set", "field": "subject.StateCode", "allowed": ["VA", "MD"]}
    assert OPERATORS["field_in_set"](logic, make_report(**{"subject.StateCode": "VA"})).triggered is False
    assert OPERATORS["field_in_set"](logic, make_report(**{"subject.StateCode": "ZZ"})).triggered is True
    assert OPERATORS["field_in_set"](logic, make_report()).triggered is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `backend\.venv\Scripts\python.exe -m pytest backend/tests/test_operators.py -v`
Expected: FAIL import error

- [ ] **Step 3: Implement**

`backend/app/rules/operators.py`:
```python
from __future__ import annotations

import re
from typing import Callable

from pydantic import BaseModel, Field

from app.models import NormalizedReport


class OperatorResult(BaseModel):
    triggered: bool
    values: dict[str, str | None] = Field(default_factory=dict)


OperatorFn = Callable[[dict, NormalizedReport], OperatorResult]


def _value(report: NormalizedReport, field_path: str) -> str | None:
    field = report.fields.get(field_path)
    return field.value if field is not None else None


def field_present(logic: dict, report: NormalizedReport) -> OperatorResult:
    value = _value(report, logic["field"])
    missing = value is None or str(value).strip() == ""
    return OperatorResult(triggered=missing, values={logic["field"]: value})


def regex_match(logic: dict, report: NormalizedReport) -> OperatorResult:
    value = _value(report, logic["field"])
    if value is None or str(value).strip() == "":
        # Presence is a separate rule (mirrors H-1, e.g. UAD1004 vs UAD1005).
        return OperatorResult(triggered=False)
    ok = re.fullmatch(logic["pattern"], str(value)) is not None
    return OperatorResult(triggered=not ok, values={logic["field"]: value})


def field_in_set(logic: dict, report: NormalizedReport) -> OperatorResult:
    value = _value(report, logic["field"])
    if value is None or str(value).strip() == "":
        return OperatorResult(triggered=False)
    allowed = set(logic["allowed"])
    return OperatorResult(triggered=str(value) not in allowed, values={logic["field"]: value})


OPERATORS: dict[str, OperatorFn] = {
    "field_present": field_present,
    "regex_match": regex_match,
    "field_in_set": field_in_set,
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `backend\.venv\Scripts\python.exe -m pytest backend/tests/test_operators.py -v`
Expected: all PASS

- [ ] **Step 5: Commit**

```powershell
git add backend
git commit -m "feat: declarative rule operators (field_present, regex_match, field_in_set)"
```

---

### Task 5: Pure rule engine

**Files:**
- Create: `backend/app/rules/engine.py`
- Modify: `backend/app/rules/__init__.py`
- Test: `backend/tests/test_engine.py`

**Interfaces:**
- Consumes: `OPERATORS` from Task 4; models from Task 1
- Produces: `evaluate(report: NormalizedReport, rules: Sequence[RuleDefinition]) -> RunResult` in `app.rules` (re-exported)

- [ ] **Step 1: Write the failing test**

`backend/tests/test_engine.py`:
```python
from app.models import NormalizedField, NormalizedReport, RuleDefinition, Severity
from app.rules import evaluate


def make_rule(**overrides) -> RuleDefinition:
    base = {
        "rule_id": "T-1",
        "category": "Test Category",
        "description": "Field must be present.",
        "severity": "HardStop",
        "logic": {"type": "field_present", "field": "subject.CityName"},
        "messages": {"appraiser": "Coach: add the city.", "reviewer": "Audit: CityName missing."},
    }
    base.update(overrides)
    return RuleDefinition.model_validate(base)


EMPTY = NormalizedReport(schema_version="TEST", fields={})
FILLED = NormalizedReport(
    schema_version="TEST",
    fields={"subject.CityName": NormalizedField(value="Treeville", xpath="/m/ADDRESS/CityName", section="Subject Property")},
)


def test_triggered_rule_produces_finding_with_location():
    result = evaluate(EMPTY, [make_rule()])
    assert len(result.findings) == 1
    f = result.findings[0]
    assert f.rule_id == "T-1"
    assert f.severity is Severity.HARD_STOP
    assert f.message_appraiser == "Coach: add the city."
    assert f.message_reviewer == "Audit: CityName missing."
    assert f.field_path == "subject.CityName"
    assert result.rule_errors == []


def test_finding_carries_xpath_and_section_from_normalized_field():
    rule = make_rule(logic={"type": "field_in_set", "field": "subject.CityName", "allowed": ["Elsewhere"]})
    result = evaluate(FILLED, [rule])
    assert result.findings[0].xpath == "/m/ADDRESS/CityName"
    assert result.findings[0].section == "Subject Property"
    assert result.findings[0].values == {"subject.CityName": "Treeville"}


def test_clean_pass():
    result = evaluate(FILLED, [make_rule()])
    assert result.findings == [] and result.rule_errors == []


def test_disabled_rule_is_skipped():
    result = evaluate(EMPTY, [make_rule(enabled=False)])
    assert result.findings == [] and result.rule_errors == []


def test_unknown_logic_type_records_error_and_continues():
    rules = [make_rule(rule_id="BAD", logic={"type": "quantum_check"}), make_rule(rule_id="GOOD")]
    result = evaluate(EMPTY, rules)
    assert [e.rule_id for e in result.rule_errors] == ["BAD"]
    assert result.rule_errors[0].error_type == "unsupported_logic"
    assert [f.rule_id for f in result.findings] == ["GOOD"]


def test_operator_exception_recorded_not_raised():
    # regex_match without 'pattern' raises KeyError inside the operator
    bad = make_rule(rule_id="BOOM", logic={"type": "regex_match", "field": "subject.CityName"})
    result = evaluate(FILLED, [bad])
    assert result.rule_errors[0].error_type == "execution_error"
    assert result.findings == []


def test_message_fallback_single_variant_used_for_both():
    rule = make_rule(messages={"reviewer": "Only audit text."})
    result = evaluate(EMPTY, [rule])
    assert result.findings[0].message_appraiser == "Only audit text."
    assert result.findings[0].message_reviewer == "Only audit text."


def test_message_fallback_to_description():
    rule = make_rule(messages={})
    result = evaluate(EMPTY, [rule])
    assert result.findings[0].message_appraiser == "Field must be present."
```

- [ ] **Step 2: Run test to verify it fails**

Run: `backend\.venv\Scripts\python.exe -m pytest backend/tests/test_engine.py -v`
Expected: FAIL import error

- [ ] **Step 3: Implement**

`backend/app/rules/engine.py`:
```python
from __future__ import annotations

from typing import Sequence

from app.models import Finding, NormalizedReport, RuleDefinition, RuleError, RunResult
from app.rules.operators import OPERATORS

# PURE: no DB, no HTTP, no file I/O in this module. Input -> output only.


def evaluate(report: NormalizedReport, rules: Sequence[RuleDefinition]) -> RunResult:
    findings: list[Finding] = []
    errors: list[RuleError] = []
    for rule in rules:
        if not rule.enabled:
            continue
        logic_type = str(rule.logic.get("type", ""))
        operator = OPERATORS.get(logic_type)
        if operator is None:
            errors.append(RuleError(
                rule_id=rule.rule_id,
                error_type="unsupported_logic",
                detail=f"Unknown logic type: {logic_type!r}",
            ))
            continue
        try:
            result = operator(rule.logic, report)
        except Exception as exc:  # noqa: BLE001 - a broken rule must never kill the run
            errors.append(RuleError(
                rule_id=rule.rule_id,
                error_type="execution_error",
                detail=f"{type(exc).__name__}: {exc}",
            ))
            continue
        if not result.triggered:
            continue
        field_path = str(rule.logic.get("field", ""))
        normalized_field = report.fields.get(field_path)
        appraiser = rule.messages.appraiser or rule.messages.reviewer or rule.description
        reviewer = rule.messages.reviewer or rule.messages.appraiser or rule.description
        findings.append(Finding(
            rule_id=rule.rule_id,
            category=rule.category,
            severity=rule.severity,
            message_appraiser=appraiser,
            message_reviewer=reviewer,
            field_path=field_path,
            xpath=normalized_field.xpath if normalized_field else None,
            section=normalized_field.section if normalized_field else None,
            values=result.values,
            citation=rule.citation,
        ))
    return RunResult(findings=findings, rule_errors=errors)
```

`backend/app/rules/__init__.py`:
```python
from .engine import evaluate

__all__ = ["evaluate"]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `backend\.venv\Scripts\python.exe -m pytest backend/tests/test_engine.py -v`
Expected: 8 PASS

- [ ] **Step 5: Commit**

```powershell
git add backend
git commit -m "feat: pure rule engine with per-rule error isolation"
```

---

### Task 6: Seed ruleset (4 real H-1 rules) + loader

**Files:**
- Create: `rules/seed_rules.json`, `backend/app/rules/loader.py`
- Modify: `backend/app/rules/__init__.py`
- Test: `backend/tests/test_loader.py`

**Interfaces:**
- Consumes: `RuleDefinition` from Task 1
- Produces: `load_ruleset(path: Path) -> tuple[list[RuleDefinition], str]` in `app.rules` — second element is the ruleset version string `"<name>-<sha256[:12]>"`

The four rules are hand-encoded from real rows of `QC_rules/Appendix H-1 - Compliance Rules - UAD Compliance Rules v1.4.csv`. Message text and citations quote that document — do not paraphrase or invent.

- [ ] **Step 1: Create the seed ruleset**

`rules/seed_rules.json`:
```json
{
  "name": "H1-seed-phase1",
  "source": "UAD 3.6 Appendix H-1 Compliance Rules v1.4 (4 of 729 rules, hand-encoded for Phase 1)",
  "rules": [
    {
      "rule_id": "UAD1001",
      "category": "Subject Property",
      "description": "Subject property physical address line must be provided.",
      "severity": "HardStop",
      "enabled": true,
      "logic": { "type": "field_present", "field": "subject.AddressLineText" },
      "citation": "UAD 3.6 Appendix H-1 v1.4, Unique ID 0100.0007, Message ID UAD1001",
      "messages": {
        "reviewer": "Provide the address line for the subject property physical address."
      }
    },
    {
      "rule_id": "UAD1002",
      "category": "Subject Property",
      "description": "Subject property city name must be provided.",
      "severity": "HardStop",
      "enabled": true,
      "logic": { "type": "field_present", "field": "subject.CityName" },
      "citation": "UAD 3.6 Appendix H-1 v1.4, Unique ID 0100.0009, Message ID UAD1002",
      "messages": {
        "reviewer": "Provide the city name for the subject property physical address."
      }
    },
    {
      "rule_id": "UAD1005",
      "category": "Subject Property",
      "description": "Subject property ZIP code must be 5 digits or ZIP+4.",
      "severity": "HardStop",
      "enabled": true,
      "logic": { "type": "regex_match", "field": "subject.PostalCode", "pattern": "\\d{5}(-\\d{4})?" },
      "citation": "UAD 3.6 Appendix H-1 v1.4, Unique ID 0100.0011, Message ID UAD1005",
      "messages": {
        "reviewer": "The ZIP code for the subject property physical address must be either 5 digits, or 5 digits, a hyphen, and 4 digits (ZIP+4)."
      }
    },
    {
      "rule_id": "UAD1007",
      "category": "Subject Property",
      "description": "Subject property state code must be a valid 2-character US State or Territory Code.",
      "severity": "HardStop",
      "enabled": true,
      "logic": {
        "type": "field_in_set",
        "field": "subject.StateCode",
        "allowed": ["AL","AK","AS","AZ","AR","CA","CO","CT","DE","DC","FL","GA","GU","HI","ID","IL","IN","IA","KS","KY","LA","ME","MD","MA","MI","MN","MP","MS","MO","MT","NE","NV","NH","NJ","NM","NY","NC","ND","OH","OK","OR","PA","PR","RI","SC","SD","TN","TX","UT","VT","VA","VI","WA","WV","WI","WY"]
      },
      "citation": "UAD 3.6 Appendix H-1 v1.4, Unique ID 0100.0012, Message ID UAD1007",
      "messages": {
        "reviewer": "The state code for the subject property physical address must be a valid 2-character US State or Territory Code."
      }
    }
  ]
}
```

- [ ] **Step 2: Write the failing test**

`backend/tests/test_loader.py`:
```python
import json

from app.rules import load_ruleset
from tests.conftest import REPO_ROOT

SEED_PATH = REPO_ROOT / "rules" / "seed_rules.json"


def test_load_seed_ruleset():
    rules, version = load_ruleset(SEED_PATH)
    assert [r.rule_id for r in rules] == ["UAD1001", "UAD1002", "UAD1005", "UAD1007"]
    assert version.startswith("H1-seed-phase1-")
    assert len(version.split("-")[-1]) == 12  # sha256 prefix


def test_version_changes_when_content_changes(tmp_path):
    data = json.loads(SEED_PATH.read_text(encoding="utf-8"))
    p1 = tmp_path / "a.json"
    p1.write_text(json.dumps(data), encoding="utf-8")
    data["rules"][0]["enabled"] = False
    p2 = tmp_path / "b.json"
    p2.write_text(json.dumps(data), encoding="utf-8")
    _, v1 = load_ruleset(p1)
    _, v2 = load_ruleset(p2)
    assert v1 != v2


def test_unknown_fields_survive_loading(tmp_path):
    data = {"name": "x", "rules": [{
        "rule_id": "R1", "category": "C", "severity": "Advisory",
        "logic": {"type": "field_present", "field": "a"},
        "some_future_key": 42,
    }]}
    p = tmp_path / "r.json"
    p.write_text(json.dumps(data), encoding="utf-8")
    rules, _ = load_ruleset(p)
    assert rules[0].model_dump()["some_future_key"] == 42
```

- [ ] **Step 3: Run test to verify it fails**

Run: `backend\.venv\Scripts\python.exe -m pytest backend/tests/test_loader.py -v`
Expected: FAIL import error

- [ ] **Step 4: Implement**

`backend/app/rules/loader.py`:
```python
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from app.models import RuleDefinition


def load_ruleset(path: Path) -> tuple[list[RuleDefinition], str]:
    """Load an external ruleset file. Version = name + content hash, so any
    change to the file produces a new recorded ruleset_version."""
    raw = Path(path).read_bytes()
    data = json.loads(raw.decode("utf-8"))
    rules = [RuleDefinition.model_validate(r) for r in data.get("rules", [])]
    name = data.get("name", Path(path).stem)
    digest = hashlib.sha256(raw).hexdigest()[:12]
    return rules, f"{name}-{digest}"
```

`backend/app/rules/__init__.py`:
```python
from .engine import evaluate
from .loader import load_ruleset

__all__ = ["evaluate", "load_ruleset"]
```

- [ ] **Step 5: Run test to verify it passes**

Run: `backend\.venv\Scripts\python.exe -m pytest backend/tests/test_loader.py -v`
Expected: 3 PASS

- [ ] **Step 6: Commit**

```powershell
git add backend rules
git commit -m "feat: ruleset loader and 4 seed rules encoded from Appendix H-1"
```

---

### Task 7: Schema adapters — protocol, placeholder, real UAD 3.6 adapter

**Files:**
- Create: `backend/app/schema_adapters/base.py`, `backend/app/schema_adapters/placeholder.py`, `backend/app/schema_adapters/uad36_v13.py`, `backend/app/config.py`
- Modify: `backend/app/schema_adapters/__init__.py`
- Test: `backend/tests/test_adapters.py`

**Interfaces:**
- Consumes: `validate_xml` (Task 3), models (Task 1)
- Produces:
  - `app.config`: `XSD_PATH: Path`, `RULES_PATH: Path`, `DATA_DIR: Path`, `DB_URL: str`, `FRONTEND_DIST: Path` (env-overridable via `QC_XSD_PATH`, `QC_RULES_PATH`, `QC_DATA_DIR`)
  - `app.schema_adapters`: `SchemaAdapter` (Protocol with `schema_version: str`, `validate(raw) -> list[StructuralError]`, `normalize(raw) -> NormalizedReport`), `get_default_adapter() -> SchemaAdapter`, `PlaceholderAdapter`, `UAD36v13Adapter`

- [ ] **Step 1: Write the failing test**

`backend/tests/test_adapters.py`:
```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `backend\.venv\Scripts\python.exe -m pytest backend/tests/test_adapters.py -v`
Expected: FAIL import error

- [ ] **Step 3: Implement config**

`backend/app/config.py`:
```python
from __future__ import annotations

import os
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_DIR.parent

XSD_PATH = Path(os.environ.get(
    "QC_XSD_PATH",
    REPO_ROOT / "GSE_UAD_3.6.0_v1.3_schema" / "Combined" / "GSE_UAD_3.6.0_v1.3.xsd",
))
RULES_PATH = Path(os.environ.get("QC_RULES_PATH", REPO_ROOT / "rules" / "seed_rules.json"))
DATA_DIR = Path(os.environ.get("QC_DATA_DIR", BACKEND_DIR / "data"))
DB_URL = f"sqlite:///{DATA_DIR / 'qc.sqlite3'}"
FRONTEND_DIST = REPO_ROOT / "frontend" / "dist"
```

- [ ] **Step 4: Implement adapters**

`backend/app/schema_adapters/base.py`:
```python
from __future__ import annotations

from typing import Protocol, runtime_checkable

from app.models import NormalizedReport, RawReport, StructuralError


@runtime_checkable
class SchemaAdapter(Protocol):
    """Contract for mapping one schema version into the normalized model.

    To integrate a new UAD schema version: implement this protocol in a new
    module, set a unique schema_version string, and return it from
    get_default_adapter() (or extend the registry). UI, engine, persistence,
    and exports never change.
    """

    schema_version: str

    def validate(self, raw: RawReport) -> list[StructuralError]: ...

    def normalize(self, raw: RawReport) -> NormalizedReport: ...
```

`backend/app/schema_adapters/placeholder.py`:
```python
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
```

`backend/app/schema_adapters/uad36_v13.py`:
```python
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
```

`backend/app/schema_adapters/__init__.py`:
```python
from app.config import XSD_PATH

from .base import SchemaAdapter
from .placeholder import PlaceholderAdapter
from .uad36_v13 import UAD36v13Adapter


def get_default_adapter() -> SchemaAdapter:
    return UAD36v13Adapter(str(XSD_PATH))


__all__ = ["PlaceholderAdapter", "SchemaAdapter", "UAD36v13Adapter", "get_default_adapter"]
```

- [ ] **Step 5: Run test to verify it passes**

Run: `backend\.venv\Scripts\python.exe -m pytest backend/tests/test_adapters.py -v`
Expected: 4 PASS

- [ ] **Step 6: Run full suite, commit**

Run: `backend\.venv\Scripts\python.exe -m pytest backend/tests -v`
Expected: all PASS

```powershell
git add backend
git commit -m "feat: schema adapter contract, placeholder adapter, real UAD 3.6 v1.3 adapter"
```

---

### Task 8: Persistence (SQLite via SQLAlchemy)

**Files:**
- Create: `backend/app/persistence/__init__.py`, `backend/app/persistence/db.py`, `backend/app/persistence/tables.py`, `backend/app/persistence/repository.py`
- Test: `backend/tests/test_repository.py`

**Interfaces:**
- Consumes: models (Task 1)
- Produces in `app.persistence`:
  - `init_db(db_url: str) -> sessionmaker`
  - `class RunRepository:` constructed with a `sessionmaker`;
    - `save_run(filename: str, file_hash: str, schema_version: str, ruleset_version: str, structural_errors: list[StructuralError], result: RunResult) -> str` (returns run id)
    - `get_run(run_id: str) -> dict | None` — full payload (shape below, reused verbatim by the API)
    - `list_runs() -> list[dict]` — summaries, newest first

Run payload shape (the API returns exactly this):
```json
{
  "id": "…uuid…", "filename": "…", "file_hash": "…", "created_at": "…iso…",
  "schema_version": "…", "ruleset_version": "…",
  "counts": {"HardStop": 0, "Warning": 0, "Advisory": 0},
  "structural_errors": [{"code": "…", "message": "…", "location": "…"}],
  "findings": [ …Finding.model_dump()… ],
  "rule_errors": [ …RuleError.model_dump()… ]
}
```

- [ ] **Step 1: Write the failing test**

`backend/tests/test_repository.py`:
```python
from app.models import Finding, RuleError, RunResult, Severity, StructuralError
from app.persistence import RunRepository, init_db


def make_repo(tmp_path):
    return RunRepository(init_db(f"sqlite:///{tmp_path / 't.sqlite3'}"))


def sample_result() -> RunResult:
    return RunResult(
        findings=[Finding(
            rule_id="UAD1002", category="Subject Property", severity=Severity.HARD_STOP,
            message_appraiser="a", message_reviewer="r", field_path="subject.CityName",
            xpath="…/CityName", section="Subject Property",
            values={"subject.CityName": None},
            citation="UAD 3.6 Appendix H-1 v1.4, Unique ID 0100.0009, Message ID UAD1002",
        )],
        rule_errors=[RuleError(rule_id="X", error_type="unsupported_logic", detail="d")],
    )


def test_save_and_get_run(tmp_path):
    repo = make_repo(tmp_path)
    run_id = repo.save_run(
        filename="SF1.zip", file_hash="abc123", schema_version="GSE_UAD_3.6.0_v1.3",
        ruleset_version="H1-seed-phase1-deadbeef0000",
        structural_errors=[StructuralError(code="XSD", message="m", location="line 5")],
        result=sample_result(),
    )
    payload = repo.get_run(run_id)
    assert payload["filename"] == "SF1.zip"
    assert payload["counts"] == {"HardStop": 1, "Warning": 0, "Advisory": 0}
    assert payload["structural_errors"][0]["code"] == "XSD"
    assert payload["findings"][0]["rule_id"] == "UAD1002"
    assert payload["findings"][0]["values"] == {"subject.CityName": None}
    assert payload["rule_errors"][0]["error_type"] == "unsupported_logic"
    assert payload["schema_version"] == "GSE_UAD_3.6.0_v1.3"


def test_get_missing_run_returns_none(tmp_path):
    assert make_repo(tmp_path).get_run("nope") is None


def test_list_runs_newest_first(tmp_path):
    repo = make_repo(tmp_path)
    empty = RunResult()
    id1 = repo.save_run("a.zip", "h1", "s", "r", [], empty)
    id2 = repo.save_run("b.zip", "h2", "s", "r", [], empty)
    runs = repo.list_runs()
    assert [r["id"] for r in runs] == [id2, id1]
    assert runs[0]["counts"] == {"HardStop": 0, "Warning": 0, "Advisory": 0}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `backend\.venv\Scripts\python.exe -m pytest backend/tests/test_repository.py -v`
Expected: FAIL import error

- [ ] **Step 3: Implement**

`backend/app/persistence/tables.py`:
```python
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import JSON, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class RunRow(Base):
    __tablename__ = "runs"
    # Retention rule: rows in this table are NEVER deleted (spec: no auto-delete).
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    filename: Mapped[str] = mapped_column(String(500))
    file_hash: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    schema_version: Mapped[str] = mapped_column(String(100))
    ruleset_version: Mapped[str] = mapped_column(String(200))


class StructuralErrorRow(Base):
    __tablename__ = "structural_errors"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.id"), index=True)
    code: Mapped[str] = mapped_column(String(50))
    message: Mapped[str] = mapped_column(Text)
    location: Mapped[str | None] = mapped_column(String(200), nullable=True)


class FindingRow(Base):
    __tablename__ = "findings"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.id"), index=True)
    rule_id: Mapped[str] = mapped_column(String(100))
    category: Mapped[str] = mapped_column(String(200))
    severity: Mapped[str] = mapped_column(String(20))
    message_appraiser: Mapped[str] = mapped_column(Text)
    message_reviewer: Mapped[str] = mapped_column(Text)
    field_path: Mapped[str] = mapped_column(String(300), default="")
    xpath: Mapped[str | None] = mapped_column(Text, nullable=True)
    section: Mapped[str | None] = mapped_column(String(200), nullable=True)
    values_json: Mapped[dict] = mapped_column(JSON, default=dict)
    citation: Mapped[str | None] = mapped_column(Text, nullable=True)


class RuleErrorRow(Base):
    __tablename__ = "rule_errors"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.id"), index=True)
    rule_id: Mapped[str] = mapped_column(String(100))
    error_type: Mapped[str] = mapped_column(String(50))
    detail: Mapped[str] = mapped_column(Text)
```

`backend/app/persistence/db.py`:
```python
from __future__ import annotations

from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from .tables import Base


def init_db(db_url: str) -> sessionmaker:
    if db_url.startswith("sqlite:///"):
        Path(db_url.removeprefix("sqlite:///")).parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(db_url)
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)
```

`backend/app/persistence/repository.py`:
```python
from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.models import RunResult, StructuralError

from .tables import FindingRow, RuleErrorRow, RunRow, StructuralErrorRow

SEVERITY_KEYS = ["HardStop", "Warning", "Advisory"]


class RunRepository:
    def __init__(self, session_factory: sessionmaker):
        self._sessions = session_factory

    def save_run(
        self,
        filename: str,
        file_hash: str,
        schema_version: str,
        ruleset_version: str,
        structural_errors: list[StructuralError],
        result: RunResult,
    ) -> str:
        run_id = str(uuid.uuid4())
        with self._sessions() as session:
            session.add(RunRow(
                id=run_id, filename=filename, file_hash=file_hash,
                schema_version=schema_version, ruleset_version=ruleset_version,
            ))
            for se in structural_errors:
                session.add(StructuralErrorRow(run_id=run_id, **se.model_dump()))
            for f in result.findings:
                session.add(FindingRow(
                    run_id=run_id, rule_id=f.rule_id, category=f.category,
                    severity=f.severity.value, message_appraiser=f.message_appraiser,
                    message_reviewer=f.message_reviewer, field_path=f.field_path,
                    xpath=f.xpath, section=f.section, values_json=f.values,
                    citation=f.citation,
                ))
            for e in result.rule_errors:
                session.add(RuleErrorRow(run_id=run_id, **e.model_dump()))
            session.commit()
        return run_id

    def get_run(self, run_id: str) -> dict | None:
        with self._sessions() as session:
            run = session.get(RunRow, run_id)
            if run is None:
                return None
            return self._payload(session, run, full=True)

    def list_runs(self) -> list[dict]:
        # Newest first. SQLite created_at has second precision, so two runs saved
        # in the same second would tie; SQLite's implicit rowid is insertion-ordered
        # and breaks the tie. (Postgres migration in the deploy phase replaces this
        # with ORDER BY created_at DESC on a bigserial-tie-broken column.)
        with self._sessions() as session:
            ids = [row[0] for row in session.execute(text("SELECT id FROM runs ORDER BY rowid DESC"))]
            runs = [session.get(RunRow, run_id) for run_id in ids]
            return [self._payload(session, r, full=False) for r in runs]

    def _payload(self, session: Session, run: RunRow, full: bool) -> dict:
        findings = session.scalars(select(FindingRow).where(FindingRow.run_id == run.id)).all()
        counts = {k: 0 for k in SEVERITY_KEYS}
        for f in findings:
            counts[f.severity] = counts.get(f.severity, 0) + 1
        payload = {
            "id": run.id,
            "filename": run.filename,
            "file_hash": run.file_hash,
            "created_at": run.created_at.isoformat(),
            "schema_version": run.schema_version,
            "ruleset_version": run.ruleset_version,
            "counts": counts,
        }
        if full:
            structural = session.scalars(
                select(StructuralErrorRow).where(StructuralErrorRow.run_id == run.id)
            ).all()
            errors = session.scalars(
                select(RuleErrorRow).where(RuleErrorRow.run_id == run.id)
            ).all()
            payload["structural_errors"] = [
                {"code": s.code, "message": s.message, "location": s.location} for s in structural
            ]
            payload["findings"] = [
                {
                    "rule_id": f.rule_id, "category": f.category, "severity": f.severity,
                    "message_appraiser": f.message_appraiser, "message_reviewer": f.message_reviewer,
                    "field_path": f.field_path, "xpath": f.xpath, "section": f.section,
                    "values": f.values_json, "citation": f.citation,
                }
                for f in findings
            ]
            payload["rule_errors"] = [
                {"rule_id": e.rule_id, "error_type": e.error_type, "detail": e.detail} for e in errors
            ]
        return payload
```

The `text` import belongs at the top of `repository.py` with the other sqlalchemy imports: `from sqlalchemy import select, text`.

`backend/app/persistence/__init__.py`:
```python
from .db import init_db
from .repository import RunRepository

__all__ = ["RunRepository", "init_db"]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `backend\.venv\Scripts\python.exe -m pytest backend/tests/test_repository.py -v`
Expected: 3 PASS

- [ ] **Step 5: Commit**

```powershell
git add backend
git commit -m "feat: run persistence with SQLite (no-delete retention)"
```

---

### Task 9: API + pipeline wiring (end-to-end on real sample)

**Files:**
- Create: `backend/app/api/__init__.py`, `backend/app/api/runs.py`, `backend/app/api/meta.py`, `backend/app/main.py`
- Test: `backend/tests/test_api.py`

**Interfaces:**
- Consumes: everything above
- Produces:
  - `app.main.create_app() -> FastAPI`
  - `POST /api/runs` (multipart `file`) → full run payload, 422 on `IngestError`
  - `GET /api/runs` → list of summaries; `GET /api/runs/{id}` → full payload or 404
  - `GET /api/meta` → `{"schema_version": …, "ruleset_version": …, "rule_count": …}`
  - Static frontend served from `frontend/dist` at `/` when the folder exists

- [ ] **Step 1: Write the failing test**

`backend/tests/test_api.py`:
```python
import pytest
from fastapi.testclient import TestClient

from tests.conftest import SAMPLES_DIR, XSD_PATH

needs_official_files = pytest.mark.skipif(
    not (SAMPLES_DIR.exists() and XSD_PATH.exists()), reason="official GSE files not present"
)


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("QC_DATA_DIR", str(tmp_path))
    # config reads env at import; build the app fresh per test
    import importlib

    import app.config
    importlib.reload(app.config)
    from app.main import create_app
    return TestClient(create_app())


@needs_official_files
def test_upload_sample_zip_end_to_end(client):
    zpath = SAMPLES_DIR / "SF1_Appraisal_v1.4.zip"
    with open(zpath, "rb") as fh:
        response = client.post("/api/runs", files={"file": ("SF1_Appraisal_v1.4.zip", fh, "application/zip")})
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["schema_version"] == "GSE_UAD_3.6.0_v1.3"
    assert payload["ruleset_version"].startswith("H1-seed-phase1-")
    assert set(payload["counts"]) == {"HardStop", "Warning", "Advisory"}
    # SF1 subject address is complete and valid -> the 4 seed rules pass
    assert payload["findings"] == []
    assert payload["rule_errors"] == []
    assert len(payload["file_hash"]) == 64  # sha256 hex


@needs_official_files
def test_upload_broken_report_produces_findings(client):
    """Blank the subject CityName and corrupt the PostalCode in-memory, re-zip, upload."""
    import io
    import zipfile

    from lxml import etree

    with zipfile.ZipFile(SAMPLES_DIR / "SF1_Appraisal_v1.4.zip") as zf:
        xml_bytes = zf.read("SF1_Appraisal_v1.4.xml")
    ns = {"m": "http://www.mismo.org/residential/2009/schemas"}
    doc = etree.fromstring(xml_bytes)
    address = doc.xpath("//m:VALUATION_ANALYSIS/m:PROPERTIES/m:PROPERTY[1]/m:ADDRESS", namespaces=ns)[0]
    address.find("m:CityName", ns).text = ""
    address.find("m:PostalCode", ns).text = "1234"
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("broken.xml", etree.tostring(doc))
    buf.seek(0)

    response = client.post("/api/runs", files={"file": ("broken.zip", buf, "application/zip")})
    assert response.status_code == 200
    payload = response.json()
    fired = {f["rule_id"] for f in payload["findings"]}
    assert fired == {"UAD1002", "UAD1005"}
    assert payload["counts"]["HardStop"] == 2
    city = next(f for f in payload["findings"] if f["rule_id"] == "UAD1002")
    assert city["severity"] == "HardStop"
    assert city["citation"].startswith("UAD 3.6 Appendix H-1")
    assert "CityName" in city["xpath"]


def test_upload_garbage_returns_422(client):
    response = client.post("/api/runs", files={"file": ("x.docx", b"hello", "application/octet-stream")})
    assert response.status_code == 422


@needs_official_files
def test_run_history_and_detail(client):
    with open(SAMPLES_DIR / "SF1_Appraisal_v1.4.zip", "rb") as fh:
        run_id = client.post("/api/runs", files={"file": ("SF1.zip", fh, "application/zip")}).json()["id"]
    listing = client.get("/api/runs").json()
    assert listing[0]["id"] == run_id
    detail = client.get(f"/api/runs/{run_id}").json()
    assert detail["findings"] == []
    assert client.get("/api/runs/does-not-exist").status_code == 404


def test_meta(client):
    meta = client.get("/api/meta").json()
    assert meta["schema_version"] == "GSE_UAD_3.6.0_v1.3"
    assert meta["rule_count"] == 4
```

- [ ] **Step 2: Run test to verify it fails**

Run: `backend\.venv\Scripts\python.exe -m pytest backend/tests/test_api.py -v`
Expected: FAIL import error

- [ ] **Step 3: Implement**

`backend/app/api/runs.py`:
```python
from __future__ import annotations

import hashlib

from fastapi import APIRouter, HTTPException, Request, UploadFile

from app.ingest import IngestError, extract
from app.rules import evaluate

router = APIRouter(prefix="/api")


@router.post("/runs")
async def create_run(file: UploadFile, request: Request) -> dict:
    state = request.app.state
    data = await file.read()
    try:
        raw = extract(data, file.filename or "upload")
    except IngestError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    adapter = state.adapter
    structural_errors = adapter.validate(raw)
    normalized = adapter.normalize(raw)
    result = evaluate(normalized, state.rules)
    run_id = state.repo.save_run(
        filename=file.filename or "upload",
        file_hash=hashlib.sha256(data).hexdigest(),
        schema_version=adapter.schema_version,
        ruleset_version=state.ruleset_version,
        structural_errors=structural_errors,
        result=result,
    )
    return state.repo.get_run(run_id)


@router.get("/runs")
def list_runs(request: Request) -> list[dict]:
    return request.app.state.repo.list_runs()


@router.get("/runs/{run_id}")
def get_run(run_id: str, request: Request) -> dict:
    payload = request.app.state.repo.get_run(run_id)
    if payload is None:
        raise HTTPException(status_code=404, detail="Run not found")
    return payload
```

`backend/app/api/meta.py`:
```python
from __future__ import annotations

from fastapi import APIRouter, Request

router = APIRouter(prefix="/api")


@router.get("/meta")
def meta(request: Request) -> dict:
    state = request.app.state
    return {
        "schema_version": state.adapter.schema_version,
        "ruleset_version": state.ruleset_version,
        "rule_count": len(state.rules),
    }
```

`backend/app/api/__init__.py`: empty file.

`backend/app/main.py`:
```python
from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app import config
from app.api import meta, runs
from app.persistence import RunRepository, init_db
from app.rules import load_ruleset
from app.schema_adapters import get_default_adapter


def create_app() -> FastAPI:
    app = FastAPI(title="UAD 3.6 QC", version="0.1.0")
    app.state.adapter = get_default_adapter()
    app.state.rules, app.state.ruleset_version = load_ruleset(config.RULES_PATH)
    app.state.repo = RunRepository(init_db(config.DB_URL))

    # Dev convenience: allow the Vite dev server origin.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(runs.router)
    app.include_router(meta.router)

    if config.FRONTEND_DIST.exists():
        app.mount("/", StaticFiles(directory=config.FRONTEND_DIST, html=True), name="frontend")
    return app


app = create_app()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `backend\.venv\Scripts\python.exe -m pytest backend/tests/test_api.py -v`
Expected: 5 PASS (XSD compile makes the first test slow — a few seconds is normal)

- [ ] **Step 5: Run full suite, commit**

Run: `backend\.venv\Scripts\python.exe -m pytest backend/tests -v`
Expected: all PASS

```powershell
git add backend
git commit -m "feat: run pipeline API - upload, evaluate, persist, history"
```

---

### Task 10: Minimal frontend

**Files:**
- Create: `frontend/` via Vite scaffold, then replace/add: `frontend/vite.config.ts`, `frontend/src/index.css`, `frontend/src/types.ts`, `frontend/src/api.ts`, `frontend/src/App.tsx`, `frontend/src/main.tsx`, `frontend/index.html`

No frontend unit tests in Phase 1 — the components are dumb renderers over payloads already covered by API tests; the end-to-end check in Task 11 verifies the UI manually. (Playwright arrives with the reviewer workflow in Phase 3, where UI logic appears.)

- [ ] **Step 1: Scaffold**

```powershell
npm create vite@latest frontend -- --template react-ts
npm --prefix frontend install
npm --prefix frontend install tailwindcss @tailwindcss/vite
```

- [ ] **Step 2: Configure**

`frontend/vite.config.ts`:
```ts
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    proxy: { "/api": "http://localhost:8000" },
  },
});
```

`frontend/src/index.css`:
```css
@import "tailwindcss";
```

`frontend/index.html` — set the title:
```html
<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>UAD 3.6 QC</title>
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/main.tsx"></script>
  </body>
</html>
```

- [ ] **Step 3: Types + API client**

`frontend/src/types.ts`:
```ts
export type Severity = "HardStop" | "Warning" | "Advisory";
export type Mode = "appraiser" | "reviewer";

export interface Finding {
  rule_id: string;
  category: string;
  severity: Severity;
  message_appraiser: string;
  message_reviewer: string;
  field_path: string;
  xpath: string | null;
  section: string | null;
  values: Record<string, string | null>;
  citation: string | null;
}

export interface StructuralError {
  code: string;
  message: string;
  location: string | null;
}

export interface RuleError {
  rule_id: string;
  error_type: string;
  detail: string;
}

export interface Run {
  id: string;
  filename: string;
  file_hash: string;
  created_at: string;
  schema_version: string;
  ruleset_version: string;
  counts: Record<Severity, number>;
  structural_errors: StructuralError[];
  findings: Finding[];
  rule_errors: RuleError[];
}
```

`frontend/src/api.ts`:
```ts
import type { Run } from "./types";

export async function uploadReport(file: File): Promise<Run> {
  const body = new FormData();
  body.append("file", file);
  const res = await fetch("/api/runs", { method: "POST", body });
  if (!res.ok) {
    const detail = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(detail.detail ?? "Upload failed");
  }
  return res.json();
}
```

- [ ] **Step 4: App UI**

`frontend/src/App.tsx`:
```tsx
import { useMemo, useState } from "react";
import { uploadReport } from "./api";
import type { Finding, Mode, Run, Severity } from "./types";

const SEVERITY_ORDER: Severity[] = ["HardStop", "Warning", "Advisory"];
const SEVERITY_STYLE: Record<Severity, string> = {
  HardStop: "bg-red-100 text-red-800 border-red-300",
  Warning: "bg-amber-100 text-amber-800 border-amber-300",
  Advisory: "bg-sky-100 text-sky-800 border-sky-300",
};
const SEVERITY_LABEL: Record<Severity, string> = {
  HardStop: "Hard Stop",
  Warning: "Warning",
  Advisory: "Advisory",
};

function SeverityBadge({ severity }: { severity: Severity }) {
  return (
    <span className={`inline-block rounded border px-2 py-0.5 text-xs font-semibold ${SEVERITY_STYLE[severity]}`}>
      {SEVERITY_LABEL[severity]}
    </span>
  );
}

function FindingCard({ finding, mode }: { finding: Finding; mode: Mode }) {
  const message = mode === "appraiser" ? finding.message_appraiser : finding.message_reviewer;
  return (
    <div className="rounded-lg border border-gray-200 bg-white p-4 shadow-sm">
      <div className="flex items-center gap-2">
        <SeverityBadge severity={finding.severity} />
        <span className="text-xs text-gray-500">{finding.rule_id}</span>
      </div>
      <p className="mt-2 text-sm text-gray-900">{message}</p>
      <dl className="mt-2 space-y-0.5 text-xs text-gray-600">
        {finding.section && <div><dt className="inline font-medium">Location: </dt><dd className="inline">{finding.section}{finding.xpath ? ` — ${finding.xpath}` : ""}</dd></div>}
        {Object.entries(finding.values).map(([k, v]) => (
          <div key={k}><dt className="inline font-medium">Value: </dt><dd className="inline">{k} = {v === null || v === "" ? "(blank)" : v}</dd></div>
        ))}
        {mode === "reviewer" && finding.citation && (
          <div><dt className="inline font-medium">Citation: </dt><dd className="inline">{finding.citation}</dd></div>
        )}
      </dl>
    </div>
  );
}

export default function App() {
  const [run, setRun] = useState<Run | null>(null);
  const [mode, setMode] = useState<Mode>("appraiser");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function onFile(file: File | undefined) {
    if (!file) return;
    setBusy(true);
    setError(null);
    try {
      setRun(await uploadReport(file));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  const grouped = useMemo(() => {
    if (!run) return [];
    const byCategory = new Map<string, Finding[]>();
    for (const f of run.findings) {
      byCategory.set(f.category, [...(byCategory.get(f.category) ?? []), f]);
    }
    return [...byCategory.entries()].map(([category, findings]) => ({
      category,
      findings: [...findings].sort(
        (a, b) => SEVERITY_ORDER.indexOf(a.severity) - SEVERITY_ORDER.indexOf(b.severity),
      ),
    }));
  }, [run]);

  return (
    <div className="min-h-screen bg-gray-50">
      <header className="border-b border-gray-200 bg-white px-6 py-4">
        <div className="mx-auto flex max-w-4xl items-center justify-between">
          <h1 className="text-lg font-semibold text-gray-900">UAD 3.6 QC</h1>
          <div className="flex rounded-lg border border-gray-300 text-sm">
            {(["appraiser", "reviewer"] as Mode[]).map((m) => (
              <button
                key={m}
                onClick={() => setMode(m)}
                className={`px-3 py-1.5 first:rounded-l-lg last:rounded-r-lg ${mode === m ? "bg-gray-900 text-white" : "bg-white text-gray-700"}`}
              >
                {m === "appraiser" ? "Appraiser" : "QD Reviewer"}
              </button>
            ))}
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-4xl space-y-6 px-6 py-8">
        <section className="rounded-lg border-2 border-dashed border-gray-300 bg-white p-8 text-center">
          <p className="text-sm text-gray-600">Upload a UAD 3.6 delivery (.zip) or report (.xml)</p>
          <input
            type="file"
            accept=".zip,.xml"
            disabled={busy}
            onChange={(e) => onFile(e.target.files?.[0])}
            className="mx-auto mt-3 block text-sm"
          />
          {busy && <p className="mt-2 text-sm text-gray-500">Checking report…</p>}
          {error && <p className="mt-2 text-sm text-red-700">{error}</p>}
        </section>

        {run && (
          <>
            <section className="rounded-lg border border-gray-200 bg-white p-4 text-xs text-gray-600">
              <span className="font-medium text-gray-900">{run.filename}</span>
              {" · "}{new Date(run.created_at).toLocaleString()}
              {" · schema "}{run.schema_version}
              {" · rules "}{run.ruleset_version}
            </section>

            <section className="flex gap-3">
              {SEVERITY_ORDER.map((s) => (
                <div key={s} className={`flex-1 rounded-lg border p-3 text-center ${SEVERITY_STYLE[s]}`}>
                  <div className="text-2xl font-bold">{run.counts[s] ?? 0}</div>
                  <div className="text-xs font-medium">{SEVERITY_LABEL[s]}s</div>
                </div>
              ))}
            </section>

            {run.structural_errors.length > 0 && (
              <section className="rounded-lg border border-purple-300 bg-purple-50 p-4">
                <h2 className="text-sm font-semibold text-purple-900">
                  Schema / structural issues ({run.structural_errors.length}) — checked before QC rules
                </h2>
                <ul className="mt-2 max-h-60 space-y-1 overflow-y-auto text-xs text-purple-800">
                  {run.structural_errors.map((e, i) => (
                    <li key={i}>[{e.code}{e.location ? ` @ ${e.location}` : ""}] {e.message}</li>
                  ))}
                </ul>
              </section>
            )}

            {run.findings.length === 0 ? (
              <section className="rounded-lg border border-green-300 bg-green-50 p-6 text-center">
                <p className="font-semibold text-green-900">No issues found</p>
                <p className="mt-1 text-xs text-green-800">
                  {run.filename} · ruleset {run.ruleset_version} · schema {run.schema_version}
                </p>
              </section>
            ) : (
              grouped.map(({ category, findings }) => (
                <section key={category} className="space-y-2">
                  <h2 className="text-sm font-semibold text-gray-900">{category}</h2>
                  {findings.map((f, i) => (
                    <FindingCard key={`${f.rule_id}-${i}`} finding={f} mode={mode} />
                  ))}
                </section>
              ))
            )}

            {mode === "reviewer" && run.rule_errors.length > 0 && (
              <section className="rounded-lg border border-gray-300 bg-gray-100 p-4">
                <h2 className="text-sm font-semibold text-gray-900">Rule execution errors ({run.rule_errors.length})</h2>
                <ul className="mt-2 space-y-1 text-xs text-gray-700">
                  {run.rule_errors.map((e, i) => (
                    <li key={i}>{e.rule_id}: [{e.error_type}] {e.detail}</li>
                  ))}
                </ul>
              </section>
            )}
          </>
        )}
      </main>
    </div>
  );
}
```

`frontend/src/main.tsx`:
```tsx
import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import "./index.css";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
```

Delete the scaffold leftovers: `frontend/src/App.css`, `frontend/src/assets/react.svg`, `frontend/public/vite.svg` references if the build complains.

- [ ] **Step 5: Build and verify**

```powershell
npm --prefix frontend run build
```
Expected: `frontend/dist` produced without TypeScript errors.

- [ ] **Step 6: Commit**

```powershell
git add frontend
git commit -m "feat: minimal findings UI with appraiser/reviewer mode switch"
```

---

### Task 11: Dev script, docs, full end-to-end verification

**Files:**
- Create: `dev.ps1`, `docs/DEV.md`

- [ ] **Step 1: Dev script**

`dev.ps1`:
```powershell
# Builds the frontend and starts the QC app at http://localhost:8000
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
npm --prefix frontend run build
backend\.venv\Scripts\python.exe -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000
```

- [ ] **Step 2: Dev doc**

`docs/DEV.md`:
```markdown
# Running the UAD 3.6 QC app (local)

## One-time setup
1. Install Python 3.12+ and Node 20+.
2. `python -m venv backend\.venv`
3. `backend\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt`
4. `npm --prefix frontend install`

## Every time
Run `.\dev.ps1` from the project folder, then open http://localhost:8000

## Try it
Upload `Sample reports\SF1_Appraisal_v1.4.zip`. You should see:
- run metadata (schema + ruleset versions),
- a purple "Schema / structural issues" box (expected — samples are v1.4, schema is v1.3),
- a green "No issues found" box (the 4 seed rules pass on this sample).

Toggle Appraiser / QD Reviewer — reviewer mode shows citations and rule errors.

## Tests
`backend\.venv\Scripts\python.exe -m pytest backend/tests -v`

## Versions on every run
- `schema_version` comes from the active SchemaAdapter (`GSE_UAD_3.6.0_v1.3`).
- `ruleset_version` = ruleset name + content hash of `rules\seed_rules.json`; editing the file changes the recorded version automatically.
```

- [ ] **Step 3: Full-suite + manual end-to-end verification**

```powershell
backend\.venv\Scripts\python.exe -m pytest backend/tests -v
.\dev.ps1
```

In the browser at http://localhost:8000, verify each item:
1. Upload `Sample reports\SF1_Appraisal_v1.4.zip` → metadata bar, counts row, structural box (if any errors), green clean-pass box.
2. Upload `Sample reports\SF3_Appraisal_v1.4.zip` and `Sample reports\Condo2_Appraisal_v1.4.zip` → both complete without server errors.
3. Toggle to QD Reviewer → citations visible on findings (upload a deliberately broken file per the Task 9 test to see findings, or temporarily rename a seed-rule field to force one).
4. Upload a `.docx` or random file → clean error message, app doesn't crash.

- [ ] **Step 4: Commit**

```powershell
git add dev.ps1 docs/DEV.md
git commit -m "feat: dev runner script and local run instructions"
```

---

## Phase 1 exit criteria (from spec success criteria)

- [x-when-done] Sample file flows end-to-end: upload → XSD validate → normalize → rules → grouped severity-ranked findings displayed.
- [x-when-done] Adapter and ruleset are pluggable: `PlaceholderAdapter` proves the contract; editing `rules/seed_rules.json` changes behavior + recorded version with zero code changes.
- [x-when-done] Both modes render from one run payload (message variants + reviewer-only citation/rule-error visibility).
- [x-when-done] Structural errors render distinctly, above findings.
- [x-when-done] Runs persist; no delete paths exist.

**Deferred to later phases (per spec):** exports (PDF/CSV — Phase 5), reviewer actions/sign-off (Phase 3), admin rules UI (Phase 4), H-1 bulk import of all 729 rules (Phase 2), AI rules (Phase 6), GCP deploy (Phase 7).
