"""Celery worker entry point (§23).

    celery -A app.worker worker --loglevel=info

Runs natively rather than in Docker: paddlepaddle has no reliable linux/arm64
wheel, and emulation makes OCR too slow to demo (see docs/architecture.md).

The same work is callable synchronously via pipeline_service.process_document,
which is what the tests and the E2E flow use -- so the pipeline is exercised
identically whether or not a broker is running.
"""

from __future__ import annotations

import logging

from celery import Celery

from app.config.settings import get_settings
from app.db import SessionLocal
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
)


@celery_app.task(name="mrittika.process_document", bind=True)
def process_document_task(self, document_external_id: str, job_id: str) -> dict:
    """Run the AI pipeline for one uploaded document."""
    with SessionLocal() as session:
        document = document_service.get_by_external_id(session, document_external_id)
        job = session.get(ProcessingJob, job_id)
        if job is None:
            raise ValueError(f"no processing job {job_id}")
        job.celery_task_id = self.request.id
        session.commit()
        return pipeline_service.process_document(session, document, job)
