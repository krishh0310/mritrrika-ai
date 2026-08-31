"""Environment gates for the Devanagari half of the AI stack.

These two tests guard the findings from the Stage-3 spike. Both failures are
silent-and-catastrophic if they regress, which is why they are tests and not
a note in a README:

1.  SHAPING -- Pillow must be linked against libraqm. Without it, Devanagari
    matras do not reorder (कि renders as क + ि instead of ि + क). Because the
    dataset generator writes ground truth BEFORE rendering (spec §44), broken
    shaping would produce images whose visible text does not match their
    labels. OCR would then score as "failing" on text that is actually
    malformed nonsense -- an error that looks like a model problem and is
    really a rendering problem.

        Fix: brew install libraqm
             PKG_CONFIG_PATH=/opt/homebrew/lib/pkgconfig \
             pip install --force-reinstall --no-binary :all: Pillow

2.  RECOGNITION -- PaddleOCR must actually load a Devanagari model on this
    platform. Note the language code is 'hi', NOT 'devanagari'; the latter is
    the internal rec-model name and raises ValueError if passed as `lang`.
"""

import numpy as np
import pytest
from PIL import Image, ImageDraw, ImageFont, features

DEVANAGARI_FONT = "/System/Library/Fonts/Supplemental/Devanagari Sangam MN.ttc"

# Realistic land-record values (spec §45): conjuncts, matras, Devanagari digits.
GOLDEN_SAMPLES = [
    "रामपुर",
    "राम प्रसाद सिंह",
    "खसरा संख्या १४२/२",
    "क्षेत्रफल २.७५ बीघा",
    "सिंचित",
]


def _render(text: str, size: int = 44) -> Image.Image:
    font = ImageFont.truetype(DEVANAGARI_FONT, size)
    img = Image.new("RGB", (900, 120), "white")
    ImageDraw.Draw(img).text((30, 25), text, fill="black", font=font)
    return img


def _in_reading_order(pages, overlap_ratio: float = 0.5):
    """Sort detected boxes into reading order: top-to-bottom, left-to-right.

    PaddleOCR does NOT guarantee reading order. The detector may split one
    visual line into several boxes and return them in arbitrary sequence -- we
    observed 'राम प्रसाद सिंह' come back as 'सिंह राम प्रसाद'. Any consumer
    that concatenates rec_texts naively will silently scramble field values.

    Grouping lines by y-centre DOES NOT WORK for Devanagari. Matras and the
    anusvara extend well above the shirorekha, so box heights vary sharply
    within a single line. Measured on that same sample:

        सिंह    y=[17, 76]  ycen=46.5
        राम     y=[35, 70]  ycen=52.5
        प्रसाद  y=[34, 71]  ycen=52.5

    A y-centre band puts सिंह on its own line and sorts it first. Instead we
    group by *vertical overlap*, which is robust to ascender variation: two
    boxes share a line when their vertical spans overlap by more than
    `overlap_ratio` of the shorter box's height.

    The production OCRProvider must apply this same ordering.

    Returns a list of (bbox, text) pairs in reading order.
    """
    items = []
    for page in pages:
        for text, box in zip(page["rec_texts"], page["rec_boxes"], strict=True):
            x1, y1, x2, y2 = (float(v) for v in box)
            items.append(((x1, y1, x2, y2), text))

    items.sort(key=lambda it: it[0][1])  # by top edge

    lines: list[list] = []
    for item in items:
        (_, y1, _, y2) = item[0]
        placed = False
        for line in lines:
            ly1 = min(b[0][1] for b in line)
            ly2 = max(b[0][3] for b in line)
            overlap = min(y2, ly2) - max(y1, ly1)
            shorter = min(y2 - y1, ly2 - ly1)
            if shorter > 0 and overlap / shorter > overlap_ratio:
                line.append(item)
                placed = True
                break
        if not placed:
            lines.append([item])

    ordered = []
    for line in lines:
        ordered.extend(sorted(line, key=lambda it: it[0][0]))  # left-to-right
    return ordered


def test_pillow_has_raqm():
    """Without libraqm every generated document is silently mislabelled."""
    assert features.check("raqm"), (
        "Pillow is not linked against libraqm; Devanagari shaping will be "
        "wrong and the synthetic dataset's ground truth will not match its "
        "images. See module docstring for the fix."
    )


def test_devanagari_matra_reorders_left():
    """कि must render the ि matra to the LEFT of क.

    Discriminator: render 'कि' and 'ि' separately. When shaping is correct the
    leading ink column-profile of 'कि' is the matra, so 'कि' is *narrower*
    than the naive concatenation width of क followed by ि.
    """
    font = ImageFont.truetype(DEVANAGARI_FONT, 80)

    def ink_width(text: str) -> int:
        img = Image.new("L", (600, 200), 255)
        ImageDraw.Draw(img).text((20, 20), text, font=font, fill=0)
        cols = np.where((np.array(img) < 128).any(axis=0))[0]
        return int(cols.max() - cols.min())

    shaped = ink_width("कि")
    unshaped_estimate = ink_width("क") + ink_width("ि")

    # Correct shaping composes the cluster under one shirorekha, so the real
    # cluster is meaningfully narrower than the two glyphs laid side by side.
    assert shaped < unshaped_estimate * 0.85, (
        f"'कि' cluster width {shaped}px is not narrower than the unshaped "
        f"estimate {unshaped_estimate}px -- matra is probably not reordering."
    )


@pytest.mark.slow
def test_paddleocr_reads_devanagari():
    """PaddleOCR must load a Devanagari model and read clean rendered text.

    This asserts the stack works, not that accuracy is production-grade:
    the input is clean rendered text, which is the easiest possible case.
    Degraded-scan accuracy is measured separately by the §65 eval harness.
    """
    from paddleocr import PaddleOCR

    ocr = PaddleOCR(
        lang="hi",  # NOT 'devanagari' -- that is the rec-model name
        use_doc_orientation_classify=False,
        use_doc_unwarping=False,
        use_textline_orientation=False,
    )

    for sample in GOLDEN_SAMPLES:
        img = np.array(_render(sample))
        result = ocr.predict(img)
        assert result, f"no OCR result for {sample!r}"
        joined = " ".join(t for _, t in _in_reading_order(result))
        assert joined.strip() == sample, f"expected {sample!r}, got {joined!r}"
