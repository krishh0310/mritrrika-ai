"""DEO document endpoints: upload, processing, status (§20-§24)."""

from __future__ import annotations

import asyncio
import json

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    UploadFile,
    status,
)
from mrittika_domain.state_machine import IllegalTransitionError
from sqlalchemy.orm import Session
from sse_starlette.sse import EventSourceResponse

from app.auth.dependencies import require
from app.db import SessionLocal, get_session
from app.services import document_service, pipeline_service, storage_service
from app.services.auth_service import Principal, document_in_jurisdiction
from app.services.document_service import DocumentAccessDenied, DocumentNotFound
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
    principal: Principal = Depends(require("ocr:view")),
    session: Session = Depends(get_session),
) -> dict:
    """Short-lived presigned URL for the original scan (§61)."""
    document = _document_or_404(session, document_id, principal)
    return {
        "document_id": document.external_id,
        "url": storage_service.presigned_url(document.storage_key),
        "expires_in": 900,
    }
