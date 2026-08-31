"""Ownership and parcel access, scoped by owner (§62).

Every function here takes an owner_id that the SERVICE layer derived from the
authenticated session. None of them accept an owner identity from a request.
"""

from __future__ import annotations

from datetime import date

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from app.models import Location, Mutation, Owner, OwnershipRecord, Parcel


def _current(stmt: Select, on: date) -> Select:
    """Restrict to interests in force on `on` (valid_to NULL means current)."""
    return stmt.where(
        OwnershipRecord.valid_from <= on,
        (OwnershipRecord.valid_to.is_(None)) | (OwnershipRecord.valid_to >= on),
    )


def parcel_ids_for_owner(session: Session, owner_id: str, on: date | None = None) -> set[str]:
    """The authoritative scope of a citizen's access."""
    on = on or date.today()
    stmt = _current(
        select(OwnershipRecord.parcel_id).where(OwnershipRecord.owner_id == owner_id),
        on,
    )
    return set(session.execute(stmt).scalars())


def holdings_for_owner(session: Session, owner_id: str, on: date | None = None) -> list[dict]:
    """Parcels a citizen holds, with their share -- the 'My Land' payload (§15)."""
    on = on or date.today()
    stmt = _current(
        select(Parcel, OwnershipRecord, Location)
        .join(OwnershipRecord, OwnershipRecord.parcel_id == Parcel.id)
        .join(Location, Location.id == Parcel.village_id)
        .where(OwnershipRecord.owner_id == owner_id),
        on,
    ).order_by(Parcel.khasra_number)

    results = []
    for parcel, ownership, village in session.execute(stmt).all():
        results.append(
            {
                "parcel_id": parcel.external_id,
                "khasra_number": parcel.khasra_number,
                "khata_number": parcel.khata_number,
                "village": village.name_devanagari or village.name,
                "village_id": village.external_id,
                "area_value": parcel.area_value,
                "area_unit": parcel.area_unit,
                "area_unit_raw": parcel.area_unit_raw,
                "land_class": parcel.land_class,
                "share": ownership.share,
                "held_since": ownership.valid_from,
                "is_synthetic": parcel.is_synthetic,
            }
        )
    return results


def ownership_history(session: Session, parcel_pk: str) -> list[dict]:
    """Full ownership timeline for a parcel -- the §25 history view."""
    stmt = (
        select(OwnershipRecord, Owner, Mutation)
        .join(Owner, Owner.id == OwnershipRecord.owner_id)
        .outerjoin(Mutation, Mutation.id == OwnershipRecord.mutation_id)
        .where(OwnershipRecord.parcel_id == parcel_pk)
        .order_by(OwnershipRecord.valid_from, Owner.name)
    )
    return [
        {
            "owner": owner.name,
            "owner_id": owner.external_id,
            "share": record.share,
            "valid_from": record.valid_from,
            "valid_to": record.valid_to,
            "mutation_number": mutation.mutation_number if mutation else None,
            "mutation_type": mutation.mutation_type if mutation else None,
        }
        for record, owner, mutation in session.execute(stmt).all()
    ]


def owners_on(session: Session, parcel_pk: str, on: date) -> list[dict]:
    """Who held a parcel on a given date -- answers demo step 24."""
    stmt = _current(
        select(OwnershipRecord, Owner)
        .join(Owner, Owner.id == OwnershipRecord.owner_id)
        .where(OwnershipRecord.parcel_id == parcel_pk),
        on,
    ).order_by(Owner.name)
    return [
        {"owner": owner.name, "owner_id": owner.external_id, "share": record.share}
        for record, owner in session.execute(stmt).all()
    ]


def get_parcel_by_external_id(session: Session, external_id: str) -> Parcel | None:
    return session.execute(
        select(Parcel).where(Parcel.external_id == external_id)
    ).scalar_one_or_none()


def count_holdings(session: Session, owner_id: str, on: date | None = None) -> int:
    on = on or date.today()
    stmt = _current(
        select(func.count(func.distinct(OwnershipRecord.parcel_id)))
        .where(OwnershipRecord.owner_id == owner_id),
        on,
    )
    return session.execute(stmt).scalar_one()
