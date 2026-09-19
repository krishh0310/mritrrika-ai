"""Integration with state land-records systems -- LRMS / DILRMP (§14).

Two directions:

  * push  -- POST /sync delivers queued Records of Rights through the
             configured adapter (file drop or HTTP), and GET /sync reports
             what is pending, delivered and failing.
  * pull  -- GET /records/{document_id} returns one approved record in the
             delivery format, for a state system that prefers to fetch.

Tehsildar-only (`integration:sync`), and scoped to the caller's jurisdiction
like every other officer view: a district officer cannot push, or read, a
record from another district by naming it.
"""

from __future__ import annotations

from fastapi import APIRouter, Body, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.auth.dependencies import require
from app.config.settings import get_settings
from app.db import get_session
from app.integrations.lrms import build_adapter
from app.services import lrms_service
from app.services.auth_service import Principal, document_in_jurisdiction
from app.services.certificate_service import hash_of
from app.services.document_service import DocumentNotFound, get_by_external_id

router = APIRouter(prefix="/api/v1/integrations/lrms", tags=["integrations"])


@router.get("/sync")
def sync_status(
    principal: Principal = Depends(require("integration:sync")),
    session: Session = Depends(get_session),
) -> dict:
    """Outbox counts by status, and the most recent deliveries."""
    return lrms_service.status(session, principal, build_adapter(get_settings()))


@router.post("/sync")
def sync(
    limit: int = Body(100, embed=True, ge=1, le=1000),
    document_ids: list[str] | None = Body(None, embed=True, max_length=1000),
    principal: Principal = Depends(require("integration:sync")),
    session: Session = Depends(get_session),
) -> dict:
    """Queue any approved record not yet queued, then deliver what is due.

    Safe to call repeatedly: delivered records are not sent again, and a
    failed one is retried until it has failed MAX_ATTEMPTS times. Pass
    `document_ids` to push or retry particular records only.
    """
    return lrms_service.deliver(
        session, build_adapter(get_settings()), principal,
        limit=limit, document_ids=document_ids,
    )


@router.get("/records/{document_id}")
def record_of_rights(
    document_id: str,
    principal: Principal = Depends(require("integration:sync")),
    session: Session = Depends(get_session),
) -> dict:
    """One approved record exactly as it is delivered, with its digest."""
    try:
        document = get_by_external_id(session, document_id)
    except DocumentNotFound:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such document") from None
    if not document_in_jurisdiction(session, principal, document):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such document")
    try:
        payload = lrms_service.ror_payload(session, document)
    except lrms_service.LrmsError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from None
    return {"payload": payload, "payload_sha256": hash_of(payload)}
