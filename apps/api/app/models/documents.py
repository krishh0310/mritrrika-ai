"""Documents, pages, jobs and the extraction chain (§38).

The provenance chain is the point of this module:

    Document -> DocumentPage -> OcrBlock -> Extraction -> FieldCorrection

Every Extraction keeps its raw OCR value AND the normalized value, plus the
bbox and the model version that produced it (§26, §64). Normalization never
overwrites raw -- that is what lets the Verifier show source-vs-value and what
makes the audit trail meaningful.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, SyntheticMixin, TimestampMixin, new_uuid


class Document(Base, TimestampMixin, SyntheticMixin):
    __tablename__ = "documents"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    external_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)

    document_type: Mapped[str] = mapped_column(String(32), nullable=False)
    #: Current node in the §37 state machine. Transitions are validated in the
    #: service layer; the column itself is just storage.
    state: Mapped[str] = mapped_column(
        String(32), nullable=False, default="UPLOADED", index=True
    )

    parcel_id: Mapped[str | None] = mapped_column(
        ForeignKey("parcels.id", ondelete="SET NULL"), index=True
    )
    village_id: Mapped[str | None] = mapped_column(
        ForeignKey("locations.id", ondelete="SET NULL"), index=True
    )
    record_year: Mapped[str | None] = mapped_column(String(16))

    #: Metadata the DEO supplied at upload (§21), kept separate from anything
    #: the AI later inferred.
    declared_khasra: Mapped[str | None] = mapped_column(String(32))
    declared_khata: Mapped[str | None] = mapped_column(String(32))

    uploaded_by_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )

    #: Object-storage key, never the bytes themselves (§63).
    storage_key: Mapped[str] = mapped_column(String(512), nullable=False)
    original_filename: Mapped[str | None] = mapped_column(String(255))
    mime_type: Mapped[str | None] = mapped_column(String(64))
    size_bytes: Mapped[int | None] = mapped_column(Integer)
    checksum_sha256: Mapped[str | None] = mapped_column(String(64), index=True)
    #: 64-bit dHash of the first page, hex encoded (§22). Indexed for lookup by
    #: exact hash; near matches are a Hamming scan, not an index seek.
    perceptual_hash: Mapped[str | None] = mapped_column(String(16), index=True)

    #: §22 quality gate outcome.
    quality_score: Mapped[float | None] = mapped_column(Float)
    quality_report: Mapped[dict | None] = mapped_column(JSON)
    quality_recommendation: Mapped[str | None] = mapped_column(String(32))
    #: "ben", "guj", "pan", "ori" or "mal" when fields came from the IndicTrans2
    #: translate-to-Hindi fallback: values are renderings, verify carefully.
    translated_from: Mapped[str | None] = mapped_column(String(8))

    pages: Mapped[list[DocumentPage]] = relationship(
        back_populates="document", cascade="all, delete-orphan"
    )
    extractions: Mapped[list[Extraction]] = relationship(
        back_populates="document", cascade="all, delete-orphan"
    )
    jobs: Mapped[list[ProcessingJob]] = relationship(
        back_populates="document", cascade="all, delete-orphan"
    )


class DocumentPage(Base, TimestampMixin):
    __tablename__ = "document_pages"
    __table_args__ = (Index("uq_page_per_document", "document_id", "page_number", unique=True),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    document_id: Mapped[str] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    page_number: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    storage_key: Mapped[str | None] = mapped_column(String(512))
    #: Result of OpenCV preprocessing, kept alongside the original so the
    #: Verifier can toggle between them (§28).
    enhanced_storage_key: Mapped[str | None] = mapped_column(String(512))
    width: Mapped[int | None] = mapped_column(Integer)
    height: Mapped[int | None] = mapped_column(Integer)

    document: Mapped[Document] = relationship(back_populates="pages")
    ocr_blocks: Mapped[list[OcrBlock]] = relationship(
        back_populates="page", cascade="all, delete-orphan"
    )


class ProcessingJob(Base, TimestampMixin):
    """One async pipeline run over a document (§23)."""

    __tablename__ = "processing_jobs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    document_id: Mapped[str] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    celery_task_id: Mapped[str | None] = mapped_column(String(64), index=True)

    stage: Mapped[str] = mapped_column(String(32), nullable=False, default="upload")
    progress: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="QUEUED", index=True)
    message: Mapped[str | None] = mapped_column(Text)
    error: Mapped[str | None] = mapped_column(Text)

    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    document: Mapped[Document] = relationship(back_populates="jobs")


class OcrBlock(Base, TimestampMixin):
    """One recognised text run, with its box and confidence (§6).

    Never store plain text alone: the Verifier UI needs the box to zoom to the
    source region, and evaluation needs the confidence.
    """

    __tablename__ = "ocr_blocks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    page_id: Mapped[str] = mapped_column(
        ForeignKey("document_pages.id", ondelete="CASCADE"), nullable=False, index=True
    )

    text: Mapped[str] = mapped_column(Text, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    bbox_x1: Mapped[int] = mapped_column(Integer, nullable=False)
    bbox_y1: Mapped[int] = mapped_column(Integer, nullable=False)
    bbox_x2: Mapped[int] = mapped_column(Integer, nullable=False)
    bbox_y2: Mapped[int] = mapped_column(Integer, nullable=False)

    script: Mapped[str | None] = mapped_column(String(32))
    #: Reading-order index, assigned by vertical-overlap line grouping --
    #: PaddleOCR does not return blocks in reading order.
    reading_order: Mapped[int | None] = mapped_column(Integer)
    is_handwritten: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    model_version: Mapped[str] = mapped_column(String(32), nullable=False)

    page: Mapped[DocumentPage] = relationship(back_populates="ocr_blocks")


class Extraction(Base, TimestampMixin):
    """One extracted field with full provenance (§26)."""

    __tablename__ = "extractions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    document_id: Mapped[str] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    page_number: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    field: Mapped[str] = mapped_column(String(32), nullable=False, index=True)

    #: BOTH are kept, always (§26).
    raw_value: Mapped[str | None] = mapped_column(Text)
    normalized_value: Mapped[str | None] = mapped_column(Text)
    #: Set only once a human edits the value; keeps AI output distinguishable.
    corrected_value: Mapped[str | None] = mapped_column(Text)

    ocr_confidence: Mapped[float | None] = mapped_column(Float)
    extraction_confidence: Mapped[float | None] = mapped_column(Float)
    layout_confidence: Mapped[float | None] = mapped_column(Float)
    validation_confidence: Mapped[float | None] = mapped_column(Float)
    final_confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    #: Component breakdown, so "why is this amber?" is answerable (§68).
    confidence_breakdown: Mapped[dict | None] = mapped_column(JSON)

    bbox_x1: Mapped[int | None] = mapped_column(Integer)
    bbox_y1: Mapped[int | None] = mapped_column(Integer)
    bbox_x2: Mapped[int | None] = mapped_column(Integer)
    bbox_y2: Mapped[int | None] = mapped_column(Integer)

    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="NEEDS_REVIEW", index=True
    )
    validation_message: Mapped[str | None] = mapped_column(Text)
    model_version: Mapped[str] = mapped_column(String(32), nullable=False)
    row_index: Mapped[int | None] = mapped_column(Integer)

    document: Mapped[Document] = relationship(back_populates="extractions")
    corrections: Mapped[list[FieldCorrection]] = relationship(
        back_populates="extraction", cascade="all, delete-orphan"
    )

    @property
    def effective_value(self) -> str | None:
        """What the record actually says: a human correction wins over AI."""
        return self.corrected_value if self.corrected_value is not None else self.normalized_value


class FieldCorrection(Base, TimestampMixin):
    """A verifier edit -- and a retraining candidate (§30).

    Stored for every correction, but NEVER fed to automatic retraining (§67).
    """

    __tablename__ = "field_corrections"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    extraction_id: Mapped[str] = mapped_column(
        ForeignKey("extractions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    document_id: Mapped[str] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    field: Mapped[str] = mapped_column(String(32), nullable=False)

    model_prediction: Mapped[str | None] = mapped_column(Text)
    corrected_value: Mapped[str | None] = mapped_column(Text)
    confidence_at_correction: Mapped[float | None] = mapped_column(Float)
    model_version: Mapped[str | None] = mapped_column(String(32))

    corrected_by_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    reason: Mapped[str | None] = mapped_column(Text)
    #: Flagged for the active-learning pool, pending human curation (§67).
    is_retraining_candidate: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False
    )

    extraction: Mapped[Extraction] = relationship(back_populates="corrections")
