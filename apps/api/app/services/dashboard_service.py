"""Dashboard and analytics aggregates (§20, §27, §31).

Each role gets the counters its own dashboard renders, computed here rather
than in a route handler (§80). Every figure is derived from persisted workflow
state -- none of these cards is a decorative constant.
"""

from __future__ import annotations

from datetime import UTC, datetime

from mrittika_domain import DocumentState
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import (
    AnomalyFlag,
    ApprovalAction,
    Document,
    Extraction,
    ProcessingJob,
    VerificationTask,
)
from app.services.auth_service import (
    Principal,
    anomaly_jurisdiction_clause,
    document_jurisdiction_clause,
)

#: §8 bands. Kept here as the reporting cut-points; the fusion that produces
#: the scores lives in packages/domain/confidence.py.
HIGH_CONFIDENCE = 0.85
MEDIUM_CONFIDENCE = 0.60

#: States that mean "the pipeline has finished with this document and a human
#: now owns it" -- used for the DEO's completed counter.
_DEO_COMPLETED = (
    DocumentState.AI_EXTRACTED,
    DocumentState.NEEDS_VERIFICATION,
    DocumentState.UNDER_VERIFICATION,
    DocumentState.VERIFIED,
    DocumentState.PENDING_APPROVAL,
    DocumentState.APPROVED,
)


def _start_of_today() -> datetime:
    now = datetime.now(UTC)
    return now.replace(hour=0, minute=0, second=0, microsecond=0)


def _count_documents(session: Session, principal: Principal, *states: str) -> int:
    return session.execute(
        select(func.count(Document.id)).where(
            document_jurisdiction_clause(session, principal),
            Document.state.in_(states),
        )
    ).scalar_one()


def deo_dashboard(session: Session, principal: Principal) -> dict:
    """§20 cards, scoped to the documents this operator uploaded.

    Scoped rather than global: an operator's "uploaded today" should count
    their own work, not the whole tehsil's.
    """
    today = _start_of_today()
    mine = Document.uploaded_by_id == principal.user.id

    def mine_where(*conditions) -> int:
        return session.execute(
            select(func.count(Document.id)).where(mine, *conditions)
        ).scalar_one()

    failed = session.execute(
        select(func.count(func.distinct(ProcessingJob.document_id)))
        .join(Document, Document.id == ProcessingJob.document_id)
        .where(mine, ProcessingJob.status == "FAILED")
    ).scalar_one()

    recent = session.execute(
        select(Document).where(mine).order_by(Document.created_at.desc()).limit(10)
    ).scalars().all()

    return {
        "cards": {
            "uploaded_today": mine_where(Document.created_at >= today),
            "processing": mine_where(
                Document.state.in_(
                    (DocumentState.QUALITY_CHECK, DocumentState.PROCESSING)
                )
            ),
            "completed": mine_where(Document.state.in_(_DEO_COMPLETED)),
            "needs_verification": mine_where(
                Document.state == DocumentState.NEEDS_VERIFICATION
            ),
            "quality_rejected": mine_where(
                Document.quality_recommendation == "REJECT_QUALITY"
            ),
            "failed": failed,
        },
        "recent_documents": [
            {
                "document_id": d.external_id,
                "document_type": d.document_type,
                "state": d.state,
                "quality_score": d.quality_score,
                "quality_recommendation": d.quality_recommendation,
                "record_year": d.record_year,
                "created_at": d.created_at.isoformat() if d.created_at else None,
            }
            for d in recent
        ],
        "is_synthetic": True,
    }


def verifier_dashboard(session: Session, principal: Principal) -> dict:
    """§27 cards.

    "Assigned" is this verifier's own; the remaining counters describe the
    shared queue, because a verifier picking up work needs to see what is
    waiting, not only what already carries their name.
    """
    today = _start_of_today()
    open_task = VerificationTask.status.in_(("PENDING", "IN_PROGRESS"))

    def tasks_where(*conditions) -> int:
        return session.execute(
            select(func.count(VerificationTask.id))
            .join(Document, Document.id == VerificationTask.document_id)
            .where(document_jurisdiction_clause(session, principal), *conditions)
        ).scalar_one()

    return {
        "cards": {
            "assigned": tasks_where(
                open_task, VerificationTask.assigned_to_id == principal.user.id
            ),
            "needs_review": tasks_where(open_task),
            "low_confidence": tasks_where(
                open_task, VerificationTask.lowest_confidence < MEDIUM_CONFIDENCE
            ),
            "medium_confidence": tasks_where(
                open_task,
                VerificationTask.lowest_confidence >= MEDIUM_CONFIDENCE,
                VerificationTask.lowest_confidence < HIGH_CONFIDENCE,
            ),
            "anomaly_flagged": tasks_where(open_task, VerificationTask.anomaly_count > 0),
            "completed_today": tasks_where(
                VerificationTask.status == "COMPLETED",
                VerificationTask.completed_at >= today,
            ),
        },
        "is_synthetic": True,
    }


def _average_verification_seconds(session: Session, principal: Principal) -> float | None:
    """Mean wall-clock time from picking a task up to completing it."""
    rows = session.execute(
        select(VerificationTask.started_at, VerificationTask.completed_at)
        .join(Document, Document.id == VerificationTask.document_id)
        .where(
            document_jurisdiction_clause(session, principal),
            VerificationTask.completed_at.is_not(None),
            VerificationTask.started_at.is_not(None),
        )
    ).all()
    if not rows:
        return None
    spans = [(done - started).total_seconds() for started, done in rows]
    return round(sum(spans) / len(spans), 1)


def tehsildar_dashboard(session: Session, principal: Principal) -> dict:
    """§31 cards plus the digitization-progress figure."""
    today = _start_of_today()

    scope = document_jurisdiction_clause(session, principal)
    total = session.execute(select(func.count(Document.id)).where(scope)).scalar_one()
    approved = _count_documents(session, principal, DocumentState.APPROVED)

    approved_today = session.execute(
        select(func.count(ApprovalAction.id))
        .join(Document, Document.id == ApprovalAction.document_id)
        .where(
            scope,
            ApprovalAction.decision == "APPROVED", ApprovalAction.created_at >= today
        )
    ).scalar_one()
    returned = session.execute(
        select(func.count(ApprovalAction.id))
        .join(Document, Document.id == ApprovalAction.document_id)
        .where(scope, ApprovalAction.decision == "RETURNED")
    ).scalar_one()

    average_confidence = session.execute(
        select(func.avg(Extraction.final_confidence))
        .join(Document, Document.id == Extraction.document_id)
        .where(scope)
    ).scalar_one()

    open_anomalies = session.execute(
        select(func.count(AnomalyFlag.id)).where(
            anomaly_jurisdiction_clause(session, principal),
            AnomalyFlag.status == "OPEN",
        )
    ).scalar_one()

    return {
        "cards": {
            "pending_approval": _count_documents(
                session, principal, DocumentState.VERIFIED, DocumentState.PENDING_APPROVAL
            ),
            "approved_today": approved_today,
            "returned": returned,
            "potential_inconsistencies": open_anomalies,
            "average_ai_confidence": (
                round(float(average_confidence), 3) if average_confidence else None
            ),
            "average_verification_seconds": _average_verification_seconds(session, principal),
            "digitization_progress": (
                round(approved / total, 3) if total else 0.0
            ),
        },
        "totals": {"documents": total, "approved": approved},
        "is_synthetic": True,
    }


def analytics(session: Session, principal: Principal) -> dict:
    """District/tehsil analytics for the tehsildar's charts (§31).

    Distributions rather than headline numbers: which states documents are
    stuck in, how confidence is spread, and which anomaly types recur.
    """
    by_state = dict(
        session.execute(
            select(Document.state, func.count(Document.id))
            .where(document_jurisdiction_clause(session, principal))
            .group_by(Document.state)
        ).all()
    )
    by_type = dict(
        session.execute(
            select(Document.document_type, func.count(Document.id))
            .where(document_jurisdiction_clause(session, principal))
            .group_by(Document.document_type)
        ).all()
    )
    by_quality = dict(
        session.execute(
            select(Document.quality_recommendation, func.count(Document.id))
            .where(
                document_jurisdiction_clause(session, principal),
                Document.quality_recommendation.is_not(None),
            )
            .group_by(Document.quality_recommendation)
        ).all()
    )
    by_anomaly = dict(
        session.execute(
            select(AnomalyFlag.anomaly_type, func.count(AnomalyFlag.id))
            .where(anomaly_jurisdiction_clause(session, principal))
            .group_by(AnomalyFlag.anomaly_type)
        ).all()
    )

    confidences = session.execute(
        select(Extraction.final_confidence)
        .join(Document, Document.id == Extraction.document_id)
        .where(
            document_jurisdiction_clause(session, principal),
            Extraction.final_confidence.is_not(None),
        )
    ).scalars().all()
    bands = {"HIGH": 0, "MEDIUM": 0, "LOW": 0}
    for score in confidences:
        if score >= HIGH_CONFIDENCE:
            bands["HIGH"] += 1
        elif score >= MEDIUM_CONFIDENCE:
            bands["MEDIUM"] += 1
        else:
            bands["LOW"] += 1

    #: Workload by operator -- who uploaded how much (§31 "workload").
    workload = [
        {"role": "DEO", "user_id": user_id, "documents": count}
        for user_id, count in session.execute(
            select(Document.uploaded_by_id, func.count(Document.id))
            .where(
                document_jurisdiction_clause(session, principal),
                Document.uploaded_by_id.is_not(None),
            )
            .group_by(Document.uploaded_by_id)
        ).all()
    ]

    return {
        "documents_by_state": by_state,
        "documents_by_type": by_type,
        "documents_by_quality": by_quality,
        "anomalies_by_type": by_anomaly,
        "confidence_bands": bands,
        "workload": workload,
        "is_synthetic": True,
    }


def approval_queue_detail(session: Session, document: Document) -> dict:
    """Extra context the approval workspace shows beyond the verifier view (§32)."""
    anomalies = session.execute(
        select(AnomalyFlag).where(AnomalyFlag.document_id == document.id)
    ).scalars().all()
    decisions = session.execute(
        select(ApprovalAction)
        .where(ApprovalAction.document_id == document.id)
        .order_by(ApprovalAction.created_at)
    ).scalars().all()

    return {
        "anomalies": [
            {
                "anomaly_type": a.anomaly_type,
                "score": a.score,
                "explanation": a.explanation,
                "evidence": a.evidence,
                "status": a.status,
                "model_version": a.model_version,
            }
            for a in anomalies
        ],
        "decisions": [
            {
                "decision": d.decision,
                "reason": d.reason,
                "at": d.created_at.isoformat() if d.created_at else None,
            }
            for d in decisions
        ],
    }


__all__ = [
    "analytics", "approval_queue_detail", "deo_dashboard", "tehsildar_dashboard",
    "verifier_dashboard",
]
