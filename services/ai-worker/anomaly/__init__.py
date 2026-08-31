"""Anomaly detection (§34).

Two detectors, deliberately kept apart:

  * `rules` -- deterministic checks over a parcel's record history. They fire on
    facts (a date out of order, a duplicate identifier) and explain themselves.
  * `detector` -- an Isolation Forest over numeric features. It finds records
    that are unusual relative to the corpus without knowing why.

`engine.analyse` runs both and returns one list. Rules come first because a
deterministic finding is always more useful to an officer than an outlier score
(§7). Nothing here uses the word "fraud" (§34).
"""

from .engine import AnomalySignal, analyse
from .features import RecordFeatures, feature_vector
from .rules import ALL_ANOMALY_TYPES, ANOMALY_RULES, evaluable_types

__all__ = [
    "ALL_ANOMALY_TYPES", "ANOMALY_RULES", "AnomalySignal", "RecordFeatures",
    "analyse", "evaluable_types", "feature_vector",
]
