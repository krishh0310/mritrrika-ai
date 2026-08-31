"""Confidence fusion and banding (§8).

The spec is explicit that final confidence must NOT be a blind average of every
available score. Different signals carry different evidential weight, and a
missing signal must not silently drag a field down (or prop it up).

So fusion is a configurable weighted mean over the signals that are actually
present, with the weights versioned as `confidence-v1` and recorded on every
stored value (§64) -- a later reweighting must never make old rows ambiguous.
"""

from dataclasses import dataclass, field

from .enums import ConfidenceBand

#: Band thresholds (§8). HIGH >= 0.85, MEDIUM 0.60-0.849, LOW < 0.60.
HIGH_THRESHOLD = 0.85
MEDIUM_THRESHOLD = 0.60


def band_for(score: float) -> ConfidenceBand:
    """Map a fused score onto its UI band."""
    if score >= HIGH_THRESHOLD:
        return ConfidenceBand.HIGH
    if score >= MEDIUM_THRESHOLD:
        return ConfidenceBand.MEDIUM
    return ConfidenceBand.LOW


@dataclass(frozen=True)
class ConfidenceWeights:
    """Relative weight of each evidence source.

    Rationale for the v1 values:
      ocr          -- highest weight; if the characters were misread nothing
                      downstream can recover the true value.
      extraction   -- next; correct characters can still be assigned to the
                      wrong field.
      layout       -- moderate; supports the extractor's field assignment.
      validation   -- moderate; a deterministic rule agreeing (or not) is
                      strong evidence but is coarse-grained.
      language     -- lowest; script/language plausibility is a weak signal on
                      its own and mostly catches gross failures.
    """

    version: str = "confidence-v1"
    ocr: float = 0.40
    extraction: float = 0.25
    layout: float = 0.15
    validation: float = 0.15
    language: float = 0.05


DEFAULT_WEIGHTS = ConfidenceWeights()


@dataclass
class ConfidenceSignals:
    """Evidence available for one field. Any signal may be absent."""

    ocr: float | None = None
    extraction: float | None = None
    layout: float | None = None
    validation: float | None = None
    language: float | None = None

    def as_pairs(self) -> list[tuple[str, float]]:
        return [
            (name, value)
            for name, value in (
                ("ocr", self.ocr),
                ("extraction", self.extraction),
                ("layout", self.layout),
                ("validation", self.validation),
                ("language", self.language),
            )
            if value is not None
        ]


@dataclass
class FusedConfidence:
    """Result of fusion -- the score plus the evidence that produced it.

    The breakdown is retained because §68 requires traceability: an officer
    asking "why is this field amber?" must get the component scores, not a
    bare number.
    """

    score: float
    band: ConfidenceBand
    version: str
    contributions: dict[str, float] = field(default_factory=dict)


def fuse(
    signals: ConfidenceSignals,
    weights: ConfidenceWeights = DEFAULT_WEIGHTS,
) -> FusedConfidence:
    """Combine available signals into one score.

    Weights are renormalised over the signals that are present, so a field with
    no layout evidence is not penalised for the absence -- it is simply scored
    on what is known. A field with no signals at all scores 0.0 and bands LOW,
    which correctly routes it to human review rather than silently passing.
    """
    present = signals.as_pairs()
    if not present:
        return FusedConfidence(0.0, ConfidenceBand.LOW, weights.version, {})

    weight_of = {
        "ocr": weights.ocr,
        "extraction": weights.extraction,
        "layout": weights.layout,
        "validation": weights.validation,
        "language": weights.language,
    }

    total_weight = sum(weight_of[name] for name, _ in present)
    if total_weight <= 0:
        return FusedConfidence(0.0, ConfidenceBand.LOW, weights.version, {})

    contributions = {
        name: (weight_of[name] / total_weight) * value for name, value in present
    }
    score = sum(contributions.values())
    # Guard against float drift pushing a perfect score just past 1.0.
    score = min(1.0, max(0.0, score))

    return FusedConfidence(
        score=score,
        band=band_for(score),
        version=weights.version,
        contributions=contributions,
    )
