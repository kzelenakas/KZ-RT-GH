from __future__ import annotations

import csv
import io

# One row per finding (spec). Run metadata repeats on every row so the CSV is
# self-describing after spreadsheet import/merge.

COLUMNS = [
    "run_id", "filename", "created_at", "schema_version", "ruleset_version",
    "mode", "reviewer", "sign_off_state",
    "rule_id", "category", "severity", "message", "field_path", "xpath", "section",
    "values", "citation", "appraiser_checked", "reviewer_status", "reviewer_note",
]


def render_csv(run: dict, mode: str) -> str:
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=COLUMNS, extrasaction="ignore")
    writer.writeheader()
    base = {
        "run_id": run["id"],
        "filename": run["filename"],
        "created_at": run["created_at"],
        "schema_version": run["schema_version"],
        "ruleset_version": run["ruleset_version"],
        "mode": mode,
        "reviewer": run.get("reviewer_name") or "",
        "sign_off_state": run.get("sign_off_state") or "",
    }
    findings = run.get("findings", [])
    if not findings:
        writer.writerow({**base, "rule_id": "", "severity": "", "message": "No issues found"})
        return buffer.getvalue()
    for f in findings:
        message = f["message_appraiser"] if mode == "appraiser" else f["message_reviewer"]
        row = {
            **base,
            "rule_id": f["rule_id"],
            "category": f["category"],
            "severity": f["severity"],
            "message": message,
            "field_path": f["field_path"],
            "xpath": f.get("xpath") or "",
            "section": f.get("section") or "",
            "values": "; ".join(f"{k}={v if v not in (None, '') else '(blank)'}" for k, v in f.get("values", {}).items()),
            "citation": f.get("citation") or "",
            "appraiser_checked": f.get("appraiser_checked", False),
        }
        if mode == "reviewer":
            row["reviewer_status"] = f.get("reviewer_status") or ""
            row["reviewer_note"] = f.get("reviewer_note") or ""
        writer.writerow(row)
    return buffer.getvalue()
