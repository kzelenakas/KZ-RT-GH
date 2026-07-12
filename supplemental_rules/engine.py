"""Rule runner. Mirrors backend/app/rules/engine.py's shape (load rules,
loop, evaluate, collect findings) trimmed to what a standalone package
needs -- no DB persistence, no run-audit-log, no FastAPI. Callers on GCP
own persistence (Firestore, Cloud SQL, BigQuery) with their own client;
this returns plain dicts, nothing to adapt around.
"""
from __future__ import annotations
import json
from pathlib import Path
from lxml import etree
from .operators import OPERATORS

def load_rules(path: str | Path | None = None) -> list[dict]:
    path = Path(path) if path else Path(__file__).parent / "rules.json"
    return json.loads(path.read_text(encoding="utf-8"))["rules"]

def evaluate(xml_bytes: bytes, rules: list[dict] | None = None) -> list[dict]:
    """Returns one finding dict per TRIGGERED rule: {rule_id, category,
    severity, description, citation, values}. Rules whose logic.type is
    'needs_encoding' are skipped (not silently claimed as checked) --
    ponytail: honest about what's actually running, see rules.json's
    needs_encoding entries for the backlog."""
    rules = rules if rules is not None else load_rules()
    doc = etree.fromstring(xml_bytes)
    findings = []
    for rule in rules:
        if not rule.get("enabled", True):
            continue  # disabled candidate rule -- e.g. new geo_proximity rules awaiting
                       # Kevin's sign-off on wording/citation before going live
        logic = rule["logic"]
        op = OPERATORS.get(logic["type"])
        if op is None:
            continue  # needs_encoding or an operator not yet implemented
        result = op(logic, doc)
        if result["triggered"]:
            findings.append({
                "rule_id": rule["rule_id"], "category": rule["category"],
                "severity": rule["severity"], "description": rule["description"],
                "citation": rule.get("citation"), "values": result["values"],
            })
    return findings

_PHOTO_LOGIC_TYPES = {"photo_face_detected", "photo_quality_flag"}

def evaluate_photos(images: dict[str, bytes], rules: list[dict] | None = None) -> list[dict]:
    """Phase 2/3. Same finding shape and same 'enabled' honesty as evaluate(),
    but loops (rule x photo) instead of (rule x document) -- photo operators
    take raw image bytes, not a parsed XML doc, so this is a separate entry
    point rather than a branch inside evaluate(). Returns one finding per
    (rule, photo) trigger, with the photo filename in values["photo"]."""
    rules = rules if rules is not None else load_rules()
    findings = []
    for rule in rules:
        if not rule.get("enabled", True):
            continue
        logic = rule["logic"]
        if logic["type"] not in _PHOTO_LOGIC_TYPES:
            continue  # not a photo rule -- evaluate() handles XML-based rules
        op = OPERATORS.get(logic["type"])
        if op is None:
            continue
        for filename, image_bytes in images.items():
            result = op(logic, image_bytes)
            if result["triggered"]:
                values = dict(result["values"])
                values["photo"] = filename
                findings.append({
                    "rule_id": rule["rule_id"], "category": rule["category"],
                    "severity": rule["severity"], "description": rule["description"],
                    "citation": rule.get("citation"), "values": values,
                })
    return findings
