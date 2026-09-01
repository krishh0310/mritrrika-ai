"""Authentication and authorization decisions (§80: services own the rules)."""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy import and_, or_, select, true
from sqlalchemy.orm import Session

from app.models import (
    AnomalyFlag,
    CitizenProfile,
    Document,
    Grievance,
    Location,
    OwnershipRecord,
    Parcel,
    User,
)
from app.repositories import user_repository
from app.security.passwords import hash_password, needs_rehash, verify_password
from app.security.tokens import create_access_token, create_refresh_token


class AuthenticationError(Exception):
    """Login failed. Deliberately carries no detail about why."""


@dataclass
class Principal:
    """The authenticated caller, assembled server-side on every request.

    Nothing here comes from the client. The token supplies only a user id; the
    role, permissions and owner link are all re-read from the database, so a
    forged or stale claim buys nothing (§12, §62).
    """

    user: User
    roles: set[str] = field(default_factory=set)
    permissions: set[str] = field(default_factory=set)
    #: Set only for citizens -- the owner they are allowed to act as.
    owner_id: str | None = None
    jurisdiction_id: str | None = None

    @property
    def id(self) -> str:
        return self.user.id

    def has(self, permission: str) -> bool:
        return permission in self.permissions

    def is_citizen(self) -> bool:
        return "CITIZEN" in self.roles

    @property
    def primary_role(self) -> str | None:
        """The role stamped onto audit events.

        Sorted rather than `next(iter(...))`: set iteration order is not
        stable, which would let audit rows for one user disagree about their
        role between requests. Demo accounts hold exactly one role each.
        """
        return sorted(self.roles)[0] if self.roles else None


def authenticate(session: Session, email: str, password: str) -> User:
    """Verify credentials.

    Always runs a hash comparison, even when the user does not exist, so
    response timing does not reveal which emails are registered.
    """
    user = user_repository.get_by_email(session, email)
    if user is None:
        # Dummy verify against a real hash to keep timing flat.
        verify_password(password, hash_password("timing-equaliser"))
        raise AuthenticationError("invalid credentials")

    if not verify_password(password, user.password_hash):
        raise AuthenticationError("invalid credentials")

    if not user.is_active:
        raise AuthenticationError("account is disabled")

    if needs_rehash(user.password_hash):
        user.password_hash = hash_password(password)
        session.commit()

    return user


def issue_tokens(user: User) -> dict[str, str]:
    return {
        "access_token": create_access_token(user.id),
        "refresh_token": create_refresh_token(user.id),
        "token_type": "bearer",
    }


def build_principal(session: Session, user: User) -> Principal:
    """Assemble the caller's authority from the database."""
    roles = user_repository.role_codes_for(session, user)
    permissions = user_repository.permissions_for(session, user)

    owner_id = None
    if "CITIZEN" in roles:
        profile = user_repository.citizen_profile_for(session, user.id)
        # A citizen with no owner link has no land scope at all. That is a
        # valid state (a registered user who owns nothing) and must resolve to
        # an EMPTY scope, never to an unscoped query.
        owner_id = profile.owner_id if profile else None

    return Principal(
        user=user,
        roles=roles,
        permissions=permissions,
        owner_id=owner_id,
        jurisdiction_id=user.jurisdiction_id,
    )


def jurisdiction_location_ids(session: Session, principal: Principal) -> set[str] | None:
    """Every location at or beneath an officer's jurisdiction (§36).

    Returns ``None`` only for citizens, whose scope is ownership-based instead.
    An officer with no assigned jurisdiction gets an empty scope: missing
    authority must fail closed rather than silently becoming district-wide.
    """
    if principal.is_citizen():
        return None
    if principal.jurisdiction_id is None:
        return set()

    # Recursive descent through the location tree.
    seen: set[str] = {principal.jurisdiction_id}
    frontier = [principal.jurisdiction_id]
    while frontier:
        children = list(
            session.execute(
                select(Location.id).where(Location.parent_id.in_(frontier))
            ).scalars()
        )
        new = [c for c in children if c not in seen]
        seen.update(new)
        frontier = new
    return seen


def location_in_jurisdiction(
    session: Session, principal: Principal, location_id: str | None
) -> bool:
    allowed = jurisdiction_location_ids(session, principal)
    return allowed is None or (location_id is not None and location_id in allowed)


def parcel_in_jurisdiction(
    session: Session, principal: Principal, parcel: Parcel | None
) -> bool:
    return parcel is not None and location_in_jurisdiction(
        session, principal, parcel.village_id
    )


def document_in_jurisdiction(
    session: Session, principal: Principal, document: Document | None
) -> bool:
    if document is None:
        return False
    if jurisdiction_location_ids(session, principal) is None:
        return True

    has_location = False
    if document.village_id is not None:
        has_location = True
        if not location_in_jurisdiction(session, principal, document.village_id):
            return False
    if document.parcel_id is not None:
        has_location = True
        if not parcel_in_jurisdiction(
            session, principal, session.get(Parcel, document.parcel_id)
        ):
            return False
    return has_location


def document_jurisdiction_clause(session: Session, principal: Principal):
    """Reusable SQL predicate for every officer-facing document collection."""
    allowed = jurisdiction_location_ids(session, principal)
    if allowed is None:
        return true()
    parcel_ids = select(Parcel.id).where(Parcel.village_id.in_(allowed))
    return and_(
        or_(Document.village_id.is_(None), Document.village_id.in_(allowed)),
        or_(Document.parcel_id.is_(None), Document.parcel_id.in_(parcel_ids)),
        or_(Document.village_id.is_not(None), Document.parcel_id.is_not(None)),
    )


def anomaly_jurisdiction_clause(session: Session, principal: Principal):
    allowed = jurisdiction_location_ids(session, principal)
    if allowed is None:
        return true()
    document_ids = select(Document.id).where(
        document_jurisdiction_clause(session, principal)
    )
    parcel_ids = select(Parcel.id).where(Parcel.village_id.in_(allowed))
    return and_(
        or_(AnomalyFlag.document_id.is_(None), AnomalyFlag.document_id.in_(document_ids)),
        or_(AnomalyFlag.parcel_id.is_(None), AnomalyFlag.parcel_id.in_(parcel_ids)),
        or_(AnomalyFlag.document_id.is_not(None), AnomalyFlag.parcel_id.is_not(None)),
    )


def grievance_jurisdiction_clause(session: Session, principal: Principal):
    allowed = jurisdiction_location_ids(session, principal)
    if allowed is None:
        return true()
    parcel_ids = select(Parcel.id).where(Parcel.village_id.in_(allowed))
    owner_ids = select(OwnershipRecord.owner_id).where(
        OwnershipRecord.parcel_id.in_(parcel_ids)
    )
    citizen_ids = select(CitizenProfile.user_id).where(
        CitizenProfile.owner_id.in_(owner_ids)
    )
    return or_(
        Grievance.parcel_id.in_(parcel_ids),
        and_(
            Grievance.parcel_id.is_(None),
            Grievance.raised_by_id.in_(citizen_ids),
        ),
    )


def grievance_in_jurisdiction(
    session: Session, principal: Principal, grievance: Grievance | None
) -> bool:
    if grievance is None:
        return False
    return session.execute(
        select(Grievance.id).where(
            Grievance.id == grievance.id,
            grievance_jurisdiction_clause(session, principal),
        )
    ).scalar_one_or_none() is not None
