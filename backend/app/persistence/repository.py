from __future__ import annotations

import uuid

from sqlalchemy import select, text
from sqlalchemy.orm import Session, sessionmaker

from app.models import RunResult, StructuralError

from .tables import FindingRow, RuleErrorRow, RunRow, StructuralErrorRow

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
                    "rule_id": f.rule_id, "category": f.category, "severity": f.severity,
                    "message_appraiser": f.message_appraiser, "message_reviewer": f.message_reviewer,
                    "field_path": f.field_path, "xpath": f.xpath, "section": f.section,
                    "values": f.values_json, "citation": f.citation,
                }
                for f in findings
            ]
            payload["rule_errors"] = [
                {"rule_id": e.rule_id, "error_type": e.error_type, "detail": e.detail} for e in errors
            ]
        return payload
