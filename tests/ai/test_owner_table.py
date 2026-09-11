"""The owners table ends where the table ends.

The remark line ("टिप्पणी: अभिलेख डिजिटलीकरण हेतु") sits directly under the
owners table, inside the name column. It was read as one more OWNER row and
auto-accepted at ~0.90 on every processed page. A first fix only rejected it
when OCR returned the remark as a single block; OCR often splits the label
from the value, and the value alone still got through.
"""

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "services" / "ai-worker"))

from extraction.field_extractor import extract_table_rows  # noqa: E402
from ocr.provider import TextBlock  # noqa: E402

TABLE = [
    TextBlock("खातेदार का नाम", 0.97, (87, 468, 230, 508)),
    TextBlock("अंश", 0.96, (640, 468, 700, 508)),
    TextBlock("गिरधारी देवी", 0.95, (89, 523, 209, 559)),
    TextBlock("१/२", 0.94, (645, 523, 695, 559)),
    TextBlock("श्याम लाल वर्मा", 0.95, (89, 563, 240, 599)),
    TextBlock("१/२", 0.94, (645, 563, 695, 599)),
]

REMARK_AS_ONE_BLOCK = [TextBlock("टिप्पणी: अभिलेख डिजिटलीकरण हेतु", 0.93, (68, 603, 437, 643))]
REMARK_SPLIT = [
    TextBlock("टिप्पणी:", 0.92, (68, 603, 150, 643)),
    TextBlock("अभिलेख डिजिटलीकरण हेतु", 0.93, (160, 603, 437, 643)),
]


def owners(blocks):
    return [v.raw_value for v in extract_table_rows(blocks) if v.field == "OWNER"]


@pytest.mark.parametrize("remark", [REMARK_AS_ONE_BLOCK, REMARK_SPLIT], ids=["one-block", "split"])
def test_remark_line_is_not_an_owner(remark):
    assert owners(TABLE + remark) == ["गिरधारी देवी", "श्याम लाल वर्मा"]


def test_rows_after_the_remark_are_not_read_as_owners():
    trailing = [TextBlock("राम प्रसाद", 0.9, (89, 660, 200, 700))]
    assert owners(TABLE + REMARK_SPLIT + trailing) == ["गिरधारी देवी", "श्याम लाल वर्मा"]


def test_owners_and_shares_stay_paired_by_row():
    values = extract_table_rows(TABLE + REMARK_SPLIT)
    rows = {(v.field, v.row_index): v.raw_value for v in values}
    assert rows[("OWNER", 0)] == "गिरधारी देवी" and rows[("SHARE", 0)] == "१/२"
    assert rows[("OWNER", 1)] == "श्याम लाल वर्मा" and rows[("SHARE", 1)] == "१/२"


def test_a_table_without_a_remark_is_unchanged():
    assert owners(TABLE) == ["गिरधारी देवी", "श्याम लाल वर्मा"]


# ── guardian column ──────────────────────────────────────────────────────────
# "पिता / पति" is a column heading. The scalar extractor matched 'पिता / प' as
# the label and recorded the remainder, 'ति', as the guardian's name.

GUARDIAN_TABLE = [
    TextBlock("खातेदार का नाम", 0.97, (87, 468, 230, 508)),
    TextBlock("पिता / पति", 0.95, (470, 468, 560, 508)),
    TextBlock("अंश", 0.96, (760, 468, 800, 508)),
    TextBlock("गिरधारी देवी", 0.95, (89, 523, 209, 559)),
    TextBlock("कैलाश वर्मा", 0.94, (480, 523, 600, 559)),
    TextBlock("१/१", 0.94, (765, 523, 800, 559)),
]


def test_guardian_is_read_from_its_column_not_the_heading():
    from extraction.field_extractor import extract

    guardians = [v for v in extract(GUARDIAN_TABLE).values if v.field == "GUARDIAN"]
    assert [(g.raw_value, g.row_index) for g in guardians] == [("कैलाश वर्मा", 0)]


def test_a_label_fragment_is_never_a_value():
    from extraction.field_extractor import _split_inline_value

    heading = TextBlock("पिता / पति", 0.95, (470, 468, 560, 508))
    assert _split_inline_value(heading, ["पिता / पति", "पिता", "पति"]) is None


def test_a_real_value_fused_to_its_label_is_still_recovered():
    from extraction.field_extractor import _split_inline_value

    fused = TextBlock("पिता / पति : कैलाश वर्मा", 0.9, (100, 100, 400, 140))
    assert _split_inline_value(fused, ["पिता / पति", "पिता", "पति"]) == "कैलाश वर्मा"
