"""Public record search and GIS (§17, §16, §53)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.auth.dependencies import require
from app.db import get_session
from app.services import search_service
from app.services.auth_service import Principal

router = APIRouter(prefix="/api/v1", tags=["records"])


@router.get("/records/search")
def search(
    village_id: str | None = None,
    khasra: str | None = None,
    khata: str | None = None,
    parcel_id: str | None = None,
    owner_name: str | None = None,
    limit: int = Query(50, ge=1, le=200),
    principal: Principal = Depends(require("record:search_public")),
    session: Session = Depends(get_session),
) -> dict:
    """Search APPROVED records only. Never exposes pipeline internals (§17)."""
    results = search_service.search_public_records(
        session, village_id=village_id, khasra=khasra, khata=khata,
        parcel_id=parcel_id, owner_name=owner_name, limit=limit,
    )
    return {"count": len(results), "results": results, "is_synthetic": True}


@router.get("/locations")
def locations(
    level: str | None = None,
    principal: Principal = Depends(require("gis:view")),
    session: Session = Depends(get_session),
) -> dict:
    return {"locations": search_service.locations(session, level)}


@router.get("/gis/villages/{village_id}/parcels")
def village_parcels(
    village_id: str,
    principal: Principal = Depends(require("gis:view")),
    session: Session = Depends(get_session),
) -> dict:
    return search_service.village_parcels(session, village_id)


@router.get("/gis/parcels")
def parcels_in_bounds(
    min_lon: float = Query(...), min_lat: float = Query(...),
    max_lon: float = Query(...), max_lat: float = Query(...),
    principal: Principal = Depends(require("gis:view")),
    session: Session = Depends(get_session),
) -> dict:
    """Viewport query -- bounded so panning never loads the whole cadastre."""
    return search_service.parcels_in_bounds(
        session, min_lon=min_lon, min_lat=min_lat, max_lon=max_lon, max_lat=max_lat
    )
