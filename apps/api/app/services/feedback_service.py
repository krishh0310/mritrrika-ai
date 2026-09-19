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

What this deliberately does NOT do (§67): retrain on its own. Every row lands
with `reviewed=False`, and `readiness()` reports whether enough ACCEPTED rows
have accumulated to be worth a training run. A human decides. Automatic
nightly retraining on unreviewed verifier edits would let one mistaken
correction, or one operator having a bad afternoon, teach the model directly.

The loop, end to end:

    verifier corrects a field     -> record_correction()   (unreviewed)
    reviewer accepts or rejects   -> review()              (audited)
    scripts/export_feedback_dataset.py -> training_pages()  -> feedback.jsonl
    scripts/train_extractor.py    trains on the synthetic corpus + feedback.jsonl

Only ACCEPTED corrections on documents a verifier has finished with are
exported. Finished matters: a training page labels every word, and on a page
still under review the fields nobody has looked at yet would be labelled with
the model's own guesses -- teaching it to agree with itself.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from mrittika_domain import DocumentState, FieldStatus
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import (
    AiFeedback,
    Document,
    DocumentPage,
    Extraction,
    FieldCorrection,
    OcrBlock,
)
from app.services import audit_service
from app.services.auth_service import Principal, document_in_jurisdiction

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

#: A reviewer's verdict on one correction.
ACCEPTED = "ACCEPTED"
REJECTED = "REJECTED"
DECISIONS = (ACCEPTED, REJECTED)

FEEDBACK_REVIEWED = "ai.feedback_reviewed"

#: Documents whose every field a verifier has seen. See the module docstring.
_FINISHED = (
    DocumentState.VERIFIED, DocumentState.PENDING_APPROVAL, DocumentState.APPROVED,
)

CONFIDENT_BUT_WRONG = "CONFIDENT_BUT_WRONG"
UNCERTAIN_AND_WRONG = "UNCERTAIN_AND_WRONG"
MODERATE_MISS = "MODERATE_MISS"
MISSED_ENTIRELY = "MISSED_ENTIRELY"


class FeedbackError(Exception):
    pass


@dataclass(frozen=True)
class Readiness:
    reviewed: int
    pending_review: int
    threshold: int
    #: Reviewed AND accepted -- the rows a training run would actually use.
    accepted: int = 0

    @property
    def ready(self) -> bool:
        return self.accepted >= self.threshold

    def to_dict(self) -> dict:
        return {
            "reviewed": self.reviewed,
            "accepted": self.accepted,
            "pending_review": self.pending_review,
            "threshold": self.threshold,
            "ready_to_retrain": self.ready,
            "note": (
                "Retraining is never automatic (§67). This reports whether the "
                "accepted pool has grown large enough to be worth a run; "
                "scripts/export_feedback_dataset.py then exports it."
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
    accepted = session.execute(
        select(func.count()).select_from(AiFeedback).where(
            AiFeedback.review_decision == ACCEPTED
        )
    ).scalar_one()
    return Readiness(
        reviewed=reviewed, pending_review=pending, threshold=RETRAINING_THRESHOLD,
        accepted=accepted,
    )


def review(
    session: Session,
    feedback_id: str,
    *,
    decision: str,
    principal: Principal,
    note: str | None = None,
) -> AiFeedback:
    """Accept a correction into the training pool, or reject it.

    ACCEPT when the verifier's value is right and the AI's was wrong: that is a
    lesson. REJECT when the correction itself is doubtful, or teaches nothing
    (a formatting preference, a value the page does not actually show).
    A decision can be changed; each change is audited.
    """
    decision = (decision or "").strip().upper()
    if decision not in DECISIONS:
        raise FeedbackError(f"decision must be one of {', '.join(DECISIONS)}")

    row = session.execute(
        select(AiFeedback, FieldCorrection)
        .join(FieldCorrection, FieldCorrection.id == AiFeedback.correction_id)
        .where(AiFeedback.id == feedback_id)
    ).one_or_none()
    # Out of jurisdiction reads as absent, like every other officer lookup.
    if row is None or not document_in_jurisdiction(
        session, principal, session.get(Document, row[1].document_id)
    ):
        raise FeedbackError(f"no feedback {feedback_id}")
    entry, correction = row

    before = {"reviewed": entry.reviewed, "decision": entry.review_decision}
    entry.reviewed = True
    entry.review_decision = decision
    entry.reviewed_by_id = principal.id
    entry.reviewed_at = datetime.now(UTC)
    entry.review_note = note
    audit_service.record(
        session, action=FEEDBACK_REVIEWED,
        entity_type="ai_feedback", entity_id=entry.id,
        actor_id=principal.id, actor_role=principal.primary_role,
        before_state=before,
        after_state={"reviewed": True, "decision": decision, "field": correction.field},
        reason=note,
    )
    session.commit()
    return entry


def training_pages(session: Session) -> list[dict]:
    """Every page holding an accepted correction, with what a trainer needs.

    Per page: its OCR blocks (words and boxes, as the model will see them) and
    every judged field on it with the value a human settled on. Labelling the
    words is the training script's job; this returns the evidence, in page
    coordinates, and nothing about who the record belongs to beyond the
    values on the page itself.
    """
    accepted = session.execute(
        select(AiFeedback.id, FieldCorrection.document_id, Extraction.page_number)
        .join(FieldCorrection, FieldCorrection.id == AiFeedback.correction_id)
        .join(Extraction, Extraction.id == FieldCorrection.extraction_id)
        .join(Document, Document.id == FieldCorrection.document_id)
        .where(
            AiFeedback.review_decision == ACCEPTED,
            Document.state.in_(_FINISHED),
        )
    ).all()

    by_page: dict[tuple[str, int], list[str]] = {}
    for feedback_id, document_id, page_number in accepted:
        by_page.setdefault((document_id, page_number), []).append(feedback_id)

    pages = []
    for (document_id, page_number), feedback_ids in sorted(by_page.items()):
        document = session.get(Document, document_id)
        page = session.execute(
            select(DocumentPage).where(
                DocumentPage.document_id == document_id,
                DocumentPage.page_number == page_number,
            )
        ).scalar_one_or_none()
        if page is None:
            continue
        blocks = session.execute(
            select(OcrBlock).where(OcrBlock.page_id == page.id)
            .order_by(OcrBlock.reading_order)
        ).scalars().all()
        extractions = session.execute(
            select(Extraction).where(
                Extraction.document_id == document_id,
                Extraction.page_number == page_number,
                Extraction.status.not_in((FieldStatus.ILLEGIBLE, FieldStatus.ESCALATED)),
            )
        ).scalars().all()

        pages.append({
            "document_id": document.external_id,
            "page_number": page_number,
            "width": page.width,
            "height": page.height,
            "feedback_ids": sorted(feedback_ids),
            "blocks": [
                {
                    "text": b.text,
                    "confidence": b.confidence,
                    "bbox": [b.bbox_x1, b.bbox_y1, b.bbox_x2, b.bbox_y2],
                    "reading_order": b.reading_order,
                }
                for b in blocks
            ],
            "fields": [
                {
                    "field": e.field,
                    "row": e.row_index,
                    "bbox": (
                        [e.bbox_x1, e.bbox_y1, e.bbox_x2, e.bbox_y2]
                        if e.bbox_x1 is not None else None
                    ),
                    "ai_value": e.normalized_value,
                    "value": e.effective_value,
                    "corrected": e.corrected_value is not None
                    and (e.corrected_value or "").strip()
                    != (e.normalized_value or "").strip(),
                }
                for e in extractions
                if e.effective_value is not None
            ],
        })
    return pages


def mark_included(session: Session, feedback_ids: list[str], tag: str) -> int:
    """Stamp rows with the first dataset they went into. Earlier stamps stay."""
    rows = session.execute(
        select(AiFeedback).where(
            AiFeedback.id.in_(feedback_ids), AiFeedback.included_in_dataset.is_(None)
        )
    ).scalars().all()
    for row in rows:
        row.included_in_dataset = tag
    session.commit()
    return len(rows)


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
            "review_decision": entry.review_decision,
            "included_in_dataset": entry.included_in_dataset,
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
    "ACCEPTED", "CONFIDENT", "CONFIDENT_BUT_WRONG", "DECISIONS", "FEEDBACK_REVIEWED",
    "MISSED_ENTIRELY", "MODERATE_MISS", "REJECTED", "RETRAINING_THRESHOLD",
    "UNCERTAIN_AND_WRONG", "UNSURE", "FeedbackError", "Readiness", "classify",
    "mark_included", "pool", "readiness", "record_correction", "review",
    "training_pages",
]
