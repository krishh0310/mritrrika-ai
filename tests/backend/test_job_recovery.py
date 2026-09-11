"""Jobs orphaned by a stopped worker are re-dispatched, not stranded.

After a reboot killed the worker mid-OCR, 16 documents sat in PROCESSING with
jobs marked RUNNING indefinitely. Nothing in the §37 graph moves a document out
of PROCESSING, so they could never reach a verifier.
"""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

pytestmark = pytest.mark.integration


@pytest.fixture
def processing_document():
    from app.db import SessionLocal
    from app.models import Document, ProcessingJob

    with SessionLocal() as session:
        document = Document(
            external_id="DOC-990077", document_type="KHASRA", state="PROCESSING",
            storage_key="tests/job-recovery/none",
        )
        session.add(document)
        session.flush()
        job = ProcessingJob(document_id=document.id, stage="ocr", progress=35,
                            status="RUNNING", started_at=datetime.now(UTC))
        session.add(job)
        session.commit()
        ids = (document.id, job.id)

    yield ids

    with SessionLocal() as session:
        session.query(ProcessingJob).filter(ProcessingJob.document_id == ids[0]).delete()
        session.query(Document).filter(Document.id == ids[0]).delete()
        session.commit()


def _recover(now):
    from app.db import SessionLocal
    from app.services import pipeline_service

    sent: list[tuple[str, str]] = []
    with SessionLocal() as session:
        recovered = pipeline_service.recover_stale_jobs(
            session,
            enqueue=lambda doc, job: sent.append((doc, job)) or "task-under-test",
            now=now,
            # Only this test's document. An unscoped sweep re-dispatched every
            # real stuck document in the shared database through this stand-in
            # enqueue, leaving jobs that claimed to be queued and never were.
            document_ids=["DOC-990077"],
        )
    return recovered, sent


def test_a_live_job_is_left_alone(processing_document):
    recovered, sent = _recover(datetime.now(UTC))
    assert "DOC-990077" not in recovered
    assert not [s for s in sent if s[0] == "DOC-990077"]


def test_a_silent_job_is_closed_and_the_document_requeued(processing_document):
    from app.db import SessionLocal
    from app.models import Document, ProcessingJob

    document_pk, old_job_id = processing_document
    recovered, sent = _recover(datetime.now(UTC) + timedelta(hours=1))

    assert "DOC-990077" in recovered
    with SessionLocal() as session:
        old = session.get(ProcessingJob, old_job_id)
        assert old.status == "FAILED" and "orphaned" in old.error

        jobs = session.execute(
            select(ProcessingJob).where(ProcessingJob.document_id == document_pk)
            .order_by(ProcessingJob.created_at)
        ).scalars().all()
        new = jobs[-1]
        assert new.id != old_job_id and new.status == "QUEUED"
        assert new.celery_task_id == "task-under-test"
        assert ("DOC-990077", new.id) in sent

        # Never processed, so it stays exactly where it was in the §37 graph.
        assert session.get(Document, document_pk).state == "PROCESSING"


def test_recovery_is_audited(processing_document):
    from app.db import SessionLocal
    from app.models import AuditEvent

    _recover(datetime.now(UTC) + timedelta(hours=1))
    with SessionLocal() as session:
        actions = session.execute(
            select(AuditEvent.action).where(AuditEvent.entity_id == "DOC-990077")
        ).scalars().all()
    assert "document.processing_requeued" in actions


def test_sweep_never_touches_documents_outside_its_scope(processing_document):
    from app.db import SessionLocal
    from app.models import Document, ProcessingJob

    with SessionLocal() as session:
        bystander = Document(external_id="DOC-990078", document_type="KHASRA",
                             state="PROCESSING", storage_key="tests/job-recovery/none")
        session.add(bystander)
        session.flush()
        session.add(ProcessingJob(document_id=bystander.id, status="RUNNING", stage="ocr"))
        session.commit()
        bystander_pk = bystander.id
    try:
        recovered, _ = _recover(datetime.now(UTC) + timedelta(hours=1))
        assert "DOC-990078" not in recovered
    finally:
        with SessionLocal() as session:
            session.query(ProcessingJob).filter(ProcessingJob.document_id == bystander_pk).delete()
            session.query(Document).filter(Document.id == bystander_pk).delete()
            session.commit()


def test_worker_acknowledges_late_and_requeues_on_worker_loss():
    from app.worker import celery_app

    assert celery_app.conf.task_acks_late is True
    assert celery_app.conf.task_reject_on_worker_lost is True
    assert celery_app.conf.worker_concurrency == 1
    assert celery_app.conf.worker_max_memory_per_child == 4096 * 1024
