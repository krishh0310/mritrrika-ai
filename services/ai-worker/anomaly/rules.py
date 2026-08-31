"""Deterministic anomaly rules (§34).

These are not the §33 validation rules. Validation asks "is this field
well-formed?" and looks at one document; these ask "is this record's history
coherent?" and look across mutations, ownership spans and the wider corpus.

Every rule returns evidence -- the specific values that made it fire -- because
an officer must be able to check the claim rather than take it on trust (§68).
Wording is always "potential inconsistency", never an accusation (§34).
"""

from __future__ import annotations

from collections.abc import Callable

from .features import RecordFeatures
from .signal import AnomalySignal

#: Area growing or shrinking by this factor between consecutive records is
#: worth a human look. Chosen to match the §33 validation threshold so the two
#: engines do not disagree about what counts as a large change.
AREA_JUMP_RATIO = 3.0

#: More mutations per year than this on one parcel is unusual for agricultural
#: land, where transfers are typically years apart.
HIGH_MUTATION_RATE = 1.0

#: A share total this far from 1.0 means the recorded holdings do not add up.
SHARE_TOLERANCE = 0.01


def area_jump(features: RecordFeatures) -> AnomalySignal | None:
    """AREA_JUMP -- the parcel's area changed by more than the threshold."""
    ratio = features.area_change_ratio
    if ratio < AREA_JUMP_RATIO:
        return None
    return AnomalySignal(
        anomaly_type="AREA_JUMP",
        score=min(ratio / (AREA_JUMP_RATIO * 4), 1.0),
        explanation=(
            f"Recorded area changed from {features.previous_area_value} to "
            f"{features.area_value} ({ratio:.1f}x). Potential inconsistency; "
            "manual investigation recommended."
        ),
        evidence={
            "previous_area": features.previous_area_value,
            "current_area": features.area_value,
            "ratio": round(ratio, 2),
            "threshold": AREA_JUMP_RATIO,
        },
    )


def invalid_chronology(features: RecordFeatures) -> AnomalySignal | None:
    """INVALID_CHRONOLOGY -- mutations or ownership spans run backwards."""
    out_of_order = [
        (str(earlier), str(later))
        for earlier, later in zip(
            features.mutation_dates, features.mutation_dates[1:], strict=False
        )
        if later < earlier
    ]

    inverted_spans = [
        {"owner_id": span.owner_id, "from": str(span.valid_from), "to": str(span.valid_to)}
        for span in features.ownership_spans
        if span.valid_from and span.valid_to and span.valid_to < span.valid_from
    ]

    if not out_of_order and not inverted_spans:
        return None

    return AnomalySignal(
        anomaly_type="INVALID_CHRONOLOGY",
        score=1.0,   # a date ordering violation is a fact, not a likelihood
        explanation=(
            "Dates on this record do not run forward in time. Potential "
            "inconsistency; manual investigation recommended."
        ),
        evidence={
            "out_of_order_mutations": out_of_order,
            "inverted_ownership_spans": inverted_spans,
        },
    )


def duplicate_parcel(features: RecordFeatures) -> AnomalySignal | None:
    """DUPLICATE_PARCEL -- the same khasra appears on another parcel."""
    others = [pid for pid in features.duplicate_parcel_ids if pid != features.parcel_id]
    if not others:
        return None
    return AnomalySignal(
        anomaly_type="DUPLICATE_PARCEL",
        score=1.0,
        explanation=(
            f"Khasra {features.khasra_number} is recorded against "
            f"{len(others) + 1} parcels in this village. Potential "
            "inconsistency; manual investigation recommended."
        ),
        evidence={
            "khasra_number": features.khasra_number,
            "village_id": features.village_id,
            "other_parcels": others,
        },
    )


def missing_mutation(features: RecordFeatures) -> AnomalySignal | None:
    """MISSING_MUTATION -- ownership changed with no mutation to account for it."""
    changes = features.ownership_change_count
    if changes == 0 or changes <= features.mutation_count:
        return None
    unexplained = changes - features.mutation_count
    return AnomalySignal(
        anomaly_type="MISSING_MUTATION",
        score=min(unexplained / 3, 1.0),
        explanation=(
            f"{changes} ownership changes are recorded but only "
            f"{features.mutation_count} mutations explain them. Potential "
            "inconsistency; manual investigation recommended."
        ),
        evidence={
            "ownership_changes": changes,
            "mutations": features.mutation_count,
            "unexplained": unexplained,
        },
    )


def location_mismatch(features: RecordFeatures) -> AnomalySignal | None:
    """LOCATION_MISMATCH -- the document's village is not the parcel's village."""
    if not features.document_village_id or not features.village_id:
        return None
    if features.document_village_id == features.village_id:
        return None
    return AnomalySignal(
        anomaly_type="LOCATION_MISMATCH",
        score=0.8,
        explanation=(
            "The village recorded on this document does not match the village "
            "the parcel belongs to. Potential inconsistency; manual "
            "investigation recommended."
        ),
        evidence={
            "document_village_id": features.document_village_id,
            "parcel_village_id": features.village_id,
        },
    )


def repeated_modification(features: RecordFeatures) -> AnomalySignal | None:
    """REPEATED_MODIFICATION -- an unusually high mutation rate."""
    rate = features.mutations_per_year
    if rate <= HIGH_MUTATION_RATE or features.mutation_count < 3:
        return None
    return AnomalySignal(
        anomaly_type="REPEATED_MODIFICATION",
        score=min(rate / (HIGH_MUTATION_RATE * 3), 1.0),
        explanation=(
            f"{features.mutation_count} mutations over "
            f"{features.record_age_years:.0f} years ({rate:.2f}/year) is an "
            "unusual pattern for this corpus. Manual investigation recommended."
        ),
        evidence={
            "mutations": features.mutation_count,
            "years": features.record_age_years,
            "rate_per_year": round(rate, 3),
            "threshold": HIGH_MUTATION_RATE,
        },
    )


def unusual_ownership_change(features: RecordFeatures) -> AnomalySignal | None:
    """UNUSUAL_OWNERSHIP_CHANGE -- current shares do not sum to a whole parcel."""
    if not features.ownership_spans:
        return None
    total = features.current_share_total
    if total == 0 or abs(total - 1.0) <= SHARE_TOLERANCE:
        return None
    return AnomalySignal(
        anomaly_type="UNUSUAL_OWNERSHIP_CHANGE",
        score=min(abs(total - 1.0), 1.0),
        explanation=(
            f"Current ownership shares total {total} rather than 1. Potential "
            "inconsistency; manual investigation recommended."
        ),
        evidence={"share_total": total, "tolerance": SHARE_TOLERANCE},
    )


#: Evaluated in order; the order is also the order flags are surfaced in.
ANOMALY_RULES: tuple[Callable[[RecordFeatures], AnomalySignal | None], ...] = (
    invalid_chronology,
    duplicate_parcel,
    area_jump,
    missing_mutation,
    location_mismatch,
    repeated_modification,
    unusual_ownership_change,
)

ALL_ANOMALY_TYPES = frozenset({
    "AREA_JUMP", "INVALID_CHRONOLOGY", "DUPLICATE_PARCEL", "MISSING_MUTATION",
    "LOCATION_MISMATCH", "REPEATED_MODIFICATION", "UNUSUAL_OWNERSHIP_CHANGE",
})

#: Rules that can only reach a verdict with a document in hand -- they compare
#: what a scan says against the record. A pass over the cadastre alone cannot
#: evaluate them, and silence from such a pass does not mean "no longer true".
DOCUMENT_DEPENDENT = frozenset({"LOCATION_MISMATCH", "AREA_JUMP"})


def evaluable_types(features: RecordFeatures) -> frozenset[str]:
    """The anomaly types this input could actually reach a verdict on.

    A caller reconciling stored flags must close only these; closing a
    document-dependent flag on the strength of a parcel-only pass would erase
    a finding nobody re-examined.
    """
    if features.has_document:
        return ALL_ANOMALY_TYPES
    return ALL_ANOMALY_TYPES - DOCUMENT_DEPENDENT


def run_all(features: RecordFeatures) -> list[AnomalySignal]:
    return [signal for rule in ANOMALY_RULES if (signal := rule(features)) is not None]


__all__ = [
    "ALL_ANOMALY_TYPES", "ANOMALY_RULES", "AREA_JUMP_RATIO", "DOCUMENT_DEPENDENT",
    "HIGH_MUTATION_RATE", "SHARE_TOLERANCE", "evaluable_types",
    "area_jump", "duplicate_parcel", "invalid_chronology", "location_mismatch",
    "missing_mutation", "repeated_modification", "run_all",
    "unusual_ownership_change",
]
