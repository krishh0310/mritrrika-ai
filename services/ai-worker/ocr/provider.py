"""OCR provider abstraction (§81) with a real fallback contract (§82).

Two rules this module exists to enforce:

  1. No single vendor is load-bearing. Swapping PaddleOCR for another engine is
     a config change, not a refactor.
  2. A failed provider NEVER fabricates output. It raises, the caller falls
     back, and if every provider fails the region is marked NEEDS_REVIEW.

Reading order is handled here, not by callers. PaddleOCR does not return blocks
in reading order, and Devanagari cannot be line-grouped by y-centre because
matras and the anusvara inflate box heights -- see group_lines().
"""

from __future__ import annotations

import base64
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field

import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class TextBlock:
    text: str
    confidence: float
    bbox: tuple[int, int, int, int]
    script: str | None = None
    reading_order: int | None = None
    is_handwritten: bool = False


@dataclass
class OcrResult:
    blocks: list[TextBlock] = field(default_factory=list)
    model_version: str = "ocr-v1"
    provider: str = "unknown"
    #: True when this came from a fallback rather than the primary provider,
    #: so downstream can weight confidence accordingly.
    degraded: bool = False

    @property
    def text(self) -> str:
        return " ".join(b.text for b in self.blocks)

    def mean_confidence(self) -> float:
        return (
            sum(b.confidence for b in self.blocks) / len(self.blocks)
            if self.blocks else 0.0
        )


class OcrUnavailable(Exception):
    """The provider could not run at all. Callers must fall back, not invent."""


def group_lines(
    blocks: list[TextBlock], overlap_ratio: float = 0.5
) -> list[list[TextBlock]]:
    """Group blocks into visual lines by VERTICAL OVERLAP.

    Grouping by y-centre is wrong for Devanagari. Matras and the anusvara
    extend well above the shirorekha, so boxes on one line differ sharply in
    height. Measured on a real sample:

        सिंह    y=[17, 76]   ycen=46.5
        राम     y=[35, 70]   ycen=52.5
        प्रसाद  y=[34, 71]   ycen=52.5

    A y-centre band puts सिंह on its own line and sorts it first, turning
    'राम प्रसाद सिंह' into 'सिंह राम प्रसाद'. Overlap is robust to that.
    """
    ordered = sorted(blocks, key=lambda b: b.bbox[1])
    lines: list[list[TextBlock]] = []

    for block in ordered:
        _, y1, _, y2 = block.bbox
        placed = False
        for line in lines:
            ly1 = min(b.bbox[1] for b in line)
            ly2 = max(b.bbox[3] for b in line)
            overlap = min(y2, ly2) - max(y1, ly1)
            shorter = min(y2 - y1, ly2 - ly1)
            if shorter > 0 and overlap / shorter > overlap_ratio:
                line.append(block)
                placed = True
                break
        if not placed:
            lines.append([block])

    for line in lines:
        line.sort(key=lambda b: b.bbox[0])
    lines.sort(key=lambda line: min(b.bbox[1] for b in line))
    return lines


def assign_reading_order(blocks: list[TextBlock]) -> list[TextBlock]:
    ordered: list[TextBlock] = []
    for line in group_lines(blocks):
        ordered.extend(line)
    for index, block in enumerate(ordered):
        block.reading_order = index
    return ordered


class OcrProvider(ABC):
    name = "abstract"

    @abstractmethod
    def recognize(self, image: np.ndarray) -> OcrResult:
        ...

    def available(self) -> bool:
        return True


class PaddleOcrProvider(OcrProvider):
    """PaddleOCR PP-OCRv5 (§6 primary).

    The language code is 'hi', NOT 'devanagari' -- the latter is the internal
    recognition-model name and raises ValueError if passed as `lang`.

    The engine is constructed lazily and cached on the instance: loading the
    models takes seconds, and a worker process handles many documents (§84).
    """

    name = "paddle"

    def __init__(self, lang: str = "hi", model_version: str = "ocr-v1") -> None:
        self.lang = lang
        self.model_version = model_version
        self._engine = None

    def _get_engine(self):
        if self._engine is None:
            try:
                from paddleocr import PaddleOCR
            except ImportError as exc:
                raise OcrUnavailable(f"paddleocr is not installed: {exc}") from exc
            try:
                self._engine = PaddleOCR(
                    lang=self.lang,
                    use_doc_orientation_classify=False,
                    use_doc_unwarping=False,
                    use_textline_orientation=False,
                )
            except Exception as exc:
                raise OcrUnavailable(f"could not initialise PaddleOCR: {exc}") from exc
        return self._engine

    def available(self) -> bool:
        try:
            self._get_engine()
            return True
        except OcrUnavailable:
            return False

    def recognize(self, image: np.ndarray) -> OcrResult:
        engine = self._get_engine()
        try:
            pages = engine.predict(image)
        except Exception as exc:
            raise OcrUnavailable(f"PaddleOCR failed: {exc}") from exc

        blocks: list[TextBlock] = []
        for page in pages:
            texts = page.get("rec_texts", [])
            scores = page.get("rec_scores", [])
            boxes = page.get("rec_boxes", [])
            for text, score, box in zip(texts, scores, boxes, strict=True):
                if not str(text).strip():
                    continue
                x1, y1, x2, y2 = (int(v) for v in box)
                blocks.append(
                    TextBlock(
                        text=str(text),
                        confidence=float(score),
                        bbox=(x1, y1, x2, y2),
                        script="devanagari" if self.lang == "hi" else self.lang,
                    )
                )

        return OcrResult(
            blocks=assign_reading_order(blocks),
            model_version=self.model_version,
            provider=self.name,
        )


class GeminiVisionOcrProvider(OcrProvider):
    """Registered fallback (§82).

    Deliberately NOT the primary: a land-records prototype whose core
    capability is a network call to a hosted model is a weaker system, and it
    fails when the demo venue's wifi does.

    Returns whole-line blocks without precise per-word geometry, so results are
    marked `degraded=True` and confidence is discounted -- the Verifier UI must
    not imply a bbox is authoritative when it is approximate.
    """

    name = "gemini"

    def __init__(self, api_key: str | None = None, model: str = "gemini-3.6-flash",
                 model_version: str = "ocr-v1-gemini") -> None:
        self.api_key = api_key
        self.model = model
        self.model_version = model_version

    def available(self) -> bool:
        return bool(self.api_key)

    def recognize(self, image: np.ndarray) -> OcrResult:
        if not self.api_key:
            raise OcrUnavailable("GEMINI_API_KEY is not configured")
        try:
            import cv2
            import httpx
        except ImportError as exc:
            raise OcrUnavailable(f"Gemini OCR dependency is not installed: {exc}") from exc

        ok, buffer = cv2.imencode(".png", image)
        if not ok:
            raise OcrUnavailable("could not encode image for the vision model")

        try:
            response = httpx.post(
                "https://generativelanguage.googleapis.com/v1beta/interactions",
                headers={"x-goog-api-key": self.api_key},
                json={
                    "model": self.model,
                    "input": [
                        {
                            "type": "image",
                            "mime_type": "image/png",
                            "data": base64.b64encode(buffer.tobytes()).decode("ascii"),
                        },
                        {
                            "type": "text",
                            "text": (
                                "Transcribe every line of visible text exactly as written, "
                                "preserving Devanagari digits and spelling. One line per "
                                "output line. Do not translate, explain or add commentary."
                            ),
                        },
                    ],
                },
                timeout=60,
            )
            response.raise_for_status()
            text = "\n".join(
                content["text"]
                for step in response.json().get("steps", [])
                if step.get("type") == "model_output"
                for content in step.get("content", [])
                if content.get("type") == "text" and content.get("text")
            ).strip()
        except Exception as exc:
            raise OcrUnavailable(f"Gemini vision call failed: {exc}") from exc

        if not text:
            raise OcrUnavailable("Gemini vision returned no text")

        height, width = image.shape[:2]
        lines = [line for line in text.splitlines() if line.strip()]
        step = height / max(len(lines), 1)
        blocks = [
            TextBlock(
                text=line.strip(),
                # Honest placeholder: this provider reports no per-line score,
                # so we record a fixed moderate value rather than inventing a
                # precise-looking one, and flag the result as degraded.
                confidence=0.55,
                bbox=(0, int(i * step), width, int((i + 1) * step)),
                script="devanagari",
            )
            for i, line in enumerate(lines)
        ]

        return OcrResult(
            blocks=assign_reading_order(blocks),
            model_version=self.model_version,
            provider=self.name,
            degraded=True,
        )


class OcrEngine:
    """Tries the primary provider, then the fallback chain (§82)."""

    def __init__(self, primary: OcrProvider, fallbacks: list[OcrProvider] | None = None):
        self.primary = primary
        self.fallbacks = fallbacks or []

    def recognize(self, image: np.ndarray) -> OcrResult:
        errors: list[str] = []
        for provider in (self.primary, *self.fallbacks):
            try:
                return provider.recognize(image)
            except OcrUnavailable as exc:
                errors.append(f"{provider.name}: {exc}")
                logger.warning("OCR provider %s unavailable: %s", provider.name, exc)

        # Never fabricate. The caller marks the page NEEDS_REVIEW.
        raise OcrUnavailable("all OCR providers failed -> " + "; ".join(errors))


def build_default_engine(
    provider: str = "paddle",
    lang: str = "hi",
    gemini_api_key: str | None = None,
    gemini_model: str = "gemini-3.6-flash",
) -> OcrEngine:
    paddle = PaddleOcrProvider(lang=lang)
    gemini = GeminiVisionOcrProvider(api_key=gemini_api_key, model=gemini_model)
    if provider == "gemini":
        return OcrEngine(primary=gemini, fallbacks=[paddle])
    return OcrEngine(primary=paddle, fallbacks=[gemini])
