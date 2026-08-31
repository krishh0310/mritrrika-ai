"""Data access for users, roles and permissions (§80: repositories own SQL)."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.models import CitizenProfile, Permission, Role, RolePermission, User, UserRole


def get_by_email(session: Session, email: str) -> User | None:
    return session.execute(
        select(User)
        .options(joinedload(User.roles).joinedload(UserRole.role))
        .where(User.email == email.lower().strip())
    ).unique().scalar_one_or_none()


def get_by_id(session: Session, user_id: str) -> User | None:
    return session.execute(
        select(User)
        .options(joinedload(User.roles).joinedload(UserRole.role))
        .where(User.id == user_id)
    ).unique().scalar_one_or_none()


def permissions_for(session: Session, user: User) -> set[str]:
    """Every permission code granted through the user's roles.

    Read from the database on each request rather than cached in the JWT, so
    revoking a role takes effect immediately (§12).
    """
    role_ids = [ur.role_id for ur in user.roles]
    if not role_ids:
        return set()
    rows = session.execute(
        select(Permission.code)
        .join(RolePermission, RolePermission.permission_id == Permission.id)
        .where(RolePermission.role_id.in_(role_ids))
    ).scalars()
    return set(rows)


def citizen_profile_for(session: Session, user_id: str) -> CitizenProfile | None:
    return session.execute(
        select(CitizenProfile).where(CitizenProfile.user_id == user_id)
    ).scalar_one_or_none()


def role_codes_for(session: Session, user: User) -> set[str]:
    role_ids = [ur.role_id for ur in user.roles]
    if not role_ids:
        return set()
    return set(
        session.execute(select(Role.code).where(Role.id.in_(role_ids))).scalars()
    )
