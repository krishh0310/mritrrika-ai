"""The three slice-1 document layouts (§47).

Each renders ONE parcel, so a document maps cleanly onto one
CanonicalLandRecord. Multi-plot registers are a later template family.

All three are invented layouts inspired only by the general structure of North
Indian land records (§47) and carry a synthetic-data notice (§83).
"""

from __future__ import annotations

from records.names import to_devanagari_digits
from rendering.canvas import RecordingCanvas, RenderedPage

from .base import MARGIN, DocumentContext, draw_footer, draw_header, draw_table


def _area_text(ctx: DocumentContext) -> str:
    return f"{to_devanagari_digits(f'{ctx.area_value:.2f}')} {ctx.area_unit_raw}"


def render_khasra_a(ctx: DocumentContext) -> RenderedPage:
    """Khasra A -- plot detail sheet with an owners table."""
    c = RecordingCanvas()
    y = draw_header(c, ctx, "खसरा", variant="A")

    c.text((MARGIN, y), "भूमि विवरण", size=28)
    y += 46

    left = MARGIN + 10
    c.text((left, y), "क्षेत्रफल :", size=25)
    c.text((left + 130, y), to_devanagari_digits(f"{ctx.area_value:.2f}"), size=25,
           field="AREA", normalized=f"{ctx.area_value:.2f}")
    c.text((left + 250, y), ctx.area_unit_raw, size=25, field="AREA_UNIT")

    c.text((left + 430, y), "भूमि श्रेणी :", size=25)
    c.text((left + 585, y), ctx.land_class, size=25, field="LAND_CLASS")
    y += 56

    rows = []
    for name, share in ctx.owners:
        rows.append([
            (name, "OWNER", None),
            (ctx.guardian or "—", "GUARDIAN" if ctx.guardian else None, None),
            (to_devanagari_digits(share), "SHARE", share),
        ])

    y = draw_table(
        c, y,
        [("खातेदार का नाम", 20), ("पिता / पति", 470), ("अंश", 830)],
        rows,
    )

    c.text((MARGIN, y + 10), "टिप्पणी :", size=24)
    c.text((MARGIN + 120, y + 10), "अभिलेख डिजिटलीकरण हेतु", size=24, field="REMARK")

    draw_footer(c, ctx)
    return c.finish()


def render_khatauni_a(ctx: DocumentContext) -> RenderedPage:
    """Khatauni A -- holding statement. Same facts, different arrangement,
    so the extractor cannot succeed by memorising one layout."""
    c = RecordingCanvas()
    y = draw_header(c, ctx, "खतौनी", variant="B")

    rows = [[
        (to_devanagari_digits(ctx.khasra_number), "KHASRA", ctx.khasra_number),
        (_area_text(ctx), "AREA", f"{ctx.area_value:.2f}"),
        (ctx.land_class, "LAND_CLASS", None),
    ]]
    y = draw_table(
        c, y,
        [("खसरा संख्या", 20), ("क्षेत्रफल", 380), ("श्रेणी", 760)],
        rows,
    )

    c.text((MARGIN, y), "खातेदारों का विवरण", size=28)
    y += 46

    owner_rows = [
        [
            (str(i + 1), None, None),
            (name, "OWNER", None),
            (to_devanagari_digits(share), "SHARE", share),
        ]
        for i, (name, share) in enumerate(ctx.owners)
    ]
    y = draw_table(
        c, y,
        [("क्र.", 20), ("नाम", 140), ("अंश", 830)],
        owner_rows,
    )

    if ctx.guardian:
        c.text((MARGIN, y + 6), "पिता / पति :", size=24)
        c.text((MARGIN + 165, y + 6), ctx.guardian, size=24, field="GUARDIAN")

    draw_footer(c, ctx)
    return c.finish()


def render_mutation_register_a(ctx: DocumentContext) -> RenderedPage:
    """Mutation Register A -- one transfer entry (§40)."""
    c = RecordingCanvas()
    y = draw_header(c, ctx, "नामांतरण पंजिका", variant="C")

    left = MARGIN + 10
    if ctx.mutation_number:
        c.text((left, y), "नामांतरण सं. :", size=25)
        c.text((left + 175, y), to_devanagari_digits(ctx.mutation_number), size=25,
               field="MUTATION", normalized=ctx.mutation_number)
    if ctx.mutation_date:
        c.text((left + 460, y), "दिनांक :", size=25)
        c.text((left + 570, y), to_devanagari_digits(ctx.mutation_date), size=25,
               field="DATE", normalized=ctx.mutation_date)
    y += 50

    if ctx.mutation_type:
        c.text((left, y), "प्रकार :", size=25)
        c.text((left + 100, y), ctx.mutation_type, size=25)
    y += 56

    prev = ctx.previous_owners or []
    max_rows = max(len(prev), len(ctx.owners))
    rows = []
    for i in range(max_rows):
        rows.append([
            (prev[i] if i < len(prev) else "—", None, None),
            (ctx.owners[i][0] if i < len(ctx.owners) else "—", "OWNER", None),
            (to_devanagari_digits(ctx.owners[i][1]) if i < len(ctx.owners) else "—",
             "SHARE", ctx.owners[i][1] if i < len(ctx.owners) else None),
        ])

    y = draw_table(
        c, y,
        [("पूर्व खातेदार", 20), ("नवीन खातेदार", 430), ("अंश", 850)],
        rows,
    )

    c.text((MARGIN, y), "क्षेत्रफल :", size=25)
    c.text((MARGIN + 130, y), _area_text(ctx), size=25, field="AREA",
           normalized=f"{ctx.area_value:.2f}")

    draw_footer(c, ctx)
    return c.finish()


TEMPLATES = {
    "KHASRA_A": ("KHASRA", render_khasra_a),
    "KHATAUNI_A": ("KHATAUNI", render_khatauni_a),
    "MUTATION_REGISTER_A": ("MUTATION_REGISTER", render_mutation_register_a),
}
