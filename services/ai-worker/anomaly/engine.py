"""Combine the rule engine and the Isolation Forest (§34).

§7's division of labour, made concrete:

    rules detect deterministic inconsistencies
    ML detects unusual patterns
    the LLM explains the evidence -- elsewhere, never here

Rules are returned first and an outlier score is dropped whenever a rule
already fired on the same record: telling an officer "this is unusual" on top
of "these dates run backwards" adds noise, not information.
"""

from __future__ import annotations

from collections.abc import Sequence

from . import rules
from .detector import IsolationForestDetector
from .features import RecordFeatures
from .signal import AnomalySignal


def analyse(
    features: RecordFeatures,
    detector: IsolationForestDetector | None = None,
) -> list[AnomalySignal]:
    """All signals for one record, most actionable first."""
    signals = rules.run_all(features)

    if detector is not None and detector.available and not signals:
        outlier = detector.signal(features)
        if outlier is not None:
            signals.append(outlier)

    return sorted(signals, key=lambda s: s.score, reverse=True)


def analyse_corpus(
    corpus: Sequence[RecordFeatures],
    *,
    model_version: str = "anomaly-v1",
) -> dict[str, list[AnomalySignal]]:
    """Fit once over the corpus, then analyse every record in it.

    This is the entry point a batch job wants; `analyse` is for a single
    document arriving through the pipeline.
    """
    detector = IsolationForestDetector(model_version=model_version)
    detector.fit(corpus)
    return {record.parcel_id: analyse(record, detector) for record in corpus}


__all__ = ["AnomalySignal", "analyse", "analyse_corpus"]
