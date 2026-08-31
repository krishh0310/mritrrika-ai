"""Verification and approval workflow (§28-§32).

Two rules enforced here:

  1. A correction never overwrites the model's prediction. `raw_value` and
     `normalized_value` are immutable once written; a human edit lands in
     `corrected_value` and a FieldCorrection row (§26, §30).
  2. Verifying and approving are separate acts by separate roles. The service
     checks the document's state, so a document cannot be approved without
     having been verified regardless of which endpoint is called.
"""

from __future__ import annotations

from datetime import UTC, datetime

from mrittika_domain import DocumentState
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    Document,
    DocumentPage,
    Extraction,
    FieldCorrection,
    LandRecord,
    OcrBlock,
    ValidationFinding,
    VerificationAction,
    VerificationTask,
)
from app.services import audit_service, document_service
from app.services.auth_service import Principal


class VerificationError(Exception):
    pass


def queue(session: Session, *, limit: int = 50, only_pending: bool = True) -> list[dict]:
    """The verifier's work queue, hardest first (§27)."""
    stmt = (
        select(VerificationTask, Document)
        .join(Document, Document.id == VerificationTask.document_id)
    )
    if only_pending:
        stmt = stmt.where(VerificationTask.status.in_(("PENDING", "IN_PROGRESS")))
    stmt = stmt.order_by(
        VerificationTask.priority,
        VerificationTask.lowest_confidence.nulls_last(),
    ).limit(limit)

    return [
        {
            "task_id": task.id,
            "document_id": document.external_id,
            "document_type": document.document_type,
            "state": document.state,
            "status": task.status,
            "priority": task.priority,
            "lowest_confidence": task.lowest_confidence,
            "anomaly_count": task.anomaly_count,
            "quality_score": document.quality_score,
        }
        for task, document in session.execute(stmt).all()
    ]


def workspace(session: Session, document: Document) -> dict:
    """Everything the split-screen verification UI needs (§28).

    Returns extractions WITH their bounding boxes and confidence breakdown, so
    clicking a field can zoom the document to its source region and explain why
    the field scored what it did (§68).
    """
    extractions = list(session.execute(
        select(Extraction).where(Extraction.document_id == document.id)
        .order_by(Extraction.field, Extraction.row_index)
    ).scalars())

    page = session.execute(
        select(DocumentPage).where(DocumentPage.document_id == document.id)
        .order_by(DocumentPage.page_number)
    ).scalars().first()

    blocks = []
    if page:
        blocks = list(session.execute(
            select(OcrBlock).where(OcrBlock.page_id == page.id)
            .order_by(OcrBlock.reading_order)
        ).scalars())

    findings = list(session.execute(
        select(ValidationFinding).where(ValidationFinding.document_id == document.id)
    ).scalars())

    return {
        "document_id": document.external_id,
        "state": document.state,
        "document_type": document.document_type,
        "quality": document.quality_report,
        "page": {
            "width": page.width if page else None,
            "height": page.height if page else None,
        },
        "fields": [
            {
                "extraction_id": e.id,
                "field": e.field,
                "raw_value": e.raw_value,
                "normalized_value": e.normalized_value,
                "corrected_value": e.corrected_value,
                "effective_value": e.effective_value,
                "ocr_confidence": e.ocr_confidence,
                "extraction_confidence": e.extraction_confidence,
                "final_confidence": e.final_confidence,
                "confidence_breakdown": e.confidence_breakdown,
                "bbox": [e.bbox_x1, e.bbox_y1, e.bbox_x2, e.bbox_y2],
                "status": e.status,
                "row_index": e.row_index,
                "model_version": e.model_version,
            }
            for e in extractions
        ],
        "ocr_blocks": [
            {
                "text": b.text,
                "confidence": b.confidence,
                "bbox": [b.bbox_x1, b.bbox_y1, b.bbox_x2, b.bbox_y2],
                "reading_order": b.reading_order,
            }
            for b in blocks
        ],
        "findings": [
            {"rule": f.rule, "severity": f.severity, "message": f.message,
             "field": f.field}
            for f in findings
        ],
        "is_synthetic": document.is_synthetic,
    }


def correct_field(
    session: Session,
    extraction_id: str,
    new_value: str,
    *,
    principal: Principal,
    reason: str | None = None,
) -> Extraction:
    """Record a human correction WITHOUT destroying the model's output (§26)."""
    extraction = session.get(Extraction, extraction_id)
    if extraction is None:
        raise VerificationError(f"no extraction {extraction_id}")

    document = session.get(Document, extraction.document_id)
    if document.state not in (
        DocumentState.NEEDS_VERIFICATION.value, DocumentState.UNDER_VERIFICATION.value
    ):
        raise VerificationError(
            f"document {document.external_id} is in state {document.state}; "
            f"corrections are only accepted during verification"
        )

    if document.state == DocumentState.NEEDS_VERIFICATION.value:
        document_service.transition(session, document,
                                    DocumentState.UNDER_VERIFICATION,
                                    principal=principal)
        task = session.execute(
            select(VerificationTask).where(VerificationTask.document_id == document.id)
        ).scalar_one_or_none()
        if task:
            task.status = "IN_PROGRESS"
            task.assigned_to_id = principal.id
            task.started_at = task.started_at or datetime.now(UTC)

    previous = extraction.effective_value
    extraction.corrected_value = new_value
    extraction.status = "VERIFIER_CORRECTED"

    session.add(
        FieldCorrection(
            extraction_id=extraction.id,
            document_id=document.id,
            field=extraction.field,
            model_prediction=extraction.normalized_value,
            corrected_value=new_value,
            confidence_at_correction=extraction.final_confidence,
            model_version=extraction.model_version,
            corrected_by_id=principal.id,
            reason=reason,
        )
    )
    audit_service.record(
        session, action=audit_service.EXTRACTION_CORRECTED,
        entity_type="document", entity_id=document.external_id,
        actor_id=principal.id, actor_role=principal.primary_role,
        before_state={"field": extraction.field, "value": previous},
        after_state={"field": extraction.field, "value": new_value},
        reason=reason,
    )
    session.commit()
    return extraction


def approve_field(session: Session, extraction_id: str, *,
                  principal: Principal) -> Extraction:
    """Accept the model's value as-is."""
    extraction = session.get(Extraction, extraction_id)
    if extraction is None:
        raise VerificationError(f"no extraction {extraction_id}")
    extraction.status = "VERIFIER_APPROVED"
    session.commit()
    return extraction


def submit_verification(session: Session, document: Document, *,
                        principal: Principal, note: str | None = None) -> Document:
    """Finish verification and hand the document to the tehsildar (§28).

    Refuses while any field still needs review -- submitting with unreviewed
    low-confidence fields would defeat the point of the queue.
    """
    outstanding = session.execute(
        select(Extraction).where(
            Extraction.document_id == document.id,
            Extraction.status == "NEEDS_REVIEW",
        )
    ).scalars().all()
    if outstanding:
        raise VerificationError(
            f"{len(outstanding)} field(s) still need review: "
            + ", ".join(sorted({e.field for e in outstanding}))
        )

    document_service.transition(session, document, DocumentState.VERIFIED,
                                principal=principal,
                                action=audit_service.VERIFICATION_SUBMITTED,
                                reason=note)
    document_service.transition(session, document, DocumentState.PENDING_APPROVAL,
                                principal=principal)

    task = session.execute(
        select(VerificationTask).where(VerificationTask.document_id == document.id)
    ).scalar_one_or_none()
    if task:
        task.status = "COMPLETED"
        task.completed_at = datetime.now(UTC)
        session.add(VerificationAction(task_id=task.id, actor_id=principal.id,
                                       action="SUBMIT", note=note))
    session.commit()
    return document


def approve(session: Session, document: Document, *, principal: Principal,
            reason: str | None = None) -> Document:
    """Tehsildar approval -- the point at which a record becomes citizen-visible."""
    from app.models import ApprovalAction

    document_service.transition(session, document, DocumentState.APPROVED,
                                principal=principal,
                                action=audit_service.APPROVED, reason=reason)
    session.add(ApprovalAction(document_id=document.id, actor_id=principal.id,
                               decision="APPROVED", reason=reason))

    # Publish the record so citizen search can see it (§17).
    if document.parcel_id:
        record = session.execute(
            select(LandRecord).where(LandRecord.parcel_id == document.parcel_id)
        ).scalars().first()
        if record:
            record.status = "APPROVED"

    session.commit()
    return document


def return_to_verifier(session: Session, document: Document, *,
                       principal: Principal, reason: str) -> Document:
    from app.models import ApprovalAction

    document_service.transition(session, document, DocumentState.UNDER_VERIFICATION,
                                principal=principal,
                                action=audit_service.RETURNED, reason=reason)
    session.add(ApprovalAction(document_id=document.id, actor_id=principal.id,
                               decision="RETURNED", reason=reason))
    task = session.execute(
        select(VerificationTask).where(VerificationTask.document_id == document.id)
    ).scalar_one_or_none()
    if task:
        task.status = "IN_PROGRESS"
    session.commit()
    return document


def reject(session: Session, document: Document, *, principal: Principal,
           reason: str) -> Document:
    from app.models import ApprovalAction

    document_service.transition(session, document, DocumentState.REJECTED,
                                principal=principal,
                                action=audit_service.REJECTED, reason=reason)
    session.add(ApprovalAction(document_id=document.id, actor_id=principal.id,
                               decision="REJECTED", reason=reason))
    session.commit()
    return document


def approval_queue(session: Session, limit: int = 50) -> list[dict]:
    stmt = (
        select(Document)
        .where(Document.state == DocumentState.PENDING_APPROVAL.value)
        .order_by(Document.updated_at)
        .limit(limit)
    )
    return [
        {
            "document_id": d.external_id,
            "document_type": d.document_type,
            "state": d.state,
            "quality_score": d.quality_score,
        }
        for d in session.execute(stmt).scalars()
    ]
