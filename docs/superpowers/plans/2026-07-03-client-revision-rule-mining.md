# Client Revision Rule Mining — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the backend pipeline and Admin UI to turn mined client-revision themes into
draft `candidate_rules`, redundancy-checked against the live 729-rule set, reviewable and
promotable from the existing Admin panel — then run it once against the real RRR export.

**Architecture:** New `backend/app/revision_mining/` package holds three pure/testable modules
(clean+split text preprocessing, redundancy checking, and a bulk-insert script) that never make
a network call. A new `candidate_rules` table + `CandidateRulesRepository` sits alongside the
existing `rules` table, reusing `RuleDefinition` for validation. Admin gets 4 new endpoints and
one new tab. The theme-mining step itself (clustering ~4,700 revision-text rows into named
patterns) is not code — it's an operational task (Task 12) run by dispatching Claude Code
subagents, per the approved design spec.

**Tech Stack:** Python 3 / FastAPI / SQLAlchemy / pydantic (backend, existing), openpyxl (new
dependency), React/TypeScript/Tailwind (frontend, existing).

**Source spec:** `docs/superpowers/specs/2026-07-03-client-revision-rule-mining-design.md`

---

### Task 1: Add openpyxl dependency

**Files:**
- Modify: `backend/requirements.txt`

- [ ] **Step 1: Add the dependency**

Append to `backend/requirements.txt`:
```
openpyxl>=3.1
```

- [ ] **Step 2: Install it into the project venv**

Run: `backend\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt`
Expected: `openpyxl` installed (already present from earlier manual install this session, so this
should be a no-op confirming the pin is satisfied).

- [ ] **Step 3: Commit**

```bash
git add backend/requirements.txt
git commit -m "chore: add openpyxl for revision-mining xlsx ingestion"
```

---

### Task 2: Port clean/split text preprocessing

**Files:**
- Create: `backend/app/revision_mining/__init__.py`
- Create: `backend/app/revision_mining/clean_split.py`
- Test: `backend/tests/test_revision_mining_clean_split.py`

- [ ] **Step 1: Create the package init**

`backend/app/revision_mining/__init__.py`:
```python
```
(empty — marks the package)

- [ ] **Step 2: Write the failing tests**

`backend/tests/test_revision_mining_clean_split.py`:
```python
"""Clean/split preprocessing for raw revision-request text.
Ported from the anthropic-skills revision-request-parser skill (Clean-4.7 + Splitv4.11).
Synthetic examples only — no real revision text (which may contain borrower PII).
"""

from app.revision_mining.clean_split import clean_revision_text, split_revision_text


def test_clean_strips_email_boilerplate_and_signoff():
    raw = (
        "Good morning,\n\n"
        "Please review the attached information as it pertains to a Reconsideration of Value request.\n"
        "The subject site has adverse external influence not addressed.\n\n"
        "Thank you,\nJohn"
    )
    cleaned = clean_revision_text(raw)
    assert cleaned is not None
    assert "adverse external influence" in cleaned
    assert "Good morning" not in cleaned
    assert "Thank you" not in cleaned


def test_clean_drops_junk_only_cells():
    assert clean_revision_text("N/A") is None
    assert clean_revision_text("See attached") is None
    assert clean_revision_text("") is None
    assert clean_revision_text(None) is None


def test_split_breaks_numbered_bundle_into_items():
    text = "1. Correct the ZIP code on the subject address.\n2. Provide support for the site adjustment.\n3. Add the missing comparable photo."
    items = split_revision_text(text)
    assert len(items) == 3
    assert items[0].startswith("Correct the ZIP code")
    assert items[1].startswith("Provide support for the site adjustment")
    assert items[2].startswith("Add the missing comparable photo")


def test_split_protects_addresses_from_being_split():
    text = "Please correct the comparable address.\n123 Main St, Springfield, IL 62704\nAdd the missing photo."
    items = split_revision_text(text)
    joined = " ".join(items)
    assert "123 Main St" in joined
    # The address line must not become its own orphan action item when it has no verb:
    assert not any(item.strip().startswith("123 Main St") and len(item.split()) < 4 for item in items)
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `backend\.venv\Scripts\python.exe -m pytest backend/tests/test_revision_mining_clean_split.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.revision_mining.clean_split'`

- [ ] **Step 4: Write the implementation (ported, with attribution)**

`backend/app/revision_mining/clean_split.py`:
```python
"""Clean + split preprocessing for raw appraisal revision-request text.

Ported from the `anthropic-skills:revision-request-parser` skill's
`scripts/process_revisions.py` (Clean-4.7 + Splitv4.11 stages). Pure regex —
no network calls, no LLM. Categorization (stage 3 of that skill) is
intentionally NOT ported here: this project routes categorization/theme-mining
through Claude Code directly rather than a script with a standalone API key
(see docs/superpowers/specs/2026-07-03-client-revision-rule-mining-design.md).
"""

from __future__ import annotations

import re
from typing import Optional


def normalize_revision_text(text: str) -> str:
    if not text:
        return text
    text = re.sub(r'Critical Rule Findings:\s*\n', 'Critical Rule Findings: ', text, flags=re.IGNORECASE)
    text = re.sub(r'(\n\d+)\.[a-zA-Z]\s', r'\1. ', text)
    text = re.sub(r'(^|\n)(\d+)[.:),-]{1,2}\s*([A-Za-z"\'])', r'\1\2. \3', text)
    return text


BOILERPLATE_PATTERNS = [
    re.compile(r'The following condition\(s\) have been requested:?\s*', re.IGNORECASE),
    re.compile(r'\**Appraisal Revisions needed:?\**\s*', re.IGNORECASE),
    re.compile(r'Appraiser please be advised the following Underwriting Conditions has been requested:?\s*', re.IGNORECASE),
    re.compile(r'Appraisal Correction Requested\s*', re.IGNORECASE),
    re.compile(r'Please review the attached information as it pertains to a Reconsideration of Value request\.?\s*', re.IGNORECASE),
    re.compile(r'The submitted order report was not approved and a revision is requested with the following reason:?\s*', re.IGNORECASE),
    re.compile(r'Revisions need to be in a dated addendum and the Date of Signature needs to be updated\.?', re.IGNORECASE),
    re.compile(r'Please place a summary of the changes on the last page.*?Signature Date\.?', re.IGNORECASE | re.DOTALL),
    re.compile(r'When re-submitting a revised or corrected report.*?Date of Signature and Report\.?', re.IGNORECASE | re.DOTALL),
    re.compile(r'Please see the request from the Underwriter:?\s*', re.IGNORECASE),
    re.compile(r'Please see the requested revisions? below:?\s*', re.IGNORECASE),
    re.compile(r'\*\*\*UPLOADED\*\*\*\s*', re.IGNORECASE),
    re.compile(r'(^|\n)\s*uploaded\s*(?=\n|$)', re.IGNORECASE),
    re.compile(r'(^|\n)\d{1,2}\/\d{1,2}(?:\/\d{2,4})?:\s*'),
    re.compile(r'Please comment regarding the following items noted in photos\s*[-:]?\s*', re.IGNORECASE),
]

JUNK_PATTERNS = [
    re.compile(r'^n\/?a$', re.IGNORECASE),
    re.compile(r'^none\.?$', re.IGNORECASE),
    re.compile(r'^see attached', re.IGNORECASE),
    re.compile(r'^no revisions needed', re.IGNORECASE),
    re.compile(r'^please review', re.IGNORECASE),
    re.compile(r'^see comments', re.IGNORECASE),
    re.compile(r'^attached', re.IGNORECASE),
    re.compile(r'^review attached', re.IGNORECASE),
]


def clean_revision_text(text: str) -> Optional[str]:
    """Full clean pipeline for a single REVISION REQUEST cell.
    Returns cleaned text, or None if the row should be dropped."""
    if not text or not text.strip():
        return None

    text = text.strip()
    text = re.sub(r'CONFIDENTIALITY NOTICE:[\s\S]*', '', text, flags=re.IGNORECASE)
    text = re.sub(r'---------- Forwarded message ---------[\s\S]*', '', text, flags=re.IGNORECASE)
    text = re.sub(r'From:.*?Date:.*?Subject:.*?\n', '', text, flags=re.IGNORECASE)
    text = re.sub(
        r'(?:^|\n)(?:good morning|good afternoon|good day|hello|hi|greetings|dear)[^\n]*[\r\n\s]*',
        '', text, flags=re.IGNORECASE
    )
    text = re.sub(
        r'(?:\r?\n|\s)*(?:thank you|thanks|best regards|sincerely|respectfully|'
        r'please let me know|should you have any questions|if you have any questions|questions\?)[\s\S]*$',
        '', text, flags=re.IGNORECASE
    )
    for pattern in BOILERPLATE_PATTERNS:
        text = pattern.sub('', text)
    text = re.sub(r'Should there be any questions.*?at:?\s*[\d\-\(\)\s]{10,15}', '', text, flags=re.IGNORECASE)
    text = re.sub(r'If you have questions.*?right away\.?', '', text, flags=re.IGNORECASE)
    text = re.sub(r'If you have any questions or need further clarification.*?[\d\-\(\)\s]{10,15}', '', text, flags=re.IGNORECASE)

    text = text.replace('\xa0', ' ')
    text = re.sub(r'\n{3,}', '\n\n', text)
    text = text.strip()

    req_header_pattern = re.compile(
        r'(?:\n|^)\s*(\d[A-Za-z]{2}\s+(?:REV\s*|REVISION\s*)?REQ(?:UEST)?\s+\d{1,2}\/\d{1,2}[:\-]?)',
        re.IGNORECASE
    )
    text = req_header_pattern.sub(r'|||SPLIT|||\1 ', text)

    if len(text) < 10 and not re.search(r'\d', text) and '|||SPLIT|||' not in text:
        return None
    if any(p.search(text) for p in JUNK_PATTERNS):
        return None

    text = normalize_revision_text(text)
    return text if text.strip() else None


ADDRESS_GUARD_PATTERNS = [
    re.compile(
        r'(^|\n)(\s*(?:Subject(?: Address)?|Property(?: Address)?|Address)[\s:]*\d{1,5}\s+.*)',
        re.IGNORECASE
    ),
    re.compile(
        r'(^|\n)(\s*(?:[-*•>]|\d+[\.\)]|\(\d+\))?\s*\d{1,5}\s+[A-Za-z0-9\s]+'
        r'(?:ST|AVE|RD|DR|LN|CT|PL|BLVD|WAY|HWY|TRL|PKWY|LOOP|TER|CIR|SQ|CV|PT|'
        r'STREET|AVENUE|ROAD|DRIVE|LANE|COURT|PLACE|BOULEVARD|TRAIL|PARKWAY|CIRCLE|'
        r'SQUARE|COVE|POINT)\b.*)',
        re.IGNORECASE
    ),
    re.compile(
        r'(^|\n)(\s*(?:[-*•>]|\d+[\.\)]|\(\d+\))?\s*[A-Za-z0-9\s]+(?:,\s*|\s+)[A-Z]{2}\s*\d{5}.*)',
    ),
]

ISOLATED_ADDRESS_RE = re.compile(
    r'^\s*(?:Subject(?: Address)?|Property(?: Address)?|Address)?[\s:]*\d{1,5}\s+[A-Za-z0-9\s]+'
    r'(?:ST|AVE|RD|DR|LN|CT|PL|BLVD|WAY|HWY|TRL|PKWY|LOOP|TER|CIR|SQ|CV|PT|'
    r'STREET|AVENUE|ROAD|DRIVE|LANE|COURT|PLACE|BOULEVARD|TRAIL|PARKWAY|CIRCLE|'
    r'SQUARE|COVE|POINT)\b[^a-z]*$',
    re.IGNORECASE
)

DANGLING_LEAD_IN_RE = re.compile(
    r'(?:following|requested|needed|revisions?|notes|comments|advises?)[^\w]*:$',
    re.IGNORECASE
)
DANGLING_LABEL_RE = re.compile(r'^[a-zA-Z\s()]+:$')
DANGLING_JUNK_RE = re.compile(
    r'^(good morning|good afternoon|hello|hi|please see below|see attached|please advise|see comments)\.?$',
    re.IGNORECASE
)
EXTENDED_BOILERPLATE_RE = re.compile(
    r'call me directly at|following item still needs to be addressed|'
    r'reasons to advise of any delay|following condition\(s\) have been requested|'
    r'Appraisal Revisions needed',
    re.IGNORECASE
)
ACTION_VERB_RE = re.compile(
    r'(update|correct|revise|provide|fix|amend|add|remove|change|comment|explain|verify)',
    re.IGNORECASE
)
FORM_KEYWORD_RE = re.compile(r'(1004|1073|UAD|FHA|VA|USDA|MC|REO|FNC-|CUSTOM-)', re.IGNORECASE)
MARKER = '|||SPLIT|||'
GUARD = '|||GUARD|||'
LEADING_MARKER_RE = re.compile(r'^\s*(?:\d{1,2}[.)\]:,-]+|[-*•>]+|[A-Za-z]\.)\s+')
REQ_LABEL_RE = re.compile(
    r'^(?:\s*|-|\*)*[1-9](?:ST|ND|RD|TH)\s+(?:REV\s*|REVISION\s*)?REQ(?:UEST)?[\s:\-]*',
    re.IGNORECASE
)


def split_revision_text(text: str) -> list[str]:
    """Break a cleaned revision-text blob into individual atomic action items."""
    for pattern in ADDRESS_GUARD_PATTERNS:
        text = pattern.sub(rf'\1{GUARD}\2', text)

    text = re.sub(r'\n\s*\n', MARKER, text)
    text = re.sub(r'(^|\n|\s)(?=(?:FNC-[A-Z0-9\-]+|CUSTOM-[A-Z0-9\-]+))', rf'\1{MARKER}', text)
    text = re.sub(r'\n\s*(?=(?:\d+[\.\)]|\(\s*\d+\s*\))[ \t]+|[-*•>~]\s*)', MARKER, text)
    text = re.sub(r'\n\s*(?=[a-zA-Z]\.[ \t]+.{30,})', MARKER, text)
    text = re.sub(r'\s+(?=\(\s*\d+\s*\)\s)', MARKER, text)
    text = re.sub(r'([.?!;:]\s{1,3})(\d{1,2}[\.\)]\s+[A-Z])', rf'\1{MARKER}\2', text)
    text = text.replace(GUARD, '\n')

    raw_segments = text.split(MARKER)
    cleaned_segments: list[str] = []

    for segment in raw_segments:
        segment = segment.strip()
        segment = REQ_LABEL_RE.sub('', segment).strip()
        segment = re.sub(r'^\*{0,3}\d{1,2}\/\d{1,2}(?:\/\d{2,4})?[:\-]\s*\n?', '', segment).strip()

        if re.match(r'^\*{1,3}\d{1,2}\/\d', segment):
            continue
        if re.match(r'^[\d\/\-\.:\s]+$', segment):
            continue

        words = segment.split()
        word_count = len(words)
        has_action_verb = bool(ACTION_VERB_RE.search(segment))
        has_form_keyword = bool(FORM_KEYWORD_RE.search(segment))

        if word_count < 3 and not has_action_verb and not has_form_keyword:
            continue
        if DANGLING_LEAD_IN_RE.search(segment) and len(segment) < 100:
            continue
        if DANGLING_LABEL_RE.match(segment) and len(segment) < 50:
            continue
        if DANGLING_JUNK_RE.match(segment):
            continue
        if EXTENDED_BOILERPLATE_RE.search(segment):
            continue
        if word_count < 3 and not re.search(r'[a-zA-Z]{4,}', segment) and not re.search(r'(FNC-|CUSTOM-)', segment, re.IGNORECASE):
            continue
        if ISOLATED_ADDRESS_RE.match(segment) and not has_action_verb:
            continue

        while LEADING_MARKER_RE.match(segment):
            segment = LEADING_MARKER_RE.sub('', segment)

        if segment:
            segment = segment[0].upper() + segment[1:]
        if len(segment) > 5:
            cleaned_segments.append(segment.strip())

    return cleaned_segments
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `backend\.venv\Scripts\python.exe -m pytest backend/tests/test_revision_mining_clean_split.py -v`
Expected: PASS (4 tests)

- [ ] **Step 6: Commit**

```bash
git add backend/app/revision_mining/__init__.py backend/app/revision_mining/clean_split.py backend/tests/test_revision_mining_clean_split.py
git commit -m "feat: port clean/split revision-text preprocessing (no LLM, no network)"
```

---

### Task 3: Preprocess loader (xlsx → deduped atomic items)

**Files:**
- Create: `backend/app/revision_mining/preprocess.py`
- Test: `backend/tests/test_revision_mining_preprocess.py`

- [ ] **Step 1: Write the failing test**

`backend/tests/test_revision_mining_preprocess.py`:
```python
"""Preprocess loader: dedupes identical sheets, applies clean+split, no PII in fixtures."""

import openpyxl
import pytest

from app.revision_mining.preprocess import extract_atomic_items, load_unique_sheets


@pytest.fixture
def synthetic_xlsx(tmp_path):
    path = tmp_path / "synthetic_rrr.xlsx"
    wb = openpyxl.Workbook()
    ws1 = wb.active
    ws1.title = "SheetA"
    ws1.append(["REVISION REQUEST"])
    ws1.append(["1. Correct the subject ZIP code.\n2. Provide support for the site adjustment."])
    ws1.append(["N/A"])

    ws2 = wb.create_sheet("SheetB-Duplicate")
    ws2.append(["REVISION REQUEST"])
    ws2.append(["1. Correct the subject ZIP code.\n2. Provide support for the site adjustment."])
    ws2.append(["N/A"])

    ws3 = wb.create_sheet("SheetC-Unique")
    ws3.append(["REVISION REQUEST"])
    ws3.append(["Add the missing comparable photo."])

    wb.save(path)
    return path


def test_load_unique_sheets_dedupes_identical_content(synthetic_xlsx):
    sheets = load_unique_sheets(synthetic_xlsx)
    assert len(sheets) == 2  # SheetA and SheetB-Duplicate are identical; SheetC-Unique differs


def test_extract_atomic_items_cleans_splits_and_dedupes(synthetic_xlsx):
    items = extract_atomic_items(synthetic_xlsx)
    assert len(items) == 3  # 2 items from the one kept duplicate sheet + 1 from the unique sheet
    assert any("ZIP code" in i for i in items)
    assert any("site adjustment" in i for i in items)
    assert any("comparable photo" in i for i in items)
    assert not any(i.strip() == "N/A" for i in items)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `backend\.venv\Scripts\python.exe -m pytest backend/tests/test_revision_mining_preprocess.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.revision_mining.preprocess'`

- [ ] **Step 3: Write the implementation**

`backend/app/revision_mining/preprocess.py`:
```python
from __future__ import annotations

import hashlib
from pathlib import Path

import openpyxl

from .clean_split import clean_revision_text, split_revision_text


def _sheet_content_hash(ws) -> str:
    """Hash a sheet's non-blank first-column values (skipping the header row).
    Used to detect byte-identical duplicate sheets (seen in the real export:
    two 'Master' tabs were exact copies of each other)."""
    h = hashlib.sha256()
    for row in ws.iter_rows(min_row=2, values_only=True):
        value = (row[0] or "").strip() if row and row[0] else ""
        if value:
            h.update(value.encode("utf-8", "ignore"))
    return h.hexdigest()


def load_unique_sheets(xlsx_path: Path) -> list:
    """Load all worksheets, dropping any whose content is byte-identical to
    an earlier sheet (keeps the first occurrence)."""
    wb = openpyxl.load_workbook(xlsx_path, read_only=True)
    seen_hashes: set[str] = set()
    kept = []
    for ws in wb.worksheets:
        digest = _sheet_content_hash(ws)
        if digest in seen_hashes:
            continue
        seen_hashes.add(digest)
        kept.append(ws)
    return kept


def extract_atomic_items(xlsx_path: Path) -> list[str]:
    """Load unique sheets, clean each REVISION REQUEST cell, split bundled
    cells into atomic action items. Returns a flat list of cleaned strings."""
    items: list[str] = []
    for ws in load_unique_sheets(xlsx_path):
        for row in ws.iter_rows(min_row=2, values_only=True):
            raw = row[0] if row else None
            cleaned = clean_revision_text(raw or "")
            if cleaned is None:
                continue
            items.extend(split_revision_text(cleaned))
    return items
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `backend\.venv\Scripts\python.exe -m pytest backend/tests/test_revision_mining_preprocess.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add backend/app/revision_mining/preprocess.py backend/tests/test_revision_mining_preprocess.py
git commit -m "feat: xlsx sheet-dedup + atomic item extraction for revision mining"
```

---

### Task 4: `candidate_rules` table

**Files:**
- Modify: `backend/app/persistence/tables.py`

- [ ] **Step 1: Add the table**

Append to `backend/app/persistence/tables.py` (after `AuditLogRow`, end of file):
```python


class CandidateRuleRow(Base):
    __tablename__ = "candidate_rules"
    # Drafts from client-revision theme mining. Never auto-promoted; Admin
    # review moves a row into RuleRow via the /candidate-rules/{id}/approve endpoint.
    rule_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    definition_json: Mapped[dict] = mapped_column(JSON)
    source: Mapped[str] = mapped_column(String(50), default="client_revision")
    theme_id: Mapped[str] = mapped_column(String(200))
    occurrence_count: Mapped[int] = mapped_column(default=0)
    date_range_start: Mapped[str | None] = mapped_column(String(20), nullable=True)
    date_range_end: Mapped[str | None] = mapped_column(String(20), nullable=True)
    redundancy_verdict: Mapped[str] = mapped_column(String(20), default="new")
    redundancy_notes: Mapped[str] = mapped_column(Text, default="")
    review_status: Mapped[str] = mapped_column(String(20), default="pending")
    reviewed_by: Mapped[str | None] = mapped_column(String(200), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
```

No test for this step alone — it's exercised by Task 5's repository tests (a bare table
definition with no behavior isn't independently testable).

- [ ] **Step 2: Verify existing tests still pass (no regression)**

Run: `backend\.venv\Scripts\python.exe -m pytest backend/tests -q`
Expected: same pass count as before this change (adding a table doesn't affect existing tests
since nothing references it yet).

- [ ] **Step 3: Commit**

```bash
git add backend/app/persistence/tables.py
git commit -m "feat: add candidate_rules table for mined revision-theme drafts"
```

---

### Task 5: `CandidateRulesRepository`

**Files:**
- Create: `backend/app/persistence/candidate_rules_repo.py`
- Modify: `backend/app/persistence/__init__.py`
- Test: `backend/tests/test_candidate_rules_repo.py`

- [ ] **Step 1: Write the failing tests**

`backend/tests/test_candidate_rules_repo.py`:
```python
"""CandidateRulesRepository: bulk insert, list/filter, get, review status transitions."""

from app.persistence import CandidateRulesRepository, init_db

VALID_DEFINITION = {
    "rule_id": "CR-0001",
    "category": "Site",
    "description": "Narrative does not analyze impact of adjacent external land use noted in map/aerial imagery.",
    "severity": "Advisory",
    "enabled": False,
    "logic": {"type": "ai", "prompt": "Does the narrative analyze the impact of the noted external factor on marketability/value?",
              "fields": ["subject:VALUATION_ANALYSIS/NEIGHBORHOOD/CommentText"]},
    "citation": "True Footage client revision pattern, 12 occurrences, date range not available in source export",
    "messages": {"appraiser": "Coaching text.", "reviewer": "Audit text."},
}


def _repo(tmp_path):
    sessions = init_db(f"sqlite:///{tmp_path}/test.db")
    return CandidateRulesRepository(sessions)


def test_bulk_insert_and_list(tmp_path):
    repo = _repo(tmp_path)
    inserted = repo.bulk_insert([{
        "definition": VALID_DEFINITION,
        "theme_id": "site-external-factor-not-analyzed",
        "occurrence_count": 12,
        "date_range_start": None,
        "date_range_end": None,
        "redundancy_verdict": "new",
        "redundancy_notes": "No matching field/logic found in the existing rule set.",
    }])
    assert inserted == 1
    items = repo.list_candidates("all")
    assert len(items) == 1
    assert items[0]["rule_id"] == "CR-0001"
    assert items[0]["occurrence_count"] == 12
    assert items[0]["review_status"] == "pending"


def test_bulk_insert_skips_existing_rule_id(tmp_path):
    repo = _repo(tmp_path)
    row = {
        "definition": VALID_DEFINITION, "theme_id": "t1", "occurrence_count": 5,
        "date_range_start": None, "date_range_end": None,
        "redundancy_verdict": "new", "redundancy_notes": "",
    }
    assert repo.bulk_insert([row]) == 1
    assert repo.bulk_insert([row]) == 0  # already exists, not re-inserted


def test_list_candidates_filters_by_status(tmp_path):
    repo = _repo(tmp_path)
    repo.bulk_insert([{
        "definition": VALID_DEFINITION, "theme_id": "t1", "occurrence_count": 5,
        "date_range_start": None, "date_range_end": None,
        "redundancy_verdict": "new", "redundancy_notes": "",
    }])
    assert len(repo.list_candidates("pending")) == 1
    assert len(repo.list_candidates("approved")) == 0


def test_mark_reviewed_updates_status_and_reviewer(tmp_path):
    repo = _repo(tmp_path)
    repo.bulk_insert([{
        "definition": VALID_DEFINITION, "theme_id": "t1", "occurrence_count": 5,
        "date_range_start": None, "date_range_end": None,
        "redundancy_verdict": "new", "redundancy_notes": "",
    }])
    updated = repo.mark_reviewed("CR-0001", "approved", "kevin.zelenakas")
    assert updated["review_status"] == "approved"
    assert updated["reviewed_by"] == "kevin.zelenakas"
    assert updated["reviewed_at"] is not None


def test_mark_reviewed_returns_none_for_unknown_id(tmp_path):
    repo = _repo(tmp_path)
    assert repo.mark_reviewed("CR-9999", "approved", "kevin.zelenakas") is None


def test_get_candidate_returns_none_for_unknown_id(tmp_path):
    repo = _repo(tmp_path)
    assert repo.get_candidate("CR-9999") is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `backend\.venv\Scripts\python.exe -m pytest backend/tests/test_candidate_rules_repo.py -v`
Expected: FAIL with `ImportError: cannot import name 'CandidateRulesRepository'`

- [ ] **Step 3: Write the implementation**

`backend/app/persistence/candidate_rules_repo.py`:
```python
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from app.models import RuleDefinition

from .tables import CandidateRuleRow


class CandidateRulesRepository:
    """DB-backed store for mined client-revision candidate rules. Distinct from
    RulesRepository (the live ruleset) — nothing here is active until an Admin
    reviewer approves it, which copies the definition into RulesRepository."""

    def __init__(self, session_factory: sessionmaker):
        self._sessions = session_factory

    def bulk_insert(self, candidates: list[dict]) -> int:
        count = 0
        with self._sessions() as session:
            for c in candidates:
                definition = c["definition"]
                rule = RuleDefinition.model_validate(definition)  # validates shape
                if session.get(CandidateRuleRow, rule.rule_id) is not None:
                    continue
                session.add(CandidateRuleRow(
                    rule_id=rule.rule_id,
                    definition_json=definition,
                    source=c.get("source", "client_revision"),
                    theme_id=c["theme_id"],
                    occurrence_count=c.get("occurrence_count", 0),
                    date_range_start=c.get("date_range_start"),
                    date_range_end=c.get("date_range_end"),
                    redundancy_verdict=c.get("redundancy_verdict", "new"),
                    redundancy_notes=c.get("redundancy_notes", ""),
                ))
                count += 1
            session.commit()
        return count

    def list_candidates(self, status: str = "all") -> list[dict]:
        with self._sessions() as session:
            rows = session.scalars(
                select(CandidateRuleRow).order_by(CandidateRuleRow.occurrence_count.desc())
            ).all()
        items = [self._row_dict(r) for r in rows]
        if status != "all":
            items = [i for i in items if i["review_status"] == status]
        return items

    def get_candidate(self, rule_id: str) -> dict | None:
        with self._sessions() as session:
            row = session.get(CandidateRuleRow, rule_id)
            return self._row_dict(row) if row else None

    def mark_reviewed(self, rule_id: str, status: str, reviewer: str) -> dict | None:
        with self._sessions() as session:
            row = session.get(CandidateRuleRow, rule_id)
            if row is None:
                return None
            row.review_status = status
            row.reviewed_by = reviewer
            row.reviewed_at = datetime.now(timezone.utc)
            session.commit()
            return self._row_dict(row)

    @staticmethod
    def _row_dict(row: CandidateRuleRow) -> dict:
        d = dict(row.definition_json)
        d.update({
            "theme_id": row.theme_id,
            "occurrence_count": row.occurrence_count,
            "date_range_start": row.date_range_start,
            "date_range_end": row.date_range_end,
            "redundancy_verdict": row.redundancy_verdict,
            "redundancy_notes": row.redundancy_notes,
            "review_status": row.review_status,
            "reviewed_by": row.reviewed_by,
            "reviewed_at": row.reviewed_at.isoformat() if row.reviewed_at else None,
            "source": row.source,
        })
        return d
```

- [ ] **Step 4: Wire the export**

`backend/app/persistence/__init__.py` — replace the full contents with:
```python
from .candidate_rules_repo import CandidateRulesRepository
from .db import init_db
from .repository import RunRepository
from .rules_repo import RulesRepository

__all__ = ["CandidateRulesRepository", "RulesRepository", "RunRepository", "init_db"]
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `backend\.venv\Scripts\python.exe -m pytest backend/tests/test_candidate_rules_repo.py -v`
Expected: PASS (6 tests)

- [ ] **Step 6: Run full suite to check for regressions**

Run: `backend\.venv\Scripts\python.exe -m pytest backend/tests -q`
Expected: all previously-passing tests still pass, plus the 6 new ones.

- [ ] **Step 7: Commit**

```bash
git add backend/app/persistence/candidate_rules_repo.py backend/app/persistence/__init__.py backend/tests/test_candidate_rules_repo.py
git commit -m "feat: CandidateRulesRepository for mined revision-theme drafts"
```

---

### Task 6: Redundancy check

**Files:**
- Create: `backend/app/revision_mining/redundancy_check.py`
- Test: `backend/tests/test_redundancy_check.py`

- [ ] **Step 1: Write the failing tests**

`backend/tests/test_redundancy_check.py`:
```python
"""Redundancy check: candidate rule vs. the live rule set, deterministic (no LLM)."""

from app.revision_mining.redundancy_check import check_redundancy

EXISTING_RULES = [
    {
        "rule_id": "UAD1001",
        "description": "Subject property physical address line must be provided.",
        "logic": {"type": "field_present", "field": "subject:VALUATION_ANALYSIS/PROPERTIES/PROPERTY/ADDRESS/AddressLineText"},
    },
    {
        "rule_id": "UAD1099",
        "description": "Comparable sale adjustments must be supported by market data.",
        "logic": {"type": "needs_encoding", "source_logic": "..."},
    },
]


def test_exact_duplicate_same_field_and_logic_type():
    candidate = {
        "description": "Subject address line is required.",
        "logic": {"type": "field_present", "field": "subject:VALUATION_ANALYSIS/PROPERTIES/PROPERTY/ADDRESS/AddressLineText"},
    }
    result = check_redundancy(candidate, EXISTING_RULES)
    assert result["verdict"] == "exact_duplicate"
    assert "UAD1001" in result["notes"]


def test_overlaps_similar_description_no_field_match():
    candidate = {
        "description": "Comparable sale adjustments must be supported by market data and cited.",
        "logic": {"type": "ai", "prompt": "Are adjustments supported?", "fields": []},
    }
    result = check_redundancy(candidate, EXISTING_RULES)
    assert result["verdict"] == "overlaps"
    assert "UAD1099" in result["notes"]


def test_new_no_overlap():
    candidate = {
        "description": "Narrative does not analyze impact of adjacency to a house of worship noted in aerial imagery.",
        "logic": {"type": "ai", "prompt": "Does the narrative analyze this external factor?", "fields": ["subject:VALUATION_ANALYSIS/NEIGHBORHOOD/CommentText"]},
    }
    result = check_redundancy(candidate, EXISTING_RULES)
    assert result["verdict"] == "new"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `backend\.venv\Scripts\python.exe -m pytest backend/tests/test_redundancy_check.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.revision_mining.redundancy_check'`

- [ ] **Step 3: Write the implementation**

`backend/app/revision_mining/redundancy_check.py`:
```python
from __future__ import annotations

import difflib

OVERLAP_THRESHOLD = 0.6


def _fields_used(logic: dict) -> set[str]:
    fields: set[str] = set()
    if "field" in logic:
        fields.add(logic["field"])
    for f in logic.get("fields") or []:
        fields.add(f)
    if logic.get("type") == "conditional":
        for group in logic.get("if_any", []):
            for cond in group:
                if "field" in cond:
                    fields.add(cond["field"])
        then = logic.get("then") or {}
        if "field" in then:
            fields.add(then["field"])
    return fields


def check_redundancy(candidate: dict, existing_rules: list[dict]) -> dict:
    """Compare a draft candidate rule against the full live rule set.
    Returns {"verdict": "exact_duplicate" | "overlaps" | "new", "notes": str}."""
    cand_fields = _fields_used(candidate.get("logic") or {})
    cand_type = (candidate.get("logic") or {}).get("type")
    cand_desc = (candidate.get("description") or "").lower()

    for rule in existing_rules:
        rule_fields = _fields_used(rule.get("logic") or {})
        rule_type = (rule.get("logic") or {}).get("type")
        if cand_fields and cand_fields == rule_fields and cand_type == rule_type:
            return {
                "verdict": "exact_duplicate",
                "notes": f"Matches existing rule {rule['rule_id']} (same field(s) and logic type).",
            }

    best_ratio = 0.0
    best_rule_id = None
    for rule in existing_rules:
        rule_desc = (rule.get("description") or "").lower()
        if not rule_desc or not cand_desc:
            continue
        ratio = difflib.SequenceMatcher(None, cand_desc, rule_desc).ratio()
        if ratio > best_ratio:
            best_ratio = ratio
            best_rule_id = rule["rule_id"]

    if best_ratio >= OVERLAP_THRESHOLD:
        return {
            "verdict": "overlaps",
            "notes": f"Overlaps existing rule {best_rule_id} (description similarity {best_ratio:.0%}).",
        }

    return {"verdict": "new", "notes": "No matching field/logic or similar description found in the existing rule set."}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `backend\.venv\Scripts\python.exe -m pytest backend/tests/test_redundancy_check.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add backend/app/revision_mining/redundancy_check.py backend/tests/test_redundancy_check.py
git commit -m "feat: deterministic redundancy check for candidate rules vs live ruleset"
```

---

### Task 7: Wire `candidate_rules_repo` into the app

**Files:**
- Modify: `backend/app/main.py:14-21`

- [ ] **Step 1: Add the import and wiring**

In `backend/app/main.py`, change:
```python
from app.persistence import RulesRepository, RunRepository, init_db
```
to:
```python
from app.persistence import CandidateRulesRepository, RulesRepository, RunRepository, init_db
```

And after line 19 (`app.state.rules_repo = RulesRepository(sessions)`), add:
```python
    app.state.candidate_rules_repo = CandidateRulesRepository(sessions)
```

So the block reads:
```python
    sessions = init_db(config.DB_URL)
    app.state.repo = RunRepository(sessions)
    app.state.rules_repo = RulesRepository(sessions)
    app.state.candidate_rules_repo = CandidateRulesRepository(sessions)
    # First boot: seed the rules DB from the external ruleset file (H-1 import).
    app.state.rules_repo.seed_from_file(config.RULES_PATH)
```

- [ ] **Step 2: Run full backend suite to confirm the app still boots correctly in tests**

Run: `backend\.venv\Scripts\python.exe -m pytest backend/tests -q`
Expected: no regressions (same pass count as Task 5's Step 6, since nothing exercises
`candidate_rules_repo` via HTTP yet).

- [ ] **Step 3: Commit**

```bash
git add backend/app/main.py
git commit -m "feat: wire CandidateRulesRepository into app state"
```

---

### Task 8: Admin API endpoints for candidate rules

**Files:**
- Modify: `backend/app/api/admin.py`
- Test: `backend/tests/test_admin_candidate_rules.py`

- [ ] **Step 1: Write the failing tests**

`backend/tests/test_admin_candidate_rules.py`:
```python
"""Admin candidate-rule endpoints: list/get/approve/reject."""

import pytest
from fastapi.testclient import TestClient

ADMIN = {"X-QC-Role": "admin"}

CANDIDATE_DEFINITION = {
    "rule_id": "CR-0001",
    "category": "Site",
    "description": "Narrative does not analyze impact of adjacent external land use.",
    "severity": "Advisory",
    "enabled": False,
    "logic": {"type": "ai", "prompt": "Does the narrative analyze this external factor?",
              "fields": ["subject:VALUATION_ANALYSIS/NEIGHBORHOOD/CommentText"]},
    "citation": "True Footage client revision pattern, 12 occurrences, date range not available in source export",
    "messages": {"appraiser": "Coaching text.", "reviewer": "Audit text."},
}


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("QC_DATA_DIR", str(tmp_path))
    import importlib

    import app.config
    importlib.reload(app.config)
    from app.main import create_app
    return TestClient(create_app())


@pytest.fixture
def seeded_candidate(client):
    client.app.state.candidate_rules_repo.bulk_insert([{
        "definition": CANDIDATE_DEFINITION,
        "theme_id": "site-external-factor-not-analyzed",
        "occurrence_count": 12,
        "date_range_start": None,
        "date_range_end": None,
        "redundancy_verdict": "new",
        "redundancy_notes": "No matching field/logic found in the existing rule set.",
    }])
    return client


def test_list_candidate_rules_requires_admin(client):
    assert client.get("/api/admin/candidate-rules").status_code == 403


def test_list_and_get_candidate_rule(seeded_candidate):
    items = seeded_candidate.get("/api/admin/candidate-rules", headers=ADMIN).json()
    assert len(items) == 1
    assert items[0]["rule_id"] == "CR-0001"

    one = seeded_candidate.get("/api/admin/candidate-rules/CR-0001", headers=ADMIN).json()
    assert one["occurrence_count"] == 12

    missing = seeded_candidate.get("/api/admin/candidate-rules/CR-9999", headers=ADMIN)
    assert missing.status_code == 404


def test_approve_promotes_into_live_rules(seeded_candidate):
    result = seeded_candidate.post(
        "/api/admin/candidate-rules/CR-0001/approve",
        json={"reviewer": "kevin.zelenakas"}, headers=ADMIN,
    )
    assert result.status_code == 200
    assert result.json()["review_status"] == "approved"

    promoted = seeded_candidate.get("/api/admin/rules/CR-0001", headers=ADMIN)
    assert promoted.status_code == 200
    assert promoted.json()["enabled"] is False  # still disabled after promotion


def test_approve_blocks_exact_duplicate(client):
    client.app.state.candidate_rules_repo.bulk_insert([{
        "definition": CANDIDATE_DEFINITION,
        "theme_id": "dup-theme", "occurrence_count": 3,
        "date_range_start": None, "date_range_end": None,
        "redundancy_verdict": "exact_duplicate",
        "redundancy_notes": "Matches existing rule UAD1234.",
    }])
    result = client.post(
        "/api/admin/candidate-rules/CR-0001/approve",
        json={"reviewer": "kevin.zelenakas"}, headers=ADMIN,
    )
    assert result.status_code == 409


def test_reject_marks_status(seeded_candidate):
    result = seeded_candidate.post(
        "/api/admin/candidate-rules/CR-0001/reject",
        json={"reviewer": "kevin.zelenakas"}, headers=ADMIN,
    )
    assert result.status_code == 200
    assert result.json()["review_status"] == "rejected"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `backend\.venv\Scripts\python.exe -m pytest backend/tests/test_admin_candidate_rules.py -v`
Expected: FAIL with 404s (routes don't exist yet)

- [ ] **Step 3: Add the endpoints**

Append to `backend/app/api/admin.py` (after the last function, `upsert_profile`):
```python


class CandidateReviewBody(BaseModel):
    reviewer: str


@router.get("/candidate-rules")
def list_candidate_rules(request: Request, status: str = "all", x_qc_role: str | None = Header(default=None)) -> list[dict]:
    _require_admin(x_qc_role)
    return request.app.state.candidate_rules_repo.list_candidates(status)


@router.get("/candidate-rules/{rule_id}")
def get_candidate_rule(rule_id: str, request: Request, x_qc_role: str | None = Header(default=None)) -> dict:
    _require_admin(x_qc_role)
    candidate = request.app.state.candidate_rules_repo.get_candidate(rule_id)
    if candidate is None:
        raise HTTPException(status_code=404, detail="Candidate rule not found")
    return candidate


@router.post("/candidate-rules/{rule_id}/approve")
def approve_candidate_rule(rule_id: str, body: CandidateReviewBody, request: Request, x_qc_role: str | None = Header(default=None)) -> dict:
    _require_admin(x_qc_role)
    candidate = request.app.state.candidate_rules_repo.get_candidate(rule_id)
    if candidate is None:
        raise HTTPException(status_code=404, detail="Candidate rule not found")
    if candidate["redundancy_verdict"] == "exact_duplicate":
        raise HTTPException(status_code=409, detail="Cannot approve an exact-duplicate candidate rule")
    definition = {
        k: candidate[k] for k in ("rule_id", "category", "description", "severity", "enabled", "logic", "citation", "messages")
    }
    definition["enabled"] = False  # promoted rules still start disabled; admin turns them on separately
    request.app.state.rules_repo.upsert_rule(definition)
    return request.app.state.candidate_rules_repo.mark_reviewed(rule_id, "approved", body.reviewer)


@router.post("/candidate-rules/{rule_id}/reject")
def reject_candidate_rule(rule_id: str, body: CandidateReviewBody, request: Request, x_qc_role: str | None = Header(default=None)) -> dict:
    _require_admin(x_qc_role)
    updated = request.app.state.candidate_rules_repo.mark_reviewed(rule_id, "rejected", body.reviewer)
    if updated is None:
        raise HTTPException(status_code=404, detail="Candidate rule not found")
    return updated
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `backend\.venv\Scripts\python.exe -m pytest backend/tests/test_admin_candidate_rules.py -v`
Expected: PASS (6 tests)

- [ ] **Step 5: Run full suite to check for regressions**

Run: `backend\.venv\Scripts\python.exe -m pytest backend/tests -q`
Expected: all tests pass (previous count + 6 new).

- [ ] **Step 6: Commit**

```bash
git add backend/app/api/admin.py backend/tests/test_admin_candidate_rules.py
git commit -m "feat: admin endpoints for candidate-rule list/get/approve/reject"
```

---

### Task 9: Bulk-insert script with redundancy tagging

**Files:**
- Create: `backend/app/revision_mining/insert_candidates.py`
- Test: `backend/tests/test_insert_candidates.py`

- [ ] **Step 1: Write the failing test**

`backend/tests/test_insert_candidates.py`:
```python
"""insert_candidates: reads mined-theme JSON, tags redundancy against live rules, bulk-inserts."""

import json

import pytest

from app.persistence import RulesRepository, init_db
from app.revision_mining.insert_candidates import insert_candidates

EXISTING_RULE = {
    "rule_id": "UAD1001",
    "category": "Subject Property",
    "description": "Subject property physical address line must be provided.",
    "severity": "HardStop",
    "enabled": True,
    "logic": {"type": "field_present", "field": "subject:VALUATION_ANALYSIS/PROPERTIES/PROPERTY/ADDRESS/AddressLineText"},
    "citation": "UAD 3.6 Appendix H-1 v1.4, Unique ID 0100.0007, Message ID UAD1001",
    "messages": {"reviewer": "Provide the address line for the subject property physical address."},
}


@pytest.fixture
def db_url(tmp_path):
    return f"sqlite:///{tmp_path}/test.db"


def _write_candidates_file(tmp_path, candidates):
    path = tmp_path / "candidates.json"
    path.write_text(json.dumps(candidates), encoding="utf-8")
    return path


def test_insert_candidates_tags_exact_duplicate_and_new(tmp_path, db_url, monkeypatch):
    monkeypatch.setenv("QC_DB_URL", db_url)
    sessions = init_db(db_url)
    RulesRepository(sessions).upsert_rule(EXISTING_RULE)

    candidates = [
        {
            "theme_id": "dup-address-theme",
            "occurrence_count": 4,
            "definition": {
                "rule_id": "CR-0001", "category": "Subject Property",
                "description": "Subject address line is required.",
                "severity": "Advisory", "enabled": False,
                "logic": {"type": "field_present", "field": "subject:VALUATION_ANALYSIS/PROPERTIES/PROPERTY/ADDRESS/AddressLineText"},
                "citation": "True Footage client revision pattern, 4 occurrences, date range not available in source export",
                "messages": {"appraiser": "x", "reviewer": "x"},
            },
        },
        {
            "theme_id": "new-theme",
            "occurrence_count": 9,
            "definition": {
                "rule_id": "CR-0002", "category": "Site",
                "description": "Narrative does not analyze impact of adjacency to a house of worship.",
                "severity": "Advisory", "enabled": False,
                "logic": {"type": "ai", "prompt": "Does the narrative analyze this factor?",
                          "fields": ["subject:VALUATION_ANALYSIS/NEIGHBORHOOD/CommentText"]},
                "citation": "True Footage client revision pattern, 9 occurrences, date range not available in source export",
                "messages": {"appraiser": "x", "reviewer": "x"},
            },
        },
    ]
    candidates_path = _write_candidates_file(tmp_path, candidates)

    result = insert_candidates(candidates_path, db_url=db_url)

    assert result["inserted"] == 2
    assert result["exact_duplicate"] == 1
    assert result["new"] == 1


def test_insert_candidates_flags_and_excludes_suspected_pii(tmp_path, db_url):
    sessions = init_db(db_url)
    candidates = [{
        "theme_id": "pii-leak-theme",
        "occurrence_count": 3,
        "definition": {
            "rule_id": "CR-0003", "category": "Subject Property",
            # Simulates a mining-step mistake: a name leaked into the description.
            "description": "Add Timothy James Henson as owner of public record per revision request.",
            "severity": "Advisory", "enabled": False,
            "logic": {"type": "field_present", "field": "subject:VALUATION_ANALYSIS/PROPERTIES/PROPERTY/OWNER/OwnerName"},
            "citation": "True Footage client revision pattern, 3 occurrences, date range not available in source export",
            "messages": {"appraiser": "x", "reviewer": "x"},
        },
    }]
    candidates_path = _write_candidates_file(tmp_path, candidates)

    result = insert_candidates(candidates_path, db_url=db_url)

    assert result["inserted"] == 0
    assert result["pii_flagged"] == 1
    from app.persistence import CandidateRulesRepository
    assert CandidateRulesRepository(sessions).list_candidates("all") == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `backend\.venv\Scripts\python.exe -m pytest backend/tests/test_insert_candidates.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.revision_mining.insert_candidates'`

- [ ] **Step 3: Write the implementation**

`backend/app/revision_mining/insert_candidates.py`:
```python
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from app.persistence import CandidateRulesRepository, RulesRepository, init_db

from .redundancy_check import check_redundancy

# Defense-in-depth only: the mining step (Task 12) is instructed to output
# abstracted, PII-free theme text. This heuristic catches the mistake if it
# happens anyway, before anything lands in the candidate_rules table.
_NAME_LIKE_RE = re.compile(r'\b[A-Z][a-z]+(?:\s+[A-Z][a-z]*\.?){1,2}\s+[A-Z][a-z]+\b')
_SSN_RE = re.compile(r'\b\d{3}-\d{2}-\d{4}\b')
_PHONE_RE = re.compile(r'\b\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4}\b')
_ORDER_NUMBER_RE = re.compile(r'#\s?\d{4,}|order\s*#?\s*\d{4,}', re.IGNORECASE)


def _pii_risk_flags(definition: dict) -> list[str]:
    """Scan description/citation/messages text for name-like patterns, SSNs,
    phone numbers, or order numbers. Returns a list of human-readable reasons
    (empty list = no risk detected)."""
    text_fields = [
        definition.get("description", ""),
        definition.get("citation") or "",
        (definition.get("messages") or {}).get("appraiser") or "",
        (definition.get("messages") or {}).get("reviewer") or "",
    ]
    blob = " ".join(text_fields)
    reasons = []
    if _NAME_LIKE_RE.search(blob):
        reasons.append("possible personal name")
    if _SSN_RE.search(blob):
        reasons.append("possible SSN")
    if _PHONE_RE.search(blob):
        reasons.append("possible phone number")
    if _ORDER_NUMBER_RE.search(blob):
        reasons.append("possible order number")
    return reasons


def insert_candidates(input_path: Path, db_url: str) -> dict:
    """Read mined-theme candidate JSON, scan for suspected PII, tag each
    against the live rule set for redundancy, and bulk-insert into
    candidate_rules. Returns a summary dict."""
    candidates = json.loads(Path(input_path).read_text(encoding="utf-8"))
    sessions = init_db(db_url)
    rules_repo = RulesRepository(sessions)
    candidate_repo = CandidateRulesRepository(sessions)
    existing_rules = rules_repo.list_rules("all")

    to_insert = []
    tally = {"exact_duplicate": 0, "overlaps": 0, "new": 0, "pii_flagged": 0}
    pii_flagged_themes = []
    for item in candidates:
        pii_reasons = _pii_risk_flags(item["definition"])
        if pii_reasons:
            tally["pii_flagged"] += 1
            pii_flagged_themes.append({"theme_id": item["theme_id"], "reasons": pii_reasons})
            continue
        verdict = check_redundancy(item["definition"], existing_rules)
        tally[verdict["verdict"]] += 1
        to_insert.append({
            "definition": item["definition"],
            "theme_id": item["theme_id"],
            "occurrence_count": item.get("occurrence_count", 0),
            "date_range_start": item.get("date_range_start"),
            "date_range_end": item.get("date_range_end"),
            "redundancy_verdict": verdict["verdict"],
            "redundancy_notes": verdict["notes"],
        })

    inserted = candidate_repo.bulk_insert(to_insert)
    return {
        "inserted": inserted,
        "skipped_existing_id": len(to_insert) - inserted,
        "pii_flagged_themes": pii_flagged_themes,
        **tally,
    }


def main() -> None:
    from app import config

    parser = argparse.ArgumentParser(description="Insert mined candidate rules with redundancy tagging")
    parser.add_argument("--input", required=True, help="Path to draft candidate rules JSON")
    args = parser.parse_args()
    result = insert_candidates(Path(args.input), db_url=config.DB_URL)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `backend\.venv\Scripts\python.exe -m pytest backend/tests/test_insert_candidates.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Run full suite to check for regressions**

Run: `backend\.venv\Scripts\python.exe -m pytest backend/tests -q`
Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
git add backend/app/revision_mining/insert_candidates.py backend/tests/test_insert_candidates.py
git commit -m "feat: insert_candidates script — redundancy-tag and bulk-insert mined rules"
```

---

### Task 10: Frontend API client for candidate rules

**Files:**
- Modify: `frontend/src/adminApi.ts`

- [ ] **Step 1: Add types and functions**

Append to `frontend/src/adminApi.ts`:
```typescript

export interface CandidateRule extends AdminRule {
  theme_id: string;
  occurrence_count: number;
  date_range_start: string | null;
  date_range_end: string | null;
  redundancy_verdict: "exact_duplicate" | "overlaps" | "new";
  redundancy_notes: string;
  review_status: "pending" | "approved" | "rejected";
  reviewed_by: string | null;
  reviewed_at: string | null;
  source: string;
}

export async function listCandidateRules(status: string): Promise<CandidateRule[]> {
  return handle(await fetch(`/api/admin/candidate-rules?status=${status}`, { headers: ADMIN }));
}

export async function approveCandidateRule(ruleId: string, reviewer: string): Promise<CandidateRule> {
  return handle(await fetch(`/api/admin/candidate-rules/${encodeURIComponent(ruleId)}/approve`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...ADMIN },
    body: JSON.stringify({ reviewer }),
  }));
}

export async function rejectCandidateRule(ruleId: string, reviewer: string): Promise<CandidateRule> {
  return handle(await fetch(`/api/admin/candidate-rules/${encodeURIComponent(ruleId)}/reject`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...ADMIN },
    body: JSON.stringify({ reviewer }),
  }));
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/adminApi.ts
git commit -m "feat: frontend API client for candidate-rule review"
```

---

### Task 11: Admin UI — "Client Revisions" tab

**Files:**
- Modify: `frontend/src/AdminPanel.tsx`

- [ ] **Step 1: Extend the Tab type and imports**

Change line 1-8 of `frontend/src/AdminPanel.tsx` from:
```typescript
import { useEffect, useMemo, useState } from "react";
import {
  archiveRule, exportRuleset, importRuleset, listAdminRules, listProfiles,
  saveProfile, saveRule, toggleRule,
} from "./adminApi";
import type { AdminRule, Profile } from "./adminApi";

type Tab = "all" | "enabled" | "needs_encoding" | "profiles";
```
to:
```typescript
import { useEffect, useMemo, useState } from "react";
import {
  approveCandidateRule, archiveRule, exportRuleset, importRuleset, listAdminRules,
  listCandidateRules, listProfiles, rejectCandidateRule, saveProfile, saveRule, toggleRule,
} from "./adminApi";
import type { AdminRule, CandidateRule, Profile } from "./adminApi";

type Tab = "all" | "enabled" | "needs_encoding" | "profiles" | "client_revisions";
```

- [ ] **Step 2: Add the tab button**

In the tab-button `.map()` (around line 117-125), change:
```typescript
          {(["all", "enabled", "needs_encoding", "profiles"] as Tab[]).map((t) => (
            <button
              key={t}
              onClick={() => setTab(t)}
              className={`rounded px-3 py-1.5 text-sm font-medium ${tab === t ? "bg-gray-900 text-white" : "bg-gray-100 text-gray-700 hover:bg-gray-200"}`}
            >
              {t === "all" ? "All rules" : t === "enabled" ? "Enabled" : t === "needs_encoding" ? "Needs encoding" : "Client profiles"}
            </button>
          ))}
```
to:
```typescript
          {(["all", "enabled", "needs_encoding", "profiles", "client_revisions"] as Tab[]).map((t) => (
            <button
              key={t}
              onClick={() => setTab(t)}
              className={`rounded px-3 py-1.5 text-sm font-medium ${tab === t ? "bg-gray-900 text-white" : "bg-gray-100 text-gray-700 hover:bg-gray-200"}`}
            >
              {t === "all" ? "All rules" : t === "enabled" ? "Enabled" : t === "needs_encoding" ? "Needs encoding" : t === "profiles" ? "Client profiles" : "Client revisions"}
            </button>
          ))}
```

- [ ] **Step 3: Route the new tab to its own panel and skip the rules-list refresh for it**

Change the `refresh()` function (around line 23-34) from:
```typescript
  async function refresh() {
    setError(null);
    try {
      if (tab === "profiles") {
        setProfiles(await listProfiles());
      } else {
        setRules(await listAdminRules(tab));
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }
```
to:
```typescript
  async function refresh() {
    setError(null);
    try {
      if (tab === "profiles" || tab === "client_revisions") {
        setProfiles(tab === "profiles" ? await listProfiles() : profiles);
      } else {
        setRules(await listAdminRules(tab));
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }
```

Change the render branch (around line 149-151) from:
```typescript
      {tab === "profiles" ? (
        <ProfilesPanel profiles={profiles} onSaved={refresh} />
      ) : (
```
to:
```typescript
      {tab === "profiles" ? (
        <ProfilesPanel profiles={profiles} onSaved={refresh} />
      ) : tab === "client_revisions" ? (
        <CandidateRulesPanel />
      ) : (
```

- [ ] **Step 4: Add the `CandidateRulesPanel` component**

Append to the end of `frontend/src/AdminPanel.tsx` (after the closing `}` of `ProfilesPanel`):
```typescript

function CandidateRulesPanel() {
  const [status, setStatus] = useState<"pending" | "approved" | "rejected" | "all">("pending");
  const [candidates, setCandidates] = useState<CandidateRule[]>([]);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function refresh() {
    setError(null);
    try {
      setCandidates(await listCandidateRules(status));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  useEffect(() => {
    refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [status]);

  async function onApprove(rule: CandidateRule) {
    const reviewer = window.prompt("Your name (for the review record):");
    if (!reviewer) return;
    try {
      await approveCandidateRule(rule.rule_id, reviewer);
      setMessage(`${rule.rule_id} approved and promoted to the live rule set (still OFF — enable it separately).`);
      await refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  async function onReject(rule: CandidateRule) {
    const reviewer = window.prompt("Your name (for the review record):");
    if (!reviewer) return;
    try {
      await rejectCandidateRule(rule.rule_id, reviewer);
      setMessage(`${rule.rule_id} rejected.`);
      await refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  const verdictLabel: Record<CandidateRule["redundancy_verdict"], string> = {
    exact_duplicate: "Exact duplicate",
    overlaps: "Overlaps existing rule",
    new: "New",
  };
  const verdictClass: Record<CandidateRule["redundancy_verdict"], string> = {
    exact_duplicate: "bg-red-100 text-red-800",
    overlaps: "bg-amber-100 text-amber-800",
    new: "bg-green-100 text-green-800",
  };

  return (
    <section className="space-y-4">
      <div className="rounded-lg border border-gray-200 bg-white p-4">
        <h3 className="text-sm font-semibold text-gray-900">Client revision candidate rules</h3>
        <p className="mt-1 text-xs text-gray-500">
          Mined from client revision-request patterns (3+ occurrences). Approving copies a rule
          into the live rule set — it still starts OFF; enable it separately once you're ready.
        </p>
        <div className="mt-3 flex flex-wrap gap-2">
          {(["pending", "approved", "rejected", "all"] as const).map((s) => (
            <button
              key={s}
              onClick={() => setStatus(s)}
              className={`rounded px-3 py-1.5 text-sm font-medium ${status === s ? "bg-gray-900 text-white" : "bg-gray-100 text-gray-700 hover:bg-gray-200"}`}
            >
              {s[0].toUpperCase() + s.slice(1)}
            </button>
          ))}
        </div>
        {message && <p className="mt-2 text-xs text-green-700">{message}</p>}
        {error && <p className="mt-2 text-xs text-red-700">{error}</p>}
      </div>
      <div className="overflow-hidden rounded-lg border border-gray-200 bg-white">
        <ul className="divide-y divide-gray-100">
          {candidates.map((c) => (
            <li key={c.rule_id} className="px-4 py-3 text-xs">
              <div className="flex items-center gap-3">
                <span className="w-24 shrink-0 font-mono font-medium text-gray-900">{c.rule_id}</span>
                <span className="w-16 shrink-0 text-gray-500">{c.occurrence_count}×</span>
                <span className={`shrink-0 rounded px-1.5 py-0.5 ${verdictClass[c.redundancy_verdict]}`}>
                  {verdictLabel[c.redundancy_verdict]}
                </span>
                <span className="min-w-0 flex-1 truncate text-gray-700">{c.description}</span>
                {status === "pending" && (
                  <>
                    <button
                      onClick={() => onApprove(c)}
                      disabled={c.redundancy_verdict === "exact_duplicate"}
                      className="shrink-0 rounded border border-gray-300 px-2 py-0.5 text-gray-700 hover:bg-gray-50 disabled:opacity-40"
                      title={c.redundancy_verdict === "exact_duplicate" ? "Blocked: exact duplicate of an existing rule" : "Approve and promote"}
                    >
                      Approve
                    </button>
                    <button onClick={() => onReject(c)} className="shrink-0 rounded border border-red-200 px-2 py-0.5 text-red-700 hover:bg-red-50">
                      Reject
                    </button>
                  </>
                )}
              </div>
              <div className="mt-1 pl-24 text-gray-500">{c.redundancy_notes}</div>
            </li>
          ))}
          {candidates.length === 0 && <li className="px-4 py-3 text-xs text-gray-500">No candidate rules in this status.</li>}
        </ul>
      </div>
    </section>
  );
}
```

- [ ] **Step 5: Manually verify in the dev server**

Run: `.\dev.ps1` (from repo root), open http://localhost:8000, switch role to Admin, click the
new **Client revisions** tab.
Expected: tab renders with the four status filter buttons and an empty-state message (no
candidates exist yet — that's Task 12).

- [ ] **Step 6: Commit**

```bash
git add frontend/src/AdminPanel.tsx
git commit -m "feat: Admin UI tab for reviewing client-revision candidate rules"
```

---

### Task 12: Run the pipeline against the real RRR export

This task is operational, not code — it executes Stages 2–5 of the design spec using the
tooling built in Tasks 1–11. Each step below is concrete and must be followed in order.

- [ ] **Step 1: Run preprocessing**

In a Python shell (`backend\.venv\Scripts\python.exe`) or a throwaway script, call:
```python
from pathlib import Path
from app.revision_mining.preprocess import extract_atomic_items

items = extract_atomic_items(Path(r"C:\Users\kzele\True Footage Dropbox\kevin.zelenakas\RRR Export for QC tool.xlsx"))
print(len(items))
```
Expected: a count in the low thousands (source was ~4,694 raw rows; splitting bundled cells
will increase the atomic-item count, junk filtering will decrease it). Save `items` to a local
scratch JSON file for the next step — this file contains real revision text (PII-bearing) and
must stay local, never committed to git or pasted into a shared location.

- [ ] **Step 2: Batch and mine themes**

Split the atomic items into batches of 150–250. For each batch, dispatch a subagent via the
Agent tool with a prompt of this shape (fill in the actual batch text):

> "Here are N appraisal revision-request action items. Cluster them into recurring themes. For
> each theme with 3+ occurrences in this batch, return: a short theme_id (kebab-case), a
> one-sentence abstracted pattern description with NO borrower names, addresses, or order
> numbers, the occurrence count in this batch, and the likely UAD report section. Do not quote
> the source text verbatim if it contains a name or address — describe the pattern generically
> instead."

Collect all batches' outputs, then run one more pass (yourself, not a subagent) to merge
near-duplicate theme_ids across batches into a single ranked master list, summing occurrence
counts. Keep only themes with a combined 3+ occurrences (per the approved design's frequency
threshold).

- [ ] **Step 3: Classify each theme**

For each theme in the master list, decide Deterministic / AI / Not-yet-buildable per the design
spec's Stage 3 rule. For Deterministic candidates, look up the exact field key in
`schemas/uad36_field_manifest.json` — if no matching field exists, downgrade to AI or
Not-yet-buildable rather than inventing a field key.

- [ ] **Step 4: Author the draft rules JSON**

Write a local JSON file (e.g. `backend/data/mined_candidates_2026-07.json` — add this filename
pattern to `.gitignore` if not already covered by an existing `data/` ignore rule, since it may
carry theme text derived from real revisions) matching the shape consumed by
`insert_candidates()` from Task 9:
```json
[
  {
    "theme_id": "<kebab-case-id>",
    "occurrence_count": <int>,
    "date_range_start": null,
    "date_range_end": null,
    "definition": {
      "rule_id": "CR-0001",
      "category": "<matches an existing rules/h1_rules.json category or UAD section>",
      "description": "<abstracted pattern, no PII>",
      "severity": "Advisory",
      "enabled": false,
      "logic": { "...": "field_present | regex_match | field_in_set | numeric_range | conditional | ai" },
      "citation": "True Footage client revision pattern, <N> occurrences, date range not available in source export",
      "messages": { "appraiser": "<coaching text>", "reviewer": "<audit text>" }
    }
  }
]
```
Number `rule_id`s sequentially starting at `CR-0001`.

- [ ] **Step 5: Verify `.gitignore` covers the scratch/output files**

Run: `git check-ignore -v backend/data/mined_candidates_2026-07.json`
Expected: shows a matching `.gitignore` rule (the existing `backend\data` rule from
`docs/ROADMAP.md` Stage A's "delete backend\data to reset" note should already cover this — if
it doesn't, add `backend/data/` to `.gitignore` before proceeding, since this file may contain
theme text derived from PII-bearing source rows).

- [ ] **Step 6: Insert the candidates**

Run:
```
backend\.venv\Scripts\python.exe -m app.revision_mining.insert_candidates --input backend\data\mined_candidates_2026-07.json
```
Expected: JSON summary printed with `inserted`, `exact_duplicate`, `overlaps`, `new` counts.

- [ ] **Step 7: Spot-check in Admin**

Start the app (`.\dev.ps1`), open the **Client revisions** tab, confirm the candidates appear
with correct occurrence counts and redundancy verdicts, spot-check 3-5 rule JSONs for accuracy
against what was mined, and confirm none show `enabled: true`.

- [ ] **Step 8: Report results back**

Summarize (in this session, not committed to any file): total themes found, how many became
candidates, the exact_duplicate/overlaps/new breakdown, and any themes flagged Not-yet-buildable
with reasons — this becomes the input for deciding what Subsystem 5 (the repeatable engine)
should prioritize next.
