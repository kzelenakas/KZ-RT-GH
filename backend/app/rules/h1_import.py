"""Import Appendix H-1 compliance rules (CSV) into the external rule format.

Conversion policy (Phase 2, extended 2026-07-03):
- Property Affected "Subject" or "N/A" -> executable scope ("subject" / "doc").
  Comparable/#n scopes need per-instance iteration (later phase) and are
  imported disabled with logic type "needs_encoding" no matter how simple
  their Rule Logic text is — the adapter only resolves one value per field
  key today, so a comparable-scoped rule can't be evaluated correctly yet.
- Rule Logic exactly "If <element> is not provided"       -> field_present
- Date Format CCYY-MM-DD / CCYY-MM + "format" in logic    -> regex_match
- "...is not in the required format (5 digits...)"        -> regex_match (ZIP)
- "...valid 2-character US State or Territory Code"       -> field_in_set
- "If <element> < N" / "If <element> > N" (element's own
  value against a literal number, nothing else in the text) -> numeric_range
- "If <condition(s)>, and <element> is not provided", where the condition
  is built only from equality/inequality checks on OTHER elements (joined
  by and/or, optionally parenthesized, no "instance of") -> conditional
  (gates a field_present check). Each condition field must resolve to
  exactly one field key elsewhere in H-1 (own scope/xPath columns on the
  row where that element is itself a Primary Data Element) — if a
  condition field is unknown, ambiguous (used with two different xPaths
  elsewhere), or the condition text doesn't parse cleanly (e.g. it mixes
  in a numeric or "instance of" clause), the rule is left needs_encoding
  rather than guessed at.
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


# "If <element> < 1,000,000" / "If <element> > 1" — element's own value against
# a bare literal number, nothing else in the Rule Logic text.
NUMERIC_THRESHOLD_RE = re.compile(r'^If (\w+) (<|>) ([\d,]+(?:\.\d+)?)$')

# Leaf condition: Field = "Value" / Field <> "Value".
_LEAF_RE = re.compile(r'^([\w@]+)\s*(=|<>)\s*"([^"]*)"$')
# Bare quoted continuation of a same-field "or" list: `... or "OtherValue"`.
_BARE_RE = re.compile(r'^"([^"]*)"$')


def _top_level_split(text: str, keyword: str) -> list[str]:
    """Split on ' <keyword> ' (case-insensitive) at paren-depth 0, outside quotes."""
    parts, buf, depth, in_quote, i = [], [], 0, False, 0
    kw = f" {keyword} "
    while i < len(text):
        ch = text[i]
        if ch == '"':
            in_quote = not in_quote
            buf.append(ch)
            i += 1
            continue
        if not in_quote:
            if ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
            if depth == 0 and text[i:i + len(kw)].lower() == kw.lower():
                parts.append("".join(buf))
                buf = []
                i += len(kw)
                continue
        buf.append(ch)
        i += 1
    parts.append("".join(buf))
    return [p.strip() for p in parts]


def _fully_wrapped(text: str) -> bool:
    if not (text.startswith("(") and text.endswith(")")):
        return False
    depth = 0
    for i, ch in enumerate(text):
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth == 0 and i != len(text) - 1:
                return False
    return True


def _parse_condition_dnf(text: str) -> list[list[tuple[str, dict]]] | None:
    """Parse an H-1 condition clause into DNF: OR-of-AND-groups of (field, comparator).

    comparator is one of {"equals": v} / {"not_equals": v}. Handles the shorthand
    "Field = "V1" or "V2"" (same field, bare quoted alternates) and one level of
    parenthesized sub-grouping — the only shapes observed in H-1's Rule Logic text.
    Returns None if the text doesn't reduce to pure equality/inequality conditions
    (e.g. it contains a numeric comparison or "instance of" clause) — callers must
    fall back to needs_encoding rather than guess.
    """
    text = re.sub(r',\s*(and|or)\b', r' \1', text, flags=re.I)
    text = " ".join(text.split()).strip()
    while _fully_wrapped(text):
        text = " ".join(text[1:-1].split()).strip()

    or_parts = _top_level_split(text, "or")
    if len(or_parts) > 1:
        dnf: list[list[tuple[str, dict]]] = []
        last_field = None
        for part in or_parts:
            part = part.strip()
            bare = _BARE_RE.match(part)
            if bare and last_field:
                dnf.append([(last_field, {"equals": bare.group(1)})])
                continue
            sub = _parse_condition_dnf(part)
            if sub is None:
                return None
            leaf = _LEAF_RE.match(part)
            if leaf:
                last_field = leaf.group(1)
            dnf.extend(sub)
        return dnf

    and_parts = _top_level_split(text, "and")
    if len(and_parts) > 1:
        sub_dnfs = [_parse_condition_dnf(p) for p in and_parts]
        if any(d is None for d in sub_dnfs):
            return None
        combos: list[list[tuple[str, dict]]] = [[]]
        for d in sub_dnfs:
            combos = [combo + group for combo in combos for group in d]
        return combos

    leaf = _LEAF_RE.match(text)
    if leaf:
        field, op, val = leaf.groups()
        cond = {"equals": val} if op == "=" else {"not_equals": val}
        return [[(field, cond)]]
    return None


def convert_row(row: dict, element_index: dict[str, str] | None = None) -> tuple[dict, dict | None]:
    """Returns (rule_definition, manifest_entry_or_None).

    ``element_index`` maps a Primary Data Element name to its one unambiguous
    field key elsewhere in H-1 (built by ``_build_element_index``). Only used
    to resolve condition fields for the ``conditional`` pattern; omitted it
    behaves exactly as before (conditional pattern never matches).
    """
    element_index = element_index or {}
    element = (row.get("Primary Data Element") or "").strip()
    logic_text = (row.get("Rule Logic") or "").strip()
    logic_norm = " ".join(logic_text.split())  # collapse embedded newlines/whitespace
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
        num_m = NUMERIC_THRESHOLD_RE.match(logic_norm)
        cond_suffix = f"and {element} is not provided"

        if logic_text == f"If {element} is not provided":
            logic = {"type": "field_present", "field": key}
        elif date_fmt in DATE_PATTERNS and "format" in logic_text.lower():
            logic = {"type": "regex_match", "field": key, "pattern": DATE_PATTERNS[date_fmt]}
        elif "is not in the required format" in logic_text and "5 digits" in logic_text:
            logic = {"type": "regex_match", "field": key, "pattern": ZIP_PATTERN}
        elif "valid 2-character US State or Territory Code" in logic_text:
            logic = {"type": "field_in_set", "field": key, "allowed": STATE_CODES}
        elif num_m and num_m.group(1) == element:
            _, op, num_text = num_m.groups()
            number = float(num_text.replace(",", ""))
            if number.is_integer():
                number = int(number)
            bound = {"min": number} if op == "<" else {"max": number}
            logic = {"type": "numeric_range", "field": key, **bound}
        elif (logic_norm.endswith(cond_suffix) and "instance of" not in logic_norm
              and logic_norm.startswith("If ")):
            cond_text = logic_norm[len("If "):-len(cond_suffix)].strip().rstrip(",").strip()
            dnf = _parse_condition_dnf(cond_text) if cond_text else None
            if_any = None
            if dnf:
                if_any = []
                for group in dnf:
                    resolved = []
                    for field_name, cmp in group:
                        field_key = element_index.get(field_name)
                        if field_key is None:
                            if_any = None
                            break
                        resolved.append({"field": field_key, **cmp})
                    if if_any is None:
                        break
                    if_any.append(resolved)
            if if_any:
                logic = {
                    "type": "conditional",
                    "if_any": if_any,
                    "then": {"type": "field_present", "field": key},
                }
        # NOTE: Min/Max columns themselves are NOT auto-converted to numeric_range —
        # inspection showed most are instance quantifiers ("at least one instance of
        # X") or compound conditions. Only the narrow "If <own element> < / > N"
        # Rule Logic shape above is auto-converted; everything else with Min/Max
        # populated stays needs_encoding until encoded deliberately.

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


def _build_element_index(rows: list[dict]) -> tuple[dict[str, str], dict[str, dict]]:
    """Element name -> field key, and key -> manifest-entry dict, built from every
    row's own scope/xPath/label/section columns — independent of whether that row's
    own Rule Logic happens to auto-convert (a condition field like PartyRoleType may
    never have simple logic itself but its xPath is still known from its own row).

    Elements that resolve to more than one distinct key across H-1 (e.g.
    AddressLineText appears under both the subject property and party addresses)
    are dropped entirely — never guessed at.
    """
    candidates: dict[str, dict[str, dict]] = {}
    for row in rows:
        element = (row.get("Primary Data Element") or "").strip()
        scope = EXECUTABLE_SCOPES.get((row.get("Property Affected") or "").strip())
        xpath_dir = _clean_xpath(row.get("xPath") or "")
        if not (scope and element and xpath_dir):
            continue
        key = _field_key(scope, xpath_dir, element)
        section = (row.get("Report Section") or "").strip() or "Uncategorized"
        label = (row.get("Report Label / Value") or "").strip()
        meta = {
            "key": key, "scope": scope, "xpath_dir": xpath_dir, "element": element,
            "label": label or element, "section": section,
        }
        candidates.setdefault(element, {}).setdefault(key, meta)
    element_to_key = {e: next(iter(ks)) for e, ks in candidates.items() if len(ks) == 1}
    key_to_meta = {m["key"]: m for ks in candidates.values() if len(ks) == 1 for m in ks.values()}
    return element_to_key, key_to_meta


def _rule_field_keys(logic: dict) -> set[str]:
    """Every field key an enabled rule's logic reads, across all supported shapes."""
    keys = set()
    if logic.get("field"):
        keys.add(logic["field"])
    for group in logic.get("if_any", []):
        for cond in group:
            if cond.get("field"):
                keys.add(cond["field"])
    then = logic.get("then") or {}
    if then.get("field"):
        keys.add(then["field"])
    return keys


def import_h1(csv_path: Path) -> tuple[dict, dict]:
    with open(csv_path, newline="", encoding="utf-8-sig") as fh:
        reader = csv.DictReader(fh)
        # Header cells carry stray whitespace (e.g. " xPath") — strip key names.
        rows = [{(k or "").strip(): v for k, v in row.items()} for row in reader]
    element_to_key, key_to_meta = _build_element_index(rows)
    rules, manifest_by_key = [], {}
    for row in rows:
        rule, manifest_entry = convert_row(row, element_to_key)
        rules.append(rule)
        if manifest_entry is not None:
            manifest_by_key.setdefault(manifest_entry["key"], manifest_entry)
    # A conditional rule's condition fields (e.g. PropertyInProjectIndicator) may
    # never be some other row's OWN convertible logic — make sure every field key
    # an enabled rule actually reads has a manifest entry, so the schema adapter
    # populates it, not just the fields whose own H-1 row happened to auto-convert.
    for rule in rules:
        if not rule["enabled"]:
            continue
        for key in _rule_field_keys(rule["logic"]):
            if key not in manifest_by_key and key in key_to_meta:
                manifest_by_key[key] = key_to_meta[key]
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
