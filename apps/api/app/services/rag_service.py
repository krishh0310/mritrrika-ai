"""Grounded question answering (§10, §18, §35).

The ordering is the security property, and it is not negotiable:

    JWT -> user_id -> owner_id -> authorized parcel_ids
        -> retrieval RESTRICTED to those parcels
        -> LLM sees only that context
        -> answer carries source record ids

The model is never handed a record the caller cannot already read, so a prompt
injection cannot exfiltrate someone else's land data -- there is nothing in the
context to leak.

Structured SQL is preferred for exact questions ('who owns khasra 142?'); the
LLM is used to explain and summarise, never as the source of fact (Principle 1:
database facts > LLM output).
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import date

from sqlalchemy.orm import Session

from app.config.settings import get_settings
from app.models import Parcel
from app.repositories import ownership_repository
from app.services.auth_service import Principal
from app.services.citizen_service import my_parcel_ids

logger = logging.getLogger(__name__)

YEAR_PATTERN = re.compile(r"\b(1[89]\d{2}|20\d{2})\b")
KHASRA_PATTERN = re.compile(r"\b(\d{1,5}(?:/\d{1,3})*)\b")


@dataclass
class Citation:
    """Where an answer's facts came from (§35)."""

    source_type: str
    source_id: str
    detail: str

    def to_dict(self) -> dict:
        return {"type": self.source_type, "id": self.source_id, "detail": self.detail}


@dataclass
class Answer:
    answer: str
    citations: list[Citation] = field(default_factory=list)
    #: Structured rows behind the answer, so the UI can render a table even
    #: when the language model is unavailable (§82).
    records: list[dict] = field(default_factory=list)
    intent: str = "unknown"
    llm_used: bool = False
    #: True when the answer is retrieval-only because no LLM was reachable.
    degraded: bool = False

    def to_dict(self) -> dict:
        return {
            "answer": self.answer,
            "citations": [c.to_dict() for c in self.citations],
            "records": self.records,
            "intent": self.intent,
            "llm_used": self.llm_used,
            "degraded": self.degraded,
            "is_synthetic": True,
        }


def classify_intent(question: str) -> str:
    """Cheap deterministic routing (§10).

    Exact-fact questions go to SQL. Only explanatory questions need the model.
    """
    lowered = question.lower()
    if YEAR_PATTERN.search(question) and any(
        w in lowered for w in ("own", "owner", "मालिक", "खातेदार", "held")
    ):
        return "historical_owner"
    if any(w in lowered for w in ("history", "changed", "इतिहास", "mutation", "नामांतरण")):
        return "ownership_history"
    if any(w in lowered for w in ("my land", "my parcel", "मेरी", "how many", "list")):
        return "my_holdings"
    if any(w in lowered for w in ("area", "क्षेत्रफल", "size", "how big")):
        return "parcel_area"
    return "general"


def _authorized_parcels(session: Session, principal: Principal) -> list[Parcel]:
    """THE authorization gate. Everything downstream reads only these rows."""
    allowed_ids = my_parcel_ids(session, principal)
    if not allowed_ids:
        return []
    return list(
        session.query(Parcel).filter(Parcel.id.in_(allowed_ids)).all()
    )


def _resolve_parcel(parcels: list[Parcel], question: str) -> Parcel | None:
    """Pick which of the caller's OWN parcels a question refers to."""
    match = KHASRA_PATTERN.search(question)
    if match:
        wanted = match.group(1)
        for parcel in parcels:
            if parcel.khasra_number == wanted or parcel.external_id.endswith(wanted):
                return parcel
    return parcels[0] if len(parcels) == 1 else None


def answer_question(
    session: Session, principal: Principal, question: str
) -> Answer:
    """Answer within the caller's authorized scope, with citations."""
    parcels = _authorized_parcels(session, principal)
    intent = classify_intent(question)

    if not parcels:
        return Answer(
            answer=(
                "No land records are linked to your account, so there is "
                "nothing I can look up for you."
            ),
            intent=intent,
        )

    if intent == "historical_owner":
        year_match = YEAR_PATTERN.search(question)
        as_of = date(int(year_match.group(1)), 12, 31) if year_match else date.today()
        parcel = _resolve_parcel(parcels, question)
        if parcel is None:
            return _holdings_answer(session, parcels, intent,
                                    "Which parcel did you mean?")
        owners = ownership_repository.owners_on(session, parcel.id, as_of)
        if not owners:
            return Answer(
                answer=f"No ownership was recorded for khasra "
                       f"{parcel.khasra_number} as of {as_of.isoformat()}.",
                intent=intent,
                records=[],
                citations=[Citation("parcel", parcel.external_id,
                                    f"khasra {parcel.khasra_number}")],
            )
        listed = ", ".join(f"{o['owner']} ({o['share']})" for o in owners)
        return Answer(
            answer=f"As of {as_of.isoformat()}, khasra {parcel.khasra_number} "
                   f"was recorded to {listed}.",
            records=owners,
            intent=intent,
            citations=[
                Citation("parcel", parcel.external_id, f"khasra {parcel.khasra_number}"),
                *[Citation("owner", o["owner_id"], o["owner"]) for o in owners],
            ],
        )

    if intent == "ownership_history":
        parcel = _resolve_parcel(parcels, question)
        if parcel is None:
            return _holdings_answer(session, parcels, intent,
                                    "Which parcel's history did you mean?")
        history = ownership_repository.ownership_history(session, parcel.id)
        lines = [
            f"{h['valid_from']} to {h['valid_to'] or 'present'}: "
            f"{h['owner']} ({h['share']})"
            + (f" via mutation {h['mutation_number']}" if h["mutation_number"] else "")
            for h in history
        ]
        return Answer(
            answer=f"Ownership of khasra {parcel.khasra_number}:\n"
                   + "\n".join(f"  - {line}" for line in lines),
            records=history,
            intent=intent,
            citations=[Citation("parcel", parcel.external_id,
                                f"khasra {parcel.khasra_number}")],
        )

    if intent == "parcel_area":
        parcel = _resolve_parcel(parcels, question)
        if parcel is None:
            return _holdings_answer(session, parcels, intent)
        return Answer(
            answer=f"Khasra {parcel.khasra_number} is recorded as "
                   f"{parcel.area_value} {parcel.area_unit_raw or parcel.area_unit}.",
            records=[{"parcel_id": parcel.external_id,
                      "area_value": parcel.area_value,
                      "area_unit": parcel.area_unit}],
            intent=intent,
            citations=[Citation("parcel", parcel.external_id,
                                f"khasra {parcel.khasra_number}")],
        )

    return _holdings_answer(session, parcels, intent)


def _holdings_answer(
    session: Session, parcels: list[Parcel], intent: str, prefix: str | None = None
) -> Answer:
    rows = [
        {
            "parcel_id": p.external_id,
            "khasra_number": p.khasra_number,
            "area_value": p.area_value,
            "area_unit": p.area_unit,
            "land_class": p.land_class,
        }
        for p in parcels
    ]
    listing = ", ".join(f"khasra {p.khasra_number}" for p in parcels)
    text = f"You have {len(parcels)} recorded parcel(s): {listing}."
    if prefix:
        text = f"{prefix} {text}"
    return Answer(
        answer=text,
        records=rows,
        intent=intent,
        citations=[Citation("parcel", p.external_id, f"khasra {p.khasra_number}")
                   for p in parcels],
    )


def explain(answer: Answer, question: str) -> Answer:
    """Optionally have the LLM phrase the retrieved facts more naturally.

    The model receives ONLY the rows already retrieved under authorization, and
    is instructed not to add facts. If it is unavailable the structured answer
    is returned unchanged and flagged `degraded` -- never a fabricated one
    (§82).
    """
    settings = get_settings()
    if not settings.gemini_api_key or not answer.records:
        answer.degraded = not bool(settings.gemini_api_key)
        return answer

    try:
        from google import genai

        client = genai.Client(api_key=settings.gemini_api_key)
        response = client.models.generate_content(
            model=settings.gemini_llm_model,
            contents=(
                "You are helping a citizen understand their own land record.\n"
                "Answer ONLY from the facts below. Do not add, infer or "
                "estimate anything. If the facts do not answer the question, "
                "say so plainly.\n\n"
                f"QUESTION: {question}\n\n"
                f"FACTS: {answer.records}\n\n"
                "Reply in two or three plain sentences."
            ),
        )
        text = (response.text or "").strip()
        if text:
            answer.answer = text
            answer.llm_used = True
    except Exception as exc:
        # Degrade to the structured answer rather than failing the request.
        logger.warning("LLM unavailable, returning structured answer: %s", exc)
        answer.degraded = True

    return answer
