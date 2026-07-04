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
