"""State LRMS connector, in the shape of an LRMS mutation API (§14).

Same contract as dilrmp_connector: mock mode while LRMS_ENDPOINT is unset,
never a fabricated success. Bulk delivery of approved Records of Rights runs
through the LRMS outbox (lrms_service, docs/lrms-integration.md); this is the
record-at-a-time API a state mutation system exposes.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

logger = logging.getLogger(__name__)

NAME = "lrms"
TIMEOUT = 15.0


def _settings():
    from app.config.settings import get_settings

    return get_settings()


def _headers() -> dict:
    return {"Authorization": f"Bearer {_settings().lrms_api_key or ''}"}


def push_record(record_id: str) -> dict:
    """POST the record as a mutation entry, or return a mock receipt."""
    import httpx

    from app.integrations.dilrmp_connector import ror_fields

    settings = _settings()
    fields = ror_fields(record_id)
    if not settings.lrms_endpoint:
        logger.warning("LRMS_ENDPOINT not set; %s not sent (mock mode)", record_id)
        return {"status": "mock", "transaction_id": f"MOCK-{record_id}",
                "submitted_at": datetime.now(UTC).isoformat()}
    response = httpx.post(f"{settings.lrms_endpoint.rstrip('/')}/mutations", json=fields,
                          headers=_headers(), timeout=TIMEOUT)
    response.raise_for_status()
    body = response.json() if response.content else {}
    return {"status": "delivered", "transaction_id": str(body.get("mutation_id", "")),
            "submitted_at": datetime.now(UTC).isoformat()}


def fetch_record(record_id: str) -> dict:
    import httpx

    settings = _settings()
    if not settings.lrms_endpoint:
        return {"record_id": record_id, "mock_data": True}
    response = httpx.get(f"{settings.lrms_endpoint.rstrip('/')}/mutations/{record_id}",
                         headers=_headers(), timeout=TIMEOUT)
    response.raise_for_status()
    return response.json()


def health_check() -> dict:
    settings = _settings()
    if not settings.lrms_endpoint:
        return {"connected": False, "reason": "LRMS_ENDPOINT not configured"}
    return {"connected": True, "endpoint": settings.lrms_endpoint}


__all__ = ["NAME", "fetch_record", "health_check", "push_record"]
