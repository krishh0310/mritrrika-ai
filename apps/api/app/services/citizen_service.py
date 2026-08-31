"""Citizen-scoped reads (§13-§18).

THE rule this module exists to enforce (§62): a citizen's identity is derived
server-side from their session, never accepted from the request.

    JWT -> user_id -> citizen_profile -> owner_id -> authorized parcel_ids

No function here takes an owner_id or parcel scope from a caller-supplied
value. `assert_can_access_parcel` is the single gate every parcel-specific
citizen endpoint must pass through.
"""

from __future__ import annotations

from datetime import date

from sqlalchemy.orm import Session

from app.models import Parcel
from app.repositories import ownership_repository
from app.services.auth_service import Principal


class ParcelAccessDenied(Exception):
    """The caller has no ownership interest in this parcel."""


def my_parcel_ids(session: Session, principal: Principal, on: date | None = None) -> set[str]:
    """Primary keys of parcels the caller may see in full.

    A citizen with no owner link resolves to an empty set -- never to an
    unrestricted query.
    """
    if principal.owner_id is None:
        return set()
    return ownership_repository.parcel_ids_for_owner(session, principal.owner_id, on)


def my_holdings(session: Session, principal: Principal, on: date | None = None) -> list[dict]:
    if principal.owner_id is None:
        return []
    return ownership_repository.holdings_for_owner(session, principal.owner_id, on)


def assert_can_access_parcel(
    session: Session, principal: Principal, parcel_external_id: str
) -> Parcel:
    """Resolve a parcel the caller is entitled to, or refuse.

    Officers are scoped by jurisdiction elsewhere; this path is the citizen
    one, where entitlement means a current ownership interest.
    """
    parcel = ownership_repository.get_parcel_by_external_id(session, parcel_external_id)
    if parcel is None:
        # Same exception as an unauthorized parcel: a citizen must not be able
        # to probe which parcel ids exist by comparing 404 against 403.
        raise ParcelAccessDenied(parcel_external_id)

    if parcel.id not in my_parcel_ids(session, principal):
        raise ParcelAccessDenied(parcel_external_id)

    return parcel


def dashboard_summary(session: Session, principal: Principal) -> dict:
    """Cards for /citizen/dashboard (§14)."""
    holdings = my_holdings(session, principal)
    total_area = sum(h["area_value"] for h in holdings)
    return {
        "citizen_name": principal.user.full_name,
        "parcel_count": len(holdings),
        "total_area": round(total_area, 2),
        "area_units": sorted({h["area_unit"] for h in holdings}),
        "is_synthetic": True,
    }


def ownership_history(
    session: Session, principal: Principal, parcel_external_id: str
) -> list[dict]:
    parcel = assert_can_access_parcel(session, principal, parcel_external_id)
    return ownership_repository.ownership_history(session, parcel.id)


def owners_on_date(
    session: Session, principal: Principal, parcel_external_id: str, on: date
) -> list[dict]:
    """Answers 'who was the recorded owner in 1998?' for an entitled caller."""
    parcel = assert_can_access_parcel(session, principal, parcel_external_id)
    return ownership_repository.owners_on(session, parcel.id, on)
