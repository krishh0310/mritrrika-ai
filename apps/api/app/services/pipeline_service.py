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


def _pages_for(session: Session, document: Document) -> list[DocumentPage]:
    pages = list(session.execute(
        select(DocumentPage).where(DocumentPage.document_id == document.id)
        .order_by(DocumentPage.page_number)
    ).scalars())
    if not pages:
        # Documents uploaded before page rows existed: the original is page 1.
        page = DocumentPage(document_id=document.id, page_number=1,
                            storage_key=document.storage_key)
        session.add(page)
        session.flush()
        pages = [page]
    return pages


def process_document(
    session: Session,
    document: Document,
    job: ProcessingJob,
    *,
    principal: Principal | None = None,
) -> dict:
    """Execute the pipeline over every page of one document and persist it all.

    Each page is OCR'd on its own image, and every OCR block and extraction
    keeps the page it came from, so the Verifier can open the right page when
    a field is clicked. A single-image upload is simply a one-page document.

    On failure the document moves to RESCAN_REQUIRED with the reason recorded
    -- never to a fabricated 'success' with empty results (§82).
    """
    from extraction_pipeline import run as run_pipeline
    from ocr.provider import OcrUnavailable

    settings = get_settings()
    pages = _pages_for(session, document)
    total = len(pages)

    job.status = "RUNNING"
    job.started_at = datetime.now(UTC)
    session.commit()

    results: list[tuple[DocumentPage, object]] = []
    current = pages[0]
    try:
        for index, page in enumerate(pages):
            current = page

            def progress(stage: str, percent: int, message: str, index=index) -> None:
                # Spread each page over its slice of the bar. "complete" is only
                # reported for the whole document, or the job would read as
                # SUCCEEDED while later pages were still running.
                overall = (index * 100 + percent) // total
                if total > 1:
                    message = f"Page {index + 1} of {total}: {message}"
                    if stage == "complete":
                        stage = "confidence" if index < total - 1 else stage
                _update_job(session, job, stage, overall, message)

            results.append((page, run_pipeline(
                document_service.page_bytes(document, page),
                get_engine(),
                declared_khasra=document.declared_khasra,
                progress=progress,
            )))
    except (OcrUnavailable, ValueError) as exc:
        reason = str(exc) if total == 1 else f"page {current.page_number} of {total}: {exc}"
        job.status = "FAILED"
        job.error = reason
        job.finished_at = datetime.now(UTC)
        # RESCAN_REQUIRED, not NEEDS_VERIFICATION. §37 forbids
        # PROCESSING -> NEEDS_VERIFICATION (verification presupposes an
        # extraction to verify), and attempting it made the failure handler
        # itself raise -- turning a recoverable OCR failure into a 500.
        # A page with no recognised text needs a better scan, not a reviewer.
        document_service.transition(
            session, document, DocumentState.RESCAN_REQUIRED,
            principal=principal, action=audit_service.PROCESSING_FAILED,
            reason=f"AI pipeline could not process this document: {reason}",
        )
        audit_service.record(
            session, action=audit_service.PROCESSING_FAILED,
            entity_type="document", entity_id=document.external_id,
            actor_id=principal.id if principal else None,
            after_state={"error": reason},
        )
        session.commit()
        logger.warning("pipeline failed for %s: %s", document.external_id, reason)
        return {"status": "FAILED", "error": reason}

    # Replace prior results so re-processing is idempotent rather than additive.
    page_ids = [page.id for page in pages]
    for model, clause in (
        (OcrBlock, OcrBlock.page_id.in_(page_ids)),
        (Extraction, Extraction.document_id == document.id),
        (ValidationFinding, ValidationFinding.document_id == document.id),
    ):
        for existing in session.execute(select(model).where(clause)).scalars():
            session.delete(existing)
    session.flush()

    for page, result in results:
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
                    page_number=page.page_number,
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
                    message=finding.message if total == 1
                    else f"Page {page.page_number}: {finding.message}",
                    field=finding.field,
                )
            )

    # The document is only as readable as its weakest page (matches the gate).
    weakest = min((result for _, result in results),
                  key=lambda result: result.quality.overall_score)
    document.quality_score = weakest.quality.overall_score
    document.quality_report = weakest.quality.to_dict() | (
        {"page_count": total} if total > 1 else {}
    )
    document.quality_recommendation = weakest.quality.recommended_action
    session.flush()

    document_service.transition(session, document, DocumentState.AI_EXTRACTED,
                                principal=principal)
    document_service.transition(session, document, DocumentState.NEEDS_VERIFICATION,
                                principal=principal)

    # §34 -- anomaly analysis runs after extraction, over the parcel's whole
    # history rather than this document alone. It needs a linked parcel; an
    # unlinked upload simply gets no flags rather than a fabricated one.
    anomaly_flags: list = []
    if document.parcel_id:
        parcel = session.get(Parcel, document.parcel_id)
        if parcel is not None:
            anomaly_flags = anomaly_service.analyse_parcel(
                session, parcel, document=document
            )

    all_results = [result for _, result in results]
    field_count = sum(len(r.fields) for r in all_results)
    needs_review = sum(r.needs_review_count() for r in all_results)
    finding_count = sum(len(r.findings) for r in all_results)
    lowest = min((r.lowest_confidence() for r in all_results if r.fields), default=0.0)
    # A field is missing only if NO page supplied it.
    missing = sorted(set.intersection(*(set(r.missing_fields) for r in all_results)))

    task = session.execute(
        select(VerificationTask).where(VerificationTask.document_id == document.id)
    ).scalar_one_or_none()
    if task is None:
        task = VerificationTask(document_id=document.id)
        session.add(task)
    task.status = "PENDING"
    task.lowest_confidence = lowest
    task.anomaly_count = (
        sum(1 for r in all_results for f in r.findings if f.severity != "info")
        + len(anomaly_flags)
    )
    # Lower confidence and more findings mean higher priority (1 = highest).
    task.priority = 1 if task.lowest_confidence < 0.6 else (2 if task.anomaly_count else 3)

    job.status = "SUCCEEDED"
    job.stage = "complete"
    job.progress = 100
    job.message = "Processing complete"
    job.finished_at = datetime.now(UTC)

    first = all_results[0]
    audit_service.record(
        session, action=audit_service.PROCESSING_COMPLETED,
        entity_type="document", entity_id=document.external_id,
        actor_id=principal.id if principal else None,
        after_state={
            "pages": total,
            "fields": field_count,
            "ocr_blocks": sum(len(r.ocr.blocks) for r in all_results),
            "needs_review": needs_review,
            "findings": finding_count,
            "lowest_confidence": round(lowest, 3),
            "anomaly_flags": [f.anomaly_type for f in anomaly_flags],
            "ocr_provider": first.ocr.provider,
            "model_version": first.ocr.model_version,
        },
    )
    session.commit()

    return {
        "status": "SUCCEEDED",
        "pages": total,
        "fields": field_count,
        "needs_review": needs_review,
        "findings": finding_count,
        "lowest_confidence": round(lowest, 3),
        "missing_fields": missing,
    }
