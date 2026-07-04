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
