"""Dashboard and analytics aggregates (§20, §27, §31).

Each role gets the counters its own dashboard renders, computed here rather
than in a route handler (§80). Every figure is derived from persisted workflow
state -- none of these cards is a decorative constant.
"""

from __future__ import annotations

from datetime import UTC, datetime

from mrittika_domain import DocumentState, FieldStatus
from sqlalchemy import case, func, or_, select
from sqlalchemy.orm import Session

from app.models import (
    AnomalyFlag,
    ApprovalAction,
    Document,
    Extraction,
    Location,
    Mutation,
    OwnershipRecord,
    Parcel,
    ProcessingJob,
    VerificationTask,
)
from app.services.auth_service import (
    Principal,
    anomaly_jurisdiction_clause,
    document_jurisdiction_clause,
    jurisdiction_location_ids,
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


#: Documents a verifier has finished with. Every field on them has been seen
#: by a person, so each one is evidence about whether the AI was right.
_HUMAN_REVIEWED = (
    DocumentState.VERIFIED,
    DocumentState.PENDING_APPROVAL,
    DocumentState.APPROVED,
)

#: Fields the verifier could not judge -- the page was unreadable there, or the
#: question went upward. Neither says anything about the AI's accuracy.
_NOT_JUDGED = (FieldStatus.ILLEGIBLE, FieldStatus.ESCALATED)

#: Workflow states grouped into the stages a progress chart shows.
PROGRESS_STAGES: dict[str, tuple[str, ...]] = {
    "approved": (DocumentState.APPROVED,),
    "awaiting_approval": (DocumentState.VERIFIED, DocumentState.PENDING_APPROVAL),
    "in_verification": (
        DocumentState.NEEDS_VERIFICATION, DocumentState.UNDER_VERIFICATION,
    ),
    "in_processing": (
        DocumentState.UPLOADED, DocumentState.QUALITY_CHECK,
        DocumentState.PROCESSING, DocumentState.AI_EXTRACTED,
    ),
    "needs_attention": (DocumentState.REJECTED, DocumentState.RESCAN_REQUIRED),
}

LEVEL_ORDER = ("COUNTRY", "STATE", "DISTRICT", "TEHSIL", "VILLAGE")


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

    accuracy = extraction_accuracy(session, principal)

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
            "extraction_accuracy": accuracy["accuracy"],
        },
        "totals": {
            "documents": total,
            "approved": approved,
            "accuracy_fields_reviewed": accuracy["fields_reviewed"],
        },
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
        "extraction_accuracy": extraction_accuracy(session, principal),
        "progress_by_location": progress_by_location(session, principal),
        "is_synthetic": True,
    }


def extraction_accuracy(session: Session, principal: Principal) -> dict:
    """How often the AI's value survived human review (§11, §31).

    Measured only on documents a verifier has finished with, because only
    there has every field been looked at: a field AUTO_ACCEPTED on a document
    nobody has opened yet is unverified, not correct. On a reviewed document a
    field counts as correct when the verifier kept the AI's value -- approved
    it, left it standing, or "corrected" it to the same value -- and as wrong
    when they changed it.

    This is precision over what the AI extracted. A field the AI missed
    entirely has no row to count; that is reported by the pipeline as MISSING
    and is not folded in here, so the figure means one thing.

    Broken down by model version as well as by field, so the effect of a
    retrained extractor is visible as a change between versions rather than an
    unexplained drift in one number.
    """
    kept = case(
        (
            or_(
                Extraction.corrected_value.is_(None),
                func.btrim(Extraction.corrected_value)
                == func.btrim(func.coalesce(Extraction.normalized_value, "")),
            ),
            1,
        ),
        else_=0,
    )
    judged = (
        document_jurisdiction_clause(session, principal),
        Document.state.in_(_HUMAN_REVIEWED),
        Extraction.status.not_in(_NOT_JUDGED),
    )

    def grouped(column) -> list[dict]:
        rows = session.execute(
            select(column, func.count(Extraction.id), func.sum(kept))
            .join(Document, Document.id == Extraction.document_id)
            .where(*judged)
            .group_by(column)
            .order_by(column)
        ).all()
        return [
            {
                "key": key,
                "reviewed": reviewed,
                "correct": int(correct or 0),
                "accuracy": round(int(correct or 0) / reviewed, 4) if reviewed else None,
            }
            for key, reviewed, correct in rows
        ]

    reviewed, correct, documents = session.execute(
        select(
            func.count(Extraction.id),
            func.sum(kept),
            func.count(func.distinct(Extraction.document_id)),
        )
        .join(Document, Document.id == Extraction.document_id)
        .where(*judged)
    ).one()
    correct = int(correct or 0)

    not_judged = session.execute(
        select(func.count(Extraction.id))
        .join(Document, Document.id == Extraction.document_id)
        .where(
            document_jurisdiction_clause(session, principal),
            Document.state.in_(_HUMAN_REVIEWED),
            Extraction.status.in_(_NOT_JUDGED),
        )
    ).scalar_one()

    return {
        "accuracy": round(correct / reviewed, 4) if reviewed else None,
        "fields_reviewed": reviewed,
        "fields_correct": correct,
        "fields_corrected": reviewed - correct,
        "fields_not_judged": not_judged,
        "documents_reviewed": documents,
        "by_field": [
            {"field": row.pop("key"), **row} for row in grouped(Extraction.field)
        ],
        "by_model_version": [
            {"model_version": row.pop("key"), **row}
            for row in grouped(Extraction.model_version)
        ],
    }


def progress_by_location(session: Session, principal: Principal) -> dict:
    """Digitization progress at every level of the revenue hierarchy (§31).

    One row per location in the caller's jurisdiction -- state, district,
    tehsil, village, as far down as their authority reaches -- each rolled up
    from the villages beneath it. Locations with no documents yet are included
    with zeros: "nothing started here" is exactly what a progress view exists
    to show.

    Two measures, because they answer different questions:

      * `progress` -- of the documents uploaded here, how many are approved.
        Throughput of the digitization pipeline.
      * `parcel_coverage` -- of the parcels here, how many have at least one
        approved record. How much of the land is actually digitized.

    Only the caller's own subtree is reported. A district officer does not get
    a "state" row: it would carry only their district's numbers under the
    state's name, which reads as a statewide figure and is not one.
    """
    allowed = jurisdiction_location_ids(session, principal)
    location_query = select(Location)
    if allowed is not None:
        location_query = location_query.where(Location.id.in_(allowed))
    locations = {loc.id: loc for loc in session.execute(location_query).scalars()}

    blank = {stage: 0 for stage in PROGRESS_STAGES}
    totals: dict[str, dict[str, int]] = {
        loc_id: {**blank, "documents": 0, "parcels": 0, "parcels_digitized": 0}
        for loc_id in locations
    }
    stage_of = {state: stage for stage, states in PROGRESS_STAGES.items()
                for state in states}

    def add(village_id: str | None, key: str, amount: int) -> None:
        """Credit a village and every ancestor of it inside the scope."""
        node = locations.get(village_id)
        while node is not None:
            totals[node.id][key] += amount
            node = locations.get(node.parent_id)

    village = func.coalesce(Document.village_id, Parcel.village_id)
    for village_id, state, count in session.execute(
        select(village, Document.state, func.count(Document.id))
        .select_from(Document)
        .outerjoin(Parcel, Parcel.id == Document.parcel_id)
        .where(document_jurisdiction_clause(session, principal))
        .group_by(village, Document.state)
    ).all():
        add(village_id, "documents", count)
        if state in stage_of:
            add(village_id, stage_of[state], count)

    for village_id, count in session.execute(
        select(Parcel.village_id, func.count(Parcel.id))
        .where(Parcel.village_id.in_(list(locations)))
        .group_by(Parcel.village_id)
    ).all():
        add(village_id, "parcels", count)

    for village_id, count in session.execute(
        select(Parcel.village_id, func.count(func.distinct(Parcel.id)))
        .join(Document, Document.parcel_id == Parcel.id)
        .where(
            Parcel.village_id.in_(list(locations)),
            Document.state == DocumentState.APPROVED,
        )
        .group_by(Parcel.village_id)
    ).all():
        add(village_id, "parcels_digitized", count)

    rank = {level: i for i, level in enumerate(LEVEL_ORDER)}
    rows = []
    for loc in sorted(locations.values(),
                      key=lambda node: (rank.get(node.level, len(rank)), node.name)):
        counts = totals[loc.id]
        parent = locations.get(loc.parent_id)
        rows.append({
            "location_id": loc.external_id,
            "name": loc.name,
            "name_local": loc.name_devanagari,
            "level": loc.level,
            "parent_id": parent.external_id if parent else None,
            **counts,
            "progress": (
                round(counts["approved"] / counts["documents"], 4)
                if counts["documents"] else None
            ),
            "parcel_coverage": (
                round(counts["parcels_digitized"] / counts["parcels"], 4)
                if counts["parcels"] else None
            ),
        })

    present = {row["level"] for row in rows}
    return {
        "levels": [level for level in LEVEL_ORDER if level in present],
        "stages": list(PROGRESS_STAGES),
        "rows": rows,
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


RESEARCH_COLUMNS = (
    "state", "district", "tehsil", "village", "area_sqm", "land_class",
    "current_holders", "mutations", "last_mutation_year", "digitized",
)


def research_rows(session: Session, principal: Principal) -> list[dict]:
    """One anonymised row per parcel in the caller's jurisdiction (§15).

    For research institutions: land-holding structure and digitization, with
    nothing that names a person or a plot. Dropped: owner and guardian names,
    parcel id, khasra and khata numbers, geometry. Area is rounded to 100 m^2
    so it cannot be matched back to a recorded figure, and rows are ordered by
    village then area, not by khasra, so position does not identify a plot.
    """
    from mrittika_domain.area import UnknownAreaUnit, to_square_metres

    allowed = jurisdiction_location_ids(session, principal)
    places = {loc.id: loc for loc in session.execute(select(Location)).scalars()}

    def ancestor(loc: Location | None, level: str) -> str | None:
        while loc is not None and loc.level != level:
            loc = places.get(loc.parent_id)
        return loc.name if loc else None

    holders = dict(session.execute(
        select(OwnershipRecord.parcel_id, func.count())
        .where(OwnershipRecord.valid_to.is_(None))
        .group_by(OwnershipRecord.parcel_id)
    ).all())
    mutations = {
        pid: (count, year) for pid, count, year in session.execute(
            select(Mutation.parcel_id, func.count(),
                   func.max(func.extract("year", Mutation.effective_date)))
            .group_by(Mutation.parcel_id)
        ).all()
    }
    digitized = set(session.execute(
        select(Document.parcel_id).where(Document.state == DocumentState.APPROVED)
    ).scalars())

    query = select(Parcel)
    if allowed is not None:
        query = query.where(Parcel.village_id.in_(allowed))
    rows = []
    for parcel in session.execute(query).scalars():
        village = places.get(parcel.village_id)
        try:
            area = round(to_square_metres(parcel.area_value, parcel.area_unit), -2)
        except UnknownAreaUnit:
            area = None
        count, year = mutations.get(parcel.id, (0, None))
        rows.append({
            "state": ancestor(village, "STATE"),
            "district": ancestor(village, "DISTRICT"),
            "tehsil": ancestor(village, "TEHSIL"),
            "village": village.name if village else None,
            "area_sqm": int(area) if area is not None else None,
            "land_class": parcel.land_class,
            "current_holders": holders.get(parcel.id, 0),
            "mutations": count,
            "last_mutation_year": int(year) if year else None,
            "digitized": parcel.id in digitized,
        })
    rows.sort(key=lambda r: (r["state"] or "", r["district"] or "", r["village"] or "",
                             r["area_sqm"] or 0))
    return rows
