"""The one shape both anomaly detectors emit.

In its own module so `rules` and `detector` can each import it without either
importing the other.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class AnomalySignal:
    """A potential inconsistency, with the evidence that produced it (§68).

    `score` is 0-1 where higher means more unusual. It is NOT a probability of
    wrongdoing, and the explanation never says it is (§34).
    """

    anomaly_type: str
    score: float
    explanation: str
    evidence: dict = field(default_factory=dict)
    #: "rules" or the model version that produced it -- an officer needs to
    #: know whether a flag is a fact or an outlier score.
    source: str = "rules"

    def to_dict(self) -> dict:
        return {
            "anomaly_type": self.anomaly_type,
            "score": round(self.score, 4),
            "explanation": self.explanation,
            "evidence": self.evidence,
            "source": self.source,
        }


__all__ = ["AnomalySignal"]
