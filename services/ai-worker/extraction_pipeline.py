"""The AI extraction pipeline, end to end (§23).

NAME: deliberately `extraction_pipeline`, not `pipeline`. Both this package and
services/dataset-generator are placed on sys.path, and each previously exposed
a top-level module called `pipeline`. Whichever directory was inserted first
won, so the API silently imported the DOCUMENT GENERATOR instead of the AI
pipeline -- which surfaced only when test ordering changed. Top-level module
names shared across packages are ambiguous; keep these distinct (§79).


    quality -> preprocess -> OCR -> layout/extraction -> normalize
            -> confidence -> validation

Pure with respect to the database: it takes image bytes and returns a result
object. Persistence and state transitions are the API service's job (§80), so
this can be evaluated offline without a database.

If OCR fails entirely the pipeline raises. It never invents blocks (§82); the
caller marks the document NEEDS_REVIEW and records the failure.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import cv2
import numpy as np
from extraction.field_extractor import ExtractedValue, extract
from normalization.normalizers import normalize_field
from ocr.provider import OcrEngine, OcrResult
from preprocessing.enhance import enhance_for_quality
from quality.assessment import QualityReport, assess
from validation.rules import Finding, run_all, validation_confidence

STAGES = [
    "quality", "preprocessing", "ocr", "layout", "extraction",
    "normalization", "validation", "confidence", "complete",
]


@dataclass
class FieldOutcome:
    """One extracted field, fully resolved (§26)."""

    field: str
    raw_value: str
    normalized_value: str | None
    bbox: tuple[int, int, int, int]
    ocr_confidence: float
    extraction_confidence: float
    layout_confidence: float
    validation_confidence: float
    final_confidence: float
    confidence_breakdown: dict
    row_index: int | None
    strategy: str
    status: str


@dataclass
class PipelineResult:
    quality: QualityReport
    ocr: OcrResult
    fields: list[FieldOutcome] = field(default_factory=list)
    findings: list[Finding] = field(default_factory=list)
    missing_fields: list[str] = field(default_factory=list)
    preprocessing_applied: list[str] = field(default_factory=list)
    #: Scaling applied by preprocessing, so bboxes can be mapped back to the
    #: ORIGINAL page. Without this the Verifier highlights the wrong region.
    scale_x: float = 1.0
    scale_y: float = 1.0

    def lowest_confidence(self) -> float:
        return min((f.final_confidence for f in self.fields), default=0.0)

    def needs_review_count(self) -> int:
        return sum(1 for f in self.fields if f.status == "NEEDS_REVIEW")


def _status_for(confidence: float) -> str:
    """§8 banding decides whether a human must look at the field."""
    return "AUTO_ACCEPTED" if confidence >= 0.85 else "NEEDS_REVIEW"


def run(
    image_bytes: bytes,
    engine: OcrEngine,
    *,
    declared_khasra: str | None = None,
    previous_area: float | None = None,
    progress=None,
) -> PipelineResult:
    """Run every stage over one page."""

    def report(stage: str, percent: int, message: str) -> None:
        if progress:
            progress(stage, percent, message)

    array = np.frombuffer(image_bytes, dtype=np.uint8)
    image = cv2.imdecode(array, cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError("could not decode the uploaded image")

    report("quality", 5, "Assessing scan quality")
    quality = assess(image)

    report("preprocessing", 18, "Enhancing the page")
    enhancement = enhance_for_quality(image, quality)
    prepared = enhancement.image

    # Preprocessing may upscale; record the factor so boxes can be mapped back
    # onto the original image the verifier is shown.
    scale_x = prepared.shape[1] / image.shape[1]
    scale_y = prepared.shape[0] / image.shape[0]

    report("ocr", 35, "Recognising Devanagari text")
    ocr = engine.recognize(prepared)

    report("layout", 55, "Parsing document structure")
    report("extraction", 65, "Extracting record fields")
    extraction = extract(ocr.blocks, prepared.shape[1])

    report("normalization", 78, "Normalising values")
    normalized: dict[str, str | None] = {}
    shares: list[str] = []
    for value in extraction.values:
        clean = normalize_field(value.field, value.raw_value)
        if value.field == "SHARE" and clean:
            shares.append(clean)
        elif value.field not in normalized:
            normalized[value.field] = clean

    report("validation", 86, "Applying validation rules")
    findings = run_all(
        normalized,
        shares=shares,
        declared_khasra=declared_khasra,
        previous_area=previous_area,
    )

    report("confidence", 93, "Scoring confidence")
    outcomes: list[FieldOutcome] = []
    for value in extraction.values:
        clean = normalize_field(value.field, value.raw_value)
        signals = _signals_for(value, ocr, findings)
        fused = _fuse(signals)
        # Map the bbox back to ORIGINAL page coordinates.
        x1, y1, x2, y2 = value.bbox
        original_bbox = (
            int(x1 / scale_x), int(y1 / scale_y),
            int(x2 / scale_x), int(y2 / scale_y),
        )
        outcomes.append(
            FieldOutcome(
                field=value.field,
                raw_value=value.raw_value,
                normalized_value=clean,
                bbox=original_bbox,
                ocr_confidence=value.ocr_confidence,
                extraction_confidence=value.extraction_confidence,
                layout_confidence=signals["layout"],
                validation_confidence=signals["validation"],
                final_confidence=fused["score"],
                confidence_breakdown=fused["contributions"],
                row_index=value.row_index,
                strategy=value.strategy,
                status=_status_for(fused["score"]),
            )
        )

    report("complete", 100, "Processing complete")
    return PipelineResult(
        quality=quality,
        ocr=ocr,
        fields=outcomes,
        findings=findings,
        missing_fields=extraction.missing,
        preprocessing_applied=enhancement.applied,
        scale_x=scale_x,
        scale_y=scale_y,
    )


def _signals_for(value: ExtractedValue, ocr: OcrResult, findings: list[Finding]) -> dict:
    """Assemble the evidence for one field's confidence (§8)."""
    # A fallback provider's geometry is approximate, so its layout evidence is
    # weaker even when the text is right.
    layout = 0.55 if ocr.degraded else {
        "label-right": 0.90,
        "table-column": 0.85,
        "label-below": 0.78,
        "inline": 0.62,
        "adjacent-to-area": 0.80,
    }.get(value.strategy, 0.70)

    return {
        "ocr": value.ocr_confidence,
        "extraction": value.extraction_confidence,
        "layout": layout,
        "validation": validation_confidence(findings, value.field),
        "language": 0.85 if ocr.provider == "paddle" else 0.60,
    }


def _fuse(signals: dict) -> dict:
    """Weighted fusion via the shared domain implementation (§8).

    Imported lazily so the worker package does not hard-depend on the API's
    path bootstrap when used standalone.
    """
    from mrittika_domain import ConfidenceSignals, fuse

    result = fuse(
        ConfidenceSignals(
            ocr=signals["ocr"],
            extraction=signals["extraction"],
            layout=signals["layout"],
            validation=signals["validation"],
            language=signals["language"],
        )
    )
    return {
        "score": result.score,
        "band": result.band.value,
        "version": result.version,
        "contributions": {k: round(v, 4) for k, v in result.contributions.items()},
    }
