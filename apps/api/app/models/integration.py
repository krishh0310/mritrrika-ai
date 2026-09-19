"""Delivery of approved records to external land-records systems (§14)."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampMixin, new_uuid


class LrmsSyncRecord(Base, TimestampMixin):
    """One approved record queued for, or delivered to, the state LRMS.

    An outbox rather than a direct call from the approval: approving a record
    must not fail because a state server is down, and a record that could not
    be delivered must stay visibly undelivered until it is. The payload is
    stored as sent, so what the LRMS received can always be shown exactly.
    """

    __tablename__ = "lrms_sync_records"
    __table_args__ = (
        # The same content is queued once. A re-approval that changes the
        # record produces a new digest, and so a new delivery.
        Index("uq_lrms_sync_document_digest", "document_id", "payload_sha256", unique=True),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    document_id: Mapped[str] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    payload_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="PENDING", index=True
    )
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    adapter: Mapped[str | None] = mapped_column(String(32))
    remote_reference: Mapped[str | None] = mapped_column(String(255))
    last_error: Mapped[str | None] = mapped_column(Text)
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class IntegrationLog(Base):
    """One attempt to reach an external land-records system, and its outcome."""

    __tablename__ = "integration_log"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    connector: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    record_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    #: "mock", "delivered" or "failed".
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    error: Mapped[str | None] = mapped_column(Text)
    attempted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )
