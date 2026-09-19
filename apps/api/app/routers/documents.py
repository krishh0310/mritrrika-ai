"""DEO document endpoints: upload, processing, status (§20-§24)."""

from __future__ import annotations

import asyncio
import json

from fastapi import (
    APIRouter,
    Body,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    UploadFile,
    status,
)
from mrittika_domain.state_machine import IllegalTransitionError
from sqlalchemy import select
from sqlalchemy.orm import Session
from sse_starlette.sse import EventSourceResponse

from app.auth.dependencies import require
from app.db import SessionLocal, get_session
from app.models import DocumentPage
from app.services import document_service, pipeline_service, storage_service
from app.services.auth_service import Principal, document_in_jurisdiction
from app.services.document_service import DocumentAccessDenied, DocumentNotFound
from app.services.duplicate_service import DuplicateDocument
from app.services.storage_service import UnsupportedFileType

router = APIRouter(prefix="/api/v1/documents", tags=["documents"])


def _summary(document) -> dict:
    return {
        "document_id": document.external_id,
        "document_type": document.document_type,
        "state": document.state,
        "quality_score": document.quality_score,
        "quality_recommendation": document.quality_recommendation,
        "quality_report": document.quality_report,
        "original_filename": document.original_filename,
        "size_bytes": document.size_bytes,
        "record_year": document.record_year,
        "declared_khasra": document.declared_khasra,
        "translated_from": document.translated_from,
        "handwriting_meta": document.handwriting_meta,
        "is_synthetic": document.is_synthetic,
    }


def _document_or_404(session: Session, document_id: str, principal: Principal):
    try:
        document = document_service.get_by_external_id(session, document_id)
    except DocumentNotFound:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such document") from None
    if not document_in_jurisdiction(session, principal, document):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such document")
    return document


@router.post("", status_code=status.HTTP_201_CREATED)
async def upload_document(
    file: UploadFile = File(...),
    document_type: str = Form(...),
    village_id: str | None = Form(None),
    record_year: str | None = Form(None),
    khasra_number: str | None = Form(None),
    khata_number: str | None = Form(None),
    parcel_id: str | None = Form(None),
    principal: Principal = Depends(require("document:upload")),
    session: Session = Depends(get_session),
) -> dict:
    """Store a scanned record and run the §22 quality gate immediately."""
    if not village_id and not parcel_id:
        # Without a location there is no jurisdiction to check against, and
        # the upload used to fail with "the selected location is outside your
        # jurisdiction" -- telling an operator who selected nothing that they
        # had selected the wrong thing.
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Choose the village this document belongs to, or link it to a parcel.",
        )
    data = await file.read()
    try:
        document = document_service.upload(
            session,
            principal=principal,
            data=data,
            filename=file.filename,
            declared_mime=file.content_type,
            document_type=document_type,
            village_external_id=village_id,
            record_year=record_year,
            declared_khasra=khasra_number,
            declared_khata=khata_number,
            parcel_external_id=parcel_id,
        )
    except DuplicateDocument as exc:
        # 409: nothing is wrong with the file, it is simply already here.
        # Naming the existing document is the point -- an operator who cannot
        # find it will upload a renamed copy instead.
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
            headers={"X-Existing-Document": exc.existing.external_id},
        ) from None
    except UnsupportedFileType as exc:
        # 415: the content is not an accepted document type. Determined by
        # sniffing the bytes, not by trusting the declared Content-Type.
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, detail=str(exc)
        ) from None
    except DocumentAccessDenied:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="The selected location is outside your jurisdiction",
        ) from None
    return _summary(document)


#: How many files one batch may carry. A DEO's tray is a few dozen pages; the
#: limit exists so a single request cannot hold an unbounded amount of image
#: data in memory while the quality gate runs over each page in turn.
MAX_BATCH_FILES = 40


@router.post("/batch", status_code=status.HTTP_207_MULTI_STATUS)
async def upload_batch(
    files: list[UploadFile] = File(...),
    document_type: str = Form(...),
    village_id: str | None = Form(None),
    record_year: str | None = Form(None),
    principal: Principal = Depends(require("document:upload")),
    session: Session = Depends(get_session),
) -> dict:
    """Upload a tray of scans in one request (§21).

    207, not 201, because partial success is the NORMAL outcome rather than an
    edge case. A DEO working through a day's scanning will routinely have a
    page that is a duplicate of one already filed, a page that fails the
    quality gate, and a page that is not an image at all -- and the other
    thirty-seven must still land. A batch that failed as a unit would make the
    operator re-upload everything to fix one file.

    Every file goes through exactly the same `upload()` path as a single
    upload: the same quality gate, the same duplicate check, the same audit
    event. There is no bulk shortcut, because a shortcut is where the
    per-document guarantees would quietly stop applying.
    """
    if not village_id:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Choose the village this batch belongs to.",
        )
    if len(files) > MAX_BATCH_FILES:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail=(
                f"{len(files)} files in one batch; the limit is "
                f"{MAX_BATCH_FILES}. Split the tray and upload again."
            ),
        )

    accepted: list[dict] = []
    rejected: list[dict] = []

    for upload_file in files:
        name = upload_file.filename or "(unnamed)"
        try:
            data = await upload_file.read()
            document = document_service.upload(
                session,
                principal=principal,
                data=data,
                filename=name,
                declared_mime=upload_file.content_type,
                document_type=document_type,
                village_external_id=village_id,
                record_year=record_year,
            )
        except DuplicateDocument as exc:
            rejected.append({
                "filename": name,
                "code": "DUPLICATE",
                "reason": str(exc),
                "existing_document": exc.existing.external_id,
            })
        except UnsupportedFileType as exc:
            rejected.append({
                "filename": name, "code": "UNSUPPORTED_TYPE", "reason": str(exc),
            })
        except DocumentAccessDenied:
            rejected.append({
                "filename": name,
                "code": "OUT_OF_JURISDICTION",
                "reason": "The selected location is outside your jurisdiction",
            })
        else:
            accepted.append(_summary(document))

    # Rejections are counted separately from quality failures: a file that was
    # never stored and a page that was stored and needs rescanning are
    # different problems with different remedies, and an operator needs to see
    # which is which.
    needs_rescan = sum(
        1 for d in accepted if d.get("quality_recommendation") == "REJECT_QUALITY"
    )
    return {
        "counts": {
            "submitted": len(files),
            "accepted": len(accepted),
            "rejected": len(rejected),
            "needs_rescan": needs_rescan,
        },
        "accepted": accepted,
        "rejected": rejected,
        "is_synthetic": True,
    }


@router.get("/{document_id}")
def get_document(
    document_id: str,
    principal: Principal = Depends(require("ocr:view")),
    session: Session = Depends(get_session),
) -> dict:
    document = _document_or_404(session, document_id, principal)
    return _summary(document)


@router.post("/{document_id}/process")
def start_processing(
    document_id: str,
    synchronous: bool = False,
    principal: Principal = Depends(require("document:start_processing")),
    session: Session = Depends(get_session),
) -> dict:
    """Queue the AI pipeline (§23).

    `synchronous=true` runs it inline. That exists for tests and for demo
    machines with no broker running -- it executes the SAME pipeline code, so
    it is not a mock path.
    """
    document = _document_or_404(session, document_id, principal)

    try:
        job = document_service.start_processing(session, document, principal=principal)
    except IllegalTransitionError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from None

    return _run_or_enqueue(session, document, job, principal, synchronous)


@router.post("/{document_id}/reprocess")
def reprocess_document(
    document_id: str,
    synchronous: bool = False,
    reason: str | None = Body(None, embed=True, max_length=500),
    principal: Principal = Depends(require("document:verify")),
    session: Session = Depends(get_session),
) -> dict:
    """Re-run extraction on a document awaiting verification (§29).

    For a verifier who sees results from an older extractor. Refused with 409
    once any field has been corrected or accepted -- re-running replaces every
    extraction, and human work must not disappear with them.
    """
    document = _document_or_404(session, document_id, principal)

    try:
        job = document_service.reprocess(
            session, document, principal=principal, reason=reason
        )
    except (IllegalTransitionError, document_service.ReprocessRefused) as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from None

    return _run_or_enqueue(session, document, job, principal, synchronous)


def _run_or_enqueue(session, document, job, principal, synchronous: bool) -> dict:
    if synchronous:
        outcome = pipeline_service.process_document(
            session, document, job, principal=principal
        )
        return {"job_id": job.id, "document_id": document.external_id,
                "mode": "synchronous", **outcome}

    try:
        from app.worker import process_document_task

        task = process_document_task.delay(document.external_id, job.id)
        job.celery_task_id = task.id
        session.commit()
        return {"job_id": job.id, "document_id": document.external_id,
                "mode": "queued", "task_id": task.id}
    except Exception as exc:
        # No broker reachable. Say so plainly rather than reporting a queued
        # job that will never run.
        job.status = "FAILED"
        job.error = f"could not enqueue: {exc}"
        session.commit()
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Processing queue is unavailable. Start Redis and the Celery "
            "worker, or call this endpoint with synchronous=true.",
        ) from None


@router.get("/{document_id}/status")
def processing_status(
    document_id: str,
    principal: Principal = Depends(require("ocr:view")),
    session: Session = Depends(get_session),
) -> dict:
    document = _document_or_404(session, document_id, principal)

    job = document_service.latest_job(session, document)
    return {
        "document_id": document.external_id,
        "state": document.state,
        "stage": job.stage if job else None,
        "progress": job.progress if job else 0,
        "status": job.status if job else "NOT_STARTED",
        "message": job.message if job else None,
        "error": job.error if job else None,
    }


@router.get("/{document_id}/stream")
async def processing_stream(
    document_id: str,
    principal: Principal = Depends(require("ocr:view")),
) -> EventSourceResponse:
    """Server-sent progress events (§24).

    Uses its own short-lived sessions rather than the request-scoped one: the
    stream outlives a single transaction, and holding one open for the duration
    would pin a connection for as long as the client watches.
    """

    async def events():
        last_payload = None
        for _ in range(600):  # ~5 minutes at 0.5s
            with SessionLocal() as session:
                try:
                    document = _document_or_404(session, document_id, principal)
                except HTTPException:
                    yield {"event": "error", "data": json.dumps({"error": "not found"})}
                    return
                job = document_service.latest_job(session, document)
                payload = {
                    "document_id": document_id,
                    "state": document.state,
                    "stage": job.stage if job else None,
                    "progress": job.progress if job else 0,
                    "status": job.status if job else "NOT_STARTED",
                    "message": job.message if job else None,
                }
            if payload != last_payload:
                yield {"event": "progress", "data": json.dumps(payload)}
                last_payload = payload
            if payload["status"] in ("SUCCEEDED", "FAILED"):
                return
            await asyncio.sleep(0.5)

    return EventSourceResponse(events())


@router.get("/{document_id}/file")
def document_file(
    document_id: str,
    page: int = Query(1, ge=1, le=100),
    principal: Principal = Depends(require("ocr:view")),
    session: Session = Depends(get_session),
) -> dict:
    """Short-lived presigned URL for one page image (§61).

    Always an image the browser can draw the bbox overlay on: for an image
    upload that is the original, for a PDF it is the rendered page.
    """
    document = _document_or_404(session, document_id, principal)
    pages = list(session.execute(
        select(DocumentPage).where(DocumentPage.document_id == document.id)
        .order_by(DocumentPage.page_number)
    ).scalars())
    target = next((p for p in pages if p.page_number == page), None)
    if target is None:
        if pages or page != 1:
            raise HTTPException(status.HTTP_404_NOT_FOUND, f"page {page} not found")
        url = storage_service.presigned_url(document.storage_key)
    else:
        url = document_service.page_url(document, target)
    return {
        "document_id": document.external_id,
        "page_number": page,
        "page_count": max(len(pages), 1),
        "url": url,
        "expires_in": 900,
    }
