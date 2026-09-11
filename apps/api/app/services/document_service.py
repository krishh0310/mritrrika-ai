"""Document lifecycle: upload, state transitions, quality gate (§21-§23, §37).

Every state change goes through `transition`, which validates the move against
the §37 graph and writes an audit event in the SAME transaction. There is no
other sanctioned way to change `Document.state` -- a service that assigns the
column directly bypasses both the graph and the audit trail.
"""

from __future__ import annotations

from datetime import UTC, datetime

from mrittika_domain import DocumentState, assert_transition
from mrittika_domain.state_machine import IllegalTransitionError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Document, DocumentPage, Location, Parcel, ProcessingJob
from app.services import audit_service, storage_service
from app.services.auth_service import Principal, location_in_jurisdiction
from app.services.storage_service import UnsupportedFileType


class DocumentNotFound(Exception):
    pass


class DocumentAccessDenied(Exception):
    pass


def _snapshot(document: Document) -> dict:
    """The slice of a document worth recording in the audit trail."""
    return {
        "state": document.state,
        "document_type": document.document_type,
        "quality_recommendation": document.quality_recommendation,
        "parcel_id": document.parcel_id,
    }


def transition(
    session: Session,
    document: Document,
    target: DocumentState,
    *,
    principal: Principal | None = None,
    action: str | None = None,
    reason: str | None = None,
) -> Document:
    """Move a document to `target`, or refuse.

    Raises IllegalTransitionError for any move the §37 graph forbids, including
    the one the spec singles out: UPLOADED -> APPROVED.
    """
    current = DocumentState(document.state)
    assert_transition(current, target)

    before = _snapshot(document)
    document.state = target.value
    session.flush()

    audit_service.record(
        session,
        action=action or audit_service.STATE_CHANGED,
        entity_type="document",
        entity_id=document.external_id,
        actor_id=principal.id if principal else None,
        actor_role=principal.primary_role if principal else None,
        before_state=before,
        after_state=_snapshot(document),
        reason=reason,
    )
    return document


def next_external_id(session: Session) -> str:
    """Sequential, human-readable document ids (DOC-00001).

    Readable ids matter here: officers quote them to each other, and the demo
    script follows one document by name through every screen.
    """
    latest = session.execute(
        select(Document.external_id).order_by(Document.external_id.desc()).limit(1)
    ).scalar_one_or_none()
    if latest is None:
        return "DOC-00001"
    try:
        return f"DOC-{int(latest.split('-')[1]) + 1:05d}"
    except (IndexError, ValueError):
        return f"DOC-{session.query(Document).count() + 1:05d}"


def upload(
    session: Session,
    *,
    principal: Principal,
    data: bytes,
    filename: str | None,
    declared_mime: str | None,
    document_type: str,
    village_external_id: str | None = None,
    record_year: str | None = None,
    declared_khasra: str | None = None,
    declared_khata: str | None = None,
    parcel_external_id: str | None = None,
) -> Document:
    """Store an uploaded file and run the §22 quality gate immediately.

    Order is deliberate: the bytes are validated and stored first, then quality
    is assessed, then the document is transitioned. A page that fails quality
    is still stored -- an operator needs to see WHY it was rejected, and the
    original is the evidence.
    """
    village = None
    if village_external_id:
        village = session.execute(
            select(Location).where(Location.external_id == village_external_id)
        ).scalar_one_or_none()
        if village is None:
            raise DocumentAccessDenied("unknown or inaccessible village")

    parcel = None
    if parcel_external_id:
        parcel = session.execute(
            select(Parcel).where(Parcel.external_id == parcel_external_id)
        ).scalar_one_or_none()
        if parcel is None:
            raise DocumentAccessDenied("unknown or inaccessible parcel")

    effective_village_id = village.id if village else (parcel.village_id if parcel else None)
    if village and parcel and village.id != parcel.village_id:
        raise DocumentAccessDenied("parcel does not belong to the selected village")
    if not location_in_jurisdiction(session, principal, effective_village_id):
        raise DocumentAccessDenied("document is outside your jurisdiction")

    stored = storage_service.put_document(
        data, declared_mime=declared_mime, prefix="documents"
    )

    document = Document(
        external_id=next_external_id(session),
        document_type=document_type,
        state=DocumentState.UPLOADED.value,
        parcel_id=parcel.id if parcel else None,
        village_id=village.id if village else None,
        record_year=record_year,
        declared_khasra=declared_khasra,
        declared_khata=declared_khata,
        uploaded_by_id=principal.id,
        storage_key=stored.key,
        original_filename=storage_service.sanitize_filename(filename),
        mime_type=stored.detected_mime,
        size_bytes=stored.size_bytes,
        checksum_sha256=stored.checksum_sha256,
    )
    session.add(document)
    session.flush()

    audit_service.record(
        session,
        action=audit_service.UPLOAD,
        entity_type="document",
        entity_id=document.external_id,
        actor_id=principal.id,
        actor_role=principal.primary_role,
        after_state=_snapshot(document) | {
            "filename": document.original_filename,
            "size_bytes": document.size_bytes,
            "checksum_sha256": document.checksum_sha256,
        },
    )

    run_quality_gate(session, document, data, principal=principal)
    session.commit()
    return document


def run_quality_gate(
    session: Session,
    document: Document,
    data: bytes,
    *,
    principal: Principal | None = None,
) -> dict:
    """Assess every page and record the verdict (§22).

    A multi-page document is judged by its WEAKEST page: one unreadable page
    in an otherwise clean PDF still needs a rescan, and averaging would hide it.
    """
    from ingest.rasterize import decode_pages, is_pdf
    from quality.assessment import assess

    transition(session, document, DocumentState.QUALITY_CHECK, principal=principal,
               action=audit_service.QUALITY_CHECK)

    images: list = []
    try:
        images = decode_pages(data)
        reports = [assess(image) for image in images]
        weakest = min(range(len(reports)), key=lambda i: reports[i].overall_score)
        report = reports[weakest]
        payload = report.to_dict()
        if len(reports) > 1:
            payload |= {
                "page_count": len(reports),
                "weakest_page": weakest + 1,
                "page_scores": [round(r.overall_score, 3) for r in reports],
            }
        document.quality_score = report.overall_score
        document.quality_report = payload
        document.quality_recommendation = report.recommended_action
    except ValueError as exc:
        # An undecodable upload is a quality failure, not a server error.
        payload = {"error": str(exc), "recommended_action": "REJECT_QUALITY"}
        document.quality_score = 0.0
        document.quality_report = payload
        document.quality_recommendation = "REJECT_QUALITY"

    session.flush()

    # Page rows give downstream stages somewhere to attach OCR results. An
    # image is its own page. A PDF's pages are rendered once here and stored,
    # because the pipeline, the Verifier overlay and the browser all need an
    # image -- none of them can draw a bbox over a PDF.
    if not document.pages:
        if images and is_pdf(data):
            for number, image in enumerate(images, start=1):
                session.add(DocumentPage(
                    document_id=document.id,
                    page_number=number,
                    storage_key=storage_service.put_page_image(image),
                    height=image.shape[0],
                    width=image.shape[1],
                ))
        else:
            page = DocumentPage(
                document_id=document.id,
                page_number=1,
                storage_key=document.storage_key,
            )
            if images:
                page.height, page.width = images[0].shape[:2]
            session.add(page)
        session.flush()

    if document.quality_recommendation == "REJECT_QUALITY":
        transition(session, document, DocumentState.RESCAN_REQUIRED,
                   principal=principal, reason="failed quality gate")

    audit_service.record(
        session,
        action=audit_service.QUALITY_CHECK,
        entity_type="document",
        entity_id=document.external_id,
        actor_id=principal.id if principal else None,
        after_state={"quality": payload},
    )
    return payload


def get_by_external_id(session: Session, external_id: str) -> Document:
    document = session.execute(
        select(Document).where(Document.external_id == external_id)
    ).scalar_one_or_none()
    if document is None:
        raise DocumentNotFound(external_id)
    return document


def latest_job(session: Session, document: Document) -> ProcessingJob | None:
    return session.execute(
        select(ProcessingJob)
        .where(ProcessingJob.document_id == document.id)
        .order_by(ProcessingJob.created_at.desc())
        .limit(1)
    ).scalar_one_or_none()


class ReprocessRefused(Exception):
    """Reprocessing would discard work a human has already done."""


def _queue_job(session: Session, document: Document) -> ProcessingJob:
    job = ProcessingJob(
        document_id=document.id,
        stage="upload",
        progress=0,
        status="QUEUED",
        started_at=datetime.now(UTC),
    )
    session.add(job)
    session.commit()
    return job


def reprocess(
    session: Session, document: Document, *, principal: Principal, reason: str | None = None
) -> ProcessingJob:
    """Re-run extraction on a document no human has worked yet (§29).

    Re-running replaces every extraction, and corrections cascade with the
    extraction they correct -- so once a verifier has corrected or accepted any
    field, reprocessing is refused rather than silently erasing that work.
    """
    from app.models import Extraction, FieldCorrection

    human_work = session.execute(
        select(Extraction.id).where(
            Extraction.document_id == document.id,
            Extraction.status.in_(("VERIFIER_APPROVED", "VERIFIER_CORRECTED")),
        ).limit(1)
    ).first() or session.execute(
        select(FieldCorrection.id).where(FieldCorrection.document_id == document.id).limit(1)
    ).first()
    if human_work:
        raise ReprocessRefused(
            "A verifier has already corrected or accepted fields on this document. "
            "Re-running extraction would discard that work."
        )

    transition(session, document, DocumentState.PROCESSING, principal=principal,
               action=audit_service.REPROCESSING_REQUESTED,
               reason=reason or "extraction re-run before verification")
    return _queue_job(session, document)


def start_processing(
    session: Session, document: Document, *, principal: Principal
) -> ProcessingJob:
    """Queue the AI pipeline (§23).

    Refuses documents the quality gate sent back, so a page already known to be
    unreadable does not consume OCR time.
    """
    if document.quality_recommendation == "REJECT_QUALITY":
        raise IllegalTransitionError(
            DocumentState(document.state), DocumentState.PROCESSING
        )

    transition(session, document, DocumentState.PROCESSING, principal=principal,
               action=audit_service.PROCESSING_STARTED)
    return _queue_job(session, document)


__all__ = [
    "DocumentAccessDenied", "DocumentNotFound", "UnsupportedFileType", "get_by_external_id",
    "ReprocessRefused", "latest_job", "reprocess", "run_quality_gate", "start_processing",
    "transition", "upload",
]


def page_bucket(document: Document, page: DocumentPage) -> str | None:
    """Which bucket holds a page's image.

    An image upload's single page IS the original, in the documents bucket.
    A rendered PDF page is derived data, in the derived bucket.
    """
    if page.storage_key == document.storage_key:
        return None  # storage_service default: the documents bucket
    return storage_service.derived_bucket()


def page_bytes(document: Document, page: DocumentPage) -> bytes:
    return storage_service.get_bytes(page.storage_key, bucket=page_bucket(document, page))


def page_url(document: Document, page: DocumentPage) -> str:
    return storage_service.presigned_url(page.storage_key, bucket=page_bucket(document, page))
