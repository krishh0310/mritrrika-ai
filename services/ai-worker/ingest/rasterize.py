"""Decode an upload into page images (§21, §63).

Every stage after upload -- quality, preprocessing, OCR, the Verifier's bbox
overlay -- works on page IMAGES. The upload allowlist has accepted PDFs from
the start, but nothing ever rendered one, so a PDF reached OpenCV as raw bytes,
failed to decode, and was recorded as REJECT_QUALITY: a format the system had
never handled, reported to the operator as a bad scan.

A PDF is rendered page by page with PDFium (pypdfium2, Apache-2.0/BSD). An
image upload is simply its own single page, so image behaviour is unchanged.
"""

from __future__ import annotations

import cv2
import numpy as np

PDF_MAGIC = b"%PDF-"

#: Scanned land records are typically A4/foolscap. 200 DPI puts an A4 page at
#: ~1654x2339 px -- above preprocessing's 1500 px floor, so no upscaling blur.
RENDER_DPI = 200

#: Cap on the rendered long edge. A malformed or poster-sized page would
#: otherwise allocate a bitmap of arbitrary size.
MAX_LONG_EDGE = 3000

#: Read from the image header before OpenCV expands compressed pixels. This
#: bounds memory even for a small PNG/JPEG that declares enormous dimensions.
MAX_SOURCE_PIXELS = 20_000_000

#: A land record runs to a few pages. Refusing hundreds bounds both memory at
#: upload and the time a single job holds a worker.
MAX_PDF_PAGES = 20

JPEG_START_OF_FRAME = {
    0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7,
    0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF,
}


def is_pdf(data: bytes) -> bool:
    return data[:5] == PDF_MAGIC


def image_dimensions(data: bytes) -> tuple[int, int] | None:
    """Read PNG/JPEG dimensions from headers without expanding the pixels."""
    if data.startswith(b"\x89PNG\r\n\x1a\n") and len(data) >= 24:
        return int.from_bytes(data[16:20], "big"), int.from_bytes(data[20:24], "big")
    if not data.startswith(b"\xff\xd8"):
        return None

    position = 2
    while position + 4 <= len(data):
        if data[position] != 0xFF:
            position += 1
            continue
        while position < len(data) and data[position] == 0xFF:
            position += 1
        if position >= len(data):
            return None
        marker = data[position]
        position += 1
        if marker in (0xD8, 0xD9):
            continue
        if marker == 0xDA or position + 2 > len(data):
            return None
        segment_length = int.from_bytes(data[position:position + 2], "big")
        if segment_length < 2 or position + segment_length > len(data):
            return None
        if marker in JPEG_START_OF_FRAME and segment_length >= 7:
            height = int.from_bytes(data[position + 3:position + 5], "big")
            width = int.from_bytes(data[position + 5:position + 7], "big")
            return width, height
        position += segment_length
    return None


def render_pdf(data: bytes) -> list[np.ndarray]:
    """Render every page of a PDF to a BGR image.

    Raises ValueError with an operator-readable reason, never a library trace.
    """
    import pypdfium2 as pdfium

    try:
        pdf = pdfium.PdfDocument(data)
    except pdfium.PdfiumError as exc:
        message = str(exc).lower()
        if "password" in message or "security" in message:
            raise ValueError("the PDF is password-protected; upload an unlocked copy") from exc
        raise ValueError("the PDF is damaged or not a valid PDF") from exc

    try:
        count = len(pdf)
        if count == 0:
            raise ValueError("the PDF has no pages")
        if count > MAX_PDF_PAGES:
            raise ValueError(
                f"the PDF has {count} pages; at most {MAX_PDF_PAGES} are accepted per document"
            )

        images = []
        for index in range(count):
            page = pdf[index]
            try:
                width_pt, height_pt = page.get_size()
                if width_pt <= 0 or height_pt <= 0:
                    raise ValueError(f"page {index + 1} of the PDF has no size")
                scale = RENDER_DPI / 72
                long_edge = max(width_pt, height_pt) * scale
                if long_edge > MAX_LONG_EDGE:
                    scale *= MAX_LONG_EDGE / long_edge
                bitmap = page.render(scale=scale)
                try:
                    rgb = np.asarray(bitmap.to_pil().convert("RGB"))
                finally:
                    bitmap.close()
            finally:
                page.close()
            images.append(cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR))
        return images
    finally:
        pdf.close()


def decode_pages(data: bytes) -> list[np.ndarray]:
    """Every page of an upload as BGR images: one for an image, N for a PDF."""
    if is_pdf(data):
        return render_pdf(data)

    dimensions = image_dimensions(data)
    if dimensions is None:
        raise ValueError("could not decode image bytes")
    width, height = dimensions
    if width <= 0 or height <= 0:
        raise ValueError("the image has no size")
    if width * height > MAX_SOURCE_PIXELS:
        raise ValueError(
            f"the image has {width * height} pixels; at most "
            f"{MAX_SOURCE_PIXELS} are accepted"
        )

    image = cv2.imdecode(np.frombuffer(data, dtype=np.uint8), cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError("could not decode image bytes")
    long_edge = max(image.shape[:2])
    if long_edge > MAX_LONG_EDGE:
        scale = MAX_LONG_EDGE / long_edge
        image = cv2.resize(image, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
    return [image]


def encode_png(image: np.ndarray) -> bytes:
    ok, buffer = cv2.imencode(".png", image)
    if not ok:
        raise ValueError("could not encode the rendered page")
    return buffer.tobytes()
