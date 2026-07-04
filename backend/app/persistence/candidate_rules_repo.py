from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from app.models import RuleDefinition

from .tables import CandidateRuleRow


class CandidateRulesRepository:
    """DB-backed store for mined client-revision candidate rules. Distinct from
    RulesRepository (the live ruleset) — nothing here is active until an Admin
    reviewer approves it, which copies the definition into RulesRepository."""

    def __init__(self, session_factory: sessionmaker):
        self._sessions = session_factory

    def bulk_insert(self, candidates: list[dict]) -> int:
        count = 0
        with self._sessions() as session:
            for c in candidates:
                definition = c["definition"]
                rule = RuleDefinition.model_validate(definition)  # validates shape
                if session.get(CandidateRuleRow, rule.rule_id) is not None:
                    continue
                session.add(CandidateRuleRow(
                    rule_id=rule.rule_id,
                    definition_json=definition,
                    source=c.get("source", "client_revision"),
                    theme_id=c["theme_id"],
                    occurrence_count=c.get("occurrence_count", 0),
                    date_range_start=c.get("date_range_start"),
                    date_range_end=c.get("date_range_end"),
                    redundancy_verdict=c.get("redundancy_verdict", "new"),
                    redundancy_notes=c.get("redundancy_notes", ""),
                ))
                count += 1
            session.commit()
        return count

    def list_candidates(self, status: str = "all") -> list[dict]:
        with self._sessions() as session:
            rows = session.scalars(
                select(CandidateRuleRow).order_by(CandidateRuleRow.occurrence_count.desc())
            ).all()
        items = [self._row_dict(r) for r in rows]
        if status != "all":
            items = [i for i in items if i["review_status"] == status]
        return items

    def get_candidate(self, rule_id: str) -> dict | None:
        with self._sessions() as session:
            row = session.get(CandidateRuleRow, rule_id)
            return self._row_dict(row) if row else None

    def mark_reviewed(self, rule_id: str, status: str, reviewer: str) -> dict | None:
        with self._sessions() as session:
            row = session.get(CandidateRuleRow, rule_id)
            if row is None:
                return None
            row.review_status = status
            row.reviewed_by = reviewer
            row.reviewed_at = datetime.now(timezone.utc)
            session.commit()
            return self._row_dict(row)

    @staticmethod
    def _row_dict(row: CandidateRuleRow) -> dict:
        d = dict(row.definition_json)
        d.update({
            "theme_id": row.theme_id,
            "occurrence_count": row.occurrence_count,
            "date_range_start": row.date_range_start,
            "date_range_end": row.date_range_end,
            "redundancy_verdict": row.redundancy_verdict,
            "redundancy_notes": row.redundancy_notes,
            "review_status": row.review_status,
            "reviewed_by": row.reviewed_by,
            "reviewed_at": row.reviewed_at.isoformat() if row.reviewed_at else None,
            "source": row.source,
        })
        return d
