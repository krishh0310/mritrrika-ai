"""DILRMP connector: push an approved record, fetch cadastre geometry (§14).

No public DILRMP sandbox exists and access needs a state-level MOU, so with
DILRMP_ENDPOINT unset this runs in MOCK mode: it builds the exact payload it
would send, sends nothing, and says "mock" -- never a fake success. Set the
endpoint and the same code POSTs. See docs/dilrmp-integration.md.

The XML element names are this system's mapping of the Record of Rights fields
DILRMP carries; no published NIC schema was available to validate against, so
they are to be confirmed with the receiving state before go-live.
"""

from __future__ import annotations

import logging
import xml.etree.ElementTree as ET
from datetime import UTC, datetime

logger = logging.getLogger(__name__)

NAME = "dilrmp"
TIMEOUT = 15.0


def _settings():
    from app.config.settings import get_settings

    return get_settings()


def ror_fields(record_id: str) -> dict:
    """The RoR fields for an approved document, from the system of record."""
    from mrittika_domain.area import SQM_PER_HECTARE

    from app.db import SessionLocal
    from app.services import lrms_service
    from app.services.document_service import get_by_external_id

    with SessionLocal() as session:
        payload = lrms_service.ror_payload(session, get_by_external_id(session, record_id))
    parcel, where = payload["parcel"], payload["location"]
    sqm = parcel["area"]["square_metres"]
    mutations = [h["mutation_number"] for h in payload["holders"] if h["mutation_number"]]
    return {
        "record_id": record_id,
        "khata_number": parcel["khata_number"],
        "khasra_number": parcel["survey_number"],
        "owner_name": "; ".join(h["owner"] for h in payload["holders"]),
        "area_hectares": round(sqm / SQM_PER_HECTARE, 4) if sqm is not None else None,
        "mutation_number": mutations[-1] if mutations else None,
        "tehsil_code": (where["tehsil"] or {}).get("code"),
        "district_code": (where["district"] or {}).get("code"),
        "state_code": (where["state"] or {}).get("code"),
    }


def to_xml(fields: dict) -> bytes:
    root = ET.Element("RecordOfRights")
    for key, value in fields.items():
        ET.SubElement(root, key).text = "" if value is None else str(value)
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def push_record(record_id: str) -> dict:
    """POST the record's RoR XML to DILRMP, or return a mock receipt."""
    import httpx

    settings = _settings()
    body = to_xml(ror_fields(record_id))
    if not settings.dilrmp_endpoint:
        logger.warning("DILRMP_ENDPOINT not set; %s not sent (mock mode)", record_id)
        return {"status": "mock", "transaction_id": f"MOCK-{record_id}",
                "submitted_at": datetime.now(UTC).isoformat()}
    response = httpx.post(
        f"{settings.dilrmp_endpoint.rstrip('/')}/ror", content=body, timeout=TIMEOUT,
        headers={"Content-Type": "application/xml",
                 "X-API-Key": settings.dilrmp_api_key or ""},
    )
    response.raise_for_status()
    return {"status": "delivered",
            "transaction_id": response.headers.get("X-Transaction-Id") or response.text[:64],
            "submitted_at": datetime.now(UTC).isoformat()}


def fetch_cadastre(survey_number: str) -> dict:
    """Parcel geometry from DILRMP as GeoJSON, or a marked mock polygon."""
    import httpx

    settings = _settings()
    if not settings.dilrmp_endpoint:
        return {
            "type": "Feature",
            "properties": {"survey_number": survey_number, "mock_data": True},
            "geometry": {"type": "Polygon", "coordinates": [[
                [80.9000, 26.8000], [80.9010, 26.8000], [80.9010, 26.8008],
                [80.9000, 26.8008], [80.9000, 26.8000],
            ]]},
        }
    response = httpx.get(
        f"{settings.dilrmp_endpoint.rstrip('/')}/cadastre/{survey_number}",
        headers={"X-API-Key": settings.dilrmp_api_key or ""}, timeout=TIMEOUT,
    )
    response.raise_for_status()
    return response.json()


def health_check() -> dict:
    settings = _settings()
    if not settings.dilrmp_endpoint:
        return {"connected": False, "reason": "DILRMP_ENDPOINT not configured"}
    return {"connected": True, "endpoint": settings.dilrmp_endpoint}


__all__ = ["NAME", "fetch_cadastre", "health_check", "push_record", "ror_fields", "to_xml"]
