from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import select, text
from sqlalchemy.orm import Session, sessionmaker

from app.models import RunResult, StructuralError

from .tables import AuditLogRow, FindingRow, RuleErrorRow, RunRow, StructuralErrorRow

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

    def set_finding_check(self, run_id: str, finding_id: int, checked: bool, role: str) -> dict | None:
        with self._sessions() as session:
            finding = session.get(FindingRow, finding_id)
            if finding is None or finding.run_id != run_id:
                return None
            finding.appraiser_checked = checked
            session.add(AuditLogRow(
                run_id=run_id, actor_role=role, action="finding_check",
                detail=f"finding {finding_id} ({finding.rule_id}) checked={checked}",
            ))
            session.commit()
        return self.get_run(run_id)

    def review_finding(self, run_id: str, finding_id: int, status: str, note: str | None, role: str) -> dict | None:
        with self._sessions() as session:
            finding = session.get(FindingRow, finding_id)
            if finding is None or finding.run_id != run_id:
                return None
            finding.reviewer_status = status
            finding.reviewer_note = note
            finding.reviewed_at = datetime.now(timezone.utc)
            session.add(AuditLogRow(
                run_id=run_id, actor_role=role, action="finding_review",
                detail=f"finding {finding_id} ({finding.rule_id}) status={status}"
                       + (f" note={note}" if note else ""),
            ))
            session.commit()
        return self.get_run(run_id)

    def finding_severity(self, run_id: str, finding_id: int) -> str | None:
        with self._sessions() as session:
            finding = session.get(FindingRow, finding_id)
            if finding is None or finding.run_id != run_id:
                return None
            return finding.severity

    def sign_off(self, run_id: str, state: str, reviewer: str | None, role: str) -> dict | None:
        with self._sessions() as session:
            run = session.get(RunRow, run_id)
            if run is None:
                return None
            run.sign_off_state = state
            run.reviewer_name = reviewer
            run.signed_off_at = datetime.now(timezone.utc)
            session.add(AuditLogRow(
                run_id=run_id, actor_role=role, action="sign_off",
                detail=f"state={state} reviewer={reviewer or ''}",
            ))
            session.commit()
        return self.get_run(run_id)

    def audit_log(self, run_id: str) -> list[dict]:
        with self._sessions() as session:
            rows = session.scalars(
                select(AuditLogRow).where(AuditLogRow.run_id == run_id).order_by(AuditLogRow.id)
            ).all()
            return [
                {
                    "actor_role": r.actor_role, "action": r.action,
                    "detail": r.detail, "created_at": r.created_at.isoformat(),
                }
                for r in rows
            ]

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
            "sign_off_state": run.sign_off_state,
            "reviewer_name": run.reviewer_name,
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
                    "id": f.id,
                    "rule_id": f.rule_id, "category": f.category, "severity": f.severity,
                    "message_appraiser": f.message_appraiser, "message_reviewer": f.message_reviewer,
                    "field_path": f.field_path, "xpath": f.xpath, "section": f.section,
                    "values": f.values_json, "citation": f.citation,
                    "appraiser_checked": f.appraiser_checked,
                    "reviewer_status": f.reviewer_status,
                    "reviewer_note": f.reviewer_note,
                    "reviewed_at": f.reviewed_at.isoformat() if f.reviewed_at else None,
                }
                for f in findings
            ]
            payload["rule_errors"] = [
                {"rule_id": e.rule_id, "error_type": e.error_type, "detail": e.detail} for e in errors
            ]
        return payload
