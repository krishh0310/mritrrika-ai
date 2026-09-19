"""IndicTrans2 fallback: only when native labels find nothing, never a crash.

The page here is Bengali OCR text whose labels are NOT in the Bengali label set
(an unusual form), so native extraction finds nothing and the fallback is what
decides the outcome.
"""

import sys
from pathlib import Path

import cv2
import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "services" / "ai-worker"))

import extraction_pipeline  # noqa: E402
from ocr import indic_translator  # noqa: E402
from ocr.provider import OcrResult, TextBlock  # noqa: E402

BENGALI = [("ভূখণ্ড নম্বর", "৭৪/২"), ("গ্রামের নাম", "বগুলা")]
HINDI = {"ভূখণ্ড নম্বর": "खसरा सं", "৭৪/২": "७४/२", "গ্রামের নাম": "ग्राम", "বগুলা": "बगुला"}


class Engine:
    def recognize(self, image):
        blocks = []
        for i, (label, value) in enumerate(BENGALI):
            y = 100 + 60 * i
            blocks += [TextBlock(label, 0.9, (80, y, 300, y + 34)),
                       TextBlock(value, 0.9, (340, y, 520, y + 34))]
        return OcrResult(blocks=blocks, provider="fake")


def page() -> bytes:
    return cv2.imencode(".png", np.full((900, 1240, 3), 255, np.uint8))[1].tobytes()


def test_disabled_translation_leaves_the_pipeline_running(monkeypatch):
    monkeypatch.delenv("INDICTRANS2_ENABLED", raising=False)
    result = extraction_pipeline.run(page(), Engine())
    assert result.translated_from is None
    assert result.fields == []


def test_an_unavailable_model_is_a_warning_not_an_error(monkeypatch):
    monkeypatch.setenv("INDICTRANS2_ENABLED", "true")
    monkeypatch.setattr(indic_translator, "_load", lambda: 1 / 0)
    assert indic_translator.translate_to_hindi("বগুলা", "ben") == "বগুলা"


def test_translated_fields_are_marked_and_held_for_review(monkeypatch):
    monkeypatch.setattr(indic_translator, "translate_lines",
                        lambda lines, source: [HINDI[line] for line in lines])
    result = extraction_pipeline.run(page(), Engine())
    assert result.translated_from == "ben"
    by_field = {f.field: f for f in result.fields}
    assert by_field["KHASRA"].normalized_value == "74/2"
    assert all(f.status == "NEEDS_REVIEW" for f in result.fields)


def test_a_page_native_labels_can_read_is_never_translated(monkeypatch):
    calls = []
    monkeypatch.setattr(indic_translator, "translate_lines",
                        lambda lines, source: calls.append(source) or lines)

    class Native(Engine):
        def recognize(self, image):
            return OcrResult(blocks=[TextBlock("দাগ নং", 0.9, (80, 100, 300, 134)),
                                     TextBlock("৭৪/২", 0.9, (340, 100, 520, 134))])

    result = extraction_pipeline.run(page(), Native())
    assert result.translated_from is None and calls == []
