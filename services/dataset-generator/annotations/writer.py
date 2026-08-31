"""Annotation payloads for one generated page (§50).

Four views of the same ground truth, because different parts of the pipeline
need different shapes:

  fields/  -- extractable values with provenance. Trains and evaluates the
              extractor, and is what the Verifier UI compares against.
  ocr/     -- every text run, value or chrome, with its box. Evaluates OCR.
  layout/  -- structural regions (header, table). Evaluates layout parsing.
  tables/  -- table cells with row/column indices.

All four are derived from what the renderer recorded, never from OCR (§44).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field


@dataclass
class PageAnnotation:
    document_id: str
    page: int
    template: str
    document_type: str
    parcel_id: str
    difficulty: str
    width: int
    height: int
    fields: list[dict] = field(default_factory=list)
    ocr: list[dict] = field(default_factory=list)
    layout: list[dict] = field(default_factory=list)
    tables: list[dict] = field(default_factory=list)
    degradations: list[dict] = field(default_factory=list)
    is_synthetic: bool = True

    def to_dict(self) -> dict:
        return asdict(self)


def build_annotation(
    *,
    document_id: str,
    page_index: int,
    template: str,
    document_type: str,
    parcel_id: str,
    difficulty: str,
    size: tuple[int, int],
    regions,
    boxes,
    layout_boxes,
    degradations,
) -> PageAnnotation:
    """Assemble the four annotation views.

    `boxes` are the POST-degradation positions, in the same order as `regions`,
    so field annotations describe where the value actually is in the degraded
    image -- not where it was before the page was rotated.
    """
    annotation = PageAnnotation(
        document_id=document_id,
        page=page_index,
        template=template,
        document_type=document_type,
        parcel_id=parcel_id,
        difficulty=difficulty,
        width=size[0],
        height=size[1],
        degradations=list(degradations),
    )

    for region, box in zip(regions, boxes, strict=True):
        entry = {
            "text": region.text,
            "bbox": list(box),
            "is_handwritten": region.is_handwritten,
        }
        annotation.ocr.append(entry)

        if region.field:
            annotation.fields.append(
                {
                    "field": region.field,
                    # Raw is what is VISIBLE on the page (Devanagari digits and
                    # all); normalized is the value the extractor must produce.
                    "raw_value": region.text,
                    "normalized_value": region.normalized or region.text,
                    "bbox": list(box),
                    "source_page": page_index,
                    "row": region.row,
                    "column": region.column,
                }
            )

        if region.row is not None:
            annotation.tables.append(
                {
                    "row": region.row,
                    "column": region.column,
                    "text": region.text,
                    "bbox": list(box),
                }
            )

    annotation.layout = list(layout_boxes)
    return annotation
