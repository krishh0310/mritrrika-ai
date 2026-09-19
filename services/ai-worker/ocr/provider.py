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
import ctypes
import logging
import signal
from abc import ABC, abstractmethod
from collections.abc import Sequence
from contextlib import contextmanager
from dataclasses import dataclass, field

import numpy as np

from .scripts import SCRIPT_TO_LANG, detect_script

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


@contextmanager
def _keeping_sigterm():
    """Put the process's SIGTERM handler back after Paddle loads.

    Importing paddle installs glog's failure handler for SIGTERM, replacing the
    one uvicorn and celery rely on to shut down. A plain stop then hangs in
    that handler and ends in a segfault (a macOS "Python quit unexpectedly"
    report). Saved and restored with sigaction itself, not signal.signal, so it
    works from the threadpool the API runs OCR in; the handler is process-wide.
    """
    libc = ctypes.CDLL(None)
    saved = ctypes.create_string_buffer(256)  # >= sizeof(struct sigaction)
    kept = libc.sigaction(signal.SIGTERM, None, saved) == 0
    try:
        yield
    finally:
        if kept:
            libc.sigaction(signal.SIGTERM, saved, None)


class PaddleOcrProvider(OcrProvider):
    """PaddleOCR PP-OCRv5 (§6 primary).

    The language code is 'hi', NOT 'devanagari' -- the latter is the internal
    recognition-model name and raises ValueError if passed as `lang`.

    The engine is constructed lazily and cached on the instance: loading the
    models takes seconds, and a worker process handles many documents (§84).
    """

    name = "paddle"

    def __init__(
        self,
        lang: str = "hi",
        model_version: str = "ocr-v1",
        detection_model: str | None = None,
    ) -> None:
        self.lang = lang
        self.model_version = model_version
        #: None keeps PaddleOCR's default text detector. See DETECTION_MODEL.
        self.detection_model = detection_model
        self._engine = None

    def _get_engine(self):
        if self._engine is None:
            with _keeping_sigterm():  # both import and construction replace it
                self._load_engine()
        return self._engine

    def _load_engine(self) -> None:
        try:
            from paddleocr import PaddleOCR
        except ImportError as exc:
            raise OcrUnavailable(f"paddleocr is not installed: {exc}") from exc
        try:
            options = dict(
                lang=self.lang,
                use_doc_orientation_classify=False,
                use_doc_unwarping=False,
                use_textline_orientation=False,
            )
            if self.detection_model:
                # Naming ANY model makes PaddleOCR ignore `lang` -- it says
                # so only in a warning -- and fall back to a recogniser that
                # cannot read Devanagari. Every field then scores zero. So a
                # named detector always travels with the language's
                # recogniser, named explicitly.
                recogniser = RECOGNITION_MODELS.get(self.lang)
                if recogniser is None:
                    raise OcrUnavailable(
                        f"no recognition model mapped for lang {self.lang!r}; "
                        "add it to RECOGNITION_MODELS before naming a detector"
                    )
                options["text_detection_model_name"] = self.detection_model
                options["text_recognition_model_name"] = recogniser
            self._engine = PaddleOCR(**options)
        except Exception as exc:
            raise OcrUnavailable(f"could not initialise PaddleOCR: {exc}") from exc

    def available(self) -> bool:
        try:
            self._get_engine()
            return True
        except OcrUnavailable:
            return False

    def recognize(self, image: np.ndarray) -> OcrResult:
        engine = self._get_engine()
        try:
            pages = list(engine.predict(image))
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
                        script=_script_for_lang(self.lang),
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
                                "in the script it is written in (Devanagari, Telugu, Tamil, "
                                "Kannada or any other), preserving the native digits and "
                                "spelling. One line per output line. Do not translate, "
                                "transliterate, explain or add commentary."
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
                # Measured from the text returned, not assumed: this provider
                # reads whatever script the page is in.
                script=detect_script(line),
            )
            for i, line in enumerate(lines)
        ]

        return OcrResult(
            blocks=assign_reading_order(blocks),
            model_version=self.model_version,
            provider=self.name,
            degraded=True,
        )


def _script_for_lang(lang: str) -> str:
    """The script name a recogniser language reads, for the block's `script`."""
    for script, code in SCRIPT_TO_LANG.items():
        if code == lang:
            return script
    return lang


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


#: The recogniser PaddleOCR selects for each `lang`, stated explicitly because
#: naming a detector disables PaddleOCR's own lang-based selection.
#:
#: One entry per SCRIPT, not per language: PP-OCRv5 maps every Devanagari
#: language -- hi, mr, ne, sa, mai, bho and the rest -- onto a single
#: `devanagari` recogniser, because the distinction between them is linguistic
#: and the recogniser only sees shapes. Telugu, Tamil and Kannada each have
#: their own; Urdu shares the Arabic recogniser.
RECOGNITION_MODELS = {
    "hi": "devanagari_PP-OCRv5_mobile_rec",
    "te": "te_PP-OCRv5_mobile_rec",
    "ta": "ta_PP-OCRv5_mobile_rec",
    "ka": "ka_PP-OCRv5_mobile_rec",
    "en": "en_PP-OCRv5_mobile_rec",
    "ur": "arabic_PP-OCRv5_mobile_rec",
}

#: Languages this pipeline will construct an engine for. Anything else is
#: refused at construction rather than quietly handed to the Devanagari
#: recogniser, which would return fluent nonsense at plausible confidence.
SUPPORTED_LANGS = frozenset(RECOGNITION_MODELS)

#: Text detector. None keeps PaddleOCR's default, PP-OCRv5_server_det.
#:
#: Measured on this pipeline's pages (val split, 40 documents):
#:
#:   detector              peak memory / process       speed   extraction F1
#:   PP-OCRv5_server_det   11 GB first page -> 19 GB   1x      0.68
#:   PP-OCRv5_mobile_det   1.8 GB                      ~3x     0.57
#:
#: Disabling MKLDNN or capping the detector's input size did not reduce the
#: server detector's memory. Accuracy wins the default; the worker contains
#: the memory instead (one process, recycled after heavy tasks). Set
#: OCR_DETECTION_MODEL=PP-OCRv5_mobile_det on a machine that cannot afford it.
DETECTION_MODEL: str | None = None


@dataclass
class RoutingDecision:
    """Which language was chosen for a page, and what it beat."""

    lang: str
    script: str | None
    score: float
    result: OcrResult
    considered: dict           # lang -> score, for the audit trail

    def to_dict(self) -> dict:
        return {
            "lang": self.lang,
            "script": self.script,
            "score": round(self.score, 4),
            "considered": {k: round(v, 4) for k, v in self.considered.items()},
        }


def _routing_score(result: OcrResult, expected_script: str) -> float:
    """How well a recogniser's output looks like the script it was asked for.

    Mean confidence alone is not enough. A Devanagari recogniser handed a
    Telugu page returns Latin-ish rubbish -- '008 28s' -- at a confidence that
    is low but not zero, and a page with little text can push that above a
    correct reading. So confidence is multiplied by the fraction of recognised
    characters that actually belong to the expected script, which for a wrong
    recogniser is close to zero regardless of how sure it claims to be.
    """
    from .scripts import profile

    if not result.blocks:
        return 0.0
    seen = profile(result.text)
    return result.mean_confidence() * seen.fraction(expected_script)


def route(
    image: np.ndarray,
    candidates: Sequence[str] = ("hi", "te", "ta", "ka"),
    *,
    detection_model: str | None = None,
    providers: dict[str, PaddleOcrProvider] | None = None,
) -> RoutingDecision:
    """Identify a page's script by recognising it with each candidate (§6).

    There is no script-identification model here, and this is deliberate: the
    script of an IMAGE cannot be read off Unicode blocks, and adding a
    classifier would add a second thing that can be wrong. Recognising with
    each candidate and comparing is slower but has no failure mode of its own
    -- the answer is judged on the output it actually produced.

    It is correspondingly expensive: one pass per candidate, and one engine
    load per candidate unless `providers` carries engines already loaded --
    which a long-lived caller should pass, so each model loads once per
    process rather than once per page. Callers that know the language should
    say so and skip this entirely; this is for the page that arrives without
    provenance.
    """
    from .scripts import SCRIPT_TO_LANG, UnsupportedScript, profile

    lang_to_script = {v: k for k, v in SCRIPT_TO_LANG.items()}
    usable = [c for c in candidates if c in RECOGNITION_MODELS]
    if not usable:
        raise UnsupportedScript(f"no supported language among {list(candidates)}")

    best: RoutingDecision | None = None
    considered: dict[str, float] = {}

    for lang in usable:
        if providers is not None:
            provider = providers.setdefault(
                lang, PaddleOcrProvider(lang=lang, detection_model=detection_model)
            )
        else:
            provider = PaddleOcrProvider(lang=lang, detection_model=detection_model)
        try:
            result = provider.recognize(image)
        except OcrUnavailable as exc:
            logger.info("routing: %s unavailable (%s)", lang, exc)
            considered[lang] = 0.0
            continue

        score = _routing_score(result, lang_to_script.get(lang, ""))
        considered[lang] = score
        if best is None or score > best.score:
            best = RoutingDecision(
                lang=lang,
                script=profile(result.text).dominant,
                score=score,
                result=result,
                considered=considered,
            )

    if best is None:
        raise OcrUnavailable("no candidate recogniser could run")

    best.considered.update(considered)
    logger.info("routing: chose %s (%s)", best.lang, considered)
    return best


class RoutedPaddleProvider(OcrProvider):
    """PaddleOCR with the recogniser chosen per page (§6).

    Used when the deployment receives pages in more than one script and the
    upload does not say which. Each page is read by every candidate recogniser
    and the one whose output is most confidently IN its own script wins (see
    `route`). Engines are cached on the instance, so each loads once.

    Several times slower than a fixed language -- one pass per candidate -- so
    a single-state deployment should name its language instead.
    """

    name = "paddle-routed"

    def __init__(
        self,
        candidates: Sequence[str] = ("hi", "te", "ta", "ka"),
        model_version: str = "ocr-v1",
        detection_model: str | None = None,
    ) -> None:
        self.candidates = tuple(candidates)
        self.model_version = model_version
        self.detection_model = detection_model
        self._providers: dict[str, PaddleOcrProvider] = {}
        #: The last page's routing decision, for the caller's audit trail.
        self.last_decision: RoutingDecision | None = None

    def recognize(self, image: np.ndarray) -> OcrResult:
        from .scripts import UnsupportedScript

        try:
            decision = route(
                image, self.candidates,
                detection_model=self.detection_model, providers=self._providers,
            )
        except UnsupportedScript as exc:
            raise OcrUnavailable(str(exc)) from exc
        self.last_decision = decision
        result = decision.result
        result.model_version = self.model_version
        result.provider = f"paddle:{decision.lang}"
        return result


#: `OCR_LANG=auto` routes each page across these recognisers.
AUTO_LANG = "auto"


def build_default_engine(
    provider: str = "paddle",
    lang: str = "hi",
    gemini_api_key: str | None = None,
    gemini_model: str = "gemini-3.6-flash",
    detection_model: str | None = DETECTION_MODEL,
) -> OcrEngine:
    paddle: OcrProvider = (
        RoutedPaddleProvider(detection_model=detection_model)
        if lang == AUTO_LANG
        else PaddleOcrProvider(lang=lang, detection_model=detection_model)
    )
    gemini = GeminiVisionOcrProvider(api_key=gemini_api_key, model=gemini_model)
    if provider == "gemini":
        # A Paddle native crash is a process-level SIGSEGV and cannot be
        # caught as OcrUnavailable, so it must never be an automatic fallback.
        return OcrEngine(primary=gemini)
    # Paddle first: it runs offline, needs no API key, and is what the measured
    # accuracy figures describe. Gemini backs it up for pages Paddle refuses --
    # a caught OcrUnavailable, which is safe to fall through.
    return OcrEngine(primary=paddle, fallbacks=[gemini])
