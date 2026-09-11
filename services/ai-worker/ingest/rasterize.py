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

#: A land record runs to a few pages. Refusing hundreds bounds both memory at
#: upload and the time a single job holds a worker.
MAX_PDF_PAGES = 20


def is_pdf(data: bytes) -> bool:
    return data[:5] == PDF_MAGIC


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
    image = cv2.imdecode(np.frombuffer(data, dtype=np.uint8), cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError("could not decode image bytes")
    return [image]


def encode_png(image: np.ndarray) -> bytes:
    ok, buffer = cv2.imencode(".png", image)
    if not ok:
        raise ValueError("could not encode the rendered page")
    return buffer.tobytes()
