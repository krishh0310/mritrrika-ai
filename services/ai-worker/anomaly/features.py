"""Feature extraction for the anomaly detector (§7).

The Isolation Forest sees only this vector, so what goes in here decides what
"unusual" can mean. Every feature is a property of the record and its history,
never of the document image -- image quality is already handled by the §22
quality gate and would otherwise dominate the outlier score.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

#: Order matters: it is the column order of the matrix the model is fit on, and
#: a model trained on one order cannot be scored with another.
FEATURE_NAMES = (
    "area_value",
    "area_change_ratio",
    "mutation_count",
    "mutations_per_year",
    "owner_count",
    "ownership_change_count",
    "correction_count",
    "mean_confidence",
    "lowest_confidence",
    "record_age_years",
)


@dataclass
class OwnershipSpan:
    """One row of a parcel's ownership history, as the detector sees it."""

    owner_id: str
    share: float
    valid_from: date | None
    valid_to: date | None
    mutation_id: str | None = None


@dataclass
class RecordFeatures:
    """Everything the anomaly engine knows about one parcel's record.

    Assembled by the caller from the database (the worker has no session), so
    this module stays pure and directly testable.
    """

    parcel_id: str
    #: Whether this analysis has a document to compare against. Rules that
    #: contrast a scan with the record cannot reach a verdict without one, and
    #: their silence must not be read as "no anomaly".
    has_document: bool = False
    khasra_number: str | None = None
    village_id: str | None = None
    document_village_id: str | None = None
    area_value: float | None = None
    previous_area_value: float | None = None
    record_year: int | None = None
    current_year: int | None = None

    ownership_spans: list[OwnershipSpan] = field(default_factory=list)
    mutation_dates: list[date] = field(default_factory=list)
    #: Parcel ids elsewhere in the corpus carrying the same khasra + village.
    duplicate_parcel_ids: list[str] = field(default_factory=list)

    correction_count: int = 0
    confidences: list[float] = field(default_factory=list)

    @property
    def area_change_ratio(self) -> float:
        """How many times larger or smaller the area became. 1.0 means stable."""
        if not self.area_value or not self.previous_area_value:
            return 1.0
        if self.area_value <= 0 or self.previous_area_value <= 0:
            return 1.0
        return max(self.area_value, self.previous_area_value) / min(
            self.area_value, self.previous_area_value
        )

    @property
    def mutation_count(self) -> int:
        return len(self.mutation_dates)

    @property
    def record_age_years(self) -> float:
        if self.record_year is None or self.current_year is None:
            return 0.0
        return float(max(self.current_year - self.record_year, 0))

    @property
    def mutations_per_year(self) -> float:
        """Mutation frequency -- the §7 "mutation frequency" feature.

        Normalised by the record's age so a 60-year-old parcel with six
        mutations does not look like a 2-year-old parcel with six.
        """
        years = self.record_age_years
        return self.mutation_count / years if years >= 1 else float(self.mutation_count)

    @property
    def owner_count(self) -> int:
        return len({span.owner_id for span in self.ownership_spans})

    @property
    def ownership_change_count(self) -> int:
        """Number of times the recorded holder set changed.

        Counted as distinct start dates minus the original grant, NOT as the
        number of spans: a parcel held jointly by two co-owners has two spans
        created by one event. Counting spans made every jointly-held parcel
        look like it had an unexplained transfer.
        """
        starts = {span.valid_from for span in self.ownership_spans if span.valid_from}
        return max(len(starts) - 1, 0)

    @property
    def mean_confidence(self) -> float:
        return sum(self.confidences) / len(self.confidences) if self.confidences else 1.0

    @property
    def lowest_confidence(self) -> float:
        return min(self.confidences) if self.confidences else 1.0

    @property
    def current_share_total(self) -> float:
        """Sum of shares held right now. Should be 1.0 on a consistent record."""
        return round(
            sum(span.share for span in self.ownership_spans if span.valid_to is None), 4
        )


def feature_vector(features: RecordFeatures) -> list[float]:
    """Project a record into FEATURE_NAMES order."""
    return [
        float(features.area_value or 0.0),
        float(features.area_change_ratio),
        float(features.mutation_count),
        float(features.mutations_per_year),
        float(features.owner_count),
        float(features.ownership_change_count),
        float(features.correction_count),
        float(features.mean_confidence),
        float(features.lowest_confidence),
        float(features.record_age_years),
    ]


__all__ = ["FEATURE_NAMES", "OwnershipSpan", "RecordFeatures", "feature_vector"]
