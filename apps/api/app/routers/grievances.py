"""Citizen grievance endpoints (§19, §55).

Two audiences on one resource: a citizen who may file and track their own, and
an officer who reviews the queue. They are separated by permission, not by a
query parameter -- `/me` never consults a caller-supplied identity, and the
review routes are unreachable without `grievance:review*`.
"""

from __future__ import annotations

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
from mrittika_domain import GrievanceStatus
from sqlalchemy.orm import Session

from app.auth.dependencies import require, require_any
from app.db import get_session
from app.services import grievance_service, storage_service
from app.services.auth_service import Principal, grievance_in_jurisdiction
from app.services.citizen_service import ParcelAccessDenied
from app.services.grievance_service import GrievanceError, GrievanceNotFound
from app.services.storage_service import UnsupportedFileType

router = APIRouter(prefix="/api/v1/grievances", tags=["grievances"])


@router.get("/issue-types")
def issue_types(
    principal: Principal = Depends(require("grievance:create")),
) -> dict:
    """The closed vocabulary the filing form offers (§19)."""
    return {"issue_types": list(grievance_service.ISSUE_TYPES)}


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_grievance(
    issue_type: str = Form(...),
    description: str = Form(..., min_length=1, max_length=4000),
    parcel_id: str | None = Form(None),
    supporting_document: UploadFile | None = File(None),
    principal: Principal = Depends(require("grievance:create")),
    session: Session = Depends(get_session),
) -> dict:
    attachment = await supporting_document.read() if supporting_document else None

    try:
        grievance = grievance_service.create(
            session,
            principal,
            issue_type=issue_type,
            description=description,
            parcel_external_id=parcel_id,
            attachment=attachment or None,
            attachment_mime=(
                supporting_document.content_type if supporting_document else None
            ),
        )
    except ParcelAccessDenied:
        # Same response as an unknown parcel, deliberately (§62).
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "You do not have access to this parcel",
        ) from None
    except UnsupportedFileType as exc:
        raise HTTPException(
            status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, str(exc)
        ) from None
    except GrievanceError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from None

    return grievance_service.detail(session, grievance)


@router.get("/me")
def my_grievances(
    principal: Principal = Depends(require("grievance:view_own")),
    session: Session = Depends(get_session),
) -> dict:
    """The caller's own grievances. Takes no identity parameter by design."""
    rows = grievance_service.for_citizen(session, principal)
    return {
        "count": len(rows),
        "grievances": rows,
        "counts_by_status": grievance_service.counts_by_status(session, principal),
        "is_synthetic": True,
    }


@router.get("")
def review_queue(
    grievance_status: str | None = Query(None, alias="status"),
    limit: int = Query(100, ge=1, le=500),
    principal: Principal = Depends(
        require_any("grievance:review", "grievance:review_limited")
    ),
    session: Session = Depends(get_session),
) -> dict:
    """Officer review queue (§31)."""
    if grievance_status and grievance_status not in set(GrievanceStatus):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            f"unknown status {grievance_status!r}",
        )
    rows = grievance_service.review_queue(
        session, principal=principal, status=grievance_status, limit=limit
    )
    return {
        "count": len(rows),
        "grievances": rows,
        "counts_by_status": grievance_service.counts_by_status(session, principal),
        "is_synthetic": True,
    }


def _visible_or_404(session: Session, grievance_id: str, principal: Principal):
    """Fetch a grievance the caller is entitled to read.

    A citizen sees only their own; a reviewer sees any. Both failure modes
    return 404 so a citizen cannot probe which grievance ids exist.
    """
    try:
        grievance = grievance_service.get(session, grievance_id)
    except GrievanceNotFound:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such grievance") from None

    is_reviewer = principal.has("grievance:review") or principal.has(
        "grievance:review_limited"
    )
    if not is_reviewer and grievance.raised_by_id != principal.user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such grievance")
    if is_reviewer and not grievance_in_jurisdiction(session, principal, grievance):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such grievance")
    return grievance


@router.get("/{grievance_id}")
def grievance_detail(
    grievance_id: str,
    principal: Principal = Depends(
        require_any("grievance:view_own", "grievance:review", "grievance:review_limited")
    ),
    session: Session = Depends(get_session),
) -> dict:
    return grievance_service.detail(
        session, _visible_or_404(session, grievance_id, principal)
    )


@router.get("/{grievance_id}/attachment")
def grievance_attachment(
    grievance_id: str,
    principal: Principal = Depends(
        require_any("grievance:view_own", "grievance:review", "grievance:review_limited")
    ),
    session: Session = Depends(get_session),
) -> dict:
    """Short-lived presigned URL for the supporting document (§61, §63)."""
    grievance = _visible_or_404(session, grievance_id, principal)
    if not grievance.supporting_storage_key:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, "This grievance has no attachment"
        )
    return {
        "grievance_id": grievance.external_id,
        "url": storage_service.presigned_url(grievance.supporting_storage_key),
        "expires_in": 900,
    }


@router.post("/{grievance_id}/status")
def set_status(
    grievance_id: str,
    new_status: str = Body(..., embed=True, alias="status"),
    note: str | None = Body(None, embed=True),
    principal: Principal = Depends(require("grievance:review")),
    session: Session = Depends(get_session),
) -> dict:
    """Advance a grievance. Only the full reviewer role may close one (§36)."""
    try:
        grievance = _visible_or_404(session, grievance_id, principal)
    except GrievanceNotFound:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such grievance") from None

    try:
        grievance = grievance_service.update_status(
            session, grievance, new_status, principal=principal, note=note
        )
    except GrievanceError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from None

    return grievance_service.detail(session, grievance)
