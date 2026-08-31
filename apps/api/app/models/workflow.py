"""Verification, approval and grievances (§27-§32, §19)."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, TimestampMixin, new_uuid


class VerificationTask(Base, TimestampMixin):
    """A document queued for a verifier (§27)."""

    __tablename__ = "verification_tasks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    document_id: Mapped[str] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    assigned_to_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    status: Mapped[str] = mapped_column(
        String(24), nullable=False, default="PENDING", index=True
    )
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    #: Denormalised so the queue can sort by confidence without a join.
    lowest_confidence: Mapped[float | None] = mapped_column(Float, index=True)
    anomaly_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    actions: Mapped[list[VerificationAction]] = relationship(
        back_populates="task", cascade="all, delete-orphan"
    )


class VerificationAction(Base, TimestampMixin):
    __tablename__ = "verification_actions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    task_id: Mapped[str] = mapped_column(
        ForeignKey("verification_tasks.id", ondelete="CASCADE"), nullable=False, index=True
    )
    actor_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    action: Mapped[str] = mapped_column(String(32), nullable=False)
    field: Mapped[str | None] = mapped_column(String(32))
    note: Mapped[str | None] = mapped_column(Text)

    task: Mapped[VerificationTask] = relationship(back_populates="actions")


class ApprovalAction(Base, TimestampMixin):
    """A tehsildar decision (§32)."""

    __tablename__ = "approval_actions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    document_id: Mapped[str] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    actor_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    decision: Mapped[str] = mapped_column(String(24), nullable=False, index=True)
    reason: Mapped[str | None] = mapped_column(Text)


class ValidationFinding(Base, TimestampMixin):
    """A deterministic rule outcome (§33)."""

    __tablename__ = "validation_findings"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    document_id: Mapped[str] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    rule: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    severity: Mapped[str] = mapped_column(String(16), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    field: Mapped[str | None] = mapped_column(String(32))


class AnomalyFlag(Base, TimestampMixin):
    """A pattern flag (§34).

    Surfaced to officers as 'potential inconsistency requiring investigation'.
    The word 'fraud' never appears in user-facing text.
    """

    __tablename__ = "anomaly_flags"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    document_id: Mapped[str | None] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), index=True
    )
    parcel_id: Mapped[str | None] = mapped_column(
        ForeignKey("parcels.id", ondelete="CASCADE"), index=True
    )
    anomaly_type: Mapped[str] = mapped_column(String(48), nullable=False, index=True)
    score: Mapped[float | None] = mapped_column(Float)
    explanation: Mapped[str] = mapped_column(Text, nullable=False)
    evidence: Mapped[dict | None] = mapped_column(JSON)
    model_version: Mapped[str | None] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="OPEN")


class Grievance(Base, TimestampMixin):
    """A citizen-raised issue (§19)."""

    __tablename__ = "grievances"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    external_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    raised_by_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    parcel_id: Mapped[str | None] = mapped_column(
        ForeignKey("parcels.id", ondelete="SET NULL"), index=True
    )
    issue_type: Mapped[str] = mapped_column(String(48), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    supporting_storage_key: Mapped[str | None] = mapped_column(String(512))
    status: Mapped[str] = mapped_column(
        String(24), nullable=False, default="SUBMITTED", index=True
    )
    resolution_note: Mapped[str | None] = mapped_column(Text)
