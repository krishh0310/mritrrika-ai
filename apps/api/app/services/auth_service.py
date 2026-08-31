"""Authentication and authorization decisions (§80: services own the rules)."""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Location, User
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

    Returns None when the caller has no jurisdiction restriction to apply
    (citizens, whose scope is ownership-based instead).
    """
    if principal.jurisdiction_id is None:
        return None

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
