"""Citizen portal endpoints (§14-§18).

Every route derives the caller's owner identity from the session. None accepts
an owner_id, and none accepts a parcel id without passing it through
`assert_can_access_parcel` first (§62).
"""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from sqlalchemy.orm import Session

from app.auth.dependencies import require, require_role
from app.db import get_session
from app.services.auth_service import Principal
from app.services.citizen_service import (
    ParcelAccessDenied,
    assert_can_access_parcel,
    dashboard_summary,
    my_holdings,
    owners_on_date,
    ownership_history,
)

router = APIRouter(prefix="/api/v1/citizen", tags=["citizen"])

FORBIDDEN = HTTPException(
    status_code=status.HTTP_403_FORBIDDEN,
    detail="You do not have access to this parcel",
)

#: Parcel ids are opaque uppercase-alphanumeric handles. Validating the shape
#: at the boundary means malformed input is rejected with 422 before it can
#: reach the database -- a NUL byte in the path previously surfaced as an
#: unhandled psycopg DataError (HTTP 500).
ParcelId = Path(
    ...,
    min_length=3,
    max_length=64,
    pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]*$",
    description="Opaque parcel identifier",
)


@router.get("/dashboard")
def dashboard(
    principal: Principal = Depends(require_role("CITIZEN")),
    session: Session = Depends(get_session),
) -> dict:
    return dashboard_summary(session, principal)


@router.get("/my-parcels")
def my_parcels(
    principal: Principal = Depends(require("parcel:view_own")),
    session: Session = Depends(get_session),
) -> dict:
    """§15 -- only parcels linked to the caller's own owner identity."""
    holdings = my_holdings(session, principal)
    return {"count": len(holdings), "parcels": holdings, "is_synthetic": True}


@router.get("/parcels/{parcel_id}")
def parcel_detail(
    parcel_id: str = ParcelId,
    principal: Principal = Depends(require("parcel:view_own")),
    session: Session = Depends(get_session),
) -> dict:
    try:
        parcel = assert_can_access_parcel(session, principal, parcel_id)
    except ParcelAccessDenied:
        raise FORBIDDEN from None

    return {
        "parcel_id": parcel.external_id,
        "khasra_number": parcel.khasra_number,
        "khata_number": parcel.khata_number,
        "area_value": parcel.area_value,
        "area_unit": parcel.area_unit,
        "area_unit_raw": parcel.area_unit_raw,
        "land_class": parcel.land_class,
        "is_synthetic": parcel.is_synthetic,
        # Deliberately absent for citizens (§17): raw OCR, confidence scores,
        # verification notes, internal anomaly scores.
    }


@router.get("/parcels/{parcel_id}/ownership-history")
def parcel_ownership_history(
    parcel_id: str = ParcelId,
    principal: Principal = Depends(require("record:view_own")),
    session: Session = Depends(get_session),
) -> dict:
    try:
        history = ownership_history(session, principal, parcel_id)
    except ParcelAccessDenied:
        raise FORBIDDEN from None
    return {"parcel_id": parcel_id, "history": history, "is_synthetic": True}


@router.get("/parcels/{parcel_id}/owners-on")
def parcel_owners_on(
    parcel_id: str = ParcelId,
    on: date = Query(..., description="Date to query ownership as of"),
    principal: Principal = Depends(require("record:view_own")),
    session: Session = Depends(get_session),
) -> dict:
    """'Who was the recorded owner in 1998?' -- demo step 24."""
    try:
        owners = owners_on_date(session, principal, parcel_id, on)
    except ParcelAccessDenied:
        raise FORBIDDEN from None
    return {"parcel_id": parcel_id, "as_of": on, "owners": owners, "is_synthetic": True}
