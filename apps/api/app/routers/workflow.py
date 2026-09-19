"""Verifier and Tehsildar endpoints (§27-§32)."""

from __future__ import annotations

from fastapi import APIRouter, Body, Depends, HTTPException, status
from mrittika_domain.state_machine import IllegalTransitionError
from sqlalchemy.orm import Session

from app.auth.dependencies import require
from app.db import get_session
from app.services import approval_service, verification_service
from app.services.auth_service import Principal, document_in_jurisdiction
from app.services.document_service import DocumentNotFound, get_by_external_id
from app.services.verification_service import VerificationError

verification_router = APIRouter(prefix="/api/v1/verifications", tags=["verification"])
approval_router = APIRouter(prefix="/api/v1/approvals", tags=["approval"])


def _document_or_404(session: Session, document_id: str, principal: Principal):
    try:
        document = get_by_external_id(session, document_id)
    except DocumentNotFound:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such document") from None
    if not document_in_jurisdiction(session, principal, document):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such document")
    return document


@verification_router.get("")
def list_queue(
    principal: Principal = Depends(require("document:verify")),
    session: Session = Depends(get_session),
) -> dict:
    tasks = verification_service.queue(session, principal)
    return {"count": len(tasks), "tasks": tasks}


@verification_router.get("/{document_id}/workspace")
def workspace(
    document_id: str,
    principal: Principal = Depends(require("extraction:correct")),
    session: Session = Depends(get_session),
) -> dict:
    """Everything the split-screen workspace renders (§28)."""
    return verification_service.workspace(
        session, _document_or_404(session, document_id, principal)
    )


@verification_router.patch("/extractions/{extraction_id}")
def correct_extraction(
    extraction_id: str,
    value: str = Body(..., embed=True),
    reason: str | None = Body(None, embed=True),
    principal: Principal = Depends(require("extraction:correct")),
    session: Session = Depends(get_session),
) -> dict:
    try:
        extraction = verification_service.correct_field(
            session, extraction_id, value, principal=principal, reason=reason
        )
    except VerificationError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from None
    return {
        "extraction_id": extraction.id,
        "field": extraction.field,
        # Both retained -- a correction never erases what the model read (§26).
        "raw_value": extraction.raw_value,
        "normalized_value": extraction.normalized_value,
        "corrected_value": extraction.corrected_value,
        "status": extraction.status,
    }


@verification_router.post("/extractions/{extraction_id}/approve")
def approve_extraction(
    extraction_id: str,
    principal: Principal = Depends(require("extraction:correct")),
    session: Session = Depends(get_session),
) -> dict:
    try:
        extraction = verification_service.approve_field(
            session, extraction_id, principal=principal
        )
    except VerificationError as exc:
        # Absent (or out of jurisdiction) is 404; present but past
        # verification is a conflict with the document's state.
        missing = str(exc).startswith("no extraction")
        raise HTTPException(
            status.HTTP_404_NOT_FOUND if missing else status.HTTP_409_CONFLICT, str(exc)
        ) from None
    return {"extraction_id": extraction.id, "status": extraction.status}


@verification_router.post("/{document_id}/submit")
def submit(
    document_id: str,
    note: str | None = Body(None, embed=True),
    principal: Principal = Depends(require("document:verify")),
    session: Session = Depends(get_session),
) -> dict:
    document = _document_or_404(session, document_id, principal)
    try:
        verification_service.submit_verification(
            session, document, principal=principal, note=note
        )
    except (VerificationError, IllegalTransitionError) as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from None
    return {"document_id": document.external_id, "state": document.state}


@approval_router.get("")
def list_approvals(
    principal: Principal = Depends(require("document:approve")),
    session: Session = Depends(get_session),
) -> dict:
    queue = verification_service.approval_queue(session, principal)
    return {"count": len(queue), "documents": queue}


@approval_router.get("/{document_id}/workspace")
def approval_workspace(
    document_id: str,
    principal: Principal = Depends(require("document:approve")),
    session: Session = Depends(get_session),
) -> dict:
    """The full §32 review: record, corrections, history, anomalies, audit."""
    return approval_service.workspace(
        session, _document_or_404(session, document_id, principal)
    )


@approval_router.post("/{document_id}/approve")
def approve_document(
    document_id: str,
    reason: str | None = Body(None, embed=True),
    principal: Principal = Depends(require("document:approve")),
    session: Session = Depends(get_session),
) -> dict:
    document = _document_or_404(session, document_id, principal)
    try:
        verification_service.approve(session, document, principal=principal,
                                     reason=reason)
    except IllegalTransitionError as exc:
        # This is the guard that makes UPLOADED -> APPROVED impossible (§37).
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from None
    return {"document_id": document.external_id, "state": document.state}


@approval_router.post("/{document_id}/return")
def return_document(
    document_id: str,
    reason: str = Body(..., embed=True),
    principal: Principal = Depends(require("document:return")),
    session: Session = Depends(get_session),
) -> dict:
    document = _document_or_404(session, document_id, principal)
    try:
        verification_service.return_to_verifier(session, document,
                                                principal=principal, reason=reason)
    except IllegalTransitionError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from None
    return {"document_id": document.external_id, "state": document.state}


@approval_router.post("/{document_id}/reject")
def reject_document(
    document_id: str,
    reason: str = Body(..., embed=True),
    principal: Principal = Depends(require("document:reject")),
    session: Session = Depends(get_session),
) -> dict:
    document = _document_or_404(session, document_id, principal)
    try:
        verification_service.reject(session, document, principal=principal,
                                    reason=reason)
    except IllegalTransitionError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from None
    return {"document_id": document.external_id, "state": document.state}
