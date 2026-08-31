"""Tamper-evident audit trail (§41).

SHA-256 hash chaining over canonicalised events. Each row's hash covers the
previous row's hash, so altering or deleting any event breaks verification from
that point onward.

This is NOT a blockchain and is never described as one (§69). There is no
distributed consensus and no proof of work -- it is an append-only hash chain
in one database, which is a real and useful property, just a smaller one.
"""

from __future__ import annotations

from sqlalchemy import JSON, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampMixin, new_uuid


class AuditEvent(Base, TimestampMixin):
    __tablename__ = "audit_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    #: Monotonic position in the chain. Gaps are themselves evidence.
    sequence: Mapped[int] = mapped_column(Integer, nullable=False, unique=True, index=True)

    actor_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    actor_role: Mapped[str | None] = mapped_column(String(32))
    action: Mapped[str] = mapped_column(String(48), nullable=False, index=True)
    entity_type: Mapped[str] = mapped_column(String(48), nullable=False, index=True)
    entity_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)

    before_state: Mapped[dict | None] = mapped_column(JSON)
    after_state: Mapped[dict | None] = mapped_column(JSON)
    reason: Mapped[str | None] = mapped_column(Text)

    previous_hash: Mapped[str | None] = mapped_column(String(64))
    event_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)


Index("ix_audit_entity", AuditEvent.entity_type, AuditEvent.entity_id)
