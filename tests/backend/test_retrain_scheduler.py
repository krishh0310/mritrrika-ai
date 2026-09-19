"""The nightly retrain loop and the model registry (§67).

Training is faked: these tests are about the decisions around it -- when a
run starts, what gets promoted, and that nothing it does can break the API or
leave the registry without exactly one active model.
"""

from __future__ import annotations

import pytest
from sqlalchemy import func, select

pytestmark = pytest.mark.integration


@pytest.fixture
def registry(client):
    """Restore the registry afterwards."""
    from app.db import SessionLocal
    from app.models import ModelRegistryEntry

    with SessionLocal() as s:
        before = {row.id for row in s.query(ModelRegistryEntry).all()}
        original = s.query(ModelRegistryEntry).filter_by(is_active=True).one().id
    yield SessionLocal
    with SessionLocal() as s:
        s.query(ModelRegistryEntry).filter(ModelRegistryEntry.id.not_in(before)).delete()
        s.query(ModelRegistryEntry).filter_by(id=original).update({"is_active": True})
        s.commit()


def active_rows(session_factory):
    from app.models import ModelRegistryEntry

    with session_factory() as s:
        return s.query(ModelRegistryEntry).filter_by(is_active=True).all()


def test_the_nightly_job_is_registered_at_startup(client):
    from app.main import app

    job = app.state.scheduler.get_job("nightly-retrain")
    assert str(job.trigger) == "cron[hour='2', minute='0']"


def test_a_better_model_is_promoted(registry):
    from app.tasks.retrain_scheduler import run_cycle

    result = run_cycle(registry, train_fn=lambda: "/models/better.pt",
                       evaluate_fn=lambda path: 0.70, min_samples=0)
    assert result["status"] == "promoted"
    [row] = active_rows(registry)
    assert (row.model_path, row.f1_score) == ("/models/better.pt", 0.70)


def test_a_worse_model_is_recorded_but_not_promoted(registry):
    from app.models import ModelRegistryEntry
    from app.tasks.retrain_scheduler import run_cycle

    result = run_cycle(registry, train_fn=lambda: "/models/worse.pt",
                       evaluate_fn=lambda path: 0.10, min_samples=0)
    assert result["status"] == "kept"
    [row] = active_rows(registry)
    assert row.model_path == "rules"
    with registry() as s:
        audit = s.query(ModelRegistryEntry).filter_by(model_path="/models/worse.pt").one()
        assert audit.is_active is False and audit.f1_score == 0.10


def test_a_failing_retrain_crashes_nothing(client, auth, registry):
    from app.tasks.retrain_scheduler import run_cycle

    def explode():
        raise RuntimeError("CUDA out of memory")

    result = run_cycle(registry, train_fn=explode, evaluate_fn=lambda p: 1.0, min_samples=0)
    assert result["status"] == "failed"
    assert [r.model_path for r in active_rows(registry)] == ["rules"]
    # The API is still up.
    assert client.get("/health").status_code == 200


def test_below_the_threshold_nothing_runs(registry):
    from app.tasks.retrain_scheduler import run_cycle

    ran = []
    result = run_cycle(registry, train_fn=lambda: ran.append(1), evaluate_fn=lambda p: 1.0,
                       min_samples=10**6)
    assert result["status"] == "skipped" and ran == []


def test_there_is_always_exactly_one_active_model(registry):
    from app.models import ModelRegistryEntry
    from app.tasks.retrain_scheduler import run_cycle
    from sqlalchemy.exc import IntegrityError

    for f1 in (0.65, 0.50, 0.80):
        run_cycle(registry, train_fn=lambda f1=f1: f"/models/{f1}.pt",
                  evaluate_fn=lambda path, f1=f1: f1, min_samples=0)
        assert len(active_rows(registry)) == 1
    with registry() as s:
        s.add(ModelRegistryEntry(model_path="/rogue.pt", is_active=True))
        with pytest.raises(IntegrityError):
            s.commit()
        s.rollback()
        count = s.execute(select(func.count()).select_from(ModelRegistryEntry)
                          .where(ModelRegistryEntry.is_active.is_(True))).scalar_one()
    assert count == 1


def test_metrics_report_retrains_and_the_active_f1(client, auth, registry):
    from app.tasks.retrain_scheduler import run_cycle
    from demo_users import TEHSILDAR

    run_cycle(registry, train_fn=lambda: "/models/x.pt", evaluate_fn=lambda p: 0.75,
              min_samples=0)
    body = client.get("/metrics", headers=auth(TEHSILDAR)).text
    assert "mrittika_retrain_triggered_total" in body
    assert "mrittika_extractor_f1 0.75" in body


def test_the_run_lock_is_always_released(registry):
    """A lock stranded on a pooled connection would skip every later night."""
    from app.tasks.retrain_scheduler import run_cycle

    for f1 in (0.9, 0.1, 0.95):
        result = run_cycle(registry, train_fn=lambda: "/models/l.pt",
                           evaluate_fn=lambda p, f1=f1: f1, min_samples=0)
        assert result["status"] in {"promoted", "kept"}, result
