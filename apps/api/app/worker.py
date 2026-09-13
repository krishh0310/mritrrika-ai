"""Celery worker entry point (§23).

    cd apps/api && celery -A app.worker.celery_app worker --loglevel=info

(`-A app.worker` alone does not work: Celery looks for an attribute named
`app` or `celery`, and this module's is `celery_app`.)

Runs natively rather than in Docker: paddlepaddle has no reliable linux/arm64
wheel, and emulation makes OCR too slow to demo (see docs/architecture.md).

The same work is callable synchronously via pipeline_service.process_document,
which is what the tests and the E2E flow use -- so the pipeline is exercised
identically whether or not a broker is running.
"""

from __future__ import annotations

import logging
import os
import sys

if sys.platform == "darwin":
    # macOS forbids most work after fork() in a process that has initialised
    # Objective-C or extra threads, and kills the child with SIGSEGV. Celery's
    # prefork pool plus PaddlePaddle's threads hit exactly that, losing OCR
    # processes mid-document. Set before Celery or Paddle is imported.
    os.environ.setdefault("OBJC_DISABLE_INITIALIZE_FORK_SAFETY", "YES")

from celery import Celery
from celery.signals import worker_process_init, worker_ready

from app.config.settings import get_settings
from app.db import SessionLocal, engine
from app.models import ProcessingJob
from app.services import document_service, pipeline_service

logger = logging.getLogger(__name__)
settings = get_settings()

celery_app = Celery(
    "mrittika",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
)
celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    task_track_started=True,
    # OCR on a degraded page takes seconds, not minutes; a bounded limit stops
    # one pathological document occupying a worker indefinitely.
    task_time_limit=600,
    task_soft_time_limit=540,
    worker_prefetch_multiplier=1,
    worker_concurrency=settings.worker_concurrency,
    worker_max_memory_per_child=settings.worker_max_memory_mb * 1024,  # Celery takes KB
    # Acknowledge a task only once it finishes, and put it back if its worker
    # dies. With the default early acknowledgement, a crash or reboot mid-OCR
    # silently lost the task and left the document in PROCESSING for good.
    # Safe to repeat: process_document replaces a document's prior results.
    task_acks_late=True,
    task_reject_on_worker_lost=True,
)

# A child killed mid-task (SIGSEGV, OOM, reboot) is replaced by Celery, and
# late acknowledgement puts its document back on the queue. Whatever escapes
# both -- a worker that never comes back -- is caught by the startup sweep in
# recover_orphaned_jobs below.


@celery_app.task(name="mrittika.process_document", bind=True)
def process_document_task(self, document_external_id: str, job_id: str) -> dict:
    """Run the AI pipeline for one uploaded document."""
    with SessionLocal() as session:
        document = document_service.get_by_external_id(session, document_external_id)
        job = session.get(ProcessingJob, job_id)
        if job is None:
            raise ValueError(f"no processing job {job_id}")
        # A task redelivered after its worker died (late acknowledgement) may
        # find its job already closed by startup recovery, which queued a
        # replacement. Running both would process one document twice at once.
        if job.status not in ("QUEUED", "RUNNING") or document.state != "PROCESSING":
            logger.warning("skipping superseded job %s for %s (job %s, document %s)",
                           job_id, document_external_id, job.status, document.state)
            return {"status": "SKIPPED", "reason": "superseded"}
        job.celery_task_id = self.request.id
        session.commit()
        return pipeline_service.process_document(session, document, job)


def _enqueue(document_external_id: str, job_id: str) -> str:
    return process_document_task.delay(document_external_id, job_id).id


@worker_process_init.connect
def fresh_connections_after_fork(**_kwargs) -> None:
    """Give each forked pool process its own database connections.

    The startup recovery below queries the database in the main process, and
    prefork children inherit its pooled connection. Two processes sharing one
    socket interleave their statements: "prepared statement _pg3_3 does not
    exist", results never saved, documents left in PROCESSING. close=False
    drops the inherited connections without closing the parent's socket.
    """
    engine.dispose(close=False)


@worker_ready.connect
def recover_orphaned_jobs(**_kwargs) -> None:
    """Re-dispatch jobs a previous worker left running when it stopped.

    Late acknowledgement covers tasks still in the broker; this covers the
    database side, and jobs from before late acknowledgement was enabled.
    """
    with SessionLocal() as session:
        recovered = pipeline_service.recover_stale_jobs(session, enqueue=_enqueue)
    if recovered:
        logger.warning("re-queued %d orphaned job(s): %s", len(recovered), ", ".join(recovered))
