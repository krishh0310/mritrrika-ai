"""The trained handwriting path: contracts, not accuracy.

Accuracy lives in the training report (IIIT-HW-Dev test split) and in
scripts/evaluate_handwriting_real.py (real scans). These tests pin what must
hold whatever the weights: shapes, decoding, the detector-over-heuristic
switch, the reader replacing text only on flagged lines, and graceful absence.
"""

import sys
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "services" / "ai-worker"))
sys.path.insert(0, str(ROOT / "packages" / "domain"))

from ocr import handwriting_model  # noqa: E402
from ocr.handwriting import flag_blocks, read_blocks, routing_meta  # noqa: E402
from ocr.provider import OcrResult, TextBlock  # noqa: E402


class FakeDetector:
    version = "fake-detector"

    def __init__(self, answer):
        self.answer = answer

    def is_handwritten(self, crop):
        return self.answer


class FakeReader:
    version = "handwriting-reader-test"

    def __init__(self, text="१४२", confidence=0.61):
        self.text, self.confidence = text, confidence

    def read(self, crop):
        return self.text, self.confidence


def test_ctc_decode_collapses_repeats_and_drops_blanks():
    charset = "कख"
    steps = [1, 1, 0, 1, 2, 2, 0]          # क क _ क ख ख _  ->  ककख
    log_probs = np.log(np.full((len(steps), 3), 0.05))
    for t, index in enumerate(steps):
        log_probs[t, index] = np.log(0.9)
    text, confidence = handwriting_model.ctc_decode(log_probs, charset)
    assert text == "ककख"
    assert abs(confidence - 0.9) < 1e-6
    assert handwriting_model.ctc_decode(np.log(np.full((3, 3), 1 / 3)) * 0, charset)[0] == ""


def test_networks_accept_line_crops_of_any_width():
    import torch

    reader = handwriting_model.build_reader(num_classes=10).eval()
    x = torch.from_numpy(handwriting_model.to_input(np.full((40, 300, 3), 255, np.uint8)))
    assert reader(x[None, None]).shape[1:] == (1, 10)
    assert reader(x[None, None]).shape[0] == x.shape[1] // 4

    detector = handwriting_model.build_detector().eval()
    crop = handwriting_model.to_input(np.zeros((30, 900), np.uint8),
                                      width=handwriting_model.DETECTOR_WIDTH)
    assert detector(torch.from_numpy(crop)[None, None]).shape == (1, 1)


def test_trained_detector_replaces_the_heuristic():
    page = np.full((100, 500, 3), 255, np.uint8)       # blank: the heuristic says no
    blocks = [TextBlock("x", .9, (0, 0, 500, 100))]
    flag_blocks(page, blocks, FakeDetector(True))
    assert blocks[0].is_handwritten
    blocks = [TextBlock("x", .9, (0, 0, 500, 100), is_handwritten=True)]
    flag_blocks(page, blocks, FakeDetector(False))
    assert blocks[0].is_handwritten                     # a provider's flag is kept


def test_reader_replaces_only_flagged_lines():
    page = np.full((100, 500, 3), 255, np.uint8)
    printed = TextBlock("खसरा संख्या", .99, (0, 0, 120, 100))
    written = TextBlock("l42", .97, (125, 0, 500, 100), is_handwritten=True)
    assert read_blocks(page, [printed, written], FakeReader()) == {"read": 1,
                                                                   "second_opinion": None}
    assert (printed.text, printed.confidence) == ("खसरा संख्या", .99)
    assert (written.text, written.confidence) == ("१४२", 0.61)


def test_pipeline_reads_handwriting_and_still_requires_review(monkeypatch):
    import extraction_pipeline as pipeline
    from preprocessing.enhance import EnhancementResult

    page = np.full((100, 500, 3), 255, np.uint8)
    monkeypatch.setattr(pipeline, "enhance_for_quality",
                        lambda image, quality: EnhancementResult(image))

    class Engine:
        def recognize(self, image):
            return OcrResult(blocks=[
                TextBlock("खसरा संख्या", .99, (0, 0, 120, 100)),
                TextBlock("l42", .97, (125, 0, 500, 100), is_handwritten=True),
            ], provider="paddle")

    result = pipeline.run(cv2.imencode(".png", page)[1].tobytes(), Engine(),
                          handwriting_reader=FakeReader())
    khasra = next(f for f in result.fields if f.field == "KHASRA")
    assert khasra.raw_value == "१४२"
    assert khasra.status == "NEEDS_REVIEW"
    assert result.handwriting_read_by == "handwriting-reader-test"
    finding = next(f for f in result.findings if f.rule == "SUSPECTED_HANDWRITING")
    assert "handwriting-reader-test" in finding.message


def test_routing_meta_names_the_reader():
    blocks = [((0, 0, 10, 10), True), ((20, 0, 30, 10), False)]
    assert routing_meta(blocks, [], None)["read_by"] is None
    assert routing_meta(blocks, [], None, "handwriting-reader-v1")["read_by"] == \
        "handwriting-reader-v1"


def test_missing_or_disabled_weights_mean_no_model(monkeypatch, tmp_path):
    missing = tmp_path / "best.pt"
    assert handwriting_model._load(handwriting_model.HandwritingReader, missing) is None
    missing.write_bytes(b"not a checkpoint")
    assert handwriting_model._load(handwriting_model.HandwritingReader, missing) is None
    monkeypatch.setenv("HANDWRITING_MODELS_ENABLED", "false")
    assert handwriting_model.load_reader() is None
    assert handwriting_model.load_detector() is None


def test_second_opinion_agreement_and_disagreement_adjust_confidence():
    page = np.full((100, 500, 3), 255, np.uint8)

    def lines():
        return [TextBlock("a", .9, (0, 0, 250, 50), is_handwritten=True),
                TextBlock("b", .9, (0, 50, 250, 100), is_handwritten=True)]

    agreeing = lines()
    outcome = read_blocks(page, agreeing, FakeReader(), FakeReader("१४२ ", 0.55))
    assert outcome["second_opinion"]["agreed"] == 2       # whitespace-insensitive
    assert all(b.confidence == 0.8 for b in agreeing)

    differing = lines()
    gemini = FakeReader("१४३", 0.55)
    gemini.version = "gemini-handwriting-test"
    outcome = read_blocks(page, differing, FakeReader(), gemini)
    opinion = outcome["second_opinion"]
    assert (opinion["model"], opinion["agreed"], opinion["disagreed"]) == \
        ("gemini-handwriting-test", 0, 2)
    assert opinion["disagreements"][0] == {"read": "१४२", "second": "१४३"}
    assert all(b.text == "१४२" and b.confidence == 0.4 for b in differing)  # first reader stands

    silent = lines()
    outcome = read_blocks(page, silent, FakeReader(), FakeReader(""))  # Gemini call failed
    assert outcome["second_opinion"]["agreed"] == outcome["second_opinion"]["disagreed"] == 0
    assert all(b.confidence == 0.61 for b in silent)


def test_gemini_reads_alone_when_there_is_no_local_reader(monkeypatch):
    import extraction_pipeline as pipeline
    from preprocessing.enhance import EnhancementResult

    monkeypatch.setattr(pipeline, "enhance_for_quality",
                        lambda image, quality: EnhancementResult(image))

    class Engine:
        def recognize(self, image):
            return OcrResult(blocks=[
                TextBlock("खसरा संख्या", .99, (0, 0, 120, 100)),
                TextBlock("l42", .97, (125, 0, 500, 100), is_handwritten=True),
            ], provider="paddle")

    gemini = FakeReader()
    gemini.version = "gemini-handwriting-test"
    page = np.full((100, 500, 3), 255, np.uint8)
    result = pipeline.run(cv2.imencode(".png", page)[1].tobytes(), Engine(),
                          handwriting_second_reader=gemini)
    assert result.handwriting_read_by == "gemini-handwriting-test"
    assert result.handwriting_second_opinion is None        # nothing to compare with


def test_gemini_reader_never_raises(monkeypatch):
    from ocr.provider import GeminiVisionOcrProvider, OcrUnavailable

    def fail(self, image):
        raise OcrUnavailable("network down")

    monkeypatch.setattr(GeminiVisionOcrProvider, "recognize", fail)
    reader = handwriting_model.GeminiHandwritingReader("key", "gemini-test")
    assert reader.read(np.full((40, 200, 3), 255, np.uint8)) == ("", 0.0)
    assert reader.version == "gemini-handwriting-gemini-test"
