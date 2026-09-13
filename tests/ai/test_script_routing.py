"""Multilingual OCR and script-based routing (§6, §82).

A land record is not always Devanagari. The same Khasra is Telugu in
Telangana, Tamil in Tamil Nadu, Kannada in Karnataka. The failure this guards
against is not a crash: a Devanagari recogniser handed a Telugu page returns
fluent-looking rubbish at a confidence that is low but not zero, and every
downstream stage treats it as a reading.

Two properties are pinned. A script the engine cannot read must be REFUSED by
name rather than handed to whichever recogniser is loaded. And routing must
pick the right recogniser from the image alone, judged on the output it
actually produced rather than on a guess made beforehand.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "services" / "ai-worker"))

from ocr.provider import (  # noqa: E402
    RECOGNITION_MODELS,
    SUPPORTED_LANGS,
    OcrResult,
    TextBlock,
    _routing_score,
)
from ocr.scripts import (  # noqa: E402
    SCRIPT_TO_LANG,
    UNSUPPORTED_SCRIPTS,
    UnsupportedScript,
    detect_script,
    language_for_script,
    profile,
)

FONTS = {
    "telugu": "/System/Library/Fonts/Supplemental/Telugu MN.ttc",
    "tamil": "/System/Library/Fonts/Supplemental/Tamil MN.ttc",
    "kannada": "/System/Library/Fonts/Supplemental/Kannada MN.ttc",
    "devanagari": "/System/Library/Fonts/Supplemental/Devanagari Sangam MN.ttc",
}

SAMPLES = {
    "devanagari": "ग्राम रामपुर खसरा १४२",
    "telugu": "తెలంగాణ భూమి రికార్డు",
    "tamil": "நிலம் பதிவு ஆவணம்",
    "kannada": "ಭೂಮಿ ದಾಖಲೆ ಗ್ರಾಮ",
}


def render(text: str, font_path: str, size: int = 48) -> np.ndarray:
    from PIL import Image, ImageDraw, ImageFont

    font = ImageFont.truetype(font_path, size)
    image = Image.new("RGB", (900, 140), "white")
    ImageDraw.Draw(image).text((30, 35), text, font=font, fill="black")
    return np.array(image)[:, :, ::-1]


class TestScriptIdentification:
    @pytest.mark.parametrize("script,text", sorted(SAMPLES.items()))
    def test_each_script_is_identified(self, script, text):
        assert detect_script(text) == script

    def test_latin_is_identified(self):
        assert detect_script("Village Rampur Khasra 142") == "latin"

    def test_devanagari_digits_count_as_devanagari(self):
        """They live inside the Devanagari block, and they are the script."""
        assert detect_script("१४२") == "devanagari"

    def test_ascii_digits_and_punctuation_are_not_a_script(self):
        assert detect_script("142/2 - 1998.") is None

    def test_empty_text_has_no_script(self):
        assert detect_script("") is None

    def test_a_mixed_page_reports_the_dominant_script(self):
        seen = profile("ग्राम रामपुर village")
        assert seen.dominant == "devanagari"
        assert seen.counts["latin"] == 7

    def test_fractions_sum_over_the_counted_characters(self):
        seen = profile("ग्राम village")
        assert abs(seen.fraction("devanagari") + seen.fraction("latin") - 1.0) < 1e-9


class TestUnsupportedScriptsAreRefused:
    """The point of the module: never silently read the wrong script."""

    @pytest.mark.parametrize("script", sorted(UNSUPPORTED_SCRIPTS))
    def test_an_unreadable_script_raises_by_name(self, script):
        with pytest.raises(UnsupportedScript, match=script):
            language_for_script(script)

    def test_gujarati_is_identified_even_though_it_cannot_be_read(self):
        """Identified and refused beats unidentified and guessed."""
        assert detect_script("ગુજરાત જમીન") == "gujarati"

    def test_an_unidentifiable_script_raises_rather_than_defaulting(self):
        with pytest.raises(UnsupportedScript):
            language_for_script(None)

    def test_no_unsupported_script_has_a_language(self):
        assert not (UNSUPPORTED_SCRIPTS & set(SCRIPT_TO_LANG))


class TestModelMapping:
    def test_every_supported_script_maps_to_a_recognition_model(self):
        for lang in SCRIPT_TO_LANG.values():
            assert lang in RECOGNITION_MODELS, lang

    def test_every_devanagari_language_shares_one_recogniser(self):
        """PP-OCRv5 has one Devanagari model; the rest is linguistics."""
        assert RECOGNITION_MODELS["hi"].startswith("devanagari")

    def test_supported_langs_matches_the_model_table(self):
        assert SUPPORTED_LANGS == frozenset(RECOGNITION_MODELS)


class TestRoutingScore:
    """Confidence alone must not decide; script agreement must gate it."""

    def _result(self, text: str, confidence: float) -> OcrResult:
        return OcrResult(blocks=[TextBlock(text, confidence, (0, 0, 10, 10))])

    def test_confident_output_in_the_wrong_script_scores_zero(self):
        """A Devanagari recogniser on a Telugu page returns Latin rubbish."""
        assert _routing_score(self._result("008 28s", 0.62), "telugu") == 0.0

    def test_output_in_the_expected_script_keeps_its_confidence(self):
        score = _routing_score(self._result("తెలంగాణ", 0.90), "telugu")
        assert score == pytest.approx(0.90, abs=1e-6)

    def test_a_mixed_reading_is_discounted_not_rejected(self):
        score = _routing_score(self._result("తెలంగాణ abcdefg", 0.90), "telugu")
        assert 0.0 < score < 0.90

    def test_an_empty_reading_scores_zero(self):
        assert _routing_score(OcrResult(blocks=[]), "telugu") == 0.0


@pytest.mark.slow
class TestRoutingOnRealImages:
    """End to end: pick the recogniser from the image, with no hint."""

    @pytest.mark.parametrize("script", ["devanagari", "telugu", "tamil"])
    def test_the_right_language_wins(self, script):
        font = FONTS[script]
        if not Path(font).exists():
            pytest.skip(f"missing font {font}")

        from ocr.provider import route

        decision = route(render(SAMPLES[script], font), candidates=("hi", "te", "ta"))
        assert decision.lang == SCRIPT_TO_LANG[script], decision.considered
        assert decision.script == script

    def test_the_losing_candidates_are_recorded(self):
        """An audit trail for a routing decision, not just its winner (§64)."""
        font = FONTS["telugu"]
        if not Path(font).exists():
            pytest.skip("missing Telugu font")

        from ocr.provider import route

        decision = route(render(SAMPLES["telugu"], font), candidates=("hi", "te"))
        assert set(decision.considered) == {"hi", "te"}
        assert decision.considered["te"] > decision.considered["hi"]

    def test_telugu_text_is_actually_read(self):
        font = FONTS["telugu"]
        if not Path(font).exists():
            pytest.skip("missing Telugu font")

        from ocr.provider import route

        decision = route(render(SAMPLES["telugu"], font), candidates=("hi", "te"))
        assert "తెలంగాణ" in decision.result.text
