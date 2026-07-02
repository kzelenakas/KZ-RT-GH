from __future__ import annotations

import io

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

SEVERITY_COLORS = {
    "HardStop": colors.HexColor("#b91c1c"),
    "Warning": colors.HexColor("#b45309"),
    "Advisory": colors.HexColor("#0369a1"),
}
SEVERITY_LABELS = {"HardStop": "Hard Stop", "Warning": "Warning", "Advisory": "Advisory"}


def render_pdf(run: dict, mode: str) -> bytes:
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=letter,
        leftMargin=0.75 * inch, rightMargin=0.75 * inch,
        topMargin=0.75 * inch, bottomMargin=0.75 * inch,
        title=f"UAD 3.6 QC Report - {run['filename']}",
    )
    styles = getSampleStyleSheet()
    body = styles["BodyText"]
    small = ParagraphStyle("small", parent=body, fontSize=8, textColor=colors.HexColor("#4b5563"))
    h1 = styles["Heading1"]
    h2 = styles["Heading2"]

    story = [Paragraph("UAD 3.6 Quality Control Report", h1)]

    counts = run.get("counts", {})
    meta_rows = [
        ["File", run["filename"]],
        ["Run ID", run["id"]],
        ["File hash (SHA-256)", run.get("file_hash", "")],
        ["Run timestamp", run["created_at"]],
        ["Schema version", run["schema_version"]],
        ["Rule set version", run["ruleset_version"]],
        ["Mode", "Appraiser self-check" if mode == "appraiser" else "QD reviewer audit"],
        ["Reviewer", run.get("reviewer_name") or "-"],
        ["Sign-off state", run.get("sign_off_state") or "-"],
        ["Counts", f"Hard Stops: {counts.get('HardStop', 0)}   Warnings: {counts.get('Warning', 0)}   Advisories: {counts.get('Advisory', 0)}"],
    ]
    meta_table = Table(meta_rows, colWidths=[1.7 * inch, 5.1 * inch])
    meta_table.setStyle(TableStyle([
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("TEXTCOLOR", (0, 0), (0, -1), colors.HexColor("#4b5563")),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("LINEBELOW", (0, 0), (-1, -2), 0.25, colors.HexColor("#e5e7eb")),
    ]))
    story += [meta_table, Spacer(1, 12)]

    structural = run.get("structural_errors", [])
    if structural:
        story.append(Paragraph(f"Schema / structural issues ({len(structural)})", h2))
        story.append(Paragraph(
            "These are file-structure problems checked before QC rules; they may invalidate rule results below.",
            small,
        ))
        for e in structural[:100]:
            loc = f" @ {e['location']}" if e.get("location") else ""
            story.append(Paragraph(f"[{e['code']}{loc}] {e['message']}", body))
        if len(structural) > 100:
            story.append(Paragraph(f"... and {len(structural) - 100} more", small))
        story.append(Spacer(1, 10))

    findings = run.get("findings", [])
    if not findings:
        story.append(Paragraph("No issues found", h2))
        story.append(Paragraph(
            f"All enabled rules passed for {run['filename']} under rule set {run['ruleset_version']}.", body,
        ))
    else:
        story.append(Paragraph(f"Findings ({len(findings)})", h2))
        by_category: dict[str, list[dict]] = {}
        for f in findings:
            by_category.setdefault(f["category"], []).append(f)
        order = {"HardStop": 0, "Warning": 1, "Advisory": 2}
        for category, items in by_category.items():
            story.append(Paragraph(category, styles["Heading3"]))
            for f in sorted(items, key=lambda x: order.get(x["severity"], 9)):
                sev = f["severity"]
                message = f["message_appraiser"] if mode == "appraiser" else f["message_reviewer"]
                head = ParagraphStyle(f"sev_{sev}", parent=body, textColor=SEVERITY_COLORS.get(sev, colors.black))
                story.append(Paragraph(f"<b>[{SEVERITY_LABELS.get(sev, sev)}] {f['rule_id']}</b> - {message}", head))
                details = []
                if f.get("section"):
                    details.append(f"Location: {f['section']}" + (f" - {f['xpath']}" if f.get("xpath") else ""))
                for k, v in (f.get("values") or {}).items():
                    details.append(f"Value: {v if v not in (None, '') else '(blank)'}")
                if mode == "reviewer" and f.get("citation"):
                    details.append(f"Citation: {f['citation']}")
                if f.get("appraiser_checked"):
                    details.append("Appraiser marked addressed")
                if mode == "reviewer" and f.get("reviewer_status") not in (None, "", "pending"):
                    note = f" - {f['reviewer_note']}" if f.get("reviewer_note") else ""
                    details.append(f"Reviewer: {f['reviewer_status']}{note}")
                for d in details:
                    story.append(Paragraph(d, small))
                story.append(Spacer(1, 6))

    doc.build(story)
    return buffer.getvalue()
