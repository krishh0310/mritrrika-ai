"""Append-only, tamper-evident audit log (§41).

Every sensitive action records who did what to which entity, with the state
before and after. Verification recomputes the whole chain, so a row that was
edited or deleted is detectable and the report says exactly where.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import AuditEvent
from app.services.audit_hash import GENESIS_HASH, compute_event_hash

#: Actions worth recording (§41).
UPLOAD = "document.upload"
QUALITY_CHECK = "document.quality_check"
PROCESSING_STARTED = "document.processing_started"
PROCESSING_COMPLETED = "document.processing_completed"
PROCESSING_FAILED = "document.processing_failed"
EXTRACTION_CORRECTED = "extraction.corrected"
VERIFICATION_SUBMITTED = "document.verified"
APPROVED = "document.approved"
REJECTED = "document.rejected"
RETURNED = "document.returned"
STATE_CHANGED = "document.state_changed"
DOWNLOAD = "document.download"
GRIEVANCE_CREATED = "grievance.created"
LOGIN = "auth.login"


def _last_event(session: Session) -> AuditEvent | None:
    return session.execute(
        select(AuditEvent).order_by(AuditEvent.sequence.desc()).limit(1)
    ).scalar_one_or_none()


def record(
    session: Session,
    *,
    action: str,
    entity_type: str,
    entity_id: str,
    actor_id: str | None = None,
    actor_role: str | None = None,
    before_state: dict | None = None,
    after_state: dict | None = None,
    reason: str | None = None,
    flush: bool = True,
) -> AuditEvent:
    """Append one event, chained to its predecessor.

    Deliberately does NOT commit: the audit row must land in the same
    transaction as the change it describes, so a rolled-back action cannot
    leave an audit entry claiming it happened.
    """
    previous = _last_event(session)
    sequence = (previous.sequence + 1) if previous else 1
    previous_hash = previous.event_hash if previous else GENESIS_HASH
    timestamp = datetime.now(UTC).isoformat()

    event_hash = compute_event_hash(
        sequence=sequence,
        timestamp=timestamp,
        actor_id=actor_id,
        actor_role=actor_role,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        before_state=before_state,
        after_state=after_state,
        reason=reason,
        previous_hash=previous_hash,
    )

    event = AuditEvent(
        sequence=sequence,
        actor_id=actor_id,
        actor_role=actor_role,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        before_state=before_state,
        after_state=after_state,
        reason=reason,
        previous_hash=previous_hash,
        event_hash=event_hash,
    )
    # The canonical timestamp is the one that was hashed, so store it verbatim
    # rather than relying on the column default.
    event.created_at = datetime.fromisoformat(timestamp)
    session.add(event)
    if flush:
        session.flush()
    return event


def timeline_for(session: Session, entity_type: str, entity_id: str) -> list[AuditEvent]:
    """Every event touching one entity, oldest first (§32 audit timeline)."""
    return list(
        session.execute(
            select(AuditEvent)
            .where(AuditEvent.entity_type == entity_type, AuditEvent.entity_id == entity_id)
            .order_by(AuditEvent.sequence)
        ).scalars()
    )


def verify_chain(session: Session, limit: int | None = None) -> dict:
    """Recompute the whole chain and report the first break.

    Detects three distinct tampering modes:
      - a field was edited      -> recomputed hash differs
      - a row was deleted       -> sequence gap, and the link no longer matches
      - a row was re-linked     -> previous_hash does not match the predecessor
    """
    stmt = select(AuditEvent).order_by(AuditEvent.sequence)
    if limit:
        stmt = stmt.limit(limit)
    events = list(session.execute(stmt).scalars())

    if not events:
        return {"valid": True, "events": 0, "problems": []}

    problems: list[dict] = []
    expected_previous = GENESIS_HASH
    expected_sequence = 1

    for event in events:
        if event.sequence != expected_sequence:
            problems.append(
                {
                    "sequence": event.sequence,
                    "issue": "sequence_gap",
                    "detail": f"expected sequence {expected_sequence}, found {event.sequence}",
                }
            )
            expected_sequence = event.sequence

        if event.previous_hash != expected_previous:
            problems.append(
                {
                    "sequence": event.sequence,
                    "issue": "broken_link",
                    "detail": "previous_hash does not match the preceding event",
                }
            )

        recomputed = compute_event_hash(
            sequence=event.sequence,
            timestamp=event.created_at.isoformat(),
            actor_id=event.actor_id,
            actor_role=event.actor_role,
            action=event.action,
            entity_type=event.entity_type,
            entity_id=event.entity_id,
            before_state=event.before_state,
            after_state=event.after_state,
            reason=event.reason,
            previous_hash=event.previous_hash,
        )
        if recomputed != event.event_hash:
            problems.append(
                {
                    "sequence": event.sequence,
                    "issue": "hash_mismatch",
                    "detail": "event contents do not match the stored hash",
                }
            )

        expected_previous = event.event_hash
        expected_sequence += 1

    return {
        "valid": not problems,
        "events": len(events),
        "problems": problems,
        # Explicitly not called a blockchain (§69).
        "mechanism": "sha256-hash-chain",
    }


def count(session: Session) -> int:
    return session.scalar(select(func.count()).select_from(AuditEvent)) or 0
