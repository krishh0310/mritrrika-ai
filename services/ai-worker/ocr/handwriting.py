"""Handwriting on a page: which lines, and what they say.

is_handwritten() is an untrained geometry heuristic, used only when the trained
detector (handwriting_model.py) has no weights. False means "not detected",
never "proved printed".
"""

import unicodedata

import cv2
import numpy as np


def is_handwritten(image: np.ndarray) -> bool:
    """Flag irregular character baselines after removing overall line tilt."""
    if image.size == 0:
        return False
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if image.ndim == 3 else image
    if int(gray.max()) - int(gray.min()) < 20:
        return False
    _, ink = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    _, _, stats, _ = cv2.connectedComponentsWithStats(ink)
    stats = stats[1:]
    # Ignore speckles and rules spanning much of the crop.
    stats = stats[
        (stats[:, 4] >= 8) & (stats[:, 3] >= 5) & (stats[:, 2] < gray.shape[1] * 0.5)
    ]
    if len(stats) < 5:
        return False
    stats = stats[stats[:, 3] >= np.median(stats[:, 3]) * 0.6]
    if len(stats) < 5:
        return False
    xs = stats[:, 0] + stats[:, 2] / 2
    if np.ptp(xs) == 0:
        return False
    bottoms = stats[:, 1] + stats[:, 3]
    baseline = np.polyval(np.polyfit(xs, bottoms, 1), xs)
    irregularity = np.median(np.abs(bottoms - baseline)) / np.median(stats[:, 3])
    # ponytail: synthetic-font development threshold; a trained classifier and
    # broader synthetic script coverage are needed for reliable detection.
    return bool(irregularity > 0.08)


def _crop(image, bbox):
    height, width = image.shape[:2]
    x1, y1, x2, y2 = bbox
    return image[max(0, y1):min(height, max(0, y2)), max(0, x1):min(width, max(0, x2))]


def flag_blocks(image, blocks, detector=None) -> None:
    """Inspect OCR line crops; retain any provider-supplied positive flag.

    `detector` is the trained classifier (handwriting_model.load_detector());
    without it, the geometry heuristic above. Text the OCR detector entirely
    misses cannot be inspected by this path.
    """
    check = detector.is_handwritten if detector is not None else is_handwritten
    for block in blocks:
        crop = _crop(image, block.bbox)
        block.is_handwritten = block.is_handwritten or (crop.size > 0 and check(crop))


def _same(a: str, b: str) -> bool:
    return unicodedata.normalize("NFC", " ".join(a.split())) == \
        unicodedata.normalize("NFC", " ".join(b.split()))


#: Two independent readers agreeing is evidence; disagreeing is a warning.
#: Neither makes a field auto-acceptable: the page is still reviewed.
AGREED_CONFIDENCE = 0.8
DISAGREED_CONFIDENCE = 0.4


def read_blocks(image, blocks, reader, second=None) -> dict:
    """Re-read flagged lines with the handwriting reader.

    The reader's text replaces PaddleOCR's, which was trained on print, and its
    confidence replaces the OCR confidence. With `second` (Gemini, opt-in),
    each line is read again: agreement raises the line's confidence,
    disagreement lowers it and is listed for the verifier. The first reader's
    text stands either way -- which is better is for real scans to show
    (scripts/evaluate_handwriting_real.py), not for this function to guess.

    Returns {"read": lines replaced, "second_opinion": {...} or None}.
    """
    read, agreed, disagreed = 0, 0, []
    for block in blocks:
        if not block.is_handwritten:
            continue
        crop = _crop(image, block.bbox)
        if crop.size == 0:
            continue
        text, confidence = reader.read(crop)
        if not text.strip():
            continue
        block.text, block.confidence = text, confidence
        read += 1
        if second is None:
            continue
        other, _ = second.read(crop)
        if not other:
            continue
        if _same(text, other):
            agreed += 1
            block.confidence = max(confidence, AGREED_CONFIDENCE)
        else:
            disagreed.append({"read": text, "second": other})
            block.confidence = min(confidence, DISAGREED_CONFIDENCE)
    opinion = None
    if second is not None:
        opinion = {"model": second.version, "agreed": agreed,
                   "disagreed": len(disagreed), "disagreements": disagreed[:20]}
    return {"read": read, "second_opinion": opinion}


#: Field -> the review slot named on the verifier's card.
REVIEW_SLOTS = {
    "OWNER": "owner",
    "AREA": "area",
    "KHASRA": "survey_number",
    "MUTATION": "mutation_number",
    "DATE": "date",
}


def _overlaps(a, b) -> bool:
    return a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]


def routing_meta(blocks, fields, quality: dict | None, read_by: str | None = None,
                 second_opinion: dict | None = None) -> dict | None:
    """What a reviewer needs to know about a page with suspected handwriting.

    `blocks` are (bbox, is_handwritten) and `fields` are (field, bbox), all in
    the same page coordinates. None when nothing was flagged -- the caller
    stores that as JSON null, so "no handwriting" and "not computed" differ.

      coverage_pct    share of OCR text regions flagged as handwritten
      affected_fields review slots whose value box overlaps a flagged region
      confidence      the scan-quality average (blur, skew, contrast): how far
                      the page itself can be trusted. It is NOT the
                      handwriting reader's confidence, which is per line.
      read_by         the handwriting reader version that re-read the flagged
                      lines, or None when they kept PaddleOCR's reading.
      second_opinion  Gemini's agreement with that reading, when enabled:
                      model, agreed / disagreed line counts, disagreements.
    """
    flagged = [box for box, handwritten in blocks if handwritten]
    if not flagged:
        return None
    affected = sorted({
        REVIEW_SLOTS.get(field, field.lower())
        for field, box in fields
        if box and any(_overlaps(box, region) for region in flagged)
    })
    scores = [float(quality[k]) for k in ("blur_score", "skew_score", "contrast_score")
              if quality and quality.get(k) is not None]
    return {
        "coverage_pct": round(len(flagged) / len(blocks), 4),
        "affected_fields": affected,
        "confidence": round(sum(scores) / len(scores), 4) if scores else None,
        "read_by": read_by,
        "second_opinion": second_opinion,
    }
