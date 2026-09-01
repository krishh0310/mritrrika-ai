"""Citizen grievances (§19).

A grievance is the one place a citizen writes into the officer workflow, so
two rules matter here:

  1. If a grievance names a parcel, the citizen must actually hold an interest
     in it. The parcel is resolved through `assert_can_access_parcel`, the same
     gate every other citizen read passes through (§62) -- a caller cannot file
     against a stranger's parcel to learn that it exists.
  2. Reads are scoped by who is asking. `for_citizen` filters to the caller's
     own rows; `review_queue` is the officer view and is reached only with a
     `grievance:review*` permission.
"""

from __future__ import annotations

from mrittika_domain import GrievanceStatus
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Grievance, Parcel, User
from app.services import audit_service, storage_service
from app.services.auth_service import Principal, grievance_jurisdiction_clause
from app.services.citizen_service import assert_can_access_parcel

#: §19 issue types. A closed vocabulary rather than free text so the officer
#: queue can be filtered and counted.
ISSUE_TYPES = (
    "INCORRECT_OWNER_NAME",
    "INCORRECT_AREA",
    "INCORRECT_KHASRA",
    "MISSING_MUTATION",
    "BOUNDARY_DISPUTE",
    "DOCUMENT_NOT_FOUND",
    "OTHER",
)

#: Transitions an officer may drive. SUBMITTED and the terminal states are
#: absent as sources where they would let a resolved grievance be silently
#: reopened into review by a limited reviewer.
ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    GrievanceStatus.SUBMITTED: {
        GrievanceStatus.UNDER_REVIEW,
        GrievanceStatus.REJECTED,
    },
    GrievanceStatus.UNDER_REVIEW: {
        GrievanceStatus.ACTION_REQUIRED,
        GrievanceStatus.RESOLVED,
        GrievanceStatus.REJECTED,
    },
    GrievanceStatus.ACTION_REQUIRED: {
        GrievanceStatus.UNDER_REVIEW,
        GrievanceStatus.RESOLVED,
        GrievanceStatus.REJECTED,
    },
    GrievanceStatus.RESOLVED: set(),
    GrievanceStatus.REJECTED: set(),
}


class GrievanceError(Exception):
    """Invalid grievance input or transition."""


class GrievanceNotFound(Exception):
    pass


def next_external_id(session: Session) -> str:
    """Sequential, human-readable ids (GRV-00001)."""
    latest = session.execute(
        select(Grievance.external_id).order_by(Grievance.external_id.desc()).limit(1)
    ).scalar_one_or_none()
    if latest is None:
        return "GRV-00001"
    try:
        return f"GRV-{int(latest.split('-')[1]) + 1:05d}"
    except (IndexError, ValueError):
        return f"GRV-{session.query(Grievance).count() + 1:05d}"


def _serialize(grievance: Grievance, parcel: Parcel | None, raised_by: User | None) -> dict:
    return {
        "grievance_id": grievance.external_id,
        "parcel_id": parcel.external_id if parcel else None,
        "khasra_number": parcel.khasra_number if parcel else None,
        "issue_type": grievance.issue_type,
        "description": grievance.description,
        "status": grievance.status,
        "resolution_note": grievance.resolution_note,
        "has_attachment": grievance.supporting_storage_key is not None,
        "raised_by": raised_by.full_name if raised_by else None,
        "created_at": grievance.created_at.isoformat() if grievance.created_at else None,
        "updated_at": grievance.updated_at.isoformat() if grievance.updated_at else None,
        "is_synthetic": True,
    }


def create(
    session: Session,
    principal: Principal,
    *,
    issue_type: str,
    description: str,
    parcel_external_id: str | None = None,
    attachment: bytes | None = None,
    attachment_mime: str | None = None,
) -> Grievance:
    """File a grievance on behalf of the authenticated citizen.

    `raised_by` comes from the session, never from the payload.
    """
    if issue_type not in ISSUE_TYPES:
        raise GrievanceError(
            f"unknown issue type {issue_type!r} "
            f"(accepted: {', '.join(ISSUE_TYPES)})"
        )
    description = description.strip()
    if not description:
        raise GrievanceError("description is required")

    parcel: Parcel | None = None
    if parcel_external_id:
        # Raises ParcelAccessDenied for both "not yours" and "does not exist",
        # so filing cannot be used to enumerate parcel ids.
        parcel = assert_can_access_parcel(session, principal, parcel_external_id)

    storage_key = None
    if attachment:
        stored = storage_service.put_document(
            attachment, declared_mime=attachment_mime, prefix="grievances"
        )
        storage_key = stored.key

    grievance = Grievance(
        external_id=next_external_id(session),
        raised_by_id=principal.user.id,
        parcel_id=parcel.id if parcel else None,
        issue_type=issue_type,
        description=description,
        supporting_storage_key=storage_key,
        status=GrievanceStatus.SUBMITTED,
    )
    session.add(grievance)
    session.flush()

    audit_service.record(
        session,
        action=audit_service.GRIEVANCE_CREATED,
        entity_type="grievance",
        entity_id=grievance.external_id,
        actor_id=principal.id,
        actor_role=principal.primary_role,
        after_state={
            "status": grievance.status,
            "issue_type": grievance.issue_type,
            "parcel_id": parcel.external_id if parcel else None,
        },
    )
    session.commit()
    session.refresh(grievance)
    return grievance


def for_citizen(session: Session, principal: Principal) -> list[dict]:
    """The caller's own grievances (§19 tracking)."""
    rows = session.execute(
        select(Grievance, Parcel)
        .outerjoin(Parcel, Parcel.id == Grievance.parcel_id)
        .where(Grievance.raised_by_id == principal.user.id)
        .order_by(Grievance.created_at.desc())
    ).all()
    return [_serialize(g, p, principal.user) for g, p in rows]


def review_queue(
    session: Session,
    *,
    principal: Principal,
    status: str | None = None,
    limit: int = 100,
) -> list[dict]:
    """The officer-facing queue (§31)."""
    stmt = (
        select(Grievance, Parcel, User)
        .outerjoin(Parcel, Parcel.id == Grievance.parcel_id)
        .join(User, User.id == Grievance.raised_by_id)
    )
    if status:
        stmt = stmt.where(Grievance.status == status)
    stmt = stmt.where(grievance_jurisdiction_clause(session, principal))
    stmt = stmt.order_by(Grievance.created_at.desc()).limit(limit)
    return [_serialize(g, p, u) for g, p, u in session.execute(stmt).all()]


def get(session: Session, external_id: str) -> Grievance:
    grievance = session.execute(
        select(Grievance).where(Grievance.external_id == external_id)
    ).scalar_one_or_none()
    if grievance is None:
        raise GrievanceNotFound(external_id)
    return grievance


def detail(session: Session, grievance: Grievance) -> dict:
    parcel = (
        session.get(Parcel, grievance.parcel_id) if grievance.parcel_id else None
    )
    return _serialize(grievance, parcel, session.get(User, grievance.raised_by_id))


def update_status(
    session: Session,
    grievance: Grievance,
    new_status: str,
    *,
    principal: Principal,
    note: str | None = None,
) -> Grievance:
    """Move a grievance through its lifecycle, validating the transition."""
    if new_status not in set(GrievanceStatus):
        raise GrievanceError(f"unknown status {new_status!r}")

    allowed = ALLOWED_TRANSITIONS.get(grievance.status, set())
    if new_status not in allowed:
        raise GrievanceError(
            f"cannot move a {grievance.status} grievance to {new_status}"
            + (f" (allowed: {', '.join(sorted(allowed))})" if allowed else
               " -- it is already closed")
        )

    before = {"status": grievance.status, "resolution_note": grievance.resolution_note}
    grievance.status = new_status
    if note:
        grievance.resolution_note = note

    audit_service.record(
        session,
        action="grievance.status_changed",
        entity_type="grievance",
        entity_id=grievance.external_id,
        actor_id=principal.id,
        actor_role=principal.primary_role,
        before_state=before,
        after_state={"status": grievance.status,
                     "resolution_note": grievance.resolution_note},
        reason=note,
    )
    session.commit()
    session.refresh(grievance)
    return grievance


def counts_by_status(session: Session, principal: Principal | None = None) -> dict[str, int]:
    """Status histogram, scoped to one citizen when a principal is given."""
    stmt = select(Grievance.status, Grievance.id)
    if principal is not None and principal.is_citizen():
        stmt = stmt.where(Grievance.raised_by_id == principal.user.id)
    elif principal is not None:
        stmt = stmt.where(grievance_jurisdiction_clause(session, principal))
    counts = {status.value: 0 for status in GrievanceStatus}
    for status_value, _ in session.execute(stmt).all():
        counts[status_value] = counts.get(status_value, 0) + 1
    return counts


__all__ = [
    "ALLOWED_TRANSITIONS", "GrievanceError", "GrievanceNotFound", "ISSUE_TYPES",
    "counts_by_status", "create", "detail", "for_citizen", "get", "review_queue",
    "update_status",
]
