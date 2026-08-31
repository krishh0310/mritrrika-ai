"""Everything the tehsildar's approval workspace renders (§32).

The verifier's workspace answers "is this page transcribed correctly?"; this
one answers "should this become the record of rights?". That is a different
question, so it needs the parcel's history, the corrections a verifier made,
the anomaly flags, and the audit trail -- assembled here rather than left to
the client to stitch together from six calls.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Document, FieldCorrection, Mutation, Parcel, User
from app.repositories import ownership_repository
from app.services import (
    anomaly_service,
    audit_service,
    dashboard_service,
    storage_service,
    verification_service,
)


def _corrections(session: Session, document: Document) -> list[dict]:
    """What the verifier changed, and away from what (§30, §32)."""
    rows = session.execute(
        select(FieldCorrection, User)
        .outerjoin(User, User.id == FieldCorrection.corrected_by_id)
        .where(FieldCorrection.document_id == document.id)
        .order_by(FieldCorrection.created_at)
    ).all()
    return [
        {
            "field": correction.field,
            "model_prediction": correction.model_prediction,
            "corrected_value": correction.corrected_value,
            "confidence_at_correction": correction.confidence_at_correction,
            "model_version": correction.model_version,
            "reason": correction.reason,
            "corrected_by": user.full_name if user else None,
            "is_retraining_candidate": correction.is_retraining_candidate,
            "at": correction.created_at.isoformat() if correction.created_at else None,
        }
        for correction, user in rows
    ]


def _mutations(session: Session, parcel: Parcel) -> list[dict]:
    """The parcel's chronological mutation timeline (§40)."""
    rows = session.execute(
        select(Mutation)
        .where(Mutation.parcel_id == parcel.id)
        .order_by(Mutation.effective_date)
    ).scalars().all()
    return [
        {
            "mutation_id": m.external_id,
            "mutation_number": m.mutation_number,
            "mutation_type": m.mutation_type,
            "effective_date": m.effective_date.isoformat(),
            "registration_date": (
                m.registration_date.isoformat() if m.registration_date else None
            ),
            "status": m.status,
            "notes": m.notes,
        }
        for m in rows
    ]


def workspace(session: Session, document: Document) -> dict:
    """Compose the full approval view for one document.

    Reuses the verifier's workspace payload verbatim for the shared half, so
    the two screens can never drift on what a field's confidence or bbox is.
    """
    payload = verification_service.workspace(session, document)
    payload["corrections"] = _corrections(session, document)
    payload.update(dashboard_service.approval_queue_detail(session, document))

    parcel = session.get(Parcel, document.parcel_id) if document.parcel_id else None
    if parcel is not None:
        payload["parcel"] = {
            "parcel_id": parcel.external_id,
            "khasra_number": parcel.khasra_number,
            "khata_number": parcel.khata_number,
            "area_value": parcel.area_value,
            "area_unit": parcel.area_unit,
            "land_class": parcel.land_class,
            "village": parcel.village.name if parcel.village else None,
        }
        payload["ownership_history"] = ownership_repository.ownership_history(
            session, parcel.id
        )
        payload["mutations"] = _mutations(session, parcel)
        payload["anomalies"] = anomaly_service.flags_for_parcel(session, parcel)
    else:
        # Say so rather than returning empty lists that read as "no history".
        payload["parcel"] = None
        payload["ownership_history"] = []
        payload["mutations"] = []
        payload["unlinked_reason"] = (
            "This document is not linked to a parcel, so ownership history and "
            "spatial context are unavailable."
        )

    payload["audit_timeline"] = [
        {
            "sequence": event.sequence,
            "action": event.action,
            "actor_role": event.actor_role,
            "reason": event.reason,
            "at": event.created_at.isoformat() if event.created_at else None,
        }
        for event in audit_service.timeline_for(
            session, "document", document.external_id
        )
    ]

    try:
        payload["original_url"] = storage_service.presigned_url(document.storage_key)
    except Exception:  # pragma: no cover - depends on MinIO being reachable
        # A missing scan must not take down the whole workspace; the officer
        # can still review the extraction and the history.
        payload["original_url"] = None

    return payload


__all__ = ["workspace"]
