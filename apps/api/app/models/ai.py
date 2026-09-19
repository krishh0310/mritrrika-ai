"""Model registry, embeddings and the active-learning pool (§64, §67, §10)."""

from __future__ import annotations

import os
from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampMixin, new_uuid

#: Gemini text-embedding-004 is 768-dimensional. Pinned via env so the column
#: width and the provider cannot drift apart silently.
EMBEDDING_DIM = int(os.environ.get("EMBEDDING_DIM", "768"))


class ModelVersion(Base, TimestampMixin):
    """Every prediction records which model made it (§64)."""

    __tablename__ = "model_versions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    code: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    kind: Mapped[str] = mapped_column(String(24), nullable=False)
    provider: Mapped[str | None] = mapped_column(String(48))
    description: Mapped[str | None] = mapped_column(Text)
    metrics: Mapped[dict | None] = mapped_column(JSON)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    activated_at: Mapped[object | None] = mapped_column(DateTime(timezone=True))


class Embedding(Base, TimestampMixin):
    """Semantic-retrieval half of the RAG pipeline (§10).

    Only content derived from APPROVED records is embedded, so the retriever
    cannot surface an unapproved document even before authorization filtering.
    """

    __tablename__ = "embeddings"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    entity_type: Mapped[str] = mapped_column(String(48), nullable=False, index=True)
    entity_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    #: Scoping columns so retrieval can be filtered BEFORE similarity search,
    #: not after -- authorization must precede retrieval (§18).
    parcel_id: Mapped[str | None] = mapped_column(
        ForeignKey("parcels.id", ondelete="CASCADE"), index=True
    )
    village_id: Mapped[str | None] = mapped_column(
        ForeignKey("locations.id", ondelete="SET NULL"), index=True
    )

    content: Mapped[str] = mapped_column(Text, nullable=False)
    embedding: Mapped[object] = mapped_column(Vector(EMBEDDING_DIM), nullable=False)
    model_version: Mapped[str] = mapped_column(String(32), nullable=False)


class AiFeedback(Base, TimestampMixin):
    """Curated retraining candidates (§67).

    Populated from verifier corrections but gated behind human review --
    nothing here is ever fed to automatic nightly retraining. Only rows a
    reviewer ACCEPTED are exported for training (feedback_service).
    """

    __tablename__ = "ai_feedback"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    correction_id: Mapped[str | None] = mapped_column(
        ForeignKey("field_corrections.id", ondelete="CASCADE"), index=True
    )
    field: Mapped[str | None] = mapped_column(String(32))
    priority_score: Mapped[float | None] = mapped_column()
    selection_reason: Mapped[str | None] = mapped_column(String(64))
    reviewed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    #: ACCEPTED (a real error worth learning from) or REJECTED (the correction
    #: itself was wrong, or teaches nothing). NULL until reviewed.
    review_decision: Mapped[str | None] = mapped_column(String(16), index=True)
    reviewed_by_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    review_note: Mapped[str | None] = mapped_column(Text)
    #: The export tag of the training set this row first went into.
    included_in_dataset: Mapped[str | None] = mapped_column(String(64))


class Notification(Base, TimestampMixin):
    __tablename__ = "notifications"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    body: Mapped[str | None] = mapped_column(Text)
    link: Mapped[str | None] = mapped_column(String(512))
    is_read: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
