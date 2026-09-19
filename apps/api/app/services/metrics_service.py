"""Prometheus exposition for /metrics (§74).

Two sources feed this file:

  * **Live counters** kept in this process by the request middleware -- API
    latency and error rate, which no table records.
  * **Database aggregates** read on scrape -- queue depth, average confidence,
    stage latencies, correction frequency, quality distribution. These are
    computed rather than incremented so a restarted API still reports the truth.

The in-process counters are per-worker and reset on restart, which is the
normal semantics for a Prometheus counter and is why the aggregates are not
kept the same way.
"""

from __future__ import annotations

import threading
from collections import defaultdict

from mrittika_domain import DocumentState
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import (
    Document,
    Extraction,
    FieldCorrection,
    ProcessingJob,
    VerificationTask,
)

#: Upper bounds in seconds for the API latency histogram.
LATENCY_BUCKETS = (0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0)


class _RequestMetrics:
    """Thread-safe request counters for the middleware.

    A lock rather than atomics because a scrape reads several structures and
    must not observe a half-updated set.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.total = 0
        self.errors = 0
        self.by_status: dict[str, int] = defaultdict(int)
        self.duration_sum = 0.0
        self.buckets: dict[float, int] = {bound: 0 for bound in LATENCY_BUCKETS}

    def observe(self, status_code: int, seconds: float) -> None:
        with self._lock:
            self.total += 1
            self.duration_sum += seconds
            # Class rather than exact code: a per-code label set grows without
            # bound on a public endpoint.
            self.by_status[f"{status_code // 100}xx"] += 1
            if status_code >= 500:
                self.errors += 1
            for bound in LATENCY_BUCKETS:
                if seconds <= bound:
                    self.buckets[bound] += 1

    def snapshot(self) -> dict:
        with self._lock:
            return {
                "total": self.total,
                "errors": self.errors,
                "by_status": dict(self.by_status),
                "duration_sum": self.duration_sum,
                "buckets": dict(self.buckets),
            }

    def reset(self) -> None:
        """Test helper -- never called in normal operation."""
        with self._lock:
            self.__init__()


requests = _RequestMetrics()


def _line(name: str, value: float | int, labels: dict[str, str] | None = None) -> str:
    if labels:
        rendered = ",".join(f'{k}="{v}"' for k, v in sorted(labels.items()))
        return f"{name}{{{rendered}}} {value}"
    return f"{name} {value}"


def _stage_latency(session: Session) -> dict[str, float]:
    """Mean seconds per pipeline stage, from job start to finish.

    ProcessingJob records one row per document run, so this is end-to-end
    pipeline latency rather than a per-model breakdown -- the job carries a
    single stage marker, not a timing per stage.
    """
    rows = session.execute(
        select(ProcessingJob.started_at, ProcessingJob.finished_at).where(
            ProcessingJob.finished_at.is_not(None),
            ProcessingJob.started_at.is_not(None),
        )
    ).all()
    if not rows:
        return {}
    spans = [(done - started).total_seconds() for started, done in rows]
    return {"pipeline": round(sum(spans) / len(spans), 4)}


def render(session: Session) -> str:
    """Build the full exposition body."""
    snap = requests.snapshot()
    out: list[str] = []

    out += [
        "# HELP mrittika_http_requests_total Total HTTP requests served.",
        "# TYPE mrittika_http_requests_total counter",
    ]
    for status_class, count in sorted(snap["by_status"].items()):
        out.append(_line("mrittika_http_requests_total", count, {"status": status_class}))
    if not snap["by_status"]:
        out.append(_line("mrittika_http_requests_total", 0, {"status": "2xx"}))

    out += [
        "# HELP mrittika_http_errors_total Responses with a 5xx status.",
        "# TYPE mrittika_http_errors_total counter",
        _line("mrittika_http_errors_total", snap["errors"]),
        "# HELP mrittika_http_request_duration_seconds API latency.",
        "# TYPE mrittika_http_request_duration_seconds histogram",
    ]
    cumulative = 0
    for bound in LATENCY_BUCKETS:
        cumulative = snap["buckets"][bound]
        out.append(
            _line("mrittika_http_request_duration_seconds_bucket", cumulative,
                  {"le": str(bound)})
        )
    out += [
        _line("mrittika_http_request_duration_seconds_bucket", snap["total"],
              {"le": "+Inf"}),
        _line("mrittika_http_request_duration_seconds_sum",
              round(snap["duration_sum"], 6)),
        _line("mrittika_http_request_duration_seconds_count", snap["total"]),
    ]

    # ── Pipeline ────────────────────────────────────────────────────────────
    queue_depth = session.execute(
        select(func.count(ProcessingJob.id)).where(
            ProcessingJob.status.in_(("QUEUED", "RUNNING"))
        )
    ).scalar_one()
    ai_failures = session.execute(
        select(func.count(ProcessingJob.id)).where(ProcessingJob.status == "FAILED")
    ).scalar_one()

    out += [
        "# HELP mrittika_processing_queue_depth Jobs queued or running.",
        "# TYPE mrittika_processing_queue_depth gauge",
        _line("mrittika_processing_queue_depth", queue_depth),
        "# HELP mrittika_ai_failures_total Processing jobs that ended in failure.",
        "# TYPE mrittika_ai_failures_total counter",
        _line("mrittika_ai_failures_total", ai_failures),
    ]

    latencies = _stage_latency(session)
    if latencies:
        out += [
            "# HELP mrittika_stage_latency_seconds Mean stage duration.",
            "# TYPE mrittika_stage_latency_seconds gauge",
        ]
        out += [
            _line("mrittika_stage_latency_seconds", value, {"stage": stage})
            for stage, value in sorted(latencies.items())
        ]

    # ── Retraining (app/tasks/retrain_scheduler.py) ─────────────────────────
    from app.models import ModelRegistryEntry

    retrains = session.execute(
        select(func.count(ModelRegistryEntry.id)).where(ModelRegistryEntry.model_path != "rules")
    ).scalar_one()
    active_f1 = session.execute(
        select(ModelRegistryEntry.f1_score).where(ModelRegistryEntry.is_active.is_(True))
    ).scalar_one_or_none()
    out += [
        "# HELP mrittika_retrain_triggered_total Retrain runs started (any outcome).",
        "# TYPE mrittika_retrain_triggered_total counter",
        _line("mrittika_retrain_triggered_total", retrains),
        "# HELP mrittika_extractor_f1 Held-out field F1 of the production extractor.",
        "# TYPE mrittika_extractor_f1 gauge",
        _line("mrittika_extractor_f1", round(active_f1 or 0.0, 4)),
    ]

    # ── Quality and confidence ──────────────────────────────────────────────
    average_confidence = session.execute(
        select(func.avg(Extraction.final_confidence))
    ).scalar_one()
    out += [
        "# HELP mrittika_average_confidence Mean final field confidence.",
        "# TYPE mrittika_average_confidence gauge",
        _line("mrittika_average_confidence",
              round(float(average_confidence), 4) if average_confidence else 0),
    ]

    quality = session.execute(
        select(Document.quality_recommendation, func.count(Document.id))
        .where(Document.quality_recommendation.is_not(None))
        .group_by(Document.quality_recommendation)
    ).all()
    if quality:
        out += [
            "# HELP mrittika_documents_by_quality Documents per quality verdict.",
            "# TYPE mrittika_documents_by_quality gauge",
        ]
        out += [
            _line("mrittika_documents_by_quality", count, {"recommendation": rec})
            for rec, count in quality
        ]

    states = session.execute(
        select(Document.state, func.count(Document.id)).group_by(Document.state)
    ).all()
    out += [
        "# HELP mrittika_documents_by_state Documents per workflow state.",
        "# TYPE mrittika_documents_by_state gauge",
    ]
    seen = {state: count for state, count in states}
    for state in DocumentState:
        out.append(
            _line("mrittika_documents_by_state", seen.get(state.value, 0),
                  {"state": state.value})
        )

    # ── Human workflow ──────────────────────────────────────────────────────
    corrections = session.execute(select(func.count(FieldCorrection.id))).scalar_one()
    extractions = session.execute(select(func.count(Extraction.id))).scalar_one()
    out += [
        "# HELP mrittika_field_corrections_total Verifier corrections recorded.",
        "# TYPE mrittika_field_corrections_total counter",
        _line("mrittika_field_corrections_total", corrections),
        "# HELP mrittika_correction_rate Corrections per extracted field.",
        "# TYPE mrittika_correction_rate gauge",
        _line("mrittika_correction_rate",
              round(corrections / extractions, 4) if extractions else 0),
    ]

    completed = session.execute(
        select(VerificationTask.started_at, VerificationTask.completed_at).where(
            VerificationTask.completed_at.is_not(None),
            VerificationTask.started_at.is_not(None),
        )
    ).all()
    if completed:
        spans = [(done - started).total_seconds() for started, done in completed]
        mean = round(sum(spans) / len(spans), 3)
    else:
        mean = 0
    out += [
        "# HELP mrittika_verification_seconds Mean time to complete a verification.",
        "# TYPE mrittika_verification_seconds gauge",
        _line("mrittika_verification_seconds", mean),
    ]

    return "\n".join(out) + "\n"


__all__ = ["LATENCY_BUCKETS", "render", "requests"]
