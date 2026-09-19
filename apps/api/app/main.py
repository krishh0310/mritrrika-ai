"""Mrittika AI API (§5).

The single authoritative backend for the web and mobile clients. Business
rules live here, never in a frontend.
"""

from __future__ import annotations

import hmac
import json
import logging
import re
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.config.settings import get_settings
from app.db import SessionLocal, engine
from app.repositories import user_repository
from app.routers import (
    ai,
    anomalies,
    audit,
    auth,
    citizen,
    dashboard,
    documents,
    geo,
    grievances,
    integrations,
    records,
    workflow,
)
from app.security.tokens import TokenError, decode_token
from app.services import metrics_service
from app.services.auth_service import build_principal

settings = get_settings()
logger = logging.getLogger("mrittika.access")

REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")

@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Start the nightly retrain check with the API (once per process)."""
    if settings.retrain_scheduler_enabled:
        from app.tasks import retrain_scheduler

        _app.state.scheduler = retrain_scheduler.start()
    yield


app = FastAPI(
    lifespan=lifespan,
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
    """Correlate, harden and time every request (§61, §74).

    An unhandled exception is counted as a 500 before being re-raised, so the
    error rate reflects crashes and not only handled failures.
    """
    supplied_request_id = request.headers.get("x-request-id", "")
    request_id = (
        supplied_request_id
        if REQUEST_ID_PATTERN.fullmatch(supplied_request_id)
        else uuid.uuid4().hex
    )
    request.state.request_id = request_id
    started = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception:
        elapsed = time.perf_counter() - started
        metrics_service.requests.observe(500, elapsed)
        logger.exception(
            json.dumps(
                {
                    "event": "http_request",
                    "request_id": request_id,
                    "method": request.method,
                    "path": request.url.path,
                    "status": 500,
                    "duration_ms": round(elapsed * 1000, 2),
                },
                separators=(",", ":"),
            )
        )
        raise
    elapsed = time.perf_counter() - started
    metrics_service.requests.observe(response.status_code, elapsed)

    response.headers["X-Request-ID"] = request_id
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    if request.url.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store"
    if settings.environment.casefold() == "production":
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"

    logger.info(
        json.dumps(
            {
                "event": "http_request",
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
                "status": response.status_code,
                "duration_ms": round(elapsed * 1000, 2),
            },
            separators=(",", ":"),
        )
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
app.include_router(integrations.router)
app.include_router(geo.router)


@app.get("/health", tags=["ops"])
def health() -> dict:
    """Liveness -- does the process answer at all (§74)."""
    return {"status": "ok", "environment": settings.environment}


@app.get("/ready", tags=["ops"])
def ready(response: Response) -> dict:
    """Readiness -- can we actually serve traffic (§74).

    Checks the database AND that both required extensions are present, since a
    database missing postgis or pgvector will fail later in a confusing way.

    Not ready is a 503, not a 200 with `"ready": false` in the body: load
    balancers, orchestrators and uptime checks read the status code, and the
    200 reported an API with no database as healthy.
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
    if not ready_now:
        response.status_code = 503
    return {"ready": ready_now, "checks": checks}


def _metrics_authorised(request: Request) -> None:
    """Let Prometheus in on a token, or an officer in on their permission.

    Two ways in and no third. Operational metrics reveal workload, queue depth
    and processing state, so this endpoint is never public.

    The token exists because Prometheus cannot hold a JWT: it has no login and
    its bearer credentials are static. With METRICS_SCRAPE_TOKEN unset there is
    no token path at all -- the safe default, where a misconfigured scraper
    fails to authenticate instead of silently publishing the exposition.
    """
    settings = get_settings()
    expected = settings.metrics_scrape_token
    presented = (request.headers.get("authorization") or "")
    presented = presented.removeprefix("Bearer ").strip()

    # compare_digest, not ==: an early-exit comparison leaks the token's length
    # and prefix to anyone who can time the response.
    if expected and hmac.compare_digest(presented, expected):
        return

    # Otherwise the caller must be an officer. current_principal raises 401 on
    # a bad or absent token, and this raises 403 on a valid one without the
    # permission -- so a scraper with a stale token gets a real error rather
    # than an empty body.
    with SessionLocal() as session:
        try:
            payload = decode_token(presented)
            user = user_repository.get_by_id(session, payload["sub"])
        except (TokenError, KeyError):
            user = None
        if user is None or not user.is_active:
            raise HTTPException(
                status_code=401, detail="Not authenticated",
                headers={"WWW-Authenticate": "Bearer"},
            )
        principal = build_principal(session, user)

    if not principal.has("analytics:view"):
        raise HTTPException(status_code=403, detail="Missing permission(s): analytics:view")


@app.get("/metrics", tags=["ops"])
def metrics(request: Request) -> Response:
    """Prometheus exposition (§74)."""
    _metrics_authorised(request)
    with SessionLocal() as session:
        body = metrics_service.render(session)
    return Response(content=body, media_type="text/plain; version=0.0.4")
