"""Duplicate detection at upload (§22, §34).

Two different questions, deliberately answered differently.

**Are these the same bytes?** A SHA-256 match is not a judgement call: the file
has already been uploaded. Re-running OCR on it would burn a worker slot to
produce a second copy of an answer the system already has, and would leave two
documents that must then be reconciled by hand. So an exact match is refused,
and the refusal names the document that already holds those bytes.

**Do these look like the same page?** A re-scan of the same register page
produces different bytes and a very similar image. That is NOT grounds for
refusal -- a genuine rescan after a quality rejection is exactly this, and it
is the correct thing for an operator to do. So a near match is recorded as a
flag an officer can see and dismiss, worded as a resemblance rather than an
accusation (§34).

The perceptual hash is a 64-bit difference hash. dHash is chosen over aHash
because it survives the brightness and contrast shifts that scanning
introduces, and over pHash because it needs no DCT and therefore no new
dependency -- numpy and Pillow are already here.
"""

from __future__ import annotations

import hashlib

import numpy as np
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AnomalyFlag, Document

#: Hamming distance at or below which two pages are called a near match.
#: 64 bits, so 10 is ~15% of the hash differing. Set from the corpus: distinct
#: template pages sit far above this, a rescan of one page far below.
NEAR_DUPLICATE_DISTANCE = 10

#: How many prior documents to compare against. dHash has no index structure,
#: so this is a linear scan; bounding it keeps upload latency predictable.
COMPARISON_LIMIT = 500

DUPLICATE_DOCUMENT = "DUPLICATE_DOCUMENT"


class DuplicateDocument(Exception):
    """These exact bytes are already stored under `existing`."""

    def __init__(self, existing: Document) -> None:
        self.existing = existing
        super().__init__(
            f"This file has already been uploaded as {existing.external_id}"
        )


def checksum(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def find_exact_duplicate(session: Session, digest: str) -> Document | None:
    """The earliest document holding these bytes, if any.

    Earliest rather than any: when an operator is told which document already
    has their file, it should be the original, not whichever row the planner
    happened to reach first.
    """
    return session.execute(
        select(Document)
        .where(Document.checksum_sha256 == digest)
        .order_by(Document.created_at.asc())
        .limit(1)
    ).scalar_one_or_none()


def perceptual_hash(image: np.ndarray) -> str:
    """64-bit dHash of one page, as 16 hex characters.

    Each bit records whether a pixel is brighter than the one to its right, on
    a 9x8 grey thumbnail. Because every bit is a COMPARISON between neighbours
    rather than a level, uniform brightness and contrast changes cancel out --
    which is most of what a second pass through a scanner does to a page.
    """
    if image.ndim == 3:
        # Rec. 601 luma. cv2 hands over BGR, so the weights run in reverse.
        grey = (0.114 * image[:, :, 0] + 0.587 * image[:, :, 1]
                + 0.299 * image[:, :, 2])
    else:
        grey = image.astype(np.float64)

    from PIL import Image

    thumb = Image.fromarray(np.clip(grey, 0, 255).astype(np.uint8)).resize(
        (9, 8), Image.Resampling.LANCZOS
    )
    cells = np.asarray(thumb, dtype=np.int16)
    bits = (cells[:, 1:] > cells[:, :-1]).flatten()

    value = 0
    for bit in bits:
        value = (value << 1) | int(bit)
    return f"{value:016x}"


def hamming_distance(a: str, b: str) -> int:
    """Differing bits between two hex-encoded hashes."""
    return bin(int(a, 16) ^ int(b, 16)).count("1")


def find_near_duplicates(
    session: Session,
    digest: str,
    *,
    exclude_id: str,
    threshold: int = NEAR_DUPLICATE_DISTANCE,
    limit: int = COMPARISON_LIMIT,
) -> list[tuple[Document, int]]:
    """Previously stored pages that look like this one, closest first."""
    candidates = session.execute(
        select(Document)
        .where(Document.perceptual_hash.is_not(None))
        .where(Document.id != exclude_id)
        .order_by(Document.created_at.desc())
        .limit(limit)
    ).scalars().all()

    matches = []
    for candidate in candidates:
        try:
            distance = hamming_distance(digest, candidate.perceptual_hash)
        except ValueError:  # a malformed stored hash must not break an upload
            continue
        if distance <= threshold:
            matches.append((candidate, distance))

    matches.sort(key=lambda pair: pair[1])
    return matches


def record_resemblance(
    session: Session, document: Document, matches: list[tuple[Document, int]]
) -> AnomalyFlag | None:
    """Flag a visual resemblance for an officer to judge (§34).

    Deliberately not an accusation and deliberately not a block: a rescan after
    a quality rejection produces exactly this signal and is the correct action.
    """
    if not matches:
        return None

    closest, distance = matches[0]
    # 0 differing bits is a visually identical page; scale down from there.
    score = max(0.0, min(1.0, 1.0 - distance / (NEAR_DUPLICATE_DISTANCE + 1)))

    flag = AnomalyFlag(
        document_id=document.id,
        parcel_id=document.parcel_id,
        anomaly_type=DUPLICATE_DOCUMENT,
        score=score,
        explanation=(
            "This page closely resembles a document already in the system. "
            "That is expected after a rescan; otherwise it may be a second "
            "copy of the same record and is worth checking."
        ),
        evidence={
            "resembles": [
                {"document": doc.external_id, "differing_bits": dist}
                for doc, dist in matches[:5]
            ],
            "threshold_bits": NEAR_DUPLICATE_DISTANCE,
            "method": "dhash-64",
        },
        model_version="duplicate-v1",
    )
    session.add(flag)
    return flag


__all__ = [
    "COMPARISON_LIMIT", "DUPLICATE_DOCUMENT", "NEAR_DUPLICATE_DISTANCE",
    "DuplicateDocument", "checksum", "find_exact_duplicate",
    "find_near_duplicates", "hamming_distance", "perceptual_hash",
    "record_resemblance",
]
