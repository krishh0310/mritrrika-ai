"""Nightly: retrain the field extractor when enough corrections exist (§67).

    02:00  enough ACCEPTED corrections since the last run?   (RETRAIN_MIN_SAMPLES)
             no  -> nothing happens
             yes -> export feedback, train on IndicBERT v2, evaluate on the
                    held-out val split
                    F1 >= active F1 -> promote (model_registry, one transaction)
                    F1 <  active F1 -> record it inactive; production unchanged

What keeps this safe to run unattended:

  * Only corrections a human ACCEPTED count, and the model only ever replaces
    production by measurably beating it on held-out pages it never trained on.
  * Training and evaluation are subprocesses: a crash, OOM or bad checkpoint
    fails that run, never the API. Any exception is caught and recorded.
  * A Postgres advisory lock means one run at a time even with several API
    workers, each of which starts its own scheduler.
"""

from __future__ import annotations

import json
import logging
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import func, select, update

from app.config.settings import get_settings
from app.models import AiFeedback, ModelRegistryEntry

logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[4]
JOB_ID = "nightly-retrain"
RULES = "rules"
#: Arbitrary constant; the lock is session-scoped and released on disconnect.
LOCK_KEY = 0x52455452


def active(session) -> ModelRegistryEntry:
    return session.execute(
        select(ModelRegistryEntry).where(ModelRegistryEntry.is_active.is_(True))
    ).scalar_one()


def new_corrections(session) -> int:
    """ACCEPTED corrections reviewed since the last retrain attempt."""
    since = session.execute(select(func.max(ModelRegistryEntry.created_at))).scalar_one()
    query = select(func.count()).select_from(AiFeedback).where(
        AiFeedback.review_decision == "ACCEPTED")
    if since is not None:
        query = query.where(AiFeedback.reviewed_at > since)
    return session.execute(query).scalar_one()


def promote(session, model_path: str, f1: float, notes: str | None = None) -> None:
    """Make `model_path` the active extractor. One transaction: never zero or
    two active rows (the partial unique index enforces the second)."""
    session.execute(update(ModelRegistryEntry)
                    .where(ModelRegistryEntry.is_active.is_(True))
                    .values(is_active=False))
    session.flush()
    session.add(ModelRegistryEntry(model_path=model_path, f1_score=f1, is_active=True,
                                   promoted_at=datetime.now(UTC), notes=notes))
    session.commit()


def _run(*args: str) -> None:
    subprocess.run([sys.executable, *args], cwd=REPO_ROOT, check=True, timeout=6 * 3600)


def train() -> str:
    """Export reviewed feedback, train, and return the checkpoint path."""
    name = f"retrain-{datetime.now(UTC):%Y%m%dT%H%M%S}"
    _run("scripts/export_feedback_dataset.py")
    _run("scripts/train_extractor.py", "--name", name)
    return str(REPO_ROOT / "models" / "checkpoints" / "extraction" / name / "best.pt")


def evaluate(model_path: str) -> float:
    """Field-level F1 on the held-out val split -- the same harness, split and
    metric the rules extractor's 0.592 was measured with."""
    tag = Path(model_path).parent.name
    _run("scripts/evaluate_extraction.py", "--split", "val", "--extractor", "model",
         "--weights", model_path, "--tag", tag)
    report = json.loads((REPO_ROOT / "datasets" / "reports" /
                         f"extraction_eval.val.v1.{tag}.json").read_text())
    tp, fp, fn = (report["overall"][k] for k in ("tp", "fp", "fn"))
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    return 2 * precision * recall / (precision + recall) if precision + recall else 0.0


def run_cycle(session_factory=None, *, train_fn=train, evaluate_fn=evaluate,
              min_samples: int | None = None) -> dict:
    """One scheduled check. Never raises. `min_samples` overrides the setting."""
    if session_factory is None:
        from app.db import SessionLocal as session_factory
    from app.db import engine

    try:
        # The lock lives on its own connection, held for the whole run. On the
        # session's connection it would be lost: the session commits midway and
        # the pool may hand the unlock a different connection, leaving the lock
        # stranded and every later night "skipped".
        with engine.connect() as lock:
            if not lock.execute(select(func.pg_try_advisory_lock(LOCK_KEY))).scalar_one():
                return {"status": "skipped", "reason": "another run holds the lock"}
            try:
                with session_factory() as session:
                    return _cycle(session, train_fn, evaluate_fn, min_samples)
            finally:
                lock.execute(select(func.pg_advisory_unlock(LOCK_KEY)))
                lock.commit()
    except Exception:  # the scheduler thread must outlive any single run
        logger.exception("retrain cycle failed")
        return {"status": "error"}


def _cycle(session, train_fn, evaluate_fn, min_samples) -> dict:
    threshold = get_settings().retrain_min_samples if min_samples is None else min_samples
    pending = new_corrections(session)
    if pending < threshold:
        return {"status": "skipped", "new_corrections": pending, "threshold": threshold}

    current = active(session)
    try:
        model_path = train_fn()
        f1 = evaluate_fn(model_path)
    except Exception as exc:
        logger.exception("retrain failed; production extractor unchanged")
        session.rollback()
        session.add(ModelRegistryEntry(model_path="(failed)", is_active=False,
                                       notes=f"retrain failed: {exc}"[:2000]))
        session.commit()
        return {"status": "failed", "error": str(exc)}

    if f1 >= (current.f1_score or 0.0):
        promote(session, model_path, f1,
                notes=f"promoted over {current.model_path} (F1 {current.f1_score})")
        logger.info("retrain promoted %s at F1 %.4f", model_path, f1)
        return {"status": "promoted", "model_path": model_path, "f1": f1}

    session.add(ModelRegistryEntry(
        model_path=model_path, f1_score=f1, is_active=False,
        notes=f"kept {current.model_path}: F1 {f1:.4f} < {current.f1_score}"))
    session.commit()
    logger.info("retrain kept %s: candidate F1 %.4f", current.model_path, f1)
    return {"status": "kept", "model_path": model_path, "f1": f1}


_scheduler = None


def start():
    """The process's scheduler, started once with the 02:00 job registered.

    One per process, however many times the app starts up (tests do it
    repeatedly). Its thread is a daemon: it ends with the process, so there is
    no shutdown to get wrong.
    """
    global _scheduler
    if _scheduler is None:
        from apscheduler.schedulers.background import BackgroundScheduler
        from apscheduler.triggers.cron import CronTrigger

        _scheduler = BackgroundScheduler(daemon=True)
        _scheduler.add_job(run_cycle, CronTrigger(hour=2, minute=0), id=JOB_ID,
                           replace_existing=True, max_instances=1, coalesce=True)
        _scheduler.start()
    return _scheduler


__all__ = ["JOB_ID", "RULES", "active", "evaluate", "new_corrections", "promote",
           "run_cycle", "start", "train"]
