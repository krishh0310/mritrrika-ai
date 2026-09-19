"""Vector parcel features for officers, through pg_featureserv (§11, §18).

GeoServer serves map tiles and has no idea who is asking. This route is the
authenticated door to the same published data as GeoJSON features: the JWT (or
API key) is checked here, the caller's jurisdiction becomes a CQL filter on the
request to pg_featureserv, and the features that come back are filtered again
before they leave -- so a filter pg_featureserv ignored or misread still
cannot widen what the caller sees.

pg_featureserv itself connects as geoserver_reader, which can SELECT the
published view and nothing else; only that one collection is proxied.
"""

from __future__ import annotations

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.dependencies import require
from app.config.settings import get_settings
from app.db import get_session
from app.models import Location
from app.services.auth_service import Principal, jurisdiction_location_ids

router = APIRouter(prefix="/api/v1/geo/features", tags=["gis"])

#: The only collection proxied: the ownership-free published view.
COLLECTIONS = {"gis_published_parcels": "public.gis_published_parcels"}


def _collection(name: str) -> str:
    table = COLLECTIONS.get(name) or COLLECTIONS.get(name.removeprefix("public."))
    if table is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"no collection {name}")
    return table


def _villages(session: Session, principal: Principal) -> set[str]:
    """External ids of the villages in the caller's jurisdiction."""
    allowed = jurisdiction_location_ids(session, principal) or set()
    return set(session.execute(
        select(Location.external_id).where(
            Location.id.in_(allowed), Location.level == "VILLAGE"
        )
    ).scalars())


def _fetch(path: str, params: dict | None = None) -> dict:
    try:
        response = httpx.get(f"{get_settings().pg_featureserv_url}{path}",
                             params=params, timeout=15)
    except httpx.HTTPError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE,
                            f"pg_featureserv unreachable: {exc}") from None
    if response.status_code == 404:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no such feature")
    if not response.is_success:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY,
                            f"pg_featureserv answered {response.status_code}")
    return response.json()


def _in_scope(feature: dict, villages: set[str]) -> bool:
    return (feature.get("properties") or {}).get("village_id") in villages


@router.get("/{collection}")
def features(
    collection: str,
    limit: int = Query(500, ge=1, le=5000),
    principal: Principal = Depends(require("gis:features")),
    session: Session = Depends(get_session),
) -> dict:
    """The collection's features within the caller's jurisdiction."""
    table = _collection(collection)
    villages = _villages(session, principal)
    if not villages:
        return {"type": "FeatureCollection", "features": [], "numberReturned": 0}
    quoted = ", ".join("'" + v.replace("'", "''") + "'" for v in sorted(villages))
    body = _fetch(f"/collections/{table}/items.json", {
        "filter": f"village_id IN ({quoted})", "filter-lang": "cql-text", "limit": limit,
    })
    kept = [f for f in body.get("features", []) if _in_scope(f, villages)]
    return {"type": "FeatureCollection", "features": kept, "numberReturned": len(kept)}


@router.get("/{collection}/{item_id}")
def feature(
    collection: str,
    item_id: str,
    principal: Principal = Depends(require("gis:features")),
    session: Session = Depends(get_session),
) -> dict:
    """One feature, if it lies in the caller's jurisdiction (404 otherwise)."""
    body = _fetch(f"/collections/{_collection(collection)}/items/{item_id}.json")
    if not _in_scope(body, _villages(session, principal)):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no such feature")
    return body
