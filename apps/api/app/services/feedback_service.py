"""Turn verifier corrections into curated retraining candidates (§30, §67).

The `ai_feedback` table has existed since the initial schema and nothing ever
wrote to it. This is what writes to it.

Not every correction is worth the same as a training example. The one that
teaches the model most is the one it got wrong *while confident*: a field
returned at 0.95 that a verifier had to rewrite is a systematic error, and the
model has no idea it is making it. A field returned at 0.30 that a verifier
rewrote is the confidence engine working as designed -- it flagged its own
doubt, a human resolved it, and there is far less signal in that.

So corrections are scored by how surprising they are, and the pool is ordered
by that score. This is ordinary uncertainty-based active learning, applied in
the direction people usually forget: high confidence plus a correction is the
interesting case, not low confidence.

What this deliberately does NOT do (§67): trigger retraining. Every row lands
with `reviewed=False`, and `readiness()` reports whether enough REVIEWED rows
have accumulated to be worth a training run. A human decides. Automatic
nightly retraining on unreviewed verifier edits would let one mistaken
correction, or one operator having a bad afternoon, teach the model directly.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import AiFeedback, Extraction, FieldCorrection

#: A prediction at or above this confidence that still needed correcting is a
#: systematic error the model cannot see.
CONFIDENT = 0.85

#: Below this the confidence engine already said it was unsure, so a correction
#: carries much less new information.
UNSURE = 0.55

#: Reviewed rows needed before a retraining run is worth proposing. Small
#: because the corpus is small; it is a floor against training on noise, not a
#: statistically derived sample size.
RETRAINING_THRESHOLD = 50

CONFIDENT_BUT_WRONG = "CONFIDENT_BUT_WRONG"
UNCERTAIN_AND_WRONG = "UNCERTAIN_AND_WRONG"
MODERATE_MISS = "MODERATE_MISS"
MISSED_ENTIRELY = "MISSED_ENTIRELY"


@dataclass(frozen=True)
class Readiness:
    reviewed: int
    pending_review: int
    threshold: int

    @property
    def ready(self) -> bool:
        return self.reviewed >= self.threshold

    def to_dict(self) -> dict:
        return {
            "reviewed": self.reviewed,
            "pending_review": self.pending_review,
            "threshold": self.threshold,
            "ready_to_retrain": self.ready,
            "note": (
                "Retraining is never automatic (§67). This reports whether a "
                "human-reviewed pool has grown large enough to be worth a run."
            ),
        }


def classify(confidence: float | None, predicted: str | None) -> tuple[str, float]:
    """The reason this correction was selected, and its priority in 0-1."""
    if not (predicted or "").strip():
        # The model produced nothing at all. Valuable, but it is a recall
        # problem rather than a mislearned value, and it is already visible as
        # a MISSING field, so it ranks below a confident wrong answer.
        return MISSED_ENTIRELY, 0.60

    if confidence is None:
        return MODERATE_MISS, 0.50

    if confidence >= CONFIDENT:
        # Scale across the confident band so 0.99-and-wrong outranks
        # 0.85-and-wrong rather than tying with it.
        span = (confidence - CONFIDENT) / max(1e-6, 1.0 - CONFIDENT)
        return CONFIDENT_BUT_WRONG, round(0.80 + 0.20 * span, 4)

    if confidence <= UNSURE:
        return UNCERTAIN_AND_WRONG, round(0.20 + 0.20 * (confidence / UNSURE), 4)

    span = (confidence - UNSURE) / (CONFIDENT - UNSURE)
    return MODERATE_MISS, round(0.45 + 0.30 * span, 4)


def record_correction(session: Session, correction: FieldCorrection) -> AiFeedback:
    """Add one correction to the retraining pool, unreviewed."""
    reason, score = classify(
        correction.confidence_at_correction, correction.model_prediction
    )
    entry = AiFeedback(
        correction_id=correction.id,
        field=correction.field,
        priority_score=score,
        selection_reason=reason,
        reviewed=False,
    )
    session.add(entry)
    return entry


def readiness(session: Session) -> Readiness:
    """How close the pool is to being worth a training run."""
    reviewed = session.execute(
        select(func.count()).select_from(AiFeedback).where(AiFeedback.reviewed.is_(True))
    ).scalar_one()
    pending = session.execute(
        select(func.count()).select_from(AiFeedback).where(AiFeedback.reviewed.is_(False))
    ).scalar_one()
    return Readiness(
        reviewed=reviewed, pending_review=pending, threshold=RETRAINING_THRESHOLD
    )


def pool(session: Session, *, limit: int = 100, reviewed: bool | None = None) -> list[dict]:
    """The retraining pool, most informative first."""
    query = (
        select(AiFeedback, FieldCorrection, Extraction)
        .join(FieldCorrection, FieldCorrection.id == AiFeedback.correction_id)
        .outerjoin(Extraction, Extraction.id == FieldCorrection.extraction_id)
        .order_by(AiFeedback.priority_score.desc())
        .limit(limit)
    )
    if reviewed is not None:
        query = query.where(AiFeedback.reviewed.is_(reviewed))

    return [
        {
            "feedback_id": entry.id,
            "field": entry.field,
            "priority_score": entry.priority_score,
            "selection_reason": entry.selection_reason,
            "reviewed": entry.reviewed,
            "confidence_at_correction": correction.confidence_at_correction,
            "model_version": correction.model_version,
            # The values themselves are NOT returned. The pool is an ML-ops
            # view of which examples are worth curating; reading record content
            # belongs to the verification screens, behind their own checks.
            "has_prediction": bool((correction.model_prediction or "").strip()),
        }
        for entry, correction, _extraction in session.execute(query).all()
    ]


__all__ = [
    "CONFIDENT", "CONFIDENT_BUT_WRONG", "MISSED_ENTIRELY", "MODERATE_MISS",
    "RETRAINING_THRESHOLD", "UNCERTAIN_AND_WRONG", "UNSURE",
    "Readiness", "classify", "pool", "readiness", "record_correction",
]
