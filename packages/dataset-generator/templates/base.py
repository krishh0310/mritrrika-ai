"""Shared chrome for the synthetic document templates (§47).

These layouts are INVENTED. They borrow the general shape of North Indian land
records -- a header naming the administrative hierarchy, a ruled table, a
signature block -- but no layout is a copy of any real government form, and
every page carries a visible synthetic-data notice (§83).
"""

from __future__ import annotations

from dataclasses import dataclass

from records.names import to_devanagari_digits
from rendering.canvas import RecordingCanvas

MARGIN = 70


@dataclass
class DocumentContext:
    """Everything a template needs to render one parcel's document."""

    document_id: str
    parcel_id: str
    state: str
    district: str
    tehsil: str
    village: str
    khasra_number: str
    khata_number: str | None
    area_value: float
    area_unit_raw: str
    land_class: str
    record_year: str
    owners: list[tuple[str, str]]          # (name, share)
    guardian: str | None = None
    mutation_number: str | None = None
    mutation_type: str | None = None
    mutation_date: str | None = None
    previous_owners: list[str] | None = None


def draw_header(c: RecordingCanvas, ctx: DocumentContext, title: str,
                variant: str = "A") -> int:
    """Administrative header. Returns the y to continue drawing from.

    Three arrangements, because a shared header would place every field at
    identical coordinates on every template -- letting an extractor score well
    by memorising positions instead of reading layout (§47). The variants move
    the fields, change the label wording, and differ in which values appear in
    the header at all.
    """
    if variant == "B":
        return _header_stacked(c, ctx, title)
    if variant == "C":
        return _header_grid(c, ctx, title)
    return _header_two_column(c, ctx, title)


def _header_two_column(c: RecordingCanvas, ctx: DocumentContext, title: str) -> int:
    """Variant A -- boxed, two balanced columns."""
    top = MARGIN
    c.rect((MARGIN - 18, top - 18, c.image.width - MARGIN + 18, top + 250), width=3)
    c.add_layout_box("header", (MARGIN - 18, top - 18, c.image.width - MARGIN + 18, top + 250))

    c.centered_text(top, ctx.state, size=30)
    c.centered_text(top + 44, title, size=42,
                    font_path="/System/Library/Fonts/Supplemental/Kohinoor.ttc")

    y = top + 118
    left = MARGIN + 10
    right = c.image.width // 2 + 40

    c.text((left, y), "जिला :", size=25)
    c.text((left + 90, y), ctx.district, size=25, field="DISTRICT")
    c.text((right, y), "तहसील :", size=25)
    c.text((right + 105, y), ctx.tehsil, size=25, field="TEHSIL")

    y += 42
    c.text((left, y), "ग्राम :", size=25)
    c.text((left + 90, y), ctx.village, size=25, field="VILLAGE")
    c.text((right, y), "वर्ष :", size=25)
    c.text((right + 105, y), to_devanagari_digits(ctx.record_year), size=25,
           field="RECORD_YEAR", normalized=ctx.record_year)

    y += 42
    if ctx.khata_number:
        c.text((left, y), "खाता सं. :", size=25)
        c.text((left + 125, y), to_devanagari_digits(ctx.khata_number), size=25,
               field="KHATA", normalized=ctx.khata_number)
    c.text((right, y), "खसरा सं. :", size=25)
    c.text((right + 135, y), to_devanagari_digits(ctx.khasra_number), size=25,
           field="KHASRA", normalized=ctx.khasra_number)

    return top + 285


def _header_stacked(c: RecordingCanvas, ctx: DocumentContext, title: str) -> int:
    """Variant B -- title left, details stacked in one narrow column.

    Deliberately omits the khasra number: on a khatauni the plot is listed in
    the body table instead, so the extractor cannot rely on a fixed header slot.
    """
    top = MARGIN
    c.text((MARGIN, top), title, size=44,
           font_path="/System/Library/Fonts/Supplemental/Kohinoor.ttc")
    c.text((c.image.width - MARGIN, top + 12), ctx.state, size=26, anchor="ra")
    c.line((MARGIN, top + 62), (c.image.width - MARGIN, top + 62), width=3)
    c.add_layout_box("header", (MARGIN, top, c.image.width - MARGIN, top + 210))

    y = top + 84
    label_x, value_x = MARGIN, MARGIN + 210
    for label, value, fname, norm in (
        ("जनपद", ctx.district, "DISTRICT", None),
        ("तहसील", ctx.tehsil, "TEHSIL", None),
        ("ग्राम / मौजा", ctx.village, "VILLAGE", None),
    ):
        c.text((label_x, y), f"{label} —", size=24)
        c.text((value_x, y), value, size=24, field=fname, normalized=norm)
        y += 38

    c.text((c.image.width - MARGIN - 300, top + 84), "फसली वर्ष :", size=24)
    c.text((c.image.width - MARGIN - 300, top + 120),
           to_devanagari_digits(ctx.record_year), size=26,
           field="RECORD_YEAR", normalized=ctx.record_year)
    if ctx.khata_number:
        c.text((c.image.width - MARGIN - 300, top + 158), "खाता :", size=24)
        c.text((c.image.width - MARGIN - 195, top + 158),
               to_devanagari_digits(ctx.khata_number), size=24,
               field="KHATA", normalized=ctx.khata_number)

    return top + 226


def _header_grid(c: RecordingCanvas, ctx: DocumentContext, title: str) -> int:
    """Variant C -- ruled grid with labels ABOVE their values."""
    top = MARGIN
    c.centered_text(top, title, size=40,
                    font_path="/System/Library/Fonts/Supplemental/Kohinoor.ttc")
    c.centered_text(top + 52, ctx.state, size=24)

    grid_top = top + 96
    grid_bottom = grid_top + 116
    c.rect((MARGIN, grid_top, c.image.width - MARGIN, grid_bottom), width=2)
    c.line((MARGIN, grid_top + 40), (c.image.width - MARGIN, grid_top + 40), width=1)
    c.add_layout_box("header", (MARGIN, grid_top, c.image.width - MARGIN, grid_bottom))

    cells = [
        ("जिला", ctx.district, "DISTRICT", None),
        ("तहसील", ctx.tehsil, "TEHSIL", None),
        ("ग्राम", ctx.village, "VILLAGE", None),
        ("खसरा", to_devanagari_digits(ctx.khasra_number), "KHASRA", ctx.khasra_number),
        ("वर्ष", to_devanagari_digits(ctx.record_year), "RECORD_YEAR", ctx.record_year),
    ]
    width = (c.image.width - 2 * MARGIN) / len(cells)
    for i, (label, value, fname, norm) in enumerate(cells):
        x = MARGIN + int(i * width) + 14
        if i:
            c.line((MARGIN + int(i * width), grid_top),
                   (MARGIN + int(i * width), grid_bottom), width=1)
        c.text((x, grid_top + 8), label, size=21)
        c.text((x, grid_top + 52), value, size=25, field=fname, normalized=norm)

    return grid_bottom + 34


def draw_footer(c: RecordingCanvas, ctx: DocumentContext) -> None:
    """Signature block, seal and the mandatory synthetic-data notice."""
    h = c.image.height
    y = h - 230

    c.line((MARGIN, y), (c.image.width - MARGIN, y), width=1)
    c.text((MARGIN, y + 24), "प्रमाणित किया जाता है", size=22)

    # Seal: a plain ring, deliberately not resembling any real emblem.
    cx, cy, r = c.image.width - MARGIN - 90, y + 78, 58
    c.draw.ellipse((cx - r, cy - r, cx + r, cy + r), outline="#4A5A7A", width=3)
    c.draw.ellipse((cx - r + 9, cy - r + 9, cx + r - 9, cy + r - 9), outline="#4A5A7A", width=1)
    c.text((cx, cy - 16), "डेमो", size=19, fill="#4A5A7A", anchor="ma")
    c.text((cx, cy + 6), "मुहर", size=19, fill="#4A5A7A", anchor="ma")

    c.line((MARGIN, y + 132), (MARGIN + 260, y + 132), width=1)
    c.text((MARGIN, y + 140), "हस्ताक्षर / लेखपाल", size=20)

    # §83 -- must be unmissable on every generated page.
    c.text(
        (c.image.width // 2, h - 42),
        "DEMO / SYNTHETIC DATA — NOT A GOVERNMENT RECORD",
        size=18,
        fill="#9A6B4A",
        anchor="ma",
        font_path="/System/Library/Fonts/Supplemental/Devanagari Sangam MN.ttc",
    )


def draw_table(
    c: RecordingCanvas,
    top: int,
    columns: list[tuple[str, int]],
    rows: list[list[tuple[str, str | None, str | None]]],
    row_height: int = 56,
) -> int:
    """Draw a ruled table.

    `columns` is (heading, x-offset). Each row cell is
    (text, field_name | None, normalized | None) so a cell can be annotated as
    an extractable value or left as chrome.
    """
    left = MARGIN
    right = c.image.width - MARGIN
    header_h = 52

    c.rect((left, top, right, top + header_h + row_height * len(rows)), width=2)
    c.line((left, top + header_h), (right, top + header_h), width=2)
    c.add_layout_box(
        "table",
        (left, top, right, top + header_h + row_height * len(rows)),
        rows=len(rows),
        columns=len(columns),
    )

    for heading, dx in columns:
        c.text((left + dx, top + 13), heading, size=23)

    for i, row in enumerate(rows):
        y = top + header_h + i * row_height
        if i:
            c.line((left, y), (right, y), width=1)
        for (text, field, normalized), (_, dx) in zip(row, columns, strict=True):
            if text:
                c.text(
                    (left + dx, y + 14),
                    text,
                    size=25,
                    field=field,
                    normalized=normalized,
                    row=i,
                )

    for _, dx in columns[1:]:
        rule_x = left + dx - 14
        c.line(
            (rule_x, top), (rule_x, top + header_h + row_height * len(rows)), width=1
        )

    return top + header_h + row_height * len(rows) + 30
