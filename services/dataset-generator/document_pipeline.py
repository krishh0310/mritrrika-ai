"""Ground truth -> template -> clean render -> annotate -> degrade (§44).

The order is the contract. Labels come from the structured world; the image is
produced from those labels; the degradation then moves the labels alongside the
pixels. At no point is a label read back from an image.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import date

from annotations.writer import PageAnnotation, build_annotation
from degradation.profiles import degrade, pick_difficulty
from templates.base import DocumentContext
from templates.layouts import TEMPLATES

MUTATION_TYPE_HI = {
    "SALE": "विक्रय",
    "INHERITANCE": "उत्तराधिकार",
    "GIFT": "दान",
    "PARTITION": "बंटवारा",
    "COURT_DECREE": "न्यायालय आदेश",
    "CORRECTION": "शुद्धि",
}


@dataclass
class GeneratedDocument:
    document_id: str
    parcel_id: str
    template: str
    document_type: str
    difficulty: str
    clean_image: object
    degraded_image: object
    annotation: PageAnnotation
    #: Grouping keys for the leakage-free split (§51).
    base_document_id: str
    template_family: str
    parcel_family: str


def _owners_on(world, parcel_id: str, when: date) -> list[tuple[str, str]]:
    names = {o.owner_id: o.name for o in world.owners}
    active = world.ownership_for(parcel_id, when)
    return [(names[o.owner_id], o.share) for o in active]


def build_context(world, parcel, document_id: str, as_of: date,
                  mutation=None) -> DocumentContext:
    locations = {loc.location_id: loc for loc in world.locations}
    village = locations[parcel.village_id]
    tehsil = locations[village.parent_id]
    district = locations[tehsil.parent_id]
    state = locations[district.parent_id]

    owners = _owners_on(world, parcel.parcel_id, as_of)
    if not owners:
        owners = _owners_on(world, parcel.parcel_id, date.today())

    guardians = {o.owner_id: o.guardian_name for o in world.owners}
    first_guardian = None
    active = world.ownership_for(parcel.parcel_id, as_of)
    if active:
        first_guardian = guardians.get(active[0].owner_id)

    record = next(
        (r for r in world.land_records if r.parcel_id == parcel.parcel_id), None
    )

    ctx = DocumentContext(
        document_id=document_id,
        parcel_id=parcel.parcel_id,
        state=state.name_devanagari or state.name,
        district=district.name_devanagari or district.name,
        tehsil=tehsil.name_devanagari or tehsil.name,
        village=village.name_devanagari or village.name,
        khasra_number=parcel.khasra_number,
        khata_number=parcel.khata_number,
        area_value=parcel.area_value,
        area_unit_raw=parcel.area_unit_raw or "बीघा",
        land_class=parcel.land_class or "सिंचित",
        record_year=record.record_year if record else "2010-11",
        owners=owners,
        guardian=first_guardian,
    )

    if mutation is not None:
        names = {o.owner_id: o.name for o in world.owners}
        ctx.mutation_number = mutation.mutation_number
        ctx.mutation_type = MUTATION_TYPE_HI.get(mutation.mutation_type.value, "अन्य")
        ctx.mutation_date = mutation.effective_date.strftime("%d/%m/%Y")
        ctx.previous_owners = [names[o] for o in mutation.previous_owner_ids]
        ctx.owners = [(names[o], "—") for o in mutation.new_owner_ids] or ctx.owners

    return ctx


def generate_document(
    world,
    parcel,
    template_name: str,
    document_id: str,
    rng: random.Random,
    as_of: date,
    mutation=None,
    difficulty: str | None = None,
) -> GeneratedDocument:
    document_type, render = TEMPLATES[template_name]
    ctx = build_context(world, parcel, document_id, as_of, mutation)

    page = render(ctx)
    clean = page.image.copy()

    tier = difficulty or pick_difficulty(rng)
    result = degrade(page.image, [r.bbox for r in page.regions], tier, rng)

    annotation = build_annotation(
        document_id=document_id,
        page_index=1,
        template=template_name,
        document_type=document_type,
        parcel_id=parcel.parcel_id,
        difficulty=tier,
        size=result.image.size,
        regions=page.regions,
        boxes=result.boxes,
        layout_boxes=page.layout_boxes,
        degradations=result.applied,
    )

    return GeneratedDocument(
        document_id=document_id,
        parcel_id=parcel.parcel_id,
        template=template_name,
        document_type=document_type,
        difficulty=tier,
        clean_image=clean,
        degraded_image=result.image,
        annotation=annotation,
        base_document_id=document_id,
        template_family=template_name.rsplit("_", 1)[0],
        parcel_family=parcel.parcel_id,
    )
