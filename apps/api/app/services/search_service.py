"""Record search and GIS reads (§17, §11).

Citizen search is restricted to APPROVED, publicly-safe fields. It never
returns raw OCR, confidence, verification notes, pending documents or internal
anomaly scores (§17) -- those columns are simply not selected here, rather than
being fetched and filtered later where a refactor could leak them.
"""

from __future__ import annotations

from geoalchemy2.functions import ST_AsGeoJSON, ST_Intersects, ST_MakeEnvelope
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.models import LandRecord, Location, Parcel

#: Hard ceiling so an unbounded query cannot pull the whole cadastre (§84).
MAX_RESULTS = 200


def _village_lookup(session: Session) -> dict[str, Location]:
    return {
        loc.id: loc
        for loc in session.execute(
            select(Location).where(Location.level == "VILLAGE")
        ).scalars()
    }


def search_public_records(
    session: Session,
    *,
    village_id: str | None = None,
    khasra: str | None = None,
    khata: str | None = None,
    parcel_id: str | None = None,
    owner_name: str | None = None,
    limit: int = 50,
) -> list[dict]:
    """Search APPROVED records only (§17).

    `owner_name` searches the record set, which is public information in a land
    register. It does NOT return contact details or any citizen account data.
    """
    limit = min(limit, MAX_RESULTS)

    stmt = (
        select(Parcel, Location)
        .join(Location, Location.id == Parcel.village_id)
        .join(LandRecord, LandRecord.parcel_id == Parcel.id)
        .where(LandRecord.status == "APPROVED")
    )

    if village_id:
        stmt = stmt.where(Location.external_id == village_id)
    if khasra:
        stmt = stmt.where(Parcel.khasra_number == khasra)
    if khata:
        stmt = stmt.where(Parcel.khata_number == khata)
    if parcel_id:
        stmt = stmt.where(Parcel.external_id == parcel_id)
    if owner_name:
        from app.models import Owner, OwnershipRecord

        stmt = (
            stmt.join(OwnershipRecord, OwnershipRecord.parcel_id == Parcel.id)
            .join(Owner, Owner.id == OwnershipRecord.owner_id)
            .where(
                or_(
                    Owner.name.ilike(f"%{owner_name}%"),
                    # Trigram similarity catches transliteration variants,
                    # which are endemic in Indian land records.
                    func.similarity(Owner.name, owner_name) > 0.3,
                ),
                OwnershipRecord.valid_to.is_(None),
            )
        )

    stmt = stmt.distinct().order_by(Parcel.khasra_number).limit(limit)

    return [
        {
            "parcel_id": parcel.external_id,
            "khasra_number": parcel.khasra_number,
            "khata_number": parcel.khata_number,
            "village": village.name_devanagari or village.name,
            "village_id": village.external_id,
            "area_value": parcel.area_value,
            "area_unit": parcel.area_unit,
            "land_class": parcel.land_class,
            "is_synthetic": parcel.is_synthetic,
            # Deliberately absent: raw_value, confidences, verification notes,
            # anomaly scores, document state (§17).
        }
        for parcel, village in session.execute(stmt).all()
    ]


def parcels_in_bounds(
    session: Session,
    *,
    min_lon: float, min_lat: float, max_lon: float, max_lat: float,
    limit: int = MAX_RESULTS,
) -> dict:
    """Parcels intersecting a map viewport, as GeoJSON (§16, §84).

    Bounded by a spatial envelope so panning a map never loads the whole
    cadastre.
    """
    envelope = ST_MakeEnvelope(min_lon, min_lat, max_lon, max_lat, 4326)
    stmt = (
        select(Parcel, Location, ST_AsGeoJSON(Parcel.geometry))
        .join(Location, Location.id == Parcel.village_id)
        .where(Parcel.geometry.isnot(None), ST_Intersects(Parcel.geometry, envelope))
        .limit(min(limit, MAX_RESULTS))
    )

    features = []
    for parcel, village, geojson in session.execute(stmt).all():
        import json

        features.append(
            {
                "type": "Feature",
                "geometry": json.loads(geojson),
                "properties": {
                    "parcel_id": parcel.external_id,
                    "khasra_number": parcel.khasra_number,
                    "village": village.name_devanagari or village.name,
                    "area_value": parcel.area_value,
                    "area_unit": parcel.area_unit,
                    "land_class": parcel.land_class,
                    "is_synthetic": True,
                    "notice": "DEMO / SYNTHETIC DATA",
                },
            }
        )
    return {"type": "FeatureCollection", "features": features}


def village_parcels(session: Session, village_external_id: str) -> dict:
    import json

    stmt = (
        select(Parcel, ST_AsGeoJSON(Parcel.geometry))
        .join(Location, Location.id == Parcel.village_id)
        .where(Location.external_id == village_external_id, Parcel.geometry.isnot(None))
    )
    features = [
        {
            "type": "Feature",
            "geometry": json.loads(geojson),
            "properties": {
                "parcel_id": parcel.external_id,
                "khasra_number": parcel.khasra_number,
                "area_value": parcel.area_value,
                "area_unit": parcel.area_unit,
                "land_class": parcel.land_class,
                "is_synthetic": True,
                "notice": "DEMO / SYNTHETIC DATA",
            },
        }
        for parcel, geojson in session.execute(stmt).all()
    ]
    return {"type": "FeatureCollection", "features": features}


def locations(session: Session, level: str | None = None) -> list[dict]:
    stmt = select(Location)
    if level:
        stmt = stmt.where(Location.level == level)
    return [
        {
            "location_id": loc.external_id,
            "name": loc.name,
            "name_devanagari": loc.name_devanagari,
            "level": loc.level,
        }
        for loc in session.execute(stmt.order_by(Location.level, Location.name)).scalars()
    ]
