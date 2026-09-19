"""Documents placed mid-lifecycle, then moved on through the real services.

Tests for what happens AFTER extraction -- corrections, accuracy, retraining
export, approval and LRMS delivery -- need a document with known fields. Going
through upload and OCR for that would make each of them an OCR test by
accident, slow and dependent on the model's reading of a page.

So `stage()` writes a document exactly as the pipeline leaves one --
NEEDS_VERIFICATION, with a page, OCR blocks, extractions and a verification
task -- and every step after that uses the production service functions:
correct_field, approve_field, submit_verification, approve. Only the part the
tests are not about is shortcut.

Staged documents are deleted on teardown (the cascade takes their pages,
blocks, extractions, corrections, feedback and outbox rows). Audit events stay:
the chain is append-only, and deleting from it would break verification.
"""

from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass

from sqlalchemy import select

#: A parcel inside the demo tehsildar's and verifier's jurisdiction.
PARCEL = "PARCEL-UP-DEMO-0181"


@dataclass
class Field:
    field: str
    value: str
    confidence: float = 0.9
    bbox: tuple[int, int, int, int] | None = None
    row: int | None = None
    status: str = "NEEDS_REVIEW"


def principal(session, email: str):
    from app.models import User
    from app.services.auth_service import build_principal

    user = session.execute(select(User).where(User.email == email)).scalar_one()
    return build_principal(session, user)


def stage(
    session,
    fields: list[Field],
    blocks: list[tuple[str, tuple[int, int, int, int]]] = (),
    *,
    parcel_external_id: str = PARCEL,
    model_version: str = "extractor-v1",
):
    """A document as the pipeline leaves it: awaiting verification."""
    from app.models import (
        Document,
        DocumentPage,
        Extraction,
        OcrBlock,
        Parcel,
        VerificationTask,
    )

    parcel = session.execute(
        select(Parcel).where(Parcel.external_id == parcel_external_id)
    ).scalar_one()
    token = uuid.uuid4().hex[:10].upper()
    document = Document(
        external_id=f"DOC-T{token}",
        document_type="KHASRA",
        state="NEEDS_VERIFICATION",
        parcel_id=parcel.id,
        village_id=parcel.village_id,
        record_year="1998-99",
        storage_key=f"test/staged/{token}.jpg",
        mime_type="image/jpeg",
        checksum_sha256=hashlib.sha256(token.encode()).hexdigest(),
    )
    session.add(document)
    session.flush()

    page = DocumentPage(document_id=document.id, page_number=1, width=1240, height=1754)
    session.add(page)
    session.flush()
    for order, (text, box) in enumerate(blocks):
        session.add(OcrBlock(
            page_id=page.id, text=text, confidence=0.9,
            bbox_x1=box[0], bbox_y1=box[1], bbox_x2=box[2], bbox_y2=box[3],
            reading_order=order, model_version="ocr-v1",
        ))

    for f in fields:
        box = f.bbox or (0, 0, 0, 0)
        session.add(Extraction(
            document_id=document.id, page_number=1, field=f.field,
            raw_value=f.value, normalized_value=f.value,
            final_confidence=f.confidence, status=f.status,
            bbox_x1=box[0], bbox_y1=box[1], bbox_x2=box[2], bbox_y2=box[3],
            row_index=f.row, model_version=model_version,
        ))
    session.add(VerificationTask(document_id=document.id, status="PENDING",
                                 lowest_confidence=min(f.confidence for f in fields)))
    session.commit()
    return document


def extraction(session, document, field: str):
    from app.models import Extraction

    return session.execute(
        select(Extraction).where(
            Extraction.document_id == document.id, Extraction.field == field
        )
    ).scalars().first()


def finish_verification(session, document, verifier_email: str, *,
                        corrections: dict[str, str] | None = None):
    """Correct what is asked, approve every other field, submit."""
    from app.models import Extraction
    from app.services import verification_service

    verifier = principal(session, verifier_email)
    corrections = corrections or {}
    for field, value in corrections.items():
        verification_service.correct_field(
            session, extraction(session, document, field).id, value, principal=verifier
        )
    for row in session.execute(
        select(Extraction).where(
            Extraction.document_id == document.id,
            Extraction.status == "NEEDS_REVIEW",
        )
    ).scalars().all():
        verification_service.approve_field(session, row.id, principal=verifier)
    session.refresh(document)
    verification_service.submit_verification(session, document, principal=verifier)
    session.refresh(document)
    return document


def approve(session, document, tehsildar_email: str):
    from app.services import verification_service

    verification_service.approve(
        session, document, principal=principal(session, tehsildar_email)
    )
    session.refresh(document)
    return document


def delete(session, *documents) -> None:
    for document in documents:
        session.delete(session.merge(document))
    session.commit()
