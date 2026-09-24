"""A PIL canvas that records the bounding box of every value it draws.

This is the mechanism that makes §44 work. Ground truth is not recovered from
the rendered image -- it is captured at the moment each value is drawn, so the
label, the pixel region and the model version are known exactly and for free.

Devanagari requires libraqm-linked Pillow. Without it matras do not reorder and
every annotation in the dataset describes text the image does not contain.
tests/ai/test_devanagari_stack.py guards this.
"""

from __future__ import annotations

from dataclasses import dataclass
from dataclasses import field as dc_field
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, features

DEVANAGARI_FONT = "/System/Library/Fonts/Supplemental/Devanagari Sangam MN.ttc"
DEVANAGARI_FONT_BOLD = "/System/Library/Fonts/Supplemental/Kohinoor.ttc"

#: Land-record extract slips are typically shorter than A4. Sizing the page to
#: the content means degradation lands ON the text rather than on blank paper,
#: which is what makes the degraded set actually hard.
PAGE_WIDTH = 1240
PAGE_HEIGHT = 1200


@dataclass
class TextRegion:
    """One drawn run of text and where it landed.

    `field` is None for static template chrome (headings, column labels) --
    those still matter for layout/OCR annotations but are not extracted values.
    """

    text: str
    bbox: tuple[int, int, int, int]
    field: str | None = None
    #: The normalized form, when the drawn text is a Devanagari-digit variant.
    normalized: str | None = None
    is_handwritten: bool = False
    row: int | None = None
    column: str | None = None


@dataclass
class RenderedPage:
    image: Image.Image
    regions: list[TextRegion] = dc_field(default_factory=list)
    #: Table/heading regions for the layout annotation (§6).
    layout_boxes: list[dict] = dc_field(default_factory=list)

    def value_regions(self) -> list[TextRegion]:
        return [r for r in self.regions if r.field]


class RecordingCanvas:
    """Draw onto a page while recording every text placement."""

    _font_cache: dict[tuple[str, int], ImageFont.FreeTypeFont] = {}

    def __init__(self, width: int = PAGE_WIDTH, height: int = PAGE_HEIGHT,
                 background: str = "#FFFEF8") -> None:
        if not features.check("raqm"):
            raise RuntimeError(
                "Pillow is not linked against libraqm; Devanagari would render "
                "with misplaced matras and every annotation would be wrong. "
                "See services/ai-worker/requirements.txt for the fix."
            )
        self.image = Image.new("RGB", (width, height), background)
        self.draw = ImageDraw.Draw(self.image)
        self.regions: list[TextRegion] = []
        self.layout_boxes: list[dict] = []

    # ── fonts ────────────────────────────────────────────────────────────
    @classmethod
    def font(cls, size: int, path: str = DEVANAGARI_FONT) -> ImageFont.FreeTypeFont:
        key = (path, size)
        if key not in cls._font_cache:
            cls._font_cache[key] = ImageFont.truetype(path, size)
        return cls._font_cache[key]

    # ── primitives ───────────────────────────────────────────────────────
    def text(
        self,
        xy: tuple[int, int],
        content: str,
        size: int = 26,
        field: str | None = None,
        normalized: str | None = None,
        fill: str = "#1A1A1A",
        font_path: str = DEVANAGARI_FONT,
        anchor: str | None = None,
        is_handwritten: bool = False,
        row: int | None = None,
        column: str | None = None,
    ) -> TextRegion:
        """Draw text and record exactly where it landed."""
        font = self.font(size, font_path)
        self.draw.text(xy, content, font=font, fill=fill, anchor=anchor)
        box = self.draw.textbbox(xy, content, font=font, anchor=anchor)
        region = TextRegion(
            text=content,
            bbox=(int(box[0]), int(box[1]), int(box[2]), int(box[3])),
            field=field,
            normalized=normalized,
            is_handwritten=is_handwritten,
            row=row,
            column=column,
        )
        self.regions.append(region)
        return region

    def centered_text(self, y: int, content: str, size: int = 34, **kwargs) -> TextRegion:
        return self.text(
            (self.image.width // 2, y), content, size=size, anchor="ma", **kwargs
        )

    def line(self, start, end, fill: str = "#2B2B2B", width: int = 2) -> None:
        self.draw.line([start, end], fill=fill, width=width)

    def rect(self, box, outline: str = "#2B2B2B", width: int = 2, fill=None) -> None:
        self.draw.rectangle(box, outline=outline, width=width, fill=fill)

    def add_layout_box(self, kind: str, box: tuple[int, int, int, int], **extra) -> None:
        """Record a structural region for the layout annotation (§6)."""
        self.layout_boxes.append({"type": kind, "bbox": list(box), **extra})

    def finish(self) -> RenderedPage:
        return RenderedPage(self.image, self.regions, self.layout_boxes)

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.image.save(path)
