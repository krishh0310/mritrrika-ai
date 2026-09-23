"""Canonical extracted record (§25) and field-level provenance (§26).

Two rules drive the shape of everything here:

1.  Normalization NEVER destroys the raw OCR value (§26). Both are carried, on
    every field, forever. The Verifier UI shows them side by side and the audit
    trail depends on being able to show what the model actually read.

2.  Every value is anchored to where it came from -- page, bounding box, and
    the model version that produced it (§64, §68). A value with no anchor
    cannot be reviewed, so it cannot be trusted.
"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .enums import AreaUnit, DocumentType, FieldName, FieldStatus


class BoundingBox(BaseModel):
    """Axis-aligned box in page pixel coordinates, origin top-left.

    Stored per field so the Verifier can zoom the source document to the exact
    region backing a value (§28), and so degradation transforms can be applied
    to annotations alongside the image (§48).
    """

    model_config = ConfigDict(frozen=True)

    x1: float
    y1: float
    x2: float
    y2: float

    @field_validator("x2")
    @classmethod
    def _x_ordered(cls, v: float, info):
        if "x1" in info.data and v < info.data["x1"]:
            raise ValueError("x2 must be >= x1")
        return v

    @field_validator("y2")
    @classmethod
    def _y_ordered(cls, v: float, info):
        if "y1" in info.data and v < info.data["y1"]:
            raise ValueError("y2 must be >= y1")
        return v

    @property
    def width(self) -> float:
        return self.x2 - self.x1

    @property
    def height(self) -> float:
        return self.y2 - self.y1


class ExtractedField(BaseModel):
    """One extracted value with its full provenance (§26).

    `raw_value` is what OCR read, verbatim, including Devanagari digits and any
    spacing oddities. `normalized_value` is the cleaned form. Keeping both is
    what makes '१४२ / २' -> '142/2' an auditable transformation rather than a
    silent rewrite.
    """

    field: FieldName
    raw_value: str | None = None
    normalized_value: str | None = None

    ocr_confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    extraction_confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    final_confidence: float = Field(ge=0.0, le=1.0)

    bbox: BoundingBox | None = None
    source_page: int = Field(default=1, ge=1)
    status: FieldStatus = FieldStatus.NEEDS_REVIEW

    #: Which model produced this value (§64). Never null in persisted rows.
    model_version: str | None = None

    #: Populated when a deterministic rule fired against this field (§33).
    validation_message: str | None = None


class OwnerShare(BaseModel):
    """An owner's stake in a parcel.

    `share` is kept as the fraction written on the document ('1/2'), not a
    float, because rounding a recorded share would corrupt the legal meaning.
    """

    owner_id: str | None = None
    name: str
    share: str = "1/1"
    guardian_name: str | None = None


class Area(BaseModel):
    """Recorded area, in the unit written on the document.

    No conversion happens here. Converting to a canonical unit is an explicit,
    separate step so the recorded figure is always recoverable.
    """

    value: float = Field(gt=0)
    unit: AreaUnit
    #: The unit exactly as written, e.g. 'बीघा'. Retained for display and audit.
    unit_raw: str | None = None


class CanonicalLandRecord(BaseModel):
    """Normalized output of the AI pipeline for one document (§25).

    This is the stable contract between the AI worker and everything
    downstream: verification, approval, GIS linking, citizen views and RAG all
    read this shape.
    """

    model_config = ConfigDict(extra="forbid")

    document_id: str
    parcel_id: str | None = None
    document_type: DocumentType

    state: str
    district: str
    tehsil: str
    village: str

    khasra_number: str | None = None
    khata_number: str | None = None

    owners: list[OwnerShare] = Field(default_factory=list)
    area: Area | None = None
    land_class: str | None = None
    record_year: str | None = None

    #: Provenance for every field above, keyed by FieldName (§26).
    fields: list[ExtractedField] = Field(default_factory=list)

    #: Pipeline metadata.
    extracted_at: datetime | None = None
    pipeline_version: str | None = None

    #: Always true in this prototype. Surfaced in the UI as a visible badge so
    #: no screenshot can be mistaken for real citizen data (§83).
    is_synthetic: bool = True

    def low_confidence_fields(self, threshold: float = 0.60) -> list[ExtractedField]:
        """Fields that must be routed to human review (§8, §27)."""
        return [f for f in self.fields if f.final_confidence < threshold]
