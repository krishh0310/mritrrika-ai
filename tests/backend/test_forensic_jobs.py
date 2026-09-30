"""Forensic jobs fail closed before provider work and expose bounded progress."""
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from app.services import forensic_service as fs


def test_revoked_authority_prevents_provider_calls(monkeypatch):
    job = SimpleNamespace(status="QUEUED", actor_id="u", document_id="d", progress=0)
    session = Mock()
    session.get.side_effect = [job, SimpleNamespace(is_active=False)]
    provider = Mock()
    monkeypatch.setattr(fs, "run", provider)
    fs.execute_job(session, "j")
    assert job.status == "FAILED"
    assert job.progress == 0
    provider.assert_not_called()


def test_completed_job_is_not_replayed(monkeypatch):
    session = Mock()
    session.get.return_value = SimpleNamespace(status="COMPLETED")
    provider = Mock()
    monkeypatch.setattr(fs, "run", provider)
    fs.execute_job(session, "j")
    provider.assert_not_called()


def test_queue_requires_explicit_consent_before_dispatch():
    from app.routers.documents import run_forensics
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as error:
        run_forensics("d", consent=False, principal=Mock(), session=Mock())
    assert error.value.status_code == 422


@pytest.mark.integration
def test_queue_admission_progress_and_current_jurisdiction(require_postgres, monkeypatch):
    from app.db import SessionLocal
    from app.models import ForensicJob
    from app.worker import forensic_task
    from sqlalchemy import delete
    from staged_documents import principal, stage

    dispatch = Mock()
    monkeypatch.setattr(forensic_task, "apply_async", dispatch)
    calls = []
    monkeypatch.setattr(fs, "run", lambda session, document, checks: calls.extend(checks))
    with SessionLocal() as session:
        doc = stage(session, [])
        actor = principal(session, "lekhpal@mrittika.demo")
        original_state = doc.state
        try:
            job = fs.enqueue_job(session, doc, actor)
            assert fs.enqueue_job(session, doc, actor).id == job.id
            assert dispatch.call_count == 1
            fs.execute_job(session, job.id)
            assert calls == list(fs.CHECKS)
            assert (job.status, job.progress) == ("COMPLETED", 100)
            assert doc.state == original_state
            fs.execute_job(session, job.id)
            assert len(calls) == 5
            # Removing authority while a job waits must prevent all model calls.
            denied = ForensicJob(document_id=doc.id, actor_id=actor.id)
            session.add(denied)
            session.commit()
            from app.services import auth_service
            monkeypatch.setattr(auth_service, "document_in_jurisdiction", lambda *args: False)
            fs.execute_job(session, denied.id)
            assert denied.status == "FAILED"
            assert len(calls) == 5
        finally:
            session.rollback()
            session.execute(delete(ForensicJob).where(ForensicJob.document_id == doc.id))
            session.delete(doc)
            session.commit()


@pytest.mark.integration
def test_queue_backpressure_and_broker_failure(require_postgres, monkeypatch):
    from app.db import SessionLocal
    from app.models import ForensicJob
    from app.worker import forensic_task
    from fastapi import HTTPException
    from sqlalchemy import delete
    from staged_documents import principal, stage

    with SessionLocal() as session:
        doc = stage(session, [])
        actor = principal(session, "lekhpal@mrittika.demo")
        try:
            monkeypatch.setattr(fs, "MAX_PENDING_JOBS", 0)
            with pytest.raises(HTTPException) as full:
                fs.enqueue_job(session, doc, actor)
            assert full.value.status_code == 429
            monkeypatch.setattr(fs, "MAX_PENDING_JOBS", 32)
            monkeypatch.setattr(forensic_task, "apply_async", Mock(side_effect=RuntimeError("secret")))
            with pytest.raises(HTTPException) as offline:
                fs.enqueue_job(session, doc, actor)
            assert offline.value.status_code == 503
            assert "secret" not in str(offline.value)
            assert fs.latest_job(session, doc).status == "FAILED"
        finally:
            session.rollback()
            session.execute(delete(ForensicJob).where(ForensicJob.document_id == doc.id))
            session.delete(doc)
            session.commit()
