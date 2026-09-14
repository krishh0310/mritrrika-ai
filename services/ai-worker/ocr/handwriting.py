"""Conservative handwriting suspicion from a single text-line image.

This is an untrained geometry heuristic, not a handwriting classifier with
validated accuracy. False means "not detected", never "proved printed".
Connected scripts, short words and neat handwriting are common blind spots.
"""

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


def flag_blocks(image, blocks) -> None:
    """Inspect OCR line crops; retain any provider-supplied positive flag.

    Text the OCR detector entirely misses cannot be inspected by this path.
    Multi-line/approximate fallback boxes can produce false positives.
    """
    height, width = image.shape[:2]
    for block in blocks:
        x1, y1, x2, y2 = block.bbox
        crop = image[max(0, y1):min(height, max(0, y2)),
                     max(0, x1):min(width, max(0, x2))]
        block.is_handwritten = block.is_handwritten or is_handwritten(crop)
