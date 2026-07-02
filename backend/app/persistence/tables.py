from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import JSON, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class RunRow(Base):
    __tablename__ = "runs"
    # Retention rule: rows in this table are NEVER deleted (spec: no auto-delete).
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    filename: Mapped[str] = mapped_column(String(500))
    file_hash: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    schema_version: Mapped[str] = mapped_column(String(100))
    ruleset_version: Mapped[str] = mapped_column(String(200))
    sign_off_state: Mapped[str] = mapped_column(String(20), default="in_review")
    reviewer_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    signed_off_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class StructuralErrorRow(Base):
    __tablename__ = "structural_errors"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.id"), index=True)
    code: Mapped[str] = mapped_column(String(50))
    message: Mapped[str] = mapped_column(Text)
    location: Mapped[str | None] = mapped_column(String(200), nullable=True)


class FindingRow(Base):
    __tablename__ = "findings"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.id"), index=True)
    rule_id: Mapped[str] = mapped_column(String(100))
    category: Mapped[str] = mapped_column(String(200))
    severity: Mapped[str] = mapped_column(String(20))
    message_appraiser: Mapped[str] = mapped_column(Text)
    message_reviewer: Mapped[str] = mapped_column(Text)
    field_path: Mapped[str] = mapped_column(String(300), default="")
    xpath: Mapped[str | None] = mapped_column(Text, nullable=True)
    section: Mapped[str | None] = mapped_column(String(200), nullable=True)
    values_json: Mapped[dict] = mapped_column(JSON, default=dict)
    citation: Mapped[str | None] = mapped_column(Text, nullable=True)
    appraiser_checked: Mapped[bool] = mapped_column(default=False)
    reviewer_status: Mapped[str] = mapped_column(String(30), default="pending")
    reviewer_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class RuleErrorRow(Base):
    __tablename__ = "rule_errors"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.id"), index=True)
    rule_id: Mapped[str] = mapped_column(String(100))
    error_type: Mapped[str] = mapped_column(String(50))
    detail: Mapped[str] = mapped_column(Text)


class AuditLogRow(Base):
    __tablename__ = "audit_log"
    # Append-only: reviewer/appraiser actions with timestamps (spec: audit trail).
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.id"), index=True)
    actor_role: Mapped[str] = mapped_column(String(20))
    action: Mapped[str] = mapped_column(String(50))
    detail: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
