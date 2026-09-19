"""PDF uploads become page images (§21).

The upload allowlist accepted PDFs, but nothing rendered them: every PDF failed
to decode and was recorded as REJECT_QUALITY -- an unsupported format reported
to the operator as a bad scan.
"""

import io
import sys
from pathlib import Path

import cv2
import numpy as np
import pytest
from PIL import Image

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "services" / "ai-worker"))

from ingest.rasterize import (  # noqa: E402
    MAX_LONG_EDGE,
    MAX_PDF_PAGES,
    MAX_SOURCE_PIXELS,
    decode_pages,
    is_pdf,
)
from quality.assessment import assess, assess_bytes  # noqa: E402


def page(text_rows: int = 30, size=(1240, 1200), blur: int = 0) -> Image.Image:
    """A synthetic page with dark text-like bars, optionally blurred."""
    canvas = np.full((size[1], size[0], 3), 245, np.uint8)
    for row in range(text_rows):
        y = 60 + row * 36
        cv2.rectangle(canvas, (80, y), (80 + 900 - (row % 5) * 90, y + 14), (30, 30, 30), -1)
    if blur:
        canvas = cv2.GaussianBlur(canvas, (blur, blur), 0)
    return Image.fromarray(canvas)


def to_pdf(pages: list[Image.Image], resolution: float = 150) -> bytes:
    buffer = io.BytesIO()
    pages[0].save(buffer, "PDF", save_all=True, append_images=pages[1:], resolution=resolution)
    return buffer.getvalue()


def to_png(image: Image.Image) -> bytes:
    buffer = io.BytesIO()
    image.save(buffer, "PNG")
    return buffer.getvalue()


def test_every_pdf_page_is_rendered():
    images = decode_pages(to_pdf([page(), page(12), page(20)]))
    assert len(images) == 3
    assert all(img.ndim == 3 and img.shape[2] == 3 for img in images)


def test_rendered_page_is_large_enough_for_ocr():
    """A 150-dpi 1240px page is ~8.3in wide; at 200 dpi that is ~1650px."""
    (image,) = decode_pages(to_pdf([page()]))
    assert max(image.shape[:2]) >= 1500


def test_an_image_upload_is_its_own_single_page():
    data = to_png(page())
    assert not is_pdf(data)
    (image,) = decode_pages(data)
    assert image.shape[:2] == (1200, 1240)


def test_oversized_pages_are_capped():
    huge = to_pdf([page(size=(1240, 1200))], resolution=10)  # ~124in wide
    (image,) = decode_pages(huge)
    assert max(image.shape[:2]) <= MAX_LONG_EDGE


def test_large_image_is_bounded_before_inference():
    (image,) = decode_pages(to_png(page(size=(4000, 1000))))
    assert max(image.shape[:2]) == MAX_LONG_EDGE


def test_excessive_source_pixels_are_refused_before_decode():
    side = int(MAX_SOURCE_PIXELS**0.5) + 1
    with pytest.raises(ValueError, match="pixels; at most"):
        decode_pages(to_png(Image.new("L", (side, side), 255)))


def test_too_many_pages_is_refused_with_a_reason():
    small = page(2, size=(200, 200))
    with pytest.raises(ValueError, match=f"at most {MAX_PDF_PAGES}"):
        decode_pages(to_pdf([small] * (MAX_PDF_PAGES + 1)))


@pytest.mark.parametrize("data", [b"%PDF-1.7\n%garbage", b"%PDF-"])
def test_damaged_pdf_is_a_readable_error(data):
    with pytest.raises(ValueError, match="damaged or not a valid PDF"):
        decode_pages(data)


def test_quality_gate_judges_a_pdf_by_its_weakest_page():
    sharp, blurred = page(), page(blur=31)
    pdf_report = assess_bytes(to_pdf([sharp, blurred]))
    weakest = min(
        (assess(img) for img in decode_pages(to_pdf([sharp, blurred]))),
        key=lambda r: r.overall_score,
    )
    assert pdf_report.overall_score == weakest.overall_score
    assert pdf_report.overall_score < assess_bytes(to_pdf([sharp])).overall_score
