"""Push approved records to external systems, and report on it (§14)."""

from __future__ import annotations

import logging

from sqlalchemy import select

from app.integrations import dilrmp_connector, lrms_connector
from app.models import IntegrationLog

logger = logging.getLogger(__name__)

CONNECTORS = {dilrmp_connector.NAME: dilrmp_connector, lrms_connector.NAME: lrms_connector}


def push_on_approval(record_id: str, session_factory=None) -> IntegrationLog:
    """Send an approved record to DILRMP and log the attempt. Never raises.

    Called AFTER the approval has committed: an unreachable state server must
    neither delay nor undo an approval. A failure is logged and left for
    retry, not surfaced to the tehsildar as a failed approval.
    """
    if session_factory is None:
        from app.db import SessionLocal as session_factory

    try:
        receipt = dilrmp_connector.push_record(record_id)
        status, error = receipt["status"], None
    except Exception as exc:
        logger.exception("DILRMP push failed for %s", record_id)
        status, error = "failed", str(exc)[:2000]

    entry = IntegrationLog(connector=dilrmp_connector.NAME, record_id=record_id,
                           status=status, error=error)
    try:
        with session_factory() as session:
            session.add(entry)
            session.commit()
            session.refresh(entry)
    except Exception:
        logger.exception("could not record the DILRMP attempt for %s", record_id)
    return entry


def status(session) -> dict:
    """Each connector's health and its last five attempts."""
    report = {}
    for name, connector in CONNECTORS.items():
        recent = session.execute(
            select(IntegrationLog).where(IntegrationLog.connector == name)
            .order_by(IntegrationLog.attempted_at.desc()).limit(5)
        ).scalars().all()
        report[name] = {
            "health": connector.health_check(),
            "recent": [{"record_id": r.record_id, "status": r.status, "error": r.error,
                        "attempted_at": r.attempted_at.isoformat()} for r in recent],
        }
    return report
