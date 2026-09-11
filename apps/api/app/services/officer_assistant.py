"""The officer assistant (§35).

Officers own no land, so the citizen scope (login -> owner -> parcels) gives
them nothing, and the assistant used to answer every tehsildar question with
"no land records are linked to your account". Officers are scoped by
jurisdiction instead, using the same predicates the document, anomaly and
queue endpoints already enforce -- the assistant must never see further than
the officer's own screens do.

Order is the same security property as the citizen path:

    principal -> jurisdiction location ids -> in-scope parcels / documents /
    flags -> retrieval restricted to those -> answer with record ids

Internal signals are gated on the permission that already guards them
elsewhere: anomaly flags need `anomaly:view`, confidence needs
`confidence:view`, raw OCR needs `ocr:view`.
"""

from __future__ import annotations

import re

from mrittika_domain.confidence import MEDIUM_THRESHOLD
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models import AnomalyFlag, Document, Extraction, Location, Parcel
from app.services import rag_service
from app.services.auth_service import (
    Principal,
    anomaly_jurisdiction_clause,
    document_jurisdiction_clause,
    jurisdiction_location_ids,
)
from app.services.rag_service import Answer, Citation

DOCUMENT_ID_PATTERN = re.compile(r"\bDOC-\d{3,}\b", re.IGNORECASE)

#: Enough to act on, few enough to read. The UI renders every row.
MAX_ROWS = 25

#: A recorded area and a digitised one this far apart is worth an officer's look.
AREA_TOLERANCE = 0.05


def classify_intent(question: str) -> str:
    lowered = question.lower()
    if any(w in lowered for w in ("flag", "anomal", "inconsisten", "suspicious", "संदिग्ध")):
        return "anomaly_explanation"
    if ("low" in lowered and "confiden" in lowered) or "needs review" in lowered or (
        "कम" in question and "विश्वास" in question
    ):
        return "low_confidence"
    if "area" in lowered and any(w in lowered for w in ("compare", "historical", "differ")):
        return "area_comparison"
    return rag_service.classify_intent(question)


def answer_question(session: Session, principal: Principal, question: str) -> Answer:
    allowed = jurisdiction_location_ids(session, principal) or set()
    intent = classify_intent(question)

    if not allowed:
        return _officer(Answer(
            answer=(
                "No jurisdiction is assigned to your account, so there are no "
                "records I can look up for you."
            ),
            intent=intent,
        ))

    parcels = list(
        session.execute(
            select(Parcel).where(Parcel.village_id.in_(allowed)).order_by(Parcel.external_id)
        ).scalars()
    )

    handlers = {
        "anomaly_explanation": _anomalies,
        "low_confidence": _low_confidence,
        "area_comparison": _area_comparison,
    }
    if intent in handlers:
        return _officer(handlers[intent](session, principal, question, parcels, allowed, intent))

    if intent in ("historical_owner", "ownership_history", "parcel_area"):
        parcel = rag_service._resolve_parcel(parcels, question)
        if parcel is None:
            return _officer(_which_parcel(parcels, intent))
        if intent == "historical_owner":
            answer = rag_service.owners_on_answer(
                session, parcel, rag_service.as_of_date(question), intent
            )
        elif intent == "ownership_history":
            answer = rag_service.history_answer(session, parcel, intent)
        else:
            answer = rag_service.area_answer(parcel, intent)
        return _officer(answer)

    return _officer(Answer(
        answer=(
            f"I can answer questions about the {len(parcels)} parcels in your "
            "jurisdiction. Try: why a document was flagged, low-confidence "
            "records for a village, the ownership history of a parcel, who "
            "owned a parcel in a given year, which mutation transferred it, or "
            "how its recorded area compares with digitised documents."
        ),
        intent=intent,
    ))


def _officer(answer: Answer) -> Answer:
    answer.audience = "officer"
    return answer


def _which_parcel(parcels: list[Parcel], intent: str) -> Answer:
    example = parcels[0].external_id if parcels else "PARCEL-UP-DEMO-0142"
    return Answer(
        answer=(
            "Which parcel did you mean? Name it by parcel ID (for example "
            f"{example}) or by its khasra number."
        ),
        intent=intent,
    )


def _refused(permission: str, what: str, intent: str) -> Answer:
    return Answer(
        answer=f"Your role cannot view {what} (requires {permission}).",
        intent=intent,
    )


def _resolve_document(session: Session, principal: Principal, question: str):
    match = DOCUMENT_ID_PATTERN.search(question)
    if not match:
        return None, None
    wanted = match.group(0).upper()
    document = session.execute(
        select(Document).where(
            Document.external_id == wanted,
            document_jurisdiction_clause(session, principal),
        )
    ).scalar_one_or_none()
    # A document outside the jurisdiction and one that does not exist return
    # the same thing, so the assistant cannot be used to probe other tehsils.
    return wanted, document


def _resolve_village(session: Session, question: str, allowed: set[str]):
    villages = session.execute(
        select(Location).where(Location.level == "VILLAGE")
    ).scalars()
    lowered = question.lower()
    for village in villages:
        names = [village.external_id.lower(), (village.name or "").lower()]
        if any(n and n in lowered for n in names) or (
            village.name_devanagari and village.name_devanagari in question
        ):
            return village, village.id in allowed
    return None, True


# ── anomaly flags ────────────────────────────────────────────────────────────
def _anomalies(session, principal, question, parcels, allowed, intent) -> Answer:
    if not principal.has("anomaly:view"):
        return _refused("anomaly:view", "anomaly flags", intent)

    stmt = (
        select(AnomalyFlag, Document.external_id, Parcel.external_id)
        .outerjoin(Document, Document.id == AnomalyFlag.document_id)
        .outerjoin(Parcel, Parcel.id == AnomalyFlag.parcel_id)
        .where(anomaly_jurisdiction_clause(session, principal))
    )

    subject = "your jurisdiction"
    wanted_doc, document = _resolve_document(session, principal, question)
    if wanted_doc:
        if document is None:
            return Answer(
                answer=f"There is no document {wanted_doc} in your jurisdiction.",
                intent=intent,
            )
        stmt = stmt.where(AnomalyFlag.document_id == document.id)
        subject = document.external_id
    else:
        parcel = rag_service._resolve_parcel(parcels, question)
        if parcel is not None:
            stmt = stmt.where(AnomalyFlag.parcel_id == parcel.id)
            subject = f"khasra {parcel.khasra_number}"
        else:
            # Unscoped questions list what still needs a decision.
            stmt = stmt.where(AnomalyFlag.status == "OPEN")

    rows = session.execute(
        stmt.order_by(AnomalyFlag.score.desc().nulls_last()).limit(MAX_ROWS)
    ).all()

    if not rows:
        return Answer(
            answer=f"No potential inconsistencies are recorded for {subject}.",
            intent=intent,
            citations=[Citation("document", document.external_id, document.document_type)]
            if document is not None else [],
        )

    records = [
        {
            "flag_id": flag.id,
            "anomaly_type": flag.anomaly_type,
            "status": flag.status,
            "score": round(flag.score, 3) if flag.score is not None else None,
            "explanation": flag.explanation,
            "document_id": doc_ext,
            "parcel_id": parcel_ext,
        }
        for flag, doc_ext, parcel_ext in rows
    ]
    lines = [
        f"  - {r['anomaly_type']} ({r['status'].lower()}"
        + (f", score {r['score']}" if r["score"] is not None else "")
        + f"): {r['explanation']}"
        for r in records
    ]
    citations = []
    for r in records:
        citations.append(Citation("anomaly", r["flag_id"], r["anomaly_type"]))
        if r["document_id"]:
            citations.append(Citation("document", r["document_id"], "flagged document"))
        if r["parcel_id"]:
            citations.append(Citation("parcel", r["parcel_id"], "flagged parcel"))

    # §34: never "fraud". These are prompts for a human to look.
    return Answer(
        answer=(
            f"{len(records)} potential inconsistenc{'y' if len(records) == 1 else 'ies'} "
            f"recorded for {subject}. Manual investigation recommended.\n"
            + "\n".join(lines)
        ),
        records=records,
        intent=intent,
        citations=_dedupe(citations),
    )


# ── low-confidence fields ────────────────────────────────────────────────────
def _low_confidence(session, principal, question, parcels, allowed, intent) -> Answer:
    if not principal.has("confidence:view"):
        return _refused("confidence:view", "confidence scores", intent)

    stmt = (
        select(Extraction, Document)
        .join(Document, Document.id == Extraction.document_id)
        .where(
            document_jurisdiction_clause(session, principal),
            or_(
                Extraction.status == "NEEDS_REVIEW",
                Extraction.final_confidence < MEDIUM_THRESHOLD,
            ),
        )
    )

    subject = "your jurisdiction"
    village, in_scope = _resolve_village(session, question, allowed)
    if village is not None:
        if not in_scope:
            return Answer(
                answer=f"{village.name} is not in your jurisdiction.",
                intent=intent,
            )
        village_parcels = select(Parcel.id).where(Parcel.village_id == village.id)
        stmt = stmt.where(
            or_(Document.village_id == village.id, Document.parcel_id.in_(village_parcels))
        )
        subject = f"{village.name} ({village.name_devanagari})"

    rows = session.execute(
        stmt.order_by(Extraction.final_confidence.asc()).limit(MAX_ROWS)
    ).all()

    if not rows:
        return Answer(
            answer=f"No low-confidence fields are waiting in {subject}.",
            intent=intent,
        )

    show_raw = principal.has("ocr:view")
    records = []
    for extraction, document in rows:
        value = extraction.corrected_value or extraction.normalized_value
        record = {
            "document_id": document.external_id,
            "document_state": document.state,
            "field": extraction.field,
            "value": value,
            "confidence": round(extraction.final_confidence, 3),
            "status": extraction.status,
        }
        if show_raw:
            record["raw_value"] = extraction.raw_value
        records.append(record)

    documents = sorted({r["document_id"] for r in records})
    lines = [
        f"  - {r['document_id']} {r['field']}: {r['value']!r} "
        f"(confidence {r['confidence']}, {r['status'].replace('_', ' ').lower()})"
        for r in records
    ]
    return Answer(
        answer=(
            f"{len(records)} low-confidence field(s) across {len(documents)} "
            f"document(s) in {subject}:\n" + "\n".join(lines)
        ),
        records=records,
        intent=intent,
        citations=[Citation("document", d, "has low-confidence fields") for d in documents],
    )


# ── recorded area vs digitised documents ─────────────────────────────────────
def _area_comparison(session, principal, question, parcels, allowed, intent) -> Answer:
    parcel = rag_service._resolve_parcel(parcels, question)
    if parcel is None:
        return _which_parcel(parcels, intent)

    rows = session.execute(
        select(Extraction, Document)
        .join(Document, Document.id == Extraction.document_id)
        .where(
            Document.parcel_id == parcel.id,
            document_jurisdiction_clause(session, principal),
            Extraction.field.in_(("AREA", "AREA_UNIT")),
        )
        .order_by(Document.record_year, Document.external_id)
    ).all()

    recorded = f"{parcel.area_value} {parcel.area_unit_raw or parcel.area_unit}"
    citations = [Citation("parcel", parcel.external_id, f"khasra {parcel.khasra_number}")]

    by_document: dict[str, dict] = {}
    for extraction, document in rows:
        entry = by_document.setdefault(document.external_id, {
            "document_id": document.external_id,
            "record_year": document.record_year,
            "document_state": document.state,
        })
        value = extraction.corrected_value or extraction.normalized_value
        entry["area_value" if extraction.field == "AREA" else "area_unit"] = value

    records = []
    lines = []
    for entry in by_document.values():
        if "area_value" not in entry:
            continue
        try:
            digitised = float(entry["area_value"])
        except (TypeError, ValueError):
            continue
        unit = entry.get("area_unit") or ""
        same_unit = not unit or unit.upper() == (parcel.area_unit or "").upper()
        differs = (
            same_unit
            and parcel.area_value
            and abs(digitised - parcel.area_value) / parcel.area_value > AREA_TOLERANCE
        )
        entry["differs_from_recorded"] = bool(differs)
        entry["comparable_unit"] = same_unit
        records.append(entry)
        citations.append(Citation("document", entry["document_id"], "digitised area"))
        note = (
            "differs from the recorded area" if differs
            else "matches the recorded area" if same_unit
            else "in a different unit, not compared"
        )
        lines.append(
            f"  - {entry['document_id']} ({entry.get('record_year') or 'year unknown'}, "
            f"{entry['document_state'].replace('_', ' ').lower()}): "
            f"{entry['area_value']} {unit} -- {note}"
        )

    if not records:
        return Answer(
            answer=(
                f"Khasra {parcel.khasra_number} is recorded as {recorded}. No "
                "digitised document for this parcel has an area to compare yet."
            ),
            records=[{"parcel_id": parcel.external_id, "area_value": parcel.area_value,
                      "area_unit": parcel.area_unit}],
            intent=intent,
            citations=citations,
        )

    flagged = sum(r["differs_from_recorded"] for r in records)
    summary = (
        f"{flagged} of {len(records)} document(s) differ by more than "
        f"{int(AREA_TOLERANCE * 100)}%." if flagged
        else "No digitised document differs by more than "
             f"{int(AREA_TOLERANCE * 100)}%."
    )
    return Answer(
        answer=(
            f"Khasra {parcel.khasra_number} is recorded as {recorded}. {summary}\n"
            + "\n".join(lines)
        ),
        records=records,
        intent=intent,
        citations=_dedupe(citations),
    )


def _dedupe(citations: list[Citation]) -> list[Citation]:
    seen: set[tuple[str, str]] = set()
    unique = []
    for c in citations:
        key = (c.source_type, c.source_id)
        if key not in seen:
            seen.add(key)
            unique.append(c)
    return unique
