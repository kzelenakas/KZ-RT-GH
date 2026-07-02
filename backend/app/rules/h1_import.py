"""Import Appendix H-1 compliance rules (CSV) into the external rule format.

Conversion policy (Phase 2):
- Property Affected "Subject" or "N/A" -> executable scope ("subject" / "doc").
  Comparable/#n scopes need per-instance iteration (later phase) and are
  imported disabled with logic type "needs_encoding".
- Rule Logic exactly "If <element> is not provided"       -> field_present
- Date Format CCYY-MM-DD / CCYY-MM + "format" in logic    -> regex_match
- Min/Max value columns + greater/less/exceed in logic    -> numeric_range
- Everything else -> logic type "needs_encoding" (imported disabled; the
  original Rule Logic text is preserved so nothing is invented or dropped).

Severity mapping: Fatal -> HardStop, Warning -> Warning.
Message text: single H-1 variant -> reviewer message (engine falls back for
appraiser mode until coaching variants are authored).
"""

from __future__ import annotations

import csv
import hashlib
import json
import re
from pathlib import Path

DATE_PATTERNS = {
    "CCYY-MM-DD": r"\d{4}-\d{2}-\d{2}",
    "CCYY-MM": r"\d{4}-\d{2}",
}

# "...must be either 5 digits, or 5 digits, a hyphen, and 4 digits (ZIP+4)"
ZIP_PATTERN = r"\d{5}(-\d{4})?"

# "...must be a valid 2-character US State or Territory Code"
STATE_CODES = [
    "AL", "AK", "AS", "AZ", "AR", "CA", "CO", "CT", "DE", "DC", "FL", "GA", "GU",
    "HI", "ID", "IL", "IN", "IA", "KS", "KY", "LA", "ME", "MD", "MA", "MI", "MN",
    "MP", "MS", "MO", "MT", "NE", "NV", "NH", "NJ", "NM", "NY", "NC", "ND", "OH",
    "OK", "OR", "PA", "PR", "RI", "SC", "SD", "TN", "TX", "UT", "VT", "VA", "VI",
    "WA", "WV", "WI", "WY",
]

EXECUTABLE_SCOPES = {"Subject": "subject", "N/A": "doc"}


def _clean_xpath(raw: str) -> str:
    x = (raw or "").strip()
    x = re.sub(r"^(\.\./)+", "", x)
    return x.rstrip("/") + "/" if x else ""


def _field_key(scope: str, xpath_dir: str, element: str) -> str:
    return f"{scope}:{xpath_dir}{element}"


def convert_row(row: dict) -> tuple[dict, dict | None]:
    """Returns (rule_definition, manifest_entry_or_None)."""
    element = (row.get("Primary Data Element") or "").strip()
    logic_text = (row.get("Rule Logic") or "").strip()
    scope = EXECUTABLE_SCOPES.get((row.get("Property Affected") or "").strip())
    xpath_dir = _clean_xpath(row.get("xPath") or "")
    section = (row.get("Report Section") or "").strip() or "Uncategorized"
    label = (row.get("Report Label / Value") or "").strip()
    severity = "HardStop" if (row.get("Severity") or "").strip() == "Fatal" else "Warning"
    unique_id = (row.get("Unique ID") or "").strip()
    message_id = (row.get("Message ID") or "").strip()

    logic: dict = {"type": "needs_encoding", "source_logic": logic_text}
    manifest_entry = None

    if scope and element and xpath_dir:
        key = _field_key(scope, xpath_dir, element)
        date_fmt = (row.get("Date Format") or "").strip()

        if logic_text == f"If {element} is not provided":
            logic = {"type": "field_present", "field": key}
        elif date_fmt in DATE_PATTERNS and "format" in logic_text.lower():
            logic = {"type": "regex_match", "field": key, "pattern": DATE_PATTERNS[date_fmt]}
        elif "is not in the required format" in logic_text and "5 digits" in logic_text:
            logic = {"type": "regex_match", "field": key, "pattern": ZIP_PATTERN}
        elif "valid 2-character US State or Territory Code" in logic_text:
            logic = {"type": "field_in_set", "field": key, "allowed": STATE_CODES}
        # NOTE: Min/Max columns are NOT auto-converted to numeric_range. Inspection
        # showed those rows are instance quantifiers ("at least one instance of X")
        # or compound conditions (range + decimal precision) — they stay
        # needs_encoding until encoded deliberately. (min_v/max_v kept in h1 extras.)

        if logic["type"] != "needs_encoding":
            manifest_entry = {
                "key": key,
                "scope": scope,
                "xpath_dir": xpath_dir,
                "element": element,
                "label": label or element,
                "section": section,
            }

    executable = logic["type"] != "needs_encoding"
    rule = {
        "rule_id": message_id,
        "category": section,
        "description": logic_text,
        "severity": severity,
        # needs_encoding rules ship disabled: visible/editable later in Admin,
        # never silently evaluated, never spamming rule_errors on every run.
        "enabled": executable,
        "logic": logic,
        "citation": f"UAD 3.6 Appendix H-1 v1.4, Unique ID {unique_id}, Message ID {message_id}",
        "messages": {"reviewer": (row.get("Message Text") or "").strip()},
        "h1": {
            "unique_id": unique_id,
            "property_affected": (row.get("Property Affected") or "").strip(),
            "report_subsection": (row.get("Report Subsection") or "").strip(),
            "data_point": (row.get("Data Point Name / Value") or "").strip(),
            "min_value": (row.get("Min Value") or "").strip(),
            "max_value": (row.get("Max Value") or "").strip(),
            "date_format": (row.get("Date Format") or "").strip(),
        },
    }
    return rule, manifest_entry


def import_h1(csv_path: Path) -> tuple[dict, dict]:
    with open(csv_path, newline="", encoding="utf-8-sig") as fh:
        reader = csv.DictReader(fh)
        # Header cells carry stray whitespace (e.g. " xPath") — strip key names.
        rows = [{(k or "").strip(): v for k, v in row.items()} for row in reader]
    rules, manifest_by_key = [], {}
    for row in rows:
        rule, manifest_entry = convert_row(row)
        rules.append(rule)
        if manifest_entry is not None:
            manifest_by_key.setdefault(manifest_entry["key"], manifest_entry)
    source_hash = hashlib.sha256(Path(csv_path).read_bytes()).hexdigest()[:12]
    ruleset = {
        "name": "H1-v1.4",
        "source": f"Appendix H-1 UAD Compliance Rules v1.4 (csv sha256:{source_hash})",
        "rules": rules,
    }
    manifest = {
        "name": "uad36-field-manifest",
        "source": f"Generated from Appendix H-1 v1.4 (csv sha256:{source_hash})",
        "fields": sorted(manifest_by_key.values(), key=lambda e: e["key"]),
    }
    return ruleset, manifest


def main() -> None:
    backend_dir = Path(__file__).resolve().parents[2]
    repo_root = backend_dir.parent
    csv_path = repo_root / "QC_rules" / "Appendix H-1 - Compliance Rules - UAD Compliance Rules v1.4.csv"
    ruleset, manifest = import_h1(csv_path)
    rules_out = repo_root / "rules" / "h1_rules.json"
    manifest_out = repo_root / "schemas" / "uad36_field_manifest.json"
    manifest_out.parent.mkdir(parents=True, exist_ok=True)
    rules_out.write_text(json.dumps(ruleset, indent=2), encoding="utf-8")
    manifest_out.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    executable = sum(1 for r in ruleset["rules"] if r["enabled"])
    print(f"rules: {len(ruleset['rules'])} total, {executable} executable, "
          f"{len(ruleset['rules']) - executable} needs_encoding")
    print(f"manifest fields: {len(manifest['fields'])}")
    print(f"wrote {rules_out}")
    print(f"wrote {manifest_out}")


if __name__ == "__main__":
    main()
