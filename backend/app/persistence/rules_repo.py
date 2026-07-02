from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from app.models import RuleDefinition

from .tables import ProfileRow, RuleRow, RulesetVersionRow


def _canonical_hash(definitions: list[dict]) -> str:
    payload = json.dumps(sorted(definitions, key=lambda d: d.get("rule_id", "")), sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class RulesRepository:
    """DB-backed rule store. Every mutation freezes a new ruleset snapshot so
    runs stay reproducible against the exact rules in force at the time."""

    def __init__(self, session_factory: sessionmaker):
        self._sessions = session_factory

    # -- bootstrap ---------------------------------------------------------

    def seed_from_file(self, path: Path) -> int:
        """Load rules from a ruleset JSON file if the table is empty."""
        with self._sessions() as session:
            existing = session.scalar(select(RuleRow).limit(1))
            if existing is not None:
                return 0
            data = json.loads(Path(path).read_bytes().decode("utf-8-sig"))
            count = 0
            for definition in data.get("rules", []):
                rule = RuleDefinition.model_validate(definition)  # validates shape
                session.add(RuleRow(
                    rule_id=rule.rule_id,
                    definition_json=definition,
                    enabled=bool(definition.get("enabled", True)),
                ))
                count += 1
            session.commit()
        self._snapshot_if_changed()
        return count

    # -- reads -------------------------------------------------------------

    def list_rules(self, status: str = "all") -> list[dict]:
        with self._sessions() as session:
            rows = session.scalars(
                select(RuleRow).where(RuleRow.archived.is_(False)).order_by(RuleRow.rule_id)
            ).all()
        items = []
        for r in rows:
            d = dict(r.definition_json)
            d["enabled"] = r.enabled
            logic_type = (d.get("logic") or {}).get("type", "")
            if status == "enabled" and not r.enabled:
                continue
            if status == "needs_encoding" and logic_type != "needs_encoding":
                continue
            items.append(d)
        return items

    def get_rule(self, rule_id: str) -> dict | None:
        with self._sessions() as session:
            row = session.get(RuleRow, rule_id)
            if row is None or row.archived:
                return None
            d = dict(row.definition_json)
            d["enabled"] = row.enabled
            return d

    def active_rules(self, profile_name: str | None = None) -> tuple[list[RuleDefinition], str]:
        """Enabled, non-archived rules (minus profile-disabled) + version string."""
        disabled: set[str] = set()
        profile_tag = ""
        if profile_name:
            profile = self.get_profile_by_name(profile_name)
            if profile is not None:
                disabled = set(profile["disabled_rule_ids"])
                profile_tag = f"+{profile['name']}"
        with self._sessions() as session:
            rows = session.scalars(
                select(RuleRow).where(RuleRow.archived.is_(False), RuleRow.enabled.is_(True))
            ).all()
            definitions = [
                {**r.definition_json, "enabled": True}
                for r in rows if r.rule_id not in disabled
            ]
        version = self._snapshot_if_changed()
        return [RuleDefinition.model_validate(d) for d in definitions], version + profile_tag

    # -- writes ------------------------------------------------------------

    def upsert_rule(self, definition: dict) -> dict:
        rule = RuleDefinition.model_validate(definition)  # raises on bad shape
        with self._sessions() as session:
            row = session.get(RuleRow, rule.rule_id)
            if row is None:
                row = RuleRow(rule_id=rule.rule_id, definition_json=definition)
                session.add(row)
            row.definition_json = definition
            row.enabled = bool(definition.get("enabled", True))
            row.archived = False
            row.updated_at = datetime.now(timezone.utc)
            session.commit()
        self._snapshot_if_changed()
        return self.get_rule(rule.rule_id)

    def set_enabled(self, rule_id: str, enabled: bool) -> dict | None:
        with self._sessions() as session:
            row = session.get(RuleRow, rule_id)
            if row is None or row.archived:
                return None
            row.enabled = enabled
            definition = dict(row.definition_json)
            definition["enabled"] = enabled
            row.definition_json = definition
            row.updated_at = datetime.now(timezone.utc)
            session.commit()
        self._snapshot_if_changed()
        return self.get_rule(rule_id)

    def archive_rule(self, rule_id: str) -> bool:
        with self._sessions() as session:
            row = session.get(RuleRow, rule_id)
            if row is None:
                return False
            row.archived = True
            row.enabled = False
            row.updated_at = datetime.now(timezone.utc)
            session.commit()
        self._snapshot_if_changed()
        return True

    def import_ruleset(self, data: dict, replace: bool = False) -> int:
        count = 0
        with self._sessions() as session:
            if replace:
                for row in session.scalars(select(RuleRow)).all():
                    row.archived = True
                    row.enabled = False
            for definition in data.get("rules", []):
                rule = RuleDefinition.model_validate(definition)
                row = session.get(RuleRow, rule.rule_id)
                if row is None:
                    row = RuleRow(rule_id=rule.rule_id, definition_json=definition)
                    session.add(row)
                row.definition_json = definition
                row.enabled = bool(definition.get("enabled", True))
                row.archived = False
                row.updated_at = datetime.now(timezone.utc)
                count += 1
            session.commit()
        self._snapshot_if_changed()
        return count

    def export_ruleset(self) -> dict:
        return {"name": "qc-rules-export", "rules": self.list_rules("all")}

    # -- profiles ----------------------------------------------------------

    def list_profiles(self) -> list[dict]:
        with self._sessions() as session:
            rows = session.scalars(
                select(ProfileRow).where(ProfileRow.archived.is_(False)).order_by(ProfileRow.name)
            ).all()
            return [self._profile_dict(r) for r in rows]

    def get_profile_by_name(self, name: str) -> dict | None:
        with self._sessions() as session:
            row = session.scalar(select(ProfileRow).where(ProfileRow.name == name, ProfileRow.archived.is_(False)))
            return self._profile_dict(row) if row else None

    def upsert_profile(self, name: str, description: str, disabled_rule_ids: list[str]) -> dict:
        with self._sessions() as session:
            row = session.scalar(select(ProfileRow).where(ProfileRow.name == name))
            if row is None:
                row = ProfileRow(name=name)
                session.add(row)
            row.description = description
            row.disabled_rule_ids = disabled_rule_ids
            row.archived = False
            row.updated_at = datetime.now(timezone.utc)
            session.commit()
            return self._profile_dict(row)

    @staticmethod
    def _profile_dict(row: ProfileRow) -> dict:
        return {
            "id": row.id, "name": row.name, "description": row.description,
            "disabled_rule_ids": list(row.disabled_rule_ids or []),
        }

    # -- versioning --------------------------------------------------------

    def _snapshot_if_changed(self) -> str:
        with self._sessions() as session:
            rows = session.scalars(
                select(RuleRow).where(RuleRow.archived.is_(False)).order_by(RuleRow.rule_id)
            ).all()
            definitions = [{**r.definition_json, "enabled": r.enabled} for r in rows]
            digest = _canonical_hash(definitions)
            latest = session.scalar(
                select(RulesetVersionRow).order_by(RulesetVersionRow.id.desc()).limit(1)
            )
            if latest is None or latest.hash != digest:
                latest = RulesetVersionRow(hash=digest, snapshot_json=definitions)
                session.add(latest)
                session.commit()
            return f"db-v{latest.id}-{digest[:12]}"
