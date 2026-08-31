"""Persist anomaly analysis against the database (§34).

The engine in services/ai-worker/anomaly is pure -- it takes a `RecordFeatures`
and knows nothing about SQLAlchemy. This module is the bridge: it assembles
those features from a parcel's real history, runs the engine, and reconciles the
resulting signals with the `anomaly_flags` table.

Reconciliation, not insertion: re-running analysis on a parcel replaces its
open flags rather than appending duplicates, and a flag an officer has already
dismissed stays dismissed.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from fractions import Fraction

from anomaly import analyse, evaluable_types
from anomaly.detector import IsolationForestDetector
from anomaly.features import OwnershipSpan, RecordFeatures
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config.settings import get_settings
from app.models import (
    AnomalyFlag,
    Document,
    Extraction,
    FieldCorrection,
    LandRecord,
    Location,
    Mutation,
    OwnershipRecord,
    Parcel,
)

logger = logging.getLogger(__name__)


def _share_as_float(share: str | None) -> float:
    """'1/2' -> 0.5. Stored as a fraction because rounding changes meaning (§39)."""
    if not share:
        return 0.0
    try:
        return float(Fraction(share.strip()))
    except (ValueError, ZeroDivisionError):
        return 0.0


def _record_year(parcel_id: str, session: Session) -> int | None:
    """Earliest record year on file for this parcel."""
    years = session.execute(
        select(LandRecord.record_year).where(LandRecord.parcel_id == parcel_id)
    ).scalars().all()
    parsed = []
    for value in years:
        # Record years are written '1998-99'; the first half is the year.
        head = str(value).split("-")[0].strip()
        if head.isdigit():
            parsed.append(int(head))
    return min(parsed) if parsed else None


def build_features(
    session: Session,
    parcel: Parcel,
    *,
    document: Document | None = None,
) -> RecordFeatures:
    """Assemble one parcel's history into the engine's input shape."""
    spans = session.execute(
        select(OwnershipRecord)
        .where(OwnershipRecord.parcel_id == parcel.id)
        .order_by(OwnershipRecord.valid_from)
    ).scalars().all()

    mutation_dates = session.execute(
        select(Mutation.effective_date)
        .where(Mutation.parcel_id == parcel.id)
        .order_by(Mutation.effective_date)
    ).scalars().all()

    # Another parcel in the same village carrying the same khasra number.
    duplicates = session.execute(
        select(Parcel.external_id).where(
            Parcel.village_id == parcel.village_id,
            Parcel.khasra_number == parcel.khasra_number,
            Parcel.id != parcel.id,
        )
    ).scalars().all()

    confidences: list[float] = []
    corrections = 0
    document_village_id: str | None = None

    # Without a document there is nothing to compare the parcel against, so the
    # area of record is both the current and the only known value.
    area_value: float | None = parcel.area_value
    previous_area: float | None = None

    if document is not None:
        confidences = list(session.execute(
            select(Extraction.final_confidence).where(
                Extraction.document_id == document.id,
                Extraction.final_confidence.is_not(None),
            )
        ).scalars().all())
        corrections = session.execute(
            select(func.count(FieldCorrection.id)).where(
                FieldCorrection.document_id == document.id
            )
        ).scalar_one()

        if document.village_id:
            village_row = session.get(Location, document.village_id)
            document_village_id = village_row.external_id if village_row else None

        # AREA_JUMP compares what this document says against the area of
        # record. An unparseable value leaves both sides equal, so no jump.
        extracted_area = session.execute(
            select(Extraction.normalized_value).where(
                Extraction.document_id == document.id, Extraction.field == "AREA"
            )
        ).scalars().first()
        if extracted_area:
            try:
                area_value = float(extracted_area)
                previous_area = parcel.area_value
            except ValueError:
                pass

    return RecordFeatures(
        parcel_id=parcel.external_id,
        has_document=document is not None,
        khasra_number=parcel.khasra_number,
        village_id=parcel.village.external_id if parcel.village else None,
        document_village_id=document_village_id,
        area_value=area_value,
        previous_area_value=previous_area,
        record_year=_record_year(parcel.id, session),
        current_year=datetime.now(UTC).year,
        ownership_spans=[
            OwnershipSpan(
                owner_id=span.owner_id,
                share=_share_as_float(span.share),
                valid_from=span.valid_from,
                valid_to=span.valid_to,
                mutation_id=span.mutation_id,
            )
            for span in spans
        ],
        mutation_dates=list(mutation_dates),
        duplicate_parcel_ids=list(duplicates),
        correction_count=corrections,
        confidences=confidences,
    )


def corpus_features(session: Session, limit: int = 2000) -> list[RecordFeatures]:
    """Features for every parcel, for fitting the Isolation Forest.

    Fitting needs the whole corpus, not one record -- an outlier is only
    definable relative to what else exists.
    """
    parcels = session.execute(select(Parcel).limit(limit)).scalars().all()
    return [build_features(session, parcel) for parcel in parcels]


def fitted_detector(session: Session) -> IsolationForestDetector:
    """A detector fitted on the current corpus.

    Returns an unfitted detector when the corpus is too small or scikit-learn
    is absent; callers must treat `available` as authoritative rather than
    assuming a score exists (§82).
    """
    settings = get_settings()
    detector = IsolationForestDetector(
        model_version=getattr(settings, "model_version_anomaly", "anomaly-v1")
    )
    detector.fit(corpus_features(session))
    if not detector.available:
        logger.info("anomaly detector unavailable: %s", detector.unavailable_reason)
    return detector


def analyse_parcel(
    session: Session,
    parcel: Parcel,
    *,
    document: Document | None = None,
    detector: IsolationForestDetector | None = None,
) -> list[AnomalyFlag]:
    """Run the engine over one parcel and reconcile its flags.

    An OPEN flag is closed as RESOLVED -- not deleted, so the record of what
    was once flagged survives -- but only when this pass could actually have
    re-raised it. A parcel-only pass cannot evaluate the document-dependent
    rules, and closing those on its silence would erase findings nobody
    re-examined. DISMISSED flags are never revived.
    """
    features = build_features(session, parcel, document=document)
    signals = analyse(features, detector)

    existing = session.execute(
        select(AnomalyFlag).where(AnomalyFlag.parcel_id == parcel.id)
    ).scalars().all()
    by_type = {flag.anomaly_type: flag for flag in existing}

    written: list[AnomalyFlag] = []
    for signal in signals:
        flag = by_type.get(signal.anomaly_type)
        if flag is not None and flag.status == "DISMISSED":
            continue    # an officer already ruled on this; do not re-raise it
        if flag is None:
            flag = AnomalyFlag(parcel_id=parcel.id, anomaly_type=signal.anomaly_type)
            session.add(flag)
        flag.document_id = document.id if document else flag.document_id
        flag.score = signal.score
        flag.explanation = signal.explanation
        flag.evidence = signal.evidence
        flag.model_version = signal.source
        flag.status = "OPEN"
        written.append(flag)

    reported = {signal.anomaly_type for signal in signals}
    closeable = evaluable_types(features)
    for flag in existing:
        if (
            flag.status == "OPEN"
            and flag.anomaly_type not in reported
            and flag.anomaly_type in closeable
        ):
            flag.status = "RESOLVED"

    session.flush()
    return written


def flags_for_parcel(session: Session, parcel: Parcel) -> list[dict]:
    flags = session.execute(
        select(AnomalyFlag)
        .where(AnomalyFlag.parcel_id == parcel.id)
        .order_by(AnomalyFlag.score.desc())
    ).scalars().all()
    return [
        {
            "anomaly_type": flag.anomaly_type,
            "score": flag.score,
            "explanation": flag.explanation,
            "evidence": flag.evidence,
            "status": flag.status,
            "model_version": flag.model_version,
        }
        for flag in flags
    ]


def analyse_all(session: Session) -> dict:
    """Batch pass over the whole cadastre. Used by scripts and the demo seed."""
    detector = fitted_detector(session)
    parcels = session.execute(select(Parcel)).scalars().all()

    total = 0
    for parcel in parcels:
        total += len(analyse_parcel(session, parcel, detector=detector))
    session.commit()

    return {
        "parcels_analysed": len(parcels),
        "flags_open": total,
        "detector": detector.model_version if detector.available else None,
        "detector_status": detector.unavailable_reason or "fitted",
    }


__all__ = [
    "analyse_all", "analyse_parcel", "build_features", "corpus_features",
    "fitted_detector", "flags_for_parcel",
]
