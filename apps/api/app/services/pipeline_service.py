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
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

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
            detection_model=settings.ocr_detection_model,
        )
    return _engine


_detector = None


def get_layout_detector():
    """The YOLO layout detector when USE_YOLO is on, else None. Cached per
    process like the OCR engine; an unavailable detector detects nothing."""
    global _detector
    if not get_settings().use_yolo:
        return None
    if _detector is None:
        from layout import build_default_detector

        _detector = build_default_detector()
    return _detector


_field_models: dict[str, object] = {}


def active_extractor(session: Session) -> tuple[object | None, str]:
    """The promoted field model (None = rules) and the version to record.

    Read per document from model_registry, so a nightly promotion takes effect
    without a restart; the checkpoint itself is loaded once per process.
    """
    from app.models import ModelRegistryEntry

    row = session.execute(
        select(ModelRegistryEntry).where(ModelRegistryEntry.is_active.is_(True))
    ).scalar_one_or_none()
    if row is None or row.model_path == "rules":
        return None, get_settings().model_version_extractor
    if row.model_path not in _field_models:
        from extraction.model_extractor import ModelExtractor

        _field_models[row.model_path] = ModelExtractor(row.model_path)
    return _field_models[row.model_path], f"extractor-trained-{row.id[:8]}"


def handwriting_meta_for(results, quality: dict | None) -> dict | None:
    """Routing metadata across every page. OCR boxes are in each page's
    prepared frame and field boxes in original page coordinates, so blocks are
    mapped back first; otherwise nothing would overlap correctly."""
    from ocr.handwriting import routing_meta

    return routing_meta(
        [(result.original_bbox(block.bbox), block.is_handwritten)
         for result in results for block in result.ocr.blocks],
        [(outcome.field, outcome.bbox) for result in results for outcome in result.fields],
        quality,
    )


def _update_job(session: Session, job: ProcessingJob, stage: str, progress: int,
                message: str) -> None:
    job.stage = stage
    job.progress = progress
    job.message = message
    # Never SUCCEEDED here. The pipeline reports "complete" when OCR and
    # extraction finish, BEFORE results are saved and the document moves on;
    # marking success at that point left documents in PROCESSING whose jobs
    # claimed to have succeeded when the save then failed. Only the end of
    # process_document, after the commit, may say so.
    job.status = "RUNNING"
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

    pages = _pages_for(session, document)
    total = len(pages)

    job.status = "RUNNING"
    job.started_at = datetime.now(UTC)
    session.commit()

    field_model, extractor_version = active_extractor(session)
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
                layout_detector=get_layout_detector(),
                field_model=field_model,
            )))
    except (OcrUnavailable, ValueError) as exc:
        detail = str(exc) if total == 1 else f"page {current.page_number} of {total}: {exc}"
        # "Rescan required" tells an operator to go and fetch a better scan.
        # That is the right answer for an unreadable page and the wrong one for
        # an OCR provider that is switched off or missing its key -- rescanning
        # a perfect page changes nothing. Same state (§37 offers no other way
        # out of PROCESSING), but say which it is.
        misconfigured = isinstance(exc, OcrUnavailable) and any(
            hint in str(exc).lower()
            for hint in ("not configured", "not installed", "api key", "could not initialise")
        )
        reason = (
            f"OCR is unavailable, so this page was never read: {detail}. "
            "This is a configuration problem, not a problem with the scan."
            if misconfigured else detail
        )
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
            reason=(reason if misconfigured
                    else f"AI pipeline could not process this document: {reason}"),
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
            x1, y1, x2, y2 = result.original_bbox(block.bbox)
            session.add(
                OcrBlock(
                    page_id=page.id,
                    text=block.text,
                    confidence=block.confidence,
                    bbox_x1=x1, bbox_y1=y1,
                    bbox_x2=x2, bbox_y2=y2,
                    script=block.script,
                    reading_order=block.reading_order,
                    is_handwritten=block.is_handwritten,
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
                    model_version=extractor_version,
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
    document.handwriting_meta = handwriting_meta_for(
        [result for _, result in results], weakest.quality.to_dict()
    )
    document.translated_from = next(
        (result.translated_from for _, result in results if result.translated_from), None
    )
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


#: A live job reports progress several times a page. One silent for this long
#: has no worker behind it. Matches the worker's hard task time limit, so a
#: job still legitimately running can never be mistaken for an orphan.
STALE_AFTER = timedelta(minutes=10)


def recover_stale_jobs(
    session: Session,
    *,
    enqueue: Callable[[str, str], str | None],
    stale_after: timedelta = STALE_AFTER,
    now: datetime | None = None,
    document_ids: list[str] | None = None,
) -> list[str]:
    """Re-dispatch documents whose processing job died with its worker.

    A worker killed mid-run (a crash, a reboot, a stopped process) leaves its
    job RUNNING and its document in PROCESSING forever -- nothing else in the
    §37 graph moves a document out of PROCESSING, so it never reaches a
    verifier. The dead job is closed as FAILED with the reason, a new job is
    queued, and the document stays in PROCESSING throughout: it was never
    processed, so no state is skipped or repeated.

    `enqueue(document_external_id, job_id)` sends the work and returns a task
    id; it is injected so this is testable without a broker.

    `document_ids` (external ids) limits the sweep. Without it every stuck
    document in the database is re-dispatched -- which is what the worker wants
    at startup, and exactly what a test must never do to a shared database.
    """
    cutoff = (now or datetime.now(UTC)) - stale_after
    query = select(Document).where(Document.state == DocumentState.PROCESSING.value)
    if document_ids is not None:
        query = query.where(Document.external_id.in_(document_ids))
    stuck = session.execute(query).scalars().all()

    recovered: list[str] = []
    for document in stuck:
        latest = session.execute(
            select(ProcessingJob).where(ProcessingJob.document_id == document.id)
            .order_by(ProcessingJob.created_at.desc()).limit(1)
        ).scalar_one_or_none()
        if latest is not None and latest.status in ("QUEUED", "RUNNING") and (
            latest.updated_at is not None and latest.updated_at > cutoff
        ):
            continue  # still alive

        if latest is not None and latest.status in ("QUEUED", "RUNNING"):
            latest.status = "FAILED"
            latest.error = (
                f"orphaned: no progress since {latest.updated_at:%Y-%m-%d %H:%M %Z} "
                "-- the worker running it stopped"
            )
            latest.finished_at = datetime.now(UTC)

        job = ProcessingJob(document_id=document.id, stage="upload", progress=0,
                            status="QUEUED", started_at=datetime.now(UTC))
        session.add(job)
        session.flush()
        audit_service.record(
            session, action=audit_service.PROCESSING_REQUEUED,
            entity_type="document", entity_id=document.external_id,
            after_state={"previous_job": latest.id if latest else None, "job": job.id},
        )
        session.commit()

        try:
            job.celery_task_id = enqueue(document.external_id, job.id)
        except Exception as exc:  # broker gone again; leave it for next time
            job.status = "FAILED"
            job.error = f"could not enqueue: {exc}"
        session.commit()
        recovered.append(document.external_id)
    return recovered
