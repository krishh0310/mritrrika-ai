"""YOLO region detection over a record page (§6, §82).

Base model and checkpoint name live in config/cv_config.py.

The extractor is label-anchored: it finds a printed label and takes the nearest
plausible value in the direction the layout implies. That works until two
regions of the page put a plausible value in the same direction -- a KHASRA
label in the header and an owners table below it both offer a number to the
right. Knowing where the table starts is what separates them.

So this module answers one narrow question: *where are the structural regions
on this page*. It returns boxes and nothing else. It does not read text, does
not classify the document, and no caller may treat a region as evidence about
content (§34).

Fallback contract, the same one every other provider here honours (§82):

  * ultralytics not installed  -> `available` is False, `detect` returns []
  * weights not on disk        -> same
  * inference raises           -> same, logged once

In every one of those cases the pipeline runs exactly as it did before this
module existed. A detector that cannot run must cost accuracy, never
correctness -- it may not block a document and may not invent a region.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path

from config.cv_config import LAYOUT_CHECKPOINT

logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[3]

#: Where scripts/train_layout_detector.py leaves its best checkpoint.
DEFAULT_WEIGHTS = (
    REPO_ROOT / "models" / "checkpoints" / "layout" / LAYOUT_CHECKPOINT / "weights" / "best.pt"
)

#: Must match CLASSES in scripts/export_layout_dataset.py. A training run and
#: an inference run that disagree about which integer means "table" produce
#: confident nonsense rather than an error.
CLASSES = ["header", "table"]

#: Below this the box is not worth acting on. Deliberately high: a wrong region
#: silently redirects extraction, which is worse than having no region at all.
MIN_CONFIDENCE = 0.45


@dataclass(frozen=True)
class LayoutRegion:
    type: str
    bbox: tuple[int, int, int, int]
    confidence: float

    def contains(self, box: tuple[int, int, int, int], slack: int = 6) -> bool:
        """Whether `box` sits inside this region, allowing for rounding."""
        x1, y1, x2, y2 = box
        rx1, ry1, rx2, ry2 = self.bbox
        return (rx1 - slack <= x1 and ry1 - slack <= y1
                and x2 <= rx2 + slack and y2 <= ry2 + slack)

    def to_dict(self) -> dict:
        return {
            "type": self.type,
            "bbox": list(self.bbox),
            "confidence": round(self.confidence, 4),
        }


class LayoutDetector:
    """Loads the fine-tuned weights lazily and detects regions on one page."""

    def __init__(
        self,
        weights: Path | str | None = None,
        *,
        min_confidence: float = MIN_CONFIDENCE,
    ) -> None:
        self.weights = Path(weights) if weights else DEFAULT_WEIGHTS
        self.min_confidence = min_confidence
        self._model = None
        self._loaded = False
        self._reason: str | None = None

    @property
    def available(self) -> bool:
        self._ensure_loaded()
        return self._model is not None

    @property
    def unavailable_reason(self) -> str | None:
        self._ensure_loaded()
        return self._reason

    def _ensure_loaded(self) -> None:
        if self._loaded:
            return
        self._loaded = True

        if not self.weights.exists():
            self._reason = (
                f"no weights at {self.weights}; run "
                "scripts/train_layout_detector.py"
            )
            logger.info("layout: %s, extraction runs unscoped (§82)", self._reason)
            return

        try:
            from ultralytics import YOLO
        except ImportError:
            self._reason = "ultralytics is not installed"
            logger.info("layout: %s, extraction runs unscoped (§82)", self._reason)
            return

        try:
            self._model = YOLO(str(self.weights))
        except Exception as exc:  # pragma: no cover - depends on the checkpoint
            self._reason = f"weights failed to load: {exc}"
            logger.warning("layout: %s", self._reason)

    def detect(self, image) -> list[LayoutRegion]:
        """Regions on one page image (a numpy BGR array or a path).

        Never raises. An unavailable or failing detector returns [], which
        every caller must already handle as "no scoping information".
        """
        self._ensure_loaded()
        if self._model is None:
            return []

        try:
            results = self._model.predict(
                image,
                conf=self.min_confidence,
                verbose=False,
            )
        except Exception as exc:  # pragma: no cover - runtime/device dependent
            logger.warning("layout: inference failed (%s), continuing unscoped", exc)
            return []

        regions: list[LayoutRegion] = []
        for result in results:
            boxes = getattr(result, "boxes", None)
            if boxes is None:
                continue
            names = getattr(result, "names", None) or dict(enumerate(CLASSES))
            for box in boxes:
                cls = int(box.cls.item())
                confidence = float(box.conf.item())
                x1, y1, x2, y2 = (float(v) for v in box.xyxy[0].tolist())
                regions.append(
                    LayoutRegion(
                        type=str(names.get(cls, CLASSES[cls] if cls < len(CLASSES) else cls)),
                        bbox=(round(x1), round(y1), round(x2), round(y2)),
                        confidence=confidence,
                    )
                )

        regions.sort(key=lambda r: r.confidence, reverse=True)
        return regions


def build_default_detector() -> LayoutDetector:
    """The detector the pipeline uses, honouring MRITTIKA_LAYOUT_WEIGHTS."""
    return LayoutDetector(os.environ.get("MRITTIKA_LAYOUT_WEIGHTS") or None)


__all__ = [
    "CLASSES", "DEFAULT_WEIGHTS", "MIN_CONFIDENCE",
    "LayoutDetector", "LayoutRegion", "build_default_detector",
]
