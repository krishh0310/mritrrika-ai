"""§41 -- the audit chain must actually detect tampering.

A verifier that always returns 'valid' is worse than none: it manufactures
confidence. Each test here mutates the log in a different way and asserts the
chain notices.
"""

import sys
from pathlib import Path

import pytest
from sqlalchemy import select

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "apps" / "api"))

pytestmark = pytest.mark.integration


@pytest.fixture
def session():
    import psycopg
    from dotenv import load_dotenv

    load_dotenv(REPO_ROOT / ".env")
    from app.config.settings import get_settings
    from app.db import SessionLocal

    try:
        psycopg.connect(
            get_settings().sqlalchemy_url.replace("postgresql+psycopg", "postgresql"),
            connect_timeout=3,
        ).close()
    except Exception as exc:  # pragma: no cover
        pytest.skip(f"postgres unavailable ({exc})")

    with SessionLocal() as s:
        yield s


def test_chain_is_valid_when_untouched(session):
    from app.services import audit_service

    result = audit_service.verify_chain(session)
    assert result["valid"] is True, result["problems"][:5]
    assert result["events"] > 0, "no audit events -- run the E2E test first"


def test_it_is_a_hash_chain_not_a_blockchain(session):
    """§69 -- capability must be described accurately."""
    from app.services import audit_service

    assert audit_service.verify_chain(session)["mechanism"] == "sha256-hash-chain"


def test_editing_an_event_breaks_verification(session):
    """The core property: altered contents no longer match the stored hash."""
    from app.models import AuditEvent
    from app.services import audit_service

    event = session.execute(
        select(AuditEvent).order_by(AuditEvent.sequence).limit(1)
    ).scalar_one_or_none()
    if event is None:
        pytest.skip("no audit events")

    original = event.action
    event.action = "document.tampered"
    session.flush()
    try:
        result = audit_service.verify_chain(session)
        assert result["valid"] is False, "editing an event went undetected!"
        assert any(p["issue"] == "hash_mismatch" for p in result["problems"])
    finally:
        event.action = original
        session.rollback()


def test_removing_an_event_breaks_verification(session):
    """Deletion must be detectable, not merely editing."""
    from app.models import AuditEvent
    from app.services import audit_service

    events = list(session.execute(
        select(AuditEvent).order_by(AuditEvent.sequence).limit(3)
    ).scalars())
    if len(events) < 3:
        pytest.skip("need at least three audit events")

    session.delete(events[1])
    session.flush()
    try:
        result = audit_service.verify_chain(session)
        assert result["valid"] is False, "deleting an event went undetected!"
        issues = {p["issue"] for p in result["problems"]}
        assert issues & {"sequence_gap", "broken_link"}, issues
    finally:
        session.rollback()


def test_relinking_an_event_breaks_verification(session):
    from app.models import AuditEvent
    from app.services import audit_service

    event = session.execute(
        select(AuditEvent).order_by(AuditEvent.sequence).offset(1).limit(1)
    ).scalar_one_or_none()
    if event is None:
        pytest.skip("need at least two audit events")

    original = event.previous_hash
    event.previous_hash = "0" * 64
    session.flush()
    try:
        result = audit_service.verify_chain(session)
        assert result["valid"] is False, "re-linking went undetected!"
    finally:
        event.previous_hash = original
        session.rollback()


def test_canonicalisation_is_stable(session):
    """Hashing depends on byte-identical canonical JSON.

    If key order or separators ever change, every historical event fails
    verification -- so the format is pinned by this test.
    """
    from app.services.audit_hash import canonicalize

    a = canonicalize({"b": 1, "a": {"d": 2, "c": [3, 4]}})
    b = canonicalize({"a": {"c": [3, 4], "d": 2}, "b": 1})
    assert a == b
    assert a == '{"a":{"c":[3,4],"d":2},"b":1}'


def test_devanagari_survives_canonicalisation(session):
    from app.services.audit_hash import canonicalize

    assert "रामपुर" in canonicalize({"village": "रामपुर"})


def test_concurrent_appends_keep_one_chain(session, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    from time import sleep
    from uuid import uuid4

    from app.db import SessionLocal
    from app.services import audit_service

    original = audit_service._last_event
    ready = Barrier(2)
    entity_id = f"synthetic-concurrency-{uuid4()}"

    def delayed_head(s):
        head = original(s)
        # Widen the read/append race that previously produced duplicate sequences.
        sleep(0.1)
        return head

    monkeypatch.setattr(audit_service, "_last_event", delayed_head)

    def append(index):
        with SessionLocal() as s:
            ready.wait(timeout=5)
            event = audit_service.record(
                s, action="test.concurrent", entity_type="synthetic-test",
                entity_id=entity_id, after_state={"writer": index},
            )
            result = (event.sequence, event.previous_hash, event.event_hash)
            s.commit()
            return result

    with ThreadPoolExecutor(max_workers=2) as pool:
        events = sorted(pool.map(append, range(2)))
    assert events[1][0] == events[0][0] + 1
    assert events[1][1] == events[0][2]
    assert audit_service.verify_chain(session)["valid"]
