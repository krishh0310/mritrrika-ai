"""Deliver approved records to the state LRMS / DILRMP (§14).

The path of a record out of this system:

    tehsildar approves  ->  enqueue()  ->  lrms_sync_records (PENDING)
                                               |
                          deliver()  ->  adapter  ->  DELIVERED | FAILED

Enqueueing happens inside the approval transaction, so an approved record is
always queued and a rolled-back approval never is. Delivery is separate and
retryable: a state server being down must not block approvals, and a failed
delivery stays visible with its error until it succeeds.

The payload is a Record of Rights in the shape DILRMP's RoR data carries --
location hierarchy, parcel (survey/khasra) number, holding (khata) number,
area, land class, current holders with shares -- plus the provenance only this
system has: the source document's checksum and the audit-chain hash of the
approval, so the receiving system can verify both independently.

Location codes are this system's location ids. A real deployment maps them to
LGD (Local Government Directory) codes in one place -- `_location` below --
because that mapping is per state and this prototype's villages are synthetic.
"""

from __future__ import annotations

from datetime import UTC, datetime

from mrittika_domain import DocumentState
from mrittika_domain.area import UnknownAreaUnit, to_square_metres
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.integrations.lrms import LrmsAdapter, LrmsDeliveryError
from app.models import AuditEvent, Document, Extraction, Location, LrmsSyncRecord, Parcel
from app.repositories import ownership_repository
from app.services import audit_service
from app.services.auth_service import Principal, document_jurisdiction_clause
from app.services.certificate_service import hash_of

SCHEMA = "mrittika.ror/1"

PENDING = "PENDING"
DELIVERED = "DELIVERED"
FAILED = "FAILED"

#: A record that has failed this many times stops being retried automatically.
#: It is not dropped: it stays FAILED, with its last error, for a person.
MAX_ATTEMPTS = 5

LRMS_SYNC = "integration.lrms_sync"

#: Fields that are one value per page. The rest (OWNER, GUARDIAN, SHARE) are
#: table rows and are reported with their row number.
_TABLE_FIELDS = frozenset({"OWNER", "GUARDIAN", "SHARE"})


class LrmsError(Exception):
    """The record cannot be expressed as a Record of Rights."""


def _location(location: Location | None) -> dict | None:
    if location is None:
        return None
    return {
        "code": location.external_id,
        "name": location.name,
        "name_local": location.name_devanagari,
    }


def _hierarchy(session: Session, village: Location | None) -> dict:
    """{village, tehsil, district, state}, walked up from the village."""
    levels: dict[str, dict | None] = {
        "state": None, "district": None, "tehsil": None, "village": None,
    }
    node = village
    while node is not None:
        levels[node.level.lower()] = _location(node)
        node = session.get(Location, node.parent_id) if node.parent_id else None
    return levels


def _approval_event(session: Session, document: Document) -> AuditEvent | None:
    return session.execute(
        select(AuditEvent)
        .where(
            AuditEvent.action == audit_service.APPROVED,
            AuditEvent.entity_type == "document",
            AuditEvent.entity_id == document.external_id,
        )
        .order_by(AuditEvent.sequence.desc())
        .limit(1)
    ).scalar_one_or_none()


def ror_payload(session: Session, document: Document) -> dict:
    """The Record of Rights for one approved document, in delivery format.

    Deterministic for a given approval: the timestamp is the approval's own
    audit timestamp, not the time of export, so the digest of an unchanged
    record never changes and re-queueing it is a no-op.
    """
    if document.state != DocumentState.APPROVED.value:
        raise LrmsError(
            f"document {document.external_id} is {document.state}; only approved "
            "records are delivered"
        )
    if document.parcel_id is None:
        raise LrmsError(
            f"document {document.external_id} is not linked to a parcel, so there "
            "is no Record of Rights to deliver"
        )
    parcel = session.get(Parcel, document.parcel_id)
    approval = _approval_event(session, document)

    try:
        area_sqm = round(to_square_metres(parcel.area_value, parcel.area_unit), 2)
    except UnknownAreaUnit:
        area_sqm = None

    holders = [
        {
            "owner": row["owner"],
            "owner_code": row["owner_id"],
            "share": row["share"],
            "since": row["valid_from"].isoformat() if row["valid_from"] else None,
            "mutation_number": row["mutation_number"],
        }
        for row in ownership_repository.ownership_history(session, parcel.id)
        if row.get("valid_to") in (None, "")
    ]

    extractions = session.execute(
        select(Extraction)
        .where(Extraction.document_id == document.id)
        .order_by(Extraction.field, Extraction.row_index)
    ).scalars().all()
    as_recorded = [
        {
            "field": e.field,
            "value": e.effective_value,
            "row": e.row_index if e.field in _TABLE_FIELDS else None,
            "verified_by_human": e.corrected_value is not None
            or e.status == "VERIFIER_APPROVED",
        }
        for e in extractions
        if e.effective_value is not None
    ]

    return {
        "schema": SCHEMA,
        "record_id": document.external_id,
        # UTC explicitly: read back from the database the same instant can come
        # in the connection's zone, and a different string is a different
        # digest -- the unchanged record would be queued twice.
        "approved_at": (
            approval.created_at.astimezone(UTC).isoformat() if approval else None
        ),
        "location": _hierarchy(session, parcel.village),
        "parcel": {
            "parcel_code": parcel.external_id,
            "survey_number": parcel.khasra_number,
            "khata_number": parcel.khata_number,
            "area": {
                "value": parcel.area_value,
                "unit": parcel.area_unit,
                "square_metres": area_sqm,
            },
            "land_class": parcel.land_class,
        },
        "holders": holders,
        "source_document": {
            "document_type": document.document_type,
            "record_year": document.record_year,
            "sha256": document.checksum_sha256,
            "as_recorded": as_recorded,
        },
        "provenance": {
            "system": "mrittika-ai",
            "approval_audit_hash": approval.event_hash if approval else None,
            "is_synthetic": bool(document.is_synthetic),
        },
    }


def enqueue(session: Session, document: Document) -> LrmsSyncRecord | None:
    """Queue an approved record. Returns None when it has no Record of Rights.

    Idempotent: identical content is queued once. Called inside the approval
    transaction and does not commit.
    """
    try:
        payload = ror_payload(session, document)
    except LrmsError:
        return None
    digest = hash_of(payload)

    existing = session.execute(
        select(LrmsSyncRecord).where(
            LrmsSyncRecord.document_id == document.id,
            LrmsSyncRecord.payload_sha256 == digest,
        )
    ).scalar_one_or_none()
    if existing is not None:
        return existing

    record = LrmsSyncRecord(
        document_id=document.id, payload=payload, payload_sha256=digest,
        status=PENDING, attempts=0,
    )
    # A savepoint, so a concurrent enqueue of the same content (the unique
    # index) cannot abort the approval transaction around it.
    try:
        with session.begin_nested():
            session.add(record)
    except IntegrityError:
        return session.execute(
            select(LrmsSyncRecord).where(
                LrmsSyncRecord.document_id == document.id,
                LrmsSyncRecord.payload_sha256 == digest,
            )
        ).scalar_one()
    return record


def backfill(session: Session, principal: Principal,
             document_ids: list[str] | None = None) -> int:
    """Queue approved records in scope that were approved before the outbox
    existed, or whose enqueue was skipped. Returns how many were added."""
    queued = select(LrmsSyncRecord.document_id)
    query = select(Document).where(
        document_jurisdiction_clause(session, principal),
        Document.state == DocumentState.APPROVED.value,
        Document.parcel_id.is_not(None),
        Document.id.not_in(queued),
    )
    if document_ids is not None:
        query = query.where(Document.external_id.in_(document_ids))
    documents = session.execute(query).scalars().all()
    added = 0
    for document in documents:
        if enqueue(session, document) is not None:
            added += 1
    return added


def _in_scope(session: Session, principal: Principal):
    return LrmsSyncRecord.document_id.in_(
        select(Document.id).where(document_jurisdiction_clause(session, principal))
    )


def deliver(
    session: Session,
    adapter: LrmsAdapter,
    principal: Principal,
    *,
    limit: int = 100,
    document_ids: list[str] | None = None,
) -> dict:
    """Push queued records in the caller's jurisdiction through the adapter.

    `document_ids` (external ids) narrows the run to those records -- to push
    one record now, or retry one that failed -- instead of everything due.
    """
    added = backfill(session, principal, document_ids)

    query = (
        select(LrmsSyncRecord)
        .where(
            _in_scope(session, principal),
            LrmsSyncRecord.status.in_((PENDING, FAILED)),
            LrmsSyncRecord.attempts < MAX_ATTEMPTS,
        )
        .order_by(LrmsSyncRecord.created_at)
        .limit(limit)
        .with_for_update(skip_locked=True)
    )
    if document_ids is not None:
        query = query.where(LrmsSyncRecord.document_id.in_(
            select(Document.id).where(Document.external_id.in_(document_ids))
        ))
    due = session.execute(query).scalars().all()

    delivered = failed = 0
    for record in due:
        record.attempts += 1
        record.adapter = adapter.name
        try:
            receipt = adapter.deliver(record.payload, record.payload_sha256)
        except LrmsDeliveryError as exc:
            record.status = FAILED
            record.last_error = str(exc)[:2000]
            failed += 1
            continue
        record.status = DELIVERED
        record.remote_reference = receipt.remote_reference
        record.delivered_at = datetime.now(UTC)
        record.last_error = None
        delivered += 1

    summary = {
        "adapter": adapter.name,
        "scope": sorted(document_ids) if document_ids is not None else "all-due",
        "queued_now": added,
        "attempted": len(due),
        "delivered": delivered,
        "failed": failed,
    }
    audit_service.record(
        session, action=LRMS_SYNC, entity_type="integration", entity_id="lrms",
        actor_id=principal.id, actor_role=principal.primary_role,
        after_state=summary,
    )
    session.commit()
    return summary


def status(session: Session, principal: Principal, adapter: LrmsAdapter, *,
           recent: int = 20) -> dict:
    """What is queued, delivered and failing, within the caller's jurisdiction."""
    counts = dict(
        session.execute(
            select(LrmsSyncRecord.status, func.count(LrmsSyncRecord.id))
            .where(_in_scope(session, principal))
            .group_by(LrmsSyncRecord.status)
        ).all()
    )
    awaiting_queue = session.execute(
        select(func.count(Document.id)).where(
            document_jurisdiction_clause(session, principal),
            Document.state == DocumentState.APPROVED.value,
            Document.parcel_id.is_not(None),
            Document.id.not_in(select(LrmsSyncRecord.document_id)),
        )
    ).scalar_one()

    rows = session.execute(
        select(LrmsSyncRecord, Document.external_id)
        .join(Document, Document.id == LrmsSyncRecord.document_id)
        .where(_in_scope(session, principal))
        .order_by(LrmsSyncRecord.updated_at.desc())
        .limit(recent)
    ).all()

    return {
        "adapter": adapter.name,
        "counts": {
            PENDING: counts.get(PENDING, 0),
            DELIVERED: counts.get(DELIVERED, 0),
            FAILED: counts.get(FAILED, 0),
        },
        #: Approved before the outbox existed; the next sync queues them.
        "approved_not_queued": awaiting_queue,
        "max_attempts": MAX_ATTEMPTS,
        "recent": [
            {
                "document_id": external_id,
                "status": record.status,
                "attempts": record.attempts,
                "payload_sha256": record.payload_sha256,
                "remote_reference": record.remote_reference,
                "last_error": record.last_error,
                "delivered_at": (
                    record.delivered_at.isoformat() if record.delivered_at else None
                ),
            }
            for record, external_id in rows
        ],
        "is_synthetic": True,
    }


__all__ = [
    "DELIVERED", "FAILED", "LRMS_SYNC", "LrmsError", "MAX_ATTEMPTS", "PENDING",
    "SCHEMA", "backfill", "deliver", "enqueue", "ror_payload", "status",
]
