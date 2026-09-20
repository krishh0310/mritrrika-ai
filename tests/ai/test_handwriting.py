"""Synthetic geometry and pipeline contracts, not handwriting accuracy claims."""

import sys
from pathlib import Path

import cv2
import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "services" / "ai-worker"))
sys.path.insert(0, str(ROOT / "packages" / "domain"))

from ocr.handwriting import flag_blocks, is_handwritten
from ocr.provider import (
    OcrEngine,
    OcrResult,
    OcrUnavailable,
    PaddleOcrProvider,
    TextBlock,
    build_default_engine,
)


def line(jitter=False):
    image = np.full((100, 500, 3), 255, np.uint8)
    for i in range(12):
        bottom = 65 + ((i % 3 - 1) * 12 if jitter else 0)
        cv2.putText(image, str(i % 10), (10 + i * 38, bottom),
                    cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 0), 2)
    return image


def test_synthetic_irregular_baseline_and_printed_control():
    assert is_handwritten(line(True))
    assert not is_handwritten(line())
    assert not is_handwritten(np.full((40, 100), 255, np.uint8))
    assert not is_handwritten(np.empty((0, 0), np.uint8))


def test_flagging_clips_boxes_and_preserves_provider_flag():
    blocks = [TextBlock("synthetic", .95, (-5, -5, 505, 105)),
              TextBlock("outside", .95, (-30, -30, -5, -5)),
              TextBlock("provider", .95, (600, 600, 650, 650), is_handwritten=True)]
    flag_blocks(line(True), blocks)
    assert [b.is_handwritten for b in blocks] == [True, False, True]


def test_pipeline_requires_review_for_suspected_handwriting(monkeypatch):
    import extraction_pipeline as pipeline
    from preprocessing.enhance import EnhancementResult

    page = line(True)
    monkeypatch.setattr(pipeline, "enhance_for_quality",
                        lambda image, quality: EnhancementResult(image))
    class Engine:
        def recognize(self, image):
            return OcrResult(blocks=[
                TextBlock("खसरा संख्या", .99, (0, 0, 120, 100)),
                TextBlock("१४२", .99, (125, 0, 500, 100), is_handwritten=True),
            ], provider="paddle")

    result = pipeline.run(cv2.imencode(".png", page)[1].tobytes(), Engine())
    assert result.fields
    assert all(f.status == "NEEDS_REVIEW" for f in result.fields)
    assert any(f.rule == "SUSPECTED_HANDWRITING" for f in result.findings)
    assert any(b.is_handwritten for b in result.ocr.blocks)


def test_lazy_paddle_failure_uses_fallback():
    class Broken:
        def predict(self, image):
            yield {}
            raise RuntimeError("synthetic inference failure")

    primary = PaddleOcrProvider()
    primary._engine = Broken()
    with pytest.raises(OcrUnavailable):
        primary.recognize(line())

    class Fallback:
        name = "test"
        def recognize(self, image):
            return OcrResult(provider=self.name)

    assert OcrEngine(primary, [Fallback()]).recognize(line()).provider == "test"


def test_configured_ocr_version_reaches_predictions():
    engine = build_default_engine(model_version="ocr-release-7")
    assert engine.primary.model_version == "ocr-release-7"
    hosted = build_default_engine(provider="gemini", model_version="ocr-release-7")
    assert hosted.primary.model_version == "ocr-release-7-gemini"


def test_deskew_and_scaling_are_undone_for_field_and_ocr_boxes(monkeypatch):
    import extraction_pipeline as pipeline
    from preprocessing.enhance import EnhancementResult

    page = np.full((200, 200, 3), 255, np.uint8)
    prepared = np.full((400, 400, 3), 255, np.uint8)
    monkeypatch.setattr(pipeline, "enhance_for_quality",
                        lambda image, quality: EnhancementResult(
                            prepared, skew_corrected=90.0))
    class Engine:
        def recognize(self, image):
            return OcrResult(blocks=[
                TextBlock("खसरा संख्या", .99, (10, 40, 90, 80)),
                TextBlock("१४२", .99, (100, 40, 160, 80)),
            ], provider="paddle")

    result = pipeline.run(cv2.imencode(".png", page)[1].tobytes(), Engine())
    # Original -> prepared is (-2*y + 400, 2*x), so inverse is
    # (prepared_y/2, 200 - prepared_x/2).
    expected = (20, 120, 40, 150)
    assert result.original_bbox((100, 40, 160, 80)) == expected
    assert next(f for f in result.fields if f.field == "KHASRA").bbox == expected
