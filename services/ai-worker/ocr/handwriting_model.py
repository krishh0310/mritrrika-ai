"""Trained handwriting models: a line classifier and a Devanagari reader (§6).

Two small networks, trained by scripts/train_handwriting.py:

  * detector -- is this OCR line crop handwritten? Replaces the geometry
    heuristic in handwriting.py when its weights exist.
  * reader   -- CRNN + CTC. Reads a handwritten Devanagari line crop that
    PaddleOCR (trained on print) mostly misreads.

Trained on IIIT-HW-Dev (CVIT, IIIT Hyderabad): handwritten Hindi WORDS, not
land records. The reader has therefore learned general handwritten Hindi; how
well that carries to a Patwari's khasra entries is measured only by
scripts/evaluate_handwriting_real.py on real scans. Everything it reads goes
to a verifier.

Fallback contract, as for the layout detector (§82): torch missing, weights
missing or inference failing -> the loader returns None, and the pipeline
runs exactly as it did before these models existed.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

import cv2
import numpy as np

logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[3]
CHECKPOINTS = REPO_ROOT / "models" / "checkpoints" / "handwriting"
READER_WEIGHTS = CHECKPOINTS / "reader" / "best.pt"
DETECTOR_WEIGHTS = CHECKPOINTS / "detector" / "best.pt"

HEIGHT = 64
#: The detector sees a fixed-size crop: long lines are resized, not tiled.
DETECTOR_WIDTH = 256
MAX_WIDTH = 1600


def to_input(crop: np.ndarray, height: int = HEIGHT, width: int | None = None) -> np.ndarray:
    """Grayscale, ink = 1.0, scaled to `height` (and `width` if given)."""
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY) if crop.ndim == 3 else crop
    h, w = gray.shape[:2]
    if width is None:
        width = int(np.clip(round(w * height / max(h, 1)), 8, MAX_WIDTH))
    resized = cv2.resize(gray, (width, height), interpolation=cv2.INTER_AREA)
    return 1.0 - resized.astype(np.float32) / 255.0


def _torch():
    import torch
    from torch import nn

    return torch, nn


def build_reader(num_classes: int):
    """CRNN: a VGG-style CNN collapses height, a BiLSTM reads left to right.

    Output: (width / 4, batch, num_classes) log-probabilities; class 0 is the
    CTC blank.
    """
    torch, nn = _torch()

    def block(cin, cout, pool):
        return [nn.Conv2d(cin, cout, 3, padding=1), nn.BatchNorm2d(cout), nn.ReLU(True),
                nn.MaxPool2d(pool)]

    class CRNN(nn.Module):
        def __init__(self):
            super().__init__()
            # Narrow early layers: they run at full resolution and were most
            # of the step time, for little accuracy (measured 0.21 s -> 0.14 s).
            self.cnn = nn.Sequential(
                *block(1, 32, (2, 2)),        # 32 x W/2
                *block(32, 96, (2, 2)),       # 16 x W/4
                *block(96, 192, (2, 1)),      # 8
                *block(192, 256, (2, 1)),     # 4
                *block(256, 384, (4, 1)),     # 1
                nn.Dropout(0.2),
            )
            self.rnn = nn.LSTM(384, 256, num_layers=2, bidirectional=True,
                               dropout=0.2, batch_first=False)
            self.head = nn.Linear(512, num_classes)

        def forward(self, x):
            features = self.cnn(x).squeeze(2).permute(2, 0, 1)   # T, B, C
            out, _ = self.rnn(features)
            return self.head(out).log_softmax(-1)

    return CRNN()


def build_detector():
    """A small CNN: handwritten (1) vs printed (0) on a 64x256 crop."""
    _, nn = _torch()

    def block(cin, cout):
        return [nn.Conv2d(cin, cout, 3, padding=1), nn.BatchNorm2d(cout), nn.ReLU(True),
                nn.MaxPool2d(2)]

    return nn.Sequential(
        *block(1, 32), *block(32, 64), *block(64, 128), *block(128, 128),
        nn.AdaptiveAvgPool2d(1), nn.Flatten(), nn.Dropout(0.3), nn.Linear(128, 1),
    )


def ctc_decode(log_probs: np.ndarray, charset: str) -> tuple[str, float]:
    """Greedy CTC decode of (T, C) log-probabilities -> text and confidence.

    Confidence is the mean probability of the emitted characters: a number the
    verifier can compare between lines, not a calibrated accuracy.
    """
    best = log_probs.argmax(-1)
    chars, probs, previous = [], [], 0
    for t, index in enumerate(best):
        if index != 0 and index != previous:
            chars.append(charset[index - 1])
            probs.append(float(np.exp(log_probs[t, index])))
        previous = index
    return "".join(chars), (float(np.mean(probs)) if probs else 0.0)


class HandwritingReader:
    def __init__(self, model, charset: str, version: str, device: str = "cpu"):
        self.model, self.charset, self.version, self.device = model, charset, version, device

    @classmethod
    def load(cls, path: Path = READER_WEIGHTS) -> HandwritingReader:
        torch, _ = _torch()
        state = torch.load(path, map_location="cpu", weights_only=False)
        model = build_reader(len(state["charset"]) + 1)
        model.load_state_dict(state["model"])
        return cls(model.eval(), state["charset"], state.get("version", "handwriting-reader"))

    def read(self, crop: np.ndarray) -> tuple[str, float]:
        torch, _ = _torch()
        x = torch.from_numpy(to_input(crop))[None, None]
        with torch.no_grad():
            log_probs = self.model(x)[:, 0].numpy()
        return ctc_decode(log_probs, self.charset)


class HandwritingDetector:
    #: Used only by checkpoints that predate a calibrated threshold.
    THRESHOLD = 0.8

    def __init__(self, model, version: str, threshold: float = THRESHOLD):
        self.model, self.version, self.threshold = model, version, threshold

    @classmethod
    def load(cls, path: Path = DETECTOR_WEIGHTS) -> HandwritingDetector:
        """The threshold travels with the weights: training calibrates it on
        validation so that at most 0.5% of printed lines are flagged."""
        torch, _ = _torch()
        state = torch.load(path, map_location="cpu", weights_only=False)
        model = build_detector()
        model.load_state_dict(state["model"])
        return cls(model.eval(), state.get("version", "handwriting-detector"),
                   state.get("threshold", cls.THRESHOLD))

    def probability(self, crop: np.ndarray) -> float:
        torch, _ = _torch()
        x = torch.from_numpy(to_input(crop, width=DETECTOR_WIDTH))[None, None]
        with torch.no_grad():
            return float(torch.sigmoid(self.model(x))[0, 0])

    def is_handwritten(self, crop: np.ndarray) -> bool:
        return self.probability(crop) >= self.threshold


class GeminiHandwritingReader:
    """Gemini vision reading one handwritten line: the opt-in second opinion.

    Untrained here and unmeasured on land records, and it sends the line crop
    to Google -- so it is off unless GEMINI_HANDWRITING_ENABLED=true, and what
    it reads is only ever compared with, or standing in for, the local reader;
    every field stays with a verifier either way.
    """

    #: The provider reports no per-line score (see GeminiVisionOcrProvider).
    CONFIDENCE = 0.55

    def __init__(self, api_key: str, model: str):
        from .provider import GeminiVisionOcrProvider

        self.provider = GeminiVisionOcrProvider(api_key=api_key, model=model)
        self.version = f"gemini-handwriting-{model}"

    def read(self, crop: np.ndarray) -> tuple[str, float]:
        """The line's text, or "" when the call fails (never raises)."""
        from .provider import OcrUnavailable

        try:
            text = " ".join(b.text for b in self.provider.recognize(crop).blocks)
        except OcrUnavailable as exc:
            logger.warning("Gemini handwriting read failed: %s", exc)
            return "", 0.0
        return text.strip(), self.CONFIDENCE


def _load(kind, path: Path):
    if os.environ.get("HANDWRITING_MODELS_ENABLED", "true").strip().lower() in {"0", "false", "no"}:
        return None
    if not path.exists():
        return None
    try:
        return kind.load(path)
    except Exception as exc:  # a model that cannot load costs accuracy, never a page
        logger.warning("handwriting model %s unavailable: %s", path, exc)
        return None


def load_reader() -> HandwritingReader | None:
    return _load(HandwritingReader, READER_WEIGHTS)


def load_detector() -> HandwritingDetector | None:
    return _load(HandwritingDetector, DETECTOR_WEIGHTS)


__all__ = ["GeminiHandwritingReader", "HandwritingDetector", "HandwritingReader",
           "build_detector", "build_reader",
           "ctc_decode", "load_detector", "load_reader", "to_input"]
