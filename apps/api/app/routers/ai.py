"""Grounded AI assistant (§18, §35)."""

from __future__ import annotations

from fastapi import APIRouter, Body, Depends
from sqlalchemy.orm import Session

from app.auth.dependencies import require
from app.db import get_session
from app.services import rag_service
from app.services.auth_service import Principal

router = APIRouter(prefix="/api/v1/ai", tags=["ai"])


@router.post("/query")
def query(
    question: str = Body(..., embed=True, min_length=3, max_length=1000),
    explain: bool = Body(True, embed=True),
    principal: Principal = Depends(require("ai:query")),
    session: Session = Depends(get_session),
) -> dict:
    """Answer a question within the caller's authorized scope.

    Authorization happens BEFORE retrieval, so the model is never shown a
    record the caller could not already read (§18).
    """
    answer = rag_service.answer_question(session, principal, question)
    if explain:
        answer = rag_service.explain(answer, question)
    return answer.to_dict()
