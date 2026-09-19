"""Anomaly flags (§34).

Internal to officers by design: §17 forbids exposing anomaly scores to
citizens, so every route here demands `anomaly:view`, which only the Verifier
and Tehsildar hold (§36).
"""

from __future__ import annotations

from fastapi import APIRouter, Body, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.dependencies import require
from app.db import get_session
from app.models import AnomalyFlag, Document, Parcel
from app.services import anomaly_service, audit_service
from app.services.auth_service import Principal, anomaly_jurisdiction_clause

router = APIRouter(prefix="/api/v1/anomalies", tags=["anomalies"])

#: An officer's verdict on a flag. RESOLVED means the underlying issue was
#: fixed; DISMISSED means the flag was wrong and must not be raised again.
OFFICER_VERDICTS = ("RESOLVED", "DISMISSED")


@router.get("")
def list_flags(
    flag_status: str = Query("OPEN", alias="status"),
    limit: int = Query(100, ge=1, le=500),
    document_id: str | None = Query(None, description="only flags on this document"),
    principal: Principal = Depends(require("anomaly:view")),
    session: Session = Depends(get_session),
) -> dict:
    # Document is joined as well as Parcel because a flag need not be about a
    # parcel: an upload-time flag (a page that resembles one already stored)
    # names only a document, and reporting it with a null parcel and nothing
    # else leaves an officer a finding they cannot act on.
    query = (
        select(AnomalyFlag, Parcel, Document)
        .outerjoin(Parcel, Parcel.id == AnomalyFlag.parcel_id)
        .outerjoin(Document, Document.id == AnomalyFlag.document_id)
        .where(
            anomaly_jurisdiction_clause(session, principal),
            AnomalyFlag.status == flag_status,
        )
        .order_by(AnomalyFlag.score.desc())
        .limit(limit)
    )
    if document_id is not None:
        query = query.where(Document.external_id == document_id)
    rows = session.execute(query).all()

    return {
        "count": len(rows),
        "flags": [
            {
                "flag_id": flag.id,
                "parcel_id": parcel.external_id if parcel else None,
                "document_id": document.external_id if document else None,
                "khasra_number": parcel.khasra_number if parcel else None,
                "anomaly_type": flag.anomaly_type,
                "score": flag.score,
                "explanation": flag.explanation,
                "evidence": flag.evidence,
                "status": flag.status,
                "model_version": flag.model_version,
            }
            for flag, parcel, document in rows
        ],
        "is_synthetic": True,
    }


@router.post("/{flag_id}/verdict")
def record_verdict(
    flag_id: str,
    verdict: str = Body(..., embed=True),
    note: str | None = Body(None, embed=True),
    principal: Principal = Depends(require("anomaly:view")),
    session: Session = Depends(get_session),
) -> dict:
    """Close a flag.

    A DISMISSED flag is never re-raised by a later analysis pass, so the
    decision is recorded in the audit chain rather than only in the row.
    """
    if verdict not in OFFICER_VERDICTS:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            f"verdict must be one of {', '.join(OFFICER_VERDICTS)}",
        )

    flag = session.execute(
        select(AnomalyFlag).where(
            AnomalyFlag.id == flag_id,
            anomaly_jurisdiction_clause(session, principal),
        )
    ).scalar_one_or_none()
    if flag is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such flag")

    before = {"status": flag.status}
    flag.status = verdict
    audit_service.record(
        session,
        action="anomaly.verdict",
        entity_type="anomaly_flag",
        entity_id=flag.id,
        actor_id=principal.id,
        actor_role=principal.primary_role,
        before_state=before,
        after_state={"status": flag.status, "anomaly_type": flag.anomaly_type},
        reason=note,
    )
    session.commit()
    return {"flag_id": flag.id, "status": flag.status}


@router.post("/reanalyse")
def reanalyse(
    principal: Principal = Depends(require("anomaly:view")),
    session: Session = Depends(get_session),
) -> dict:
    """Re-run the engine over the whole cadastre.

    Controlled reprocessing rather than automatic: §29 says not to rerun models
    on every edit, and refitting the forest is a corpus-wide operation.
    """
    return anomaly_service.analyse_all(session, principal)
