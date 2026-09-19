"""All ORM models. Imported as one module so Alembic autogenerate sees the
entire schema from a single import of Base.metadata.
"""

from .ai import AiFeedback, Embedding, ModelVersion, Notification
from .audit import AuditEvent
from .base import Base
from .documents import (
    Document,
    DocumentPage,
    Extraction,
    FieldCorrection,
    OcrBlock,
    ProcessingJob,
)
from .geography import Location, Parcel
from .identity import (
    ApiKey,
    CitizenProfile,
    Permission,
    Role,
    RolePermission,
    User,
    UserRole,
)
from .integration import LrmsSyncRecord
from .land import LandRecord, Mutation, Owner, OwnershipRecord
from .workflow import (
    AnomalyFlag,
    ApprovalAction,
    Grievance,
    ValidationFinding,
    VerificationAction,
    VerificationTask,
)

__all__ = [
    "AiFeedback", "AnomalyFlag", "ApiKey", "ApprovalAction", "AuditEvent", "Base",
    "CitizenProfile", "Document", "DocumentPage", "Embedding", "Extraction",
    "FieldCorrection", "Grievance", "LandRecord", "Location", "LrmsSyncRecord",
    "ModelVersion",
    "Mutation", "Notification", "OcrBlock", "Owner", "OwnershipRecord",
    "Parcel", "Permission", "ProcessingJob", "Role", "RolePermission", "User",
    "UserRole", "ValidationFinding", "VerificationAction", "VerificationTask",
]
