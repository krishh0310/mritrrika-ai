"""Grounded AI assistant (§18, §35)."""

from __future__ import annotations

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request, status
from sqlalchemy.orm import Session

from app.auth.dependencies import require, require_any
from app.db import get_session
from app.security.auth_state import AiRateLimited, consume_ai_query
from app.services import feedback_service, rag_service
from app.services.auth_service import Principal

router = APIRouter(prefix="/api/v1/ai", tags=["ai"])


@router.post("/query")
def query(
    request: Request,
    question: str = Body(..., embed=True, min_length=3, max_length=1000),
    explain: bool = Body(True, embed=True),
    principal: Principal = Depends(require("ai:query")),
    session: Session = Depends(get_session),
) -> dict:
    """Answer a question within the caller's authorized scope.

    Authorization happens BEFORE retrieval, so the model is never shown a
    record the caller could not already read (§18).
    """
    client_ip = request.client.host if request.client else "unknown"
    try:
        consume_ai_query(principal.user.id, client_ip)
    except AiRateLimited as exc:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="AI query limit reached. Try again later.",
            headers={"Retry-After": str(exc.retry_after)},
        ) from None
    answer = rag_service.answer_question(session, principal, question)
    if explain:
        answer = rag_service.explain(answer, question)
    return answer.to_dict()


@router.get("/feedback")
def retraining_pool(
    limit: int = Query(100, ge=1, le=500),
    reviewed: bool | None = Query(None),
    principal: Principal = Depends(require_any("analytics:view", "anomaly:view")),
    session: Session = Depends(get_session),
) -> dict:
    """The curated retraining pool and whether a run is worth proposing (§67).

    Officer-internal, like every other model-facing view: it says which
    corrections are most informative, never what the corrected values were.
    Reading record content belongs to the verification screens, behind their
    own authorization.
    """
    return {
        "readiness": feedback_service.readiness(session).to_dict(),
        "pool": feedback_service.pool(session, limit=limit, reviewed=reviewed),
        "is_synthetic": True,
    }


@router.post("/feedback/{feedback_id}/review")
def review_feedback(
    feedback_id: str,
    decision: str = Body(..., embed=True, max_length=16),
    note: str | None = Body(None, embed=True, max_length=1000),
    principal: Principal = Depends(require("document:approve")),
    session: Session = Depends(get_session),
) -> dict:
    """Accept a verifier correction into the training pool, or reject it (§67).

    The curation step between a correction and a training run. Tehsildar-only:
    deciding what the model learns is a supervisory call, not something the
    verifier who made the correction should approve for themselves.
    """
    try:
        entry = feedback_service.review(
            session, feedback_id, decision=decision, principal=principal, note=note
        )
    except feedback_service.FeedbackError as exc:
        code = (status.HTTP_404_NOT_FOUND if str(exc).startswith("no feedback")
                else status.HTTP_422_UNPROCESSABLE_CONTENT)
        raise HTTPException(code, str(exc)) from None
    return {
        "feedback_id": entry.id,
        "review_decision": entry.review_decision,
        "reviewed_at": entry.reviewed_at.isoformat(),
        "readiness": feedback_service.readiness(session).to_dict(),
    }
