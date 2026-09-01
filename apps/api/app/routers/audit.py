"""Audit trail endpoints (§41)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.auth.dependencies import require, require_any
from app.db import get_session
from app.services import audit_service
from app.services.auth_service import Principal, document_in_jurisdiction
from app.services.document_service import DocumentNotFound, get_by_external_id

router = APIRouter(prefix="/api/v1/audit", tags=["audit"])


@router.get("/documents/{document_id}")
def document_timeline(
    document_id: str,
    principal: Principal = Depends(require_any("audit:view_limited", "audit:view_full")),
    session: Session = Depends(get_session),
) -> dict:
    """Every recorded action on one document, oldest first (§32)."""
    try:
        document = get_by_external_id(session, document_id)
    except DocumentNotFound:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such document") from None
    if not document_in_jurisdiction(session, principal, document):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such document")

    events = audit_service.timeline_for(session, "document", document_id)
    return {
        "document_id": document_id,
        "events": [
            {
                "sequence": e.sequence,
                "timestamp": e.created_at.isoformat(),
                "action": e.action,
                "actor_role": e.actor_role,
                "before_state": e.before_state,
                "after_state": e.after_state,
                "reason": e.reason,
                "event_hash": e.event_hash,
                "previous_hash": e.previous_hash,
            }
            for e in events
        ],
    }


@router.get("/verify")
def verify_chain(
    principal: Principal = Depends(require("audit:view_full")),
    session: Session = Depends(get_session),
) -> dict:
    """Recompute the hash chain and report any break (§41).

    A hash chain, not a blockchain (§69): tamper-evident, single-writer, no
    consensus.
    """
    return audit_service.verify_chain(session)
