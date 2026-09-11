"""Document quality assessment (§22).

Runs immediately on upload, before any expensive model, so a page that cannot
usefully be read is sent back for a rescan rather than burning OCR time and
producing confident nonsense.

Every metric is normalised to 0..1 where 1 is good, so they can be combined and
compared across documents. The raw measurement is kept alongside the normalised
score because "blur_score 0.71" is meaningless to an operator without knowing
the variance it came from.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field

import cv2
import numpy as np

#: Laplacian variance (AFTER denoising) above which a page is treated as fully
#: sharp. Calibrated against the generated set rather than guessed -- measured
#: medians were clean 36.0, moderate 19.4, hard 5.0, extreme 5.5.
SHARP_VARIANCE = 30.0

#: Action thresholds on the overall score.
#:
#: Deliberately reluctant to reject. A rejected page never reaches OCR at all,
#: so a trigger-happy gate silently removes exactly the hard cases the Verifier
#: workflow exists to handle. An earlier calibration rejected 94% of the 'hard'
#: tier -- pages whose text is plainly legible by eye. Rejection is reserved
#: for pages that are genuinely unreadable.
REJECT_BELOW = 0.22
RESCAN_BELOW = 0.34
WARN_BELOW = 0.58

#: Long edge, in pixels, considered adequate for Devanagari OCR at ~150 dpi.
GOOD_RESOLUTION = 1100


@dataclass
class QualityReport:
    blur_score: float
    contrast_score: float
    resolution_quality: str
    resolution_score: float
    skew_angle: float
    skew_score: float
    brightness_score: float
    overall_score: float
    recommended_action: str
    raw: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


def _to_gray(image: np.ndarray) -> np.ndarray:
    if image.ndim == 3:
        return cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    return image


def measure_blur(gray: np.ndarray) -> tuple[float, float]:
    """Variance of the Laplacian, measured AFTER impulse-noise removal.

    Raw Laplacian variance is a well-known trap on scanned documents: salt-and-
    pepper noise creates enormous local gradients, so a heavily degraded page
    scores as *sharper* than a mildly blurred one. Measured on the generated
    set, 'extreme' pages scored 1.00 (fully sharp) while 'moderate' scored 0.55.

    A 5x5 median kills impulse noise; the light Gaussian that follows removes
    JPEG blocking artefacts, which a median alone leaves behind (8x8 block
    edges are not impulses). Measured medians after both filters fall in the
    right order -- clean 36.0, moderate 19.4, hard 5.0, extreme 5.5 -- whereas
    the raw variance ranked 'extreme' as the SHARPEST tier.
    """
    denoised = cv2.medianBlur(gray, 5)
    denoised = cv2.GaussianBlur(denoised, (3, 3), 0)
    variance = float(cv2.Laplacian(denoised, cv2.CV_64F).var())
    return min(1.0, variance / SHARP_VARIANCE), variance


def measure_contrast(gray: np.ndarray) -> tuple[float, float]:
    """Std-dev of intensity, normalised.

    A faded scan and a blown-out one both collapse the spread, so this catches
    both directions of failure.
    """
    std = float(gray.std())
    return min(1.0, std / 64.0), std


def measure_brightness(gray: np.ndarray) -> tuple[float, float]:
    """Penalise pages that are too dark or too bright to threshold reliably."""
    mean = float(gray.mean())
    # Peak score at mid-grey, falling off towards either extreme.
    score = 1.0 - abs(mean - 140.0) / 140.0
    return max(0.0, min(1.0, score)), mean


def measure_skew(gray: np.ndarray, search_deg: float = 12.0,
                 step: float = 0.5) -> tuple[float, float]:
    """Estimate page rotation by horizontal projection profile.

    SIGN CONVENTION: the returned angle is the page's own rotation, matching
    what a human would call "this page is tilted 3 degrees". To straighten the
    page, rotate by the NEGATIVE of this value. The search below finds the
    correction angle, so it is negated before returning -- getting this
    backwards would make the deskew step double the tilt instead of removing
    it.

    The obvious approach -- minAreaRect over all ink -- does NOT work here. It
    returns the angle of the bounding box of the whole text block, which for a
    roughly rectangular page is arbitrary (we measured -89.6 and -90.0 on pages
    that were within a degree of upright).

    Projection profiling is the reliable method: rotate through candidate
    angles and score each by the variance of the row-sum profile. When lines of
    text are horizontal, rows alternate sharply between ink and paper, so the
    variance peaks at the true skew.
    """
    inverted = cv2.bitwise_not(gray)
    _, binary = cv2.threshold(inverted, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)
    if cv2.countNonZero(binary) < 50:
        return 0.0, 1.0

    # Downscale: skew is a global property and this makes the search cheap.
    scale = 600.0 / max(binary.shape)
    if scale < 1.0:
        binary = cv2.resize(binary, None, fx=scale, fy=scale,
                            interpolation=cv2.INTER_AREA)

    height, width = binary.shape
    centre = (width / 2.0, height / 2.0)

    best_angle, best_variance = 0.0, -1.0
    candidate = -search_deg
    while candidate <= search_deg:
        matrix = cv2.getRotationMatrix2D(centre, candidate, 1.0)
        rotated = cv2.warpAffine(binary, matrix, (width, height),
                                 flags=cv2.INTER_NEAREST, borderValue=0)
        profile = rotated.sum(axis=1, dtype=np.float64)
        variance = float(profile.var())
        if variance > best_variance:
            best_variance, best_angle = variance, candidate
        candidate += step

    # best_angle straightens the page; the page's own rotation is its negative.
    page_rotation = -float(best_angle)

    # Beyond ~10 degrees a scan is genuinely awkward, not merely tilted.
    score = max(0.0, 1.0 - abs(page_rotation) / 10.0)
    return page_rotation, score


def measure_resolution(gray: np.ndarray) -> tuple[str, float]:
    long_edge = max(gray.shape)
    score = min(1.0, long_edge / GOOD_RESOLUTION)
    if long_edge >= GOOD_RESOLUTION:
        label = "good"
    elif long_edge >= GOOD_RESOLUTION * 0.7:
        label = "medium"
    else:
        label = "low"
    return label, score


def recommend(overall: float, blur: float, resolution_score: float) -> str:
    """Map scores onto the §22 action vocabulary.

    Blur and resolution can each veto on their own: a sharp-but-dim page is
    recoverable by preprocessing, a smeared one is not.
    """
    if overall < REJECT_BELOW or blur < 0.04:
        return "REJECT_QUALITY"
    if overall < RESCAN_BELOW or resolution_score < 0.55:
        return "RESCAN_RECOMMENDED"
    if overall < WARN_BELOW:
        return "PROCESS_WITH_WARNING"
    return "PROCESS"


def assess(image: np.ndarray) -> QualityReport:
    """Score one page."""
    gray = _to_gray(image)

    blur_score, blur_raw = measure_blur(gray)
    contrast_score, contrast_raw = measure_contrast(gray)
    brightness_score, brightness_raw = measure_brightness(gray)
    skew_angle, skew_score = measure_skew(gray)
    resolution_quality, resolution_score = measure_resolution(gray)

    # Weighted towards the properties OCR actually depends on. Blur dominates:
    # nothing downstream recovers characters that were never resolved.
    overall = (
        0.40 * blur_score
        + 0.22 * contrast_score
        + 0.18 * resolution_score
        + 0.12 * skew_score
        + 0.08 * brightness_score
    )

    return QualityReport(
        blur_score=round(blur_score, 3),
        contrast_score=round(contrast_score, 3),
        resolution_quality=resolution_quality,
        resolution_score=round(resolution_score, 3),
        skew_angle=round(skew_angle, 2),
        skew_score=round(skew_score, 3),
        brightness_score=round(brightness_score, 3),
        overall_score=round(overall, 3),
        recommended_action=recommend(overall, blur_score, resolution_score),
        raw={
            "laplacian_variance": round(blur_raw, 1),
            "intensity_std": round(contrast_raw, 1),
            "mean_intensity": round(brightness_raw, 1),
            "long_edge_px": int(max(gray.shape)),
        },
    )


def assess_bytes(data: bytes) -> QualityReport:
    """Assess an upload (JPEG, PNG or PDF), returning its WEAKEST page.

    This docstring used to say "PDFs are rasterised upstream" while nothing
    did, so every PDF failed to decode here. Pages are now rendered by
    ingest.rasterize, and the document is only as good as its worst page.
    """
    from ingest.rasterize import decode_pages

    return min((assess(image) for image in decode_pages(data)),
               key=lambda report: report.overall_score)
