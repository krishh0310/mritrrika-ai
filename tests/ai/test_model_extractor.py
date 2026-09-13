"""The trained extractor, and the rules kept underneath it (§6, §66, §82).

Three things are worth pinning, and "does the model score well" is not among
them -- that is measured by the evaluation harness, against ground truth, and
reported in docs/ai-pipeline.md.

What matters here is that the model cannot make things WORSE. Its absence must
leave extraction exactly as it was; its output must never displace a rule on a
field it said nothing about; and the label set must not drift, because label
ids are baked into a checkpoint and a reordering would silently mean the model
predicts VILLAGE where the file says AREA.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "services" / "ai-worker"))

from extraction.layout_model import (  # noqa: E402
    FIELDS,
    LABEL_TO_ID,
    LABELS,
    FieldSpan,
    decode_spans,
)
from extraction.model_extractor import (  # noqa: E402
    MULTI_VALUED,
    ModelExtractor,
    build_default_extractor,
)
from extraction.model_extractor import extract as extract_hybrid  # noqa: E402
from normalization.normalizers import (  # noqa: E402
    canonicalise_devanagari,
    normalize_field,
)
from ocr.provider import TextBlock  # noqa: E402


def blocks(*pairs) -> list[TextBlock]:
    return [TextBlock(text, 0.95, box) for text, box in pairs]


SAMPLE = (
    ("ग्राम", (100, 100, 180, 130)),
    ("रामपुर", (200, 100, 300, 130)),
    ("खसरा सं", (100, 160, 200, 190)),
    ("१४०", (220, 160, 270, 190)),
)


class TestLabelSetStability:
    """Label ids live inside a checkpoint. Reordering invalidates it."""

    def test_O_is_always_zero(self):
        assert LABELS[0] == "O" and LABEL_TO_ID["O"] == 0

    def test_every_field_has_both_a_B_and_an_I(self):
        for field in FIELDS:
            assert f"B-{field}" in LABEL_TO_ID
            assert f"I-{field}" in LABEL_TO_ID

    def test_the_label_count_matches_the_field_count(self):
        assert len(LABELS) == 1 + 2 * len(FIELDS)

    def test_the_field_order_is_the_one_checkpoints_were_trained_with(self):
        """A guard, not a preference: change this and retrain, or values move."""
        assert FIELDS[:6] == [
            "DISTRICT", "TEHSIL", "VILLAGE", "RECORD_YEAR", "KHATA", "KHASRA",
        ]


class TestSpanDecoding:
    def _decode(self, labels):
        words = ["a", "b", "c", "d"]
        boxes = [[0, 0, 10, 10], [10, 0, 20, 10], [20, 0, 30, 10], [30, 0, 40, 10]]
        return decode_spans(words, boxes, [LABEL_TO_ID[x] for x in labels], [0.9] * 4)

    def test_a_B_then_I_run_is_one_value(self):
        spans = self._decode(["B-OWNER", "I-OWNER", "O", "O"])
        assert len(spans) == 1
        assert spans[0].text == "a b"

    def test_two_B_tags_are_two_values(self):
        spans = self._decode(["B-OWNER", "B-OWNER", "O", "O"])
        assert len(spans) == 2

    def test_a_run_ends_when_the_field_changes(self):
        spans = self._decode(["B-OWNER", "I-SHARE", "O", "O"])
        assert [s.field for s in spans] == ["OWNER", "SHARE"]

    def test_a_bare_I_still_starts_a_value(self):
        """The model is not required to be self-consistent; dropping an
        unopened run would lose a field on a formatting technicality."""
        spans = self._decode(["O", "I-VILLAGE", "O", "O"])
        assert len(spans) == 1 and spans[0].field == "VILLAGE"

    def test_the_span_box_encloses_every_word_in_it(self):
        spans = self._decode(["B-OWNER", "I-OWNER", "O", "O"])
        assert spans[0].bbox == (0, 0, 20, 10)

    def test_all_O_produces_nothing(self):
        assert self._decode(["O"] * 4) == []


class TestFallbackContract:
    """§82 -- unavailable must mean inert, never broken."""

    def test_a_missing_checkpoint_reports_unavailable(self, tmp_path):
        extractor = ModelExtractor(tmp_path / "nope.pt")
        assert extractor.available is False
        assert "no checkpoint" in extractor.unavailable_reason

    def test_a_missing_checkpoint_predicts_nothing_rather_than_raising(self, tmp_path):
        assert ModelExtractor(tmp_path / "nope.pt").predict(blocks(*SAMPLE), 1240, 1754) == []

    def test_extraction_without_a_model_equals_the_rule_based_result(self, tmp_path):
        from extraction.field_extractor import extract as extract_with_rules

        page = blocks(*SAMPLE)
        rules = extract_with_rules(page, 1240)
        hybrid = extract_hybrid(
            page, 1240, 1754, extractor=ModelExtractor(tmp_path / "nope.pt")
        )
        assert [(v.field, v.raw_value) for v in hybrid.values] == \
               [(v.field, v.raw_value) for v in rules.values]

    def test_a_none_extractor_is_the_same_as_no_model(self):
        from extraction.field_extractor import extract as extract_with_rules

        page = blocks(*SAMPLE)
        assert [(v.field, v.raw_value) for v in extract_hybrid(page, 1240, 1754).values] == \
               [(v.field, v.raw_value) for v in extract_with_rules(page, 1240).values]

    def test_the_default_extractor_is_constructible_without_weights(self):
        """Importing and building it must never be what breaks a worker."""
        assert build_default_extractor().predict(blocks(*SAMPLE), 1240, 1754) == []


class TestCompositionRules:
    def test_the_table_columns_are_the_multi_valued_ones(self):
        assert MULTI_VALUED == {"OWNER", "GUARDIAN", "SHARE"}

    @pytest.mark.parametrize("field", ["VILLAGE", "KHASRA", "AREA", "DISTRICT"])
    def test_page_metadata_is_single_valued(self, field):
        """A page has one village, not four."""
        assert field not in MULTI_VALUED


class TestIndicNormalisation:
    """AI4Bharat's normaliser, used for one job: one spelling per word."""

    def test_the_two_nukta_spellings_converge(self):
        """OCR emits 'क़' as one codepoint or as 'क' + U+093C, at random."""
        assert canonicalise_devanagari("क़िला") == canonicalise_devanagari("क़िला")

    def test_zero_width_joiners_are_stripped(self):
        assert canonicalise_devanagari("रामपुर‍") == "रामपुर"

    def test_ordinary_text_is_unchanged(self):
        assert canonicalise_devanagari("रामपुर") == "रामपुर"

    def test_empty_input_is_safe(self):
        assert canonicalise_devanagari("") == ""

    def test_canonicalisation_runs_before_field_rules(self):
        """A joiner must not survive into a stored value."""
        assert normalize_field("VILLAGE", "रामपुर‍") == "रामपुर"

    def test_devanagari_digits_still_convert(self):
        assert normalize_field("KHASRA", "१४२/२") == "142/2"

    def test_area_still_parses(self):
        assert normalize_field("AREA", "०.८९") == "0.89"


class TestSpanShape:
    def test_a_span_carries_its_words_for_provenance(self):
        span = FieldSpan("VILLAGE", "रामपुर", (0, 0, 10, 10), 0.9, [3])
        assert span.word_indices == [3]
