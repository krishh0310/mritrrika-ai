"""Mrittika AI API (§5).

The single authoritative backend for the web and mobile clients. Business
rules live here, never in a frontend.
"""

from __future__ import annotations

import time

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.config.settings import get_settings
from app.db import SessionLocal, engine
from app.routers import (
    ai,
    anomalies,
    audit,
    auth,
    citizen,
    dashboard,
    documents,
    grievances,
    records,
    workflow,
)
from app.services import metrics_service

settings = get_settings()

app = FastAPI(
    title="Mrittika AI",
    description=(
        "Intelligent digitization for India's land records. "
        "ALL DATA IN THIS DEPLOYMENT IS SYNTHETIC DEMO DATA."
    ),
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,   # allowlist, never "*" (§61)
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
)


@app.middleware("http")
async def record_request_metrics(request: Request, call_next) -> Response:
    """Time every request for /metrics (§74).

    An unhandled exception is counted as a 500 before being re-raised, so the
    error rate reflects crashes and not only handled failures.
    """
    started = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception:
        metrics_service.requests.observe(500, time.perf_counter() - started)
        raise
    metrics_service.requests.observe(
        response.status_code, time.perf_counter() - started
    )
    return response


app.include_router(auth.router)
app.include_router(citizen.router)
app.include_router(documents.router)
app.include_router(workflow.verification_router)
app.include_router(workflow.approval_router)
app.include_router(grievances.router)
app.include_router(dashboard.router)
app.include_router(anomalies.router)
app.include_router(audit.router)
app.include_router(records.router)
app.include_router(ai.router)


@app.get("/health", tags=["ops"])
def health() -> dict:
    """Liveness -- does the process answer at all (§74)."""
    return {"status": "ok", "environment": settings.environment}


@app.get("/ready", tags=["ops"])
def ready() -> dict:
    """Readiness -- can we actually serve traffic (§74).

    Checks the database AND that both required extensions are present, since a
    database missing postgis or pgvector will fail later in a confusing way.
    """
    checks: dict[str, str] = {}
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
            extensions = set(
                conn.execute(
                    text("SELECT extname FROM pg_extension")
                ).scalars()
            )
        checks["database"] = "ok"
        checks["postgis"] = "ok" if "postgis" in extensions else "missing"
        checks["pgvector"] = "ok" if "vector" in extensions else "missing"
    except Exception as exc:  # pragma: no cover - depends on infra state
        checks["database"] = f"error: {exc.__class__.__name__}"

    ready_now = all(v == "ok" for v in checks.values())
    return {"ready": ready_now, "checks": checks}


@app.get("/metrics", tags=["ops"])
def metrics() -> Response:
    """Prometheus exposition (§74).

    Unauthenticated, like /health and /ready: it carries counts and latencies,
    never record content. Restrict it at the ingress in a real deployment.
    """
    with SessionLocal() as session:
        body = metrics_service.render(session)
    return Response(content=body, media_type="text/plain; version=0.0.4")
