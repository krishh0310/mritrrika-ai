"""Isolation Forest outlier detection (§7, §34).

An Isolation Forest is unsupervised: it learns what the corpus looks like and
scores how easily a record is separated from it. That makes it useful for
patterns nobody wrote a rule for, and useless on its own -- an outlier score
carries no explanation, which is why every flag it produces is worded as
"unusual relative to comparable records" and is ranked below a rule finding.

Two fallbacks matter here (§82):

  * scikit-learn missing -> `IsolationForestDetector.available` is False and
    `score` returns None. The rules engine still runs. Nothing is fabricated.
  * too few records to fit -> same. A forest fit on five parcels would call
    almost anything an outlier.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence

from .features import FEATURE_NAMES, RecordFeatures, feature_vector
from .signal import AnomalySignal

logger = logging.getLogger(__name__)

try:  # pragma: no cover - exercised by whichever environment is installed
    from sklearn.ensemble import IsolationForest

    SKLEARN_AVAILABLE = True
except ImportError:  # pragma: no cover
    IsolationForest = None  # type: ignore[assignment]
    SKLEARN_AVAILABLE = False

#: Below this many records the corpus is too small to describe "normal".
MIN_CORPUS = 30

#: Expected outlier fraction. Deliberately low: a false flag costs an officer's
#: time and erodes trust in every other flag (§34).
CONTAMINATION = 0.05

#: Only scores at least this unusual are surfaced at all.
REPORT_THRESHOLD = 0.55


class IsolationForestDetector:
    """Fit-on-corpus, score-one-record outlier detector.

    Fitting is the caller's job and happens once per batch, not per record --
    refitting per document would be both slow and meaningless.
    """

    def __init__(self, model_version: str = "anomaly-v1", random_state: int = 42) -> None:
        self.model_version = model_version
        self.random_state = random_state
        self._model = None
        self._corpus_size = 0

    @property
    def available(self) -> bool:
        """Whether this detector can produce a score at all."""
        return SKLEARN_AVAILABLE and self._model is not None

    @property
    def unavailable_reason(self) -> str | None:
        if not SKLEARN_AVAILABLE:
            return "scikit-learn is not installed"
        if self._model is None:
            return f"not fitted (needs at least {MIN_CORPUS} records)"
        return None

    def fit(self, corpus: Sequence[RecordFeatures]) -> bool:
        """Learn the corpus. Returns whether a usable model resulted."""
        if not SKLEARN_AVAILABLE:
            logger.info("anomaly: scikit-learn unavailable, rules only (§82)")
            return False
        if len(corpus) < MIN_CORPUS:
            logger.info(
                "anomaly: corpus of %d is below the %d minimum, rules only",
                len(corpus), MIN_CORPUS,
            )
            return False

        matrix = [feature_vector(record) for record in corpus]
        model = IsolationForest(
            n_estimators=100,
            contamination=CONTAMINATION,
            random_state=self.random_state,
        )
        model.fit(matrix)
        self._model = model
        self._corpus_size = len(corpus)
        return True

    def score(self, features: RecordFeatures) -> float | None:
        """Normalised outlier score in 0-1, or None when unavailable.

        sklearn's `score_samples` returns a log-density where *lower* is more
        anomalous, on an unbounded scale. `decision_function` is the same
        quantity shifted so that negative means outlier, which maps onto 0-1
        far more predictably.
        """
        if not self.available:
            return None
        raw = float(self._model.decision_function([feature_vector(features)])[0])
        # decision_function is roughly [-0.5, 0.5] in practice; clamp and invert
        # so 1.0 is maximally unusual.
        return max(0.0, min(1.0, 0.5 - raw))

    def signal(self, features: RecordFeatures) -> AnomalySignal | None:
        """Score a record and, if unusual enough, describe it as a signal."""
        score = self.score(features)
        if score is None or score < REPORT_THRESHOLD:
            return None

        # Carry the whole feature vector as evidence. The forest cannot say
        # which feature drove the score, so naming one would be a guess; an
        # officer can at least see what the record actually looks like (§68).
        return AnomalySignal(
            anomaly_type="UNUSUAL_PATTERN",
            score=score,
            explanation=(
                "This record is unusual relative to comparable records in the "
                "corpus. No specific rule was violated; manual investigation "
                "recommended."
            ),
            evidence={
                "features": dict(
                    zip(FEATURE_NAMES, feature_vector(features), strict=True)
                ),
                "corpus_size": self._corpus_size,
                "threshold": REPORT_THRESHOLD,
            },
            source=self.model_version,
        )


__all__ = [
    "CONTAMINATION", "IsolationForestDetector", "MIN_CORPUS", "REPORT_THRESHOLD",
    "SKLEARN_AVAILABLE",
]
