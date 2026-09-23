"""OpenCV preprocessing before OCR (§6, §23 stage 'preprocessing').

Measured motivation: with raw degraded pages fed straight to OCR, extraction F1
was 0.75 on clean pages but 0.07 on 'hard' and 0.00 on 'extreme'. The pipeline
cannot rely on the recogniser to cope with fading, speckle and tilt on its own.

Order is deliberate and each step is justified where it appears. The enhanced
image is KEPT alongside the original (§28) so a verifier can compare them --
preprocessing is an aid, never the record.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import cv2
import numpy as np

#: Below this long-edge, upscale before recognition. Devanagari matras are
#: small features; recognisers lose them at low effective resolution.
MIN_LONG_EDGE = 1500


@dataclass
class EnhancementResult:
    image: np.ndarray
    applied: list[str] = field(default_factory=list)
    skew_corrected: float = 0.0


def deskew(gray: np.ndarray, angle: float) -> np.ndarray:
    """Rotate by -angle to straighten the page.

    `angle` is the page's own rotation as reported by quality.measure_skew, so
    the correction is its negative. Border is filled with the page's own median
    tone rather than black, which would otherwise create a hard artificial edge
    that the detector reads as content.
    """
    if abs(angle) < 0.15:
        return gray
    height, width = gray.shape[:2]
    matrix = cv2.getRotationMatrix2D((width / 2, height / 2), -angle, 1.0)
    border = int(np.median(gray))
    return cv2.warpAffine(
        gray, matrix, (width, height),
        flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_CONSTANT, borderValue=border,
    )


def remove_speckle(gray: np.ndarray) -> np.ndarray:
    """Median filter for salt-and-pepper noise.

    Chosen over a Gaussian because impulse noise is exactly what a median
    removes cleanly, and a Gaussian would smear the strokes we need to keep.
    """
    return cv2.medianBlur(gray, 3)


def equalize(gray: np.ndarray, clip_limit: float = 1.4) -> np.ndarray:
    """CLAHE -- local contrast, so a faded corner is lifted without blowing out
    a well-exposed one.

    clipLimit is deliberately low. At 2.5 it amplified surviving sensor grain
    so hard that OCR confidence on degraded pages FELL from 0.62 to 0.44 and
    the recogniser began emitting Latin garbage. Contrast is only useful here
    to the extent it does not also boost the noise floor.
    """
    clahe = cv2.createCLAHE(clipLimit=clip_limit, tileGridSize=(8, 8))
    return clahe.apply(gray)


def denoise_strong(gray: np.ndarray, strength: int = 10) -> np.ndarray:
    """Edge-preserving denoise for badly degraded scans.

    Non-local means rather than a bigger median: it removes the broad grain
    that CLAHE would otherwise amplify, while keeping stroke edges that a
    larger median kernel would round off.
    """
    return cv2.fastNlMeansDenoising(gray, None, h=strength,
                                    templateWindowSize=7, searchWindowSize=21)


def flatten_illumination(gray: np.ndarray) -> np.ndarray:
    """Divide out a large-scale background estimate.

    Removes the lighting gradient while leaving strokes intact. A morphological
    close with a large kernel approximates 'the page without its text'.
    """
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (41, 41))
    background = cv2.morphologyEx(gray, cv2.MORPH_CLOSE, kernel)
    normalized = cv2.divide(gray, background, scale=255)
    return normalized


def upscale(gray: np.ndarray, min_long_edge: int = MIN_LONG_EDGE) -> np.ndarray:
    long_edge = max(gray.shape[:2])
    if long_edge >= min_long_edge:
        return gray
    scale = min_long_edge / long_edge
    return cv2.resize(gray, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)


def enhance(image: np.ndarray, skew_angle: float = 0.0,
            aggressive: bool = False) -> EnhancementResult:
    """Prepare a page for recognition.

    `aggressive` adds illumination flattening and sharpening, which help badly
    degraded scans but can thin the strokes on an already-clean page. The
    caller decides based on the quality report rather than applying it blindly.
    """
    applied: list[str] = []

    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if image.ndim == 3 else image.copy()

    gray = remove_speckle(gray)
    applied.append("median_denoise")

    if aggressive:
        # Order matters: denoise BEFORE any contrast operation. Running CLAHE
        # first amplifies the grain, and no later filter recovers the strokes.
        gray = denoise_strong(gray)
        applied.append("nlmeans_denoise")
        gray = flatten_illumination(gray)
        applied.append("flatten_illumination")

    gray = equalize(gray)
    applied.append("clahe")

    if abs(skew_angle) >= 0.15:
        gray = deskew(gray, skew_angle)
        applied.append(f"deskew({skew_angle:+.2f})")

    before = gray.shape
    gray = upscale(gray)
    if gray.shape != before:
        applied.append(f"upscale->{max(gray.shape)}px")

    # Sharpening is deliberately NOT applied on the aggressive path: on noisy
    # pages the unsharp mask amplified speckle into false strokes. It remains
    # available for callers dealing with soft-but-clean scans.

    # Recognisers expect 3-channel input.
    return EnhancementResult(
        image=cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR),
        applied=applied,
        skew_corrected=skew_angle,
    )


def enhance_for_quality(image: np.ndarray, report) -> EnhancementResult:
    """Choose an enhancement strength from the §22 quality report.

    A page the gate rates PROCESS is left alone apart from deskewing. Measured:
    running the full chain over already-clean pages LOWERED extraction F1 from
    0.75 to 0.67, because CLAHE and upscaling thin strokes that were already
    crisp. Enhancement is a remedy, not a default.
    """
    if report.recommended_action == "PROCESS":
        if abs(report.skew_angle) < 0.15:
            return EnhancementResult(image=image, applied=["none"], skew_corrected=0.0)
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if image.ndim == 3 else image
        straightened = deskew(gray, report.skew_angle)
        return EnhancementResult(
            image=cv2.cvtColor(straightened, cv2.COLOR_GRAY2BGR),
            applied=[f"deskew({report.skew_angle:+.2f})"],
            skew_corrected=report.skew_angle,
        )

    aggressive = report.recommended_action in (
        "RESCAN_RECOMMENDED", "REJECT_QUALITY", "PROCESS_WITH_WARNING"
    )
    return enhance(image, skew_angle=report.skew_angle, aggressive=aggressive)
