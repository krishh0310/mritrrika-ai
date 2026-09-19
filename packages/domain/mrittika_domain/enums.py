"""Controlled vocabularies shared by the API, the AI worker and the frontends.

Every value here is part of the wire contract. Renaming one is a breaking
change that must ripple to packages/shared-types (regenerated, not hand-edited).
"""

from enum import StrEnum


class Role(StrEnum):
    """The roles (§12). Authorization is always decided from the role on the
    authenticated user record -- never from anything the client sends.

    The first four run the workflow. The rest are read-only stakeholders:
    state and central oversight, the survey department, and research
    institutions, who get anonymised data only.
    """

    CITIZEN = "CITIZEN"
    DEO = "DEO"
    VERIFIER = "VERIFIER"
    TEHSILDAR = "TEHSILDAR"
    STATE_OFFICER = "STATE_OFFICER"
    CENTRAL_OFFICER = "CENTRAL_OFFICER"
    SURVEYOR = "SURVEYOR"
    RESEARCHER = "RESEARCHER"
    #: A service account for another government system; used with an API key.
    INTEGRATION = "INTEGRATION"


class DocumentType(StrEnum):
    """Legacy record types targeted by the prototype (§1)."""

    KHASRA = "KHASRA"
    KHATAUNI = "KHATAUNI"
    JAMABANDI = "JAMABANDI"
    RECORD_OF_RIGHTS = "RECORD_OF_RIGHTS"
    MUTATION_REGISTER = "MUTATION_REGISTER"
    SUPPORTING = "SUPPORTING"


class DocumentState(StrEnum):
    """Document lifecycle (§37).

    Transitions are validated server-side in the service layer against
    ALLOWED_TRANSITIONS in state_machine.py. UPLOADED -> APPROVED must never
    be reachable.
    """

    UPLOADED = "UPLOADED"
    QUALITY_CHECK = "QUALITY_CHECK"
    PROCESSING = "PROCESSING"
    AI_EXTRACTED = "AI_EXTRACTED"
    NEEDS_VERIFICATION = "NEEDS_VERIFICATION"
    UNDER_VERIFICATION = "UNDER_VERIFICATION"
    VERIFIED = "VERIFIED"
    PENDING_APPROVAL = "PENDING_APPROVAL"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    RESCAN_REQUIRED = "RESCAN_REQUIRED"
    ARCHIVED = "ARCHIVED"


class ProcessingStage(StrEnum):
    """Stages streamed to the client during async processing (§24)."""

    UPLOAD = "upload"
    QUALITY = "quality"
    PREPROCESSING = "preprocessing"
    OCR = "ocr"
    LAYOUT = "layout"
    EXTRACTION = "extraction"
    NORMALIZATION = "normalization"
    VALIDATION = "validation"
    CONFIDENCE = "confidence"
    COMPLETE = "complete"


class QualityRecommendation(StrEnum):
    """Outcome of the pre-processing quality gate (§22)."""

    PROCESS = "PROCESS"
    PROCESS_WITH_WARNING = "PROCESS_WITH_WARNING"
    RESCAN_RECOMMENDED = "RESCAN_RECOMMENDED"
    REJECT_QUALITY = "REJECT_QUALITY"


class FieldStatus(StrEnum):
    """Per-field verification state (§26, §28)."""

    AUTO_ACCEPTED = "AUTO_ACCEPTED"
    NEEDS_REVIEW = "NEEDS_REVIEW"
    VERIFIER_APPROVED = "VERIFIER_APPROVED"
    VERIFIER_CORRECTED = "VERIFIER_CORRECTED"
    ILLEGIBLE = "ILLEGIBLE"
    ESCALATED = "ESCALATED"


class ConfidenceBand(StrEnum):
    """UI banding (§8). Always paired with text/icon, never colour alone (§86)."""

    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class FieldName(StrEnum):
    """Entities the extractor targets (§6).

    A closed vocabulary so extraction, validation, correction and the RAG
    retriever all refer to the same field by the same key.
    """

    OWNER = "OWNER"
    GUARDIAN = "GUARDIAN"
    KHASRA = "KHASRA"
    KHATA = "KHATA"
    VILLAGE = "VILLAGE"
    TEHSIL = "TEHSIL"
    DISTRICT = "DISTRICT"
    STATE = "STATE"
    COUNTRY = "COUNTRY"
    AREA = "AREA"
    AREA_UNIT = "AREA_UNIT"
    LAND_CLASS = "LAND_CLASS"
    MUTATION = "MUTATION"
    DATE = "DATE"
    RECORD_YEAR = "RECORD_YEAR"
    SHARE = "SHARE"
    REMARK = "REMARK"


class AreaUnit(StrEnum):
    """Area units found in Indian land records.

    Stored as the unit actually written on the document; conversion to a
    canonical unit is a separate, explicit step so the original is never lost.
    BIGHA and BISWA are northern; GUNTHA and CENT are the southern subdivisions
    of the acre (Telangana, Andhra Pradesh, Karnataka, Tamil Nadu).
    """

    BIGHA = "BIGHA"
    BISWA = "BISWA"
    ACRE = "ACRE"
    HECTARE = "HECTARE"
    SQUARE_METRE = "SQUARE_METRE"
    GUNTHA = "GUNTHA"
    CENT = "CENT"


class MutationType(StrEnum):
    """How ownership changed (§40)."""

    SALE = "SALE"
    INHERITANCE = "INHERITANCE"
    GIFT = "GIFT"
    PARTITION = "PARTITION"
    COURT_DECREE = "COURT_DECREE"
    CORRECTION = "CORRECTION"


class ValidationSeverity(StrEnum):
    """Deterministic rule outcomes (§33)."""

    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


class AnomalyType(StrEnum):
    """Pattern flags (§34).

    Presented to officers as 'potential inconsistency requiring investigation'.
    The word 'fraud' is never used in user-facing text.
    """

    AREA_JUMP = "AREA_JUMP"
    INVALID_CHRONOLOGY = "INVALID_CHRONOLOGY"
    DUPLICATE_PARCEL = "DUPLICATE_PARCEL"
    MISSING_MUTATION = "MISSING_MUTATION"
    LOCATION_MISMATCH = "LOCATION_MISMATCH"
    REPEATED_MODIFICATION = "REPEATED_MODIFICATION"
    UNUSUAL_OWNERSHIP_CHANGE = "UNUSUAL_OWNERSHIP_CHANGE"
    #: The uploaded page closely resembles one already stored (§22). A rescan
    #: after a quality rejection produces this legitimately, so it is a
    #: resemblance to check, never a refusal.
    DUPLICATE_DOCUMENT = "DUPLICATE_DOCUMENT"


class GrievanceStatus(StrEnum):
    """Citizen grievance lifecycle (§19)."""

    SUBMITTED = "SUBMITTED"
    UNDER_REVIEW = "UNDER_REVIEW"
    ACTION_REQUIRED = "ACTION_REQUIRED"
    RESOLVED = "RESOLVED"
    REJECTED = "REJECTED"
