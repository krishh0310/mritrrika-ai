"""Role dashboards and analytics (§20, §27, §31, §55).

One route per role rather than a single `/dashboard?role=` endpoint: the shape
of each response differs, and the permission each demands differs. A DEO
cannot reach the tehsildar's analytics by changing a query string.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.auth.dependencies import require
from app.db import get_session
from app.services import dashboard_service
from app.services.auth_service import Principal

router = APIRouter(prefix="/api/v1/dashboard", tags=["dashboard"])


@router.get("/deo")
def deo(
    principal: Principal = Depends(require("document:upload")),
    session: Session = Depends(get_session),
) -> dict:
    return dashboard_service.deo_dashboard(session, principal)


@router.get("/verifier")
def verifier(
    principal: Principal = Depends(require("document:verify")),
    session: Session = Depends(get_session),
) -> dict:
    return dashboard_service.verifier_dashboard(session, principal)


@router.get("/tehsildar")
def tehsildar(
    principal: Principal = Depends(require("document:approve")),
    session: Session = Depends(get_session),
) -> dict:
    return dashboard_service.tehsildar_dashboard(session, principal)


@router.get("/analytics")
def analytics(
    principal: Principal = Depends(require("analytics:view")),
    session: Session = Depends(get_session),
) -> dict:
    """Distributions for the tehsildar's charts. Tehsildar-only (§36)."""
    return dashboard_service.analytics(session, principal)
