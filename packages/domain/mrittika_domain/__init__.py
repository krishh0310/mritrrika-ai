"""Mrittika AI shared domain.

Imported by BOTH apps/api and services/ai-worker so there is exactly one
definition of the record shape, the state machine and the confidence rules.
The TypeScript mirror in packages/shared-types is GENERATED from this package
(scripts/generate_shared_types.py) and must not be hand-edited.
"""

from .confidence import (
    DEFAULT_WEIGHTS,
    HIGH_THRESHOLD,
    MEDIUM_THRESHOLD,
    ConfidenceSignals,
    ConfidenceWeights,
    FusedConfidence,
    band_for,
    fuse,
)
from .entities import (
    LandRecord,
    Location,
    Mutation,
    Owner,
    OwnershipRecord,
    Parcel,
    SyntheticUser,
    SyntheticWorld,
)
from .enums import (
    AnomalyType,
    AreaUnit,
    ConfidenceBand,
    DocumentState,
    DocumentType,
    FieldName,
    FieldStatus,
    GrievanceStatus,
    MutationType,
    ProcessingStage,
    QualityRecommendation,
    Role,
    ValidationSeverity,
)
from .records import (
    Area,
    BoundingBox,
    CanonicalLandRecord,
    ExtractedField,
    OwnerShare,
)
from .state_machine import (
    ALLOWED_TRANSITIONS,
    CITIZEN_VISIBLE_STATES,
    TERMINAL_STATES,
    IllegalTransitionError,
    assert_transition,
    can_transition,
)

__all__ = [
    "ALLOWED_TRANSITIONS",
    "CITIZEN_VISIBLE_STATES",
    "DEFAULT_WEIGHTS",
    "HIGH_THRESHOLD",
    "MEDIUM_THRESHOLD",
    "TERMINAL_STATES",
    "AnomalyType",
    "Area",
    "AreaUnit",
    "BoundingBox",
    "CanonicalLandRecord",
    "ConfidenceBand",
    "ConfidenceSignals",
    "ConfidenceWeights",
    "DocumentState",
    "DocumentType",
    "ExtractedField",
    "FieldName",
    "FieldStatus",
    "FusedConfidence",
    "GrievanceStatus",
    "IllegalTransitionError",
    "LandRecord",
    "Location",
    "Mutation",
    "MutationType",
    "Owner",
    "OwnerShare",
    "OwnershipRecord",
    "Parcel",
    "ProcessingStage",
    "QualityRecommendation",
    "Role",
    "SyntheticUser",
    "SyntheticWorld",
    "ValidationSeverity",
    "assert_transition",
    "band_for",
    "can_transition",
    "fuse",
]
