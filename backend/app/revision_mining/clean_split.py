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
