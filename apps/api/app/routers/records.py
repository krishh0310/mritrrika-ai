"""Public record search and GIS (§17, §16, §53)."""

from __future__ import annotations

import csv
import io

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session

from app.auth.dependencies import require
from app.db import get_session
from app.services import audit_service, dashboard_service, embedding_service, search_service
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


@router.get("/records/semantic-search")
def semantic_search(
    q: str = Query(..., min_length=2, max_length=300),
    limit: int = Query(10, ge=1, le=50),
    principal: Principal = Depends(require("record:search_public")),
    session: Session = Depends(get_session),
) -> dict:
    """Approved records nearest a free-text description, via pgvector.

    Same scope and fields as /records/search; owner names are not indexed.
    """
    results = embedding_service.search(session, q, limit)
    return {"count": len(results), "results": results, "is_synthetic": True}


@router.get("/research/export.csv")
def research_export(
    principal: Principal = Depends(require("research:export")),
    session: Session = Depends(get_session),
) -> Response:
    """Anonymised per-parcel data for research institutions, as CSV.

    See dashboard_service.research_rows for what is removed and why. Every
    export is audited: this is data leaving the system.
    """
    rows = dashboard_service.research_rows(session, principal)
    out = io.StringIO()
    writer = csv.DictWriter(out, fieldnames=dashboard_service.RESEARCH_COLUMNS)
    writer.writeheader()
    writer.writerows(rows)
    audit_service.record(
        session, action="research.export", entity_type="dataset", entity_id="parcels",
        actor_id=principal.id, actor_role=principal.primary_role,
        after_state={"rows": len(rows), "columns": list(dashboard_service.RESEARCH_COLUMNS)},
    )
    session.commit()
    return Response(
        out.getvalue(), media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="mrittika-parcels-anonymised.csv"'},
    )
