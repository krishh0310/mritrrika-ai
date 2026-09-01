"""Runs the AI pipeline and persists its results (§23, §26).

The worker package is pure; this module owns the database side: OCR blocks,
extractions with provenance, validation findings, the verification task, and
the state transitions that move the document through §37.

Every prediction records its model version (§64), and every bbox is stored in
ORIGINAL page coordinates so the Verifier highlights the right region even
though OCR ran on an upscaled, enhanced copy.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from mrittika_domain import DocumentState
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config.settings import get_settings
from app.models import (
    Document,
    DocumentPage,
    Extraction,
    OcrBlock,
    Parcel,
    ProcessingJob,
    ValidationFinding,
    VerificationTask,
)
from app.services import (
    anomaly_service,
    audit_service,
    document_service,
    storage_service,
)
from app.services.auth_service import Principal

logger = logging.getLogger(__name__)

_engine = None


def get_engine():
    """Cache the OCR engine per process (§84 -- never load models per request)."""
    global _engine
    if _engine is None:
        from ocr.provider import build_default_engine

        settings = get_settings()
        _engine = build_default_engine(
            provider=settings.ocr_provider,
            lang=settings.ocr_lang,
            gemini_api_key=settings.gemini_api_key,
            gemini_model=settings.gemini_llm_model,
        )
    return _engine


def _update_job(session: Session, job: ProcessingJob, stage: str, progress: int,
                message: str) -> None:
    job.stage = stage
    job.progress = progress
    job.message = message
    job.status = "RUNNING" if stage != "complete" else "SUCCEEDED"
    session.commit()


def process_document(
    session: Session,
    document: Document,
    job: ProcessingJob,
    *,
    principal: Principal | None = None,
) -> dict:
    """Execute the pipeline for one document and persist everything.

    On OCR failure the document is moved to NEEDS_VERIFICATION with the failure
    recorded -- never to a fabricated 'success' with empty results (§82).
    """
    from extraction_pipeline import run as run_pipeline
    from ocr.provider import OcrUnavailable

    settings = get_settings()
    data = storage_service.get_bytes(document.storage_key)

    job.status = "RUNNING"
    job.started_at = datetime.now(UTC)
    session.commit()

    def progress(stage: str, percent: int, message: str) -> None:
        _update_job(session, job, stage, percent, message)

    try:
        result = run_pipeline(
            data,
            get_engine(),
            declared_khasra=document.declared_khasra,
            progress=progress,
        )
    except (OcrUnavailable, ValueError) as exc:
        job.status = "FAILED"
        job.error = str(exc)
        job.finished_at = datetime.now(UTC)
        # RESCAN_REQUIRED, not NEEDS_VERIFICATION. §37 forbids
        # PROCESSING -> NEEDS_VERIFICATION (verification presupposes an
        # extraction to verify), and attempting it made the failure handler
        # itself raise -- turning a recoverable OCR failure into a 500.
        # A page with no recognised text needs a better scan, not a reviewer.
        document_service.transition(
            session, document, DocumentState.RESCAN_REQUIRED,
            principal=principal, action=audit_service.PROCESSING_FAILED,
            reason=f"AI pipeline could not process this page: {exc}",
        )
        audit_service.record(
            session, action=audit_service.PROCESSING_FAILED,
            entity_type="document", entity_id=document.external_id,
            actor_id=principal.id if principal else None,
            after_state={"error": str(exc)},
        )
        session.commit()
        logger.warning("pipeline failed for %s: %s", document.external_id, exc)
        return {"status": "FAILED", "error": str(exc)}

    page = session.execute(
        select(DocumentPage).where(DocumentPage.document_id == document.id)
        .order_by(DocumentPage.page_number)
    ).scalars().first()
    if page is None:
        page = DocumentPage(document_id=document.id, page_number=1,
                            storage_key=document.storage_key)
        session.add(page)
        session.flush()

    # Replace prior results so re-processing is idempotent rather than additive.
    for existing in session.execute(
        select(OcrBlock).where(OcrBlock.page_id == page.id)
    ).scalars():
        session.delete(existing)
    for existing in session.execute(
        select(Extraction).where(Extraction.document_id == document.id)
    ).scalars():
        session.delete(existing)
    for existing in session.execute(
        select(ValidationFinding).where(ValidationFinding.document_id == document.id)
    ).scalars():
        session.delete(existing)
    session.flush()

    for block in result.ocr.blocks:
        x1, y1, x2, y2 = block.bbox
        session.add(
            OcrBlock(
                page_id=page.id,
                text=block.text,
                confidence=block.confidence,
                bbox_x1=int(x1 / result.scale_x), bbox_y1=int(y1 / result.scale_y),
                bbox_x2=int(x2 / result.scale_x), bbox_y2=int(y2 / result.scale_y),
                script=block.script,
                reading_order=block.reading_order,
                model_version=result.ocr.model_version,
            )
        )

    for outcome in result.fields:
        x1, y1, x2, y2 = outcome.bbox
        session.add(
            Extraction(
                document_id=document.id,
                page_number=1,
                field=outcome.field,
                raw_value=outcome.raw_value,
                normalized_value=outcome.normalized_value,
                ocr_confidence=outcome.ocr_confidence,
                extraction_confidence=outcome.extraction_confidence,
                layout_confidence=outcome.layout_confidence,
                validation_confidence=outcome.validation_confidence,
                final_confidence=outcome.final_confidence,
                confidence_breakdown=outcome.confidence_breakdown,
                bbox_x1=x1, bbox_y1=y1, bbox_x2=x2, bbox_y2=y2,
                status=outcome.status,
                model_version=settings.model_version_extractor,
                row_index=outcome.row_index,
            )
        )

    for finding in result.findings:
        session.add(
            ValidationFinding(
                document_id=document.id,
                rule=finding.rule,
                severity=finding.severity,
                message=finding.message,
                field=finding.field,
            )
        )

    document.quality_score = result.quality.overall_score
    document.quality_report = result.quality.to_dict()
    document.quality_recommendation = result.quality.recommended_action
    session.flush()

    document_service.transition(session, document, DocumentState.AI_EXTRACTED,
                                principal=principal)
    document_service.transition(session, document, DocumentState.NEEDS_VERIFICATION,
                                principal=principal)

    # §34 -- anomaly analysis runs after extraction, over the parcel's whole
    # history rather than this page alone. It needs a linked parcel; an
    # unlinked upload simply gets no flags rather than a fabricated one.
    anomaly_flags: list = []
    if document.parcel_id:
        parcel = session.get(Parcel, document.parcel_id)
        if parcel is not None:
            anomaly_flags = anomaly_service.analyse_parcel(
                session, parcel, document=document
            )

    task = session.execute(
        select(VerificationTask).where(VerificationTask.document_id == document.id)
    ).scalar_one_or_none()
    if task is None:
        task = VerificationTask(document_id=document.id)
        session.add(task)
    task.status = "PENDING"
    task.lowest_confidence = result.lowest_confidence()
    task.anomaly_count = (
        sum(1 for f in result.findings if f.severity != "info") + len(anomaly_flags)
    )
    # Lower confidence and more findings mean higher priority (1 = highest).
    task.priority = 1 if task.lowest_confidence < 0.6 else (2 if task.anomaly_count else 3)

    job.status = "SUCCEEDED"
    job.stage = "complete"
    job.progress = 100
    job.finished_at = datetime.now(UTC)

    audit_service.record(
        session, action=audit_service.PROCESSING_COMPLETED,
        entity_type="document", entity_id=document.external_id,
        actor_id=principal.id if principal else None,
        after_state={
            "fields": len(result.fields),
            "ocr_blocks": len(result.ocr.blocks),
            "needs_review": result.needs_review_count(),
            "findings": len(result.findings),
            "lowest_confidence": round(result.lowest_confidence(), 3),
            "anomaly_flags": [f.anomaly_type for f in anomaly_flags],
            "ocr_provider": result.ocr.provider,
            "model_version": result.ocr.model_version,
        },
    )
    session.commit()

    return {
        "status": "SUCCEEDED",
        "fields": len(result.fields),
        "needs_review": result.needs_review_count(),
        "findings": len(result.findings),
        "lowest_confidence": round(result.lowest_confidence(), 3),
        "missing_fields": result.missing_fields,
    }
