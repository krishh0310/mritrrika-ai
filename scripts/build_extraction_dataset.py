#!/usr/bin/env python
"""Turn cached OCR + annotations into a token-classification dataset (§6, §66).

    python scripts/cache_ocr.py --profile v1
    python scripts/build_extraction_dataset.py --profile v1

Each page becomes: the words real OCR produced, their boxes, and a BIO label
per word saying which field (if any) that word is part of.

The labelling is geometric, not textual, and that is the whole difficulty.
Ground truth says "AREA is at box X"; OCR says "the text '0.89' is at box Y".
Matching them on TEXT would silently drop every field OCR misread -- which is
exactly the hard third of the corpus, and would train the model only on the
easy pages. So words are matched to fields by overlap, and a word OCR got wrong
still carries the right label. The model then learns "the value in this
position is an area" rather than "this string is an area", which is the only
thing that generalises to a page it has not seen.

Fields whose ground-truth box no OCR word overlaps are counted and reported:
those are fields OCR missed entirely, and no extraction model can recover them.
That number is the ceiling on recall, and it is printed rather than hidden.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DATASETS = REPO_ROOT / "datasets"
sys.path.insert(0, str(REPO_ROOT / "packages" / "domain"))

#: The fields the extractor targets, in a fixed order so label ids are stable
#: across runs. A reordering here silently invalidates a trained checkpoint.
FIELDS = [
    "DISTRICT", "TEHSIL", "VILLAGE", "RECORD_YEAR", "KHATA", "KHASRA",
    "AREA", "AREA_UNIT", "LAND_CLASS", "MUTATION", "DATE",
    "OWNER", "GUARDIAN", "SHARE",
]

LABELS = ["O"] + [f"{prefix}-{field}" for field in FIELDS for prefix in ("B", "I")]
LABEL_TO_ID = {label: i for i, label in enumerate(LABELS)}

#: Minimum coincidence (see `overlap`) for a word to carry a field's label.
#: Not IoU: a field box usually spans several words, or is swallowed by one, and
#: IoU rejects both.
MIN_CONTAINMENT = 0.45



def deskew_matrix(angle: float, width: int, height: int):
    """The exact rotation preprocessing applied, so boxes can follow it.

    preprocessing/enhance.py deskews with
    `cv2.getRotationMatrix2D((w/2, h/2), -angle, 1.0)` and then upscales. A
    ground-truth box mapped with the scale factors ALONE therefore lands
    wherever the page was before it was straightened -- which is how the
    village 'रामपुर' came to be labelled B-DISTRICT, and why the first two
    training runs learned nothing: most of the supervision was simply wrong.
    """
    import cv2

    return cv2.getRotationMatrix2D((width / 2, height / 2), -angle, 1.0)


def map_box_to_prepared(box, matrix, scale_x: float, scale_y: float):
    """Original-image box -> prepared-image box, through rotation then scale."""
    x1, y1, x2, y2 = box
    corners = ((x1, y1), (x2, y1), (x2, y2), (x1, y2))
    if matrix is not None:
        a, b, c = matrix[0]
        d, e, f = matrix[1]
        corners = tuple((a * x + b * y + c, d * x + e * y + f) for x, y in corners)
    xs = [x * scale_x for x, _ in corners]
    ys = [y * scale_y for _, y in corners]
    return (min(xs), min(ys), max(xs), max(ys))


def _intersection(a: tuple, b: tuple) -> float:
    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b
    ix1, iy1 = max(ax1, bx1), max(ay1, by1)
    ix2, iy2 = min(ax2, bx2), min(ay2, by2)
    if ix2 <= ix1 or iy2 <= iy1:
        return 0.0
    return (ix2 - ix1) * (iy2 - iy1)


def containment(word: tuple, field: tuple) -> float:
    """How much of the WORD lies inside the field box: 'is this word part of
    that value'."""
    area = max(1.0, (word[2] - word[0]) * (word[3] - word[1]))
    return _intersection(word, field) / area


def coverage(word: tuple, field: tuple) -> float:
    """How much of the FIELD lies inside the word: 'did this block swallow the
    value whole', which is what happens when OCR returns a label and its value
    as one line."""
    area = max(1.0, (field[2] - field[0]) * (field[3] - field[1]))
    return _intersection(word, field) / area


def split_into_words(block: dict) -> list[dict]:
    """One entry per WORD, not per OCR line.

    PaddleOCR returns a whole form line as a single block: `तहसील डेमो तहसील`
    is the printed label followed by its value. Labelling at block granularity
    therefore tags the printed label as part of the value, and the model is
    asked to tell `तहसील`-the-label from `तहसील`-the-value using a token that
    is identical in both -- 43.6% of supervised tokens came out ambiguous by
    text alone that way.

    The deterministic extractor does not have this problem because it splits a
    label off its value INSIDE a block. A token classifier over blocks cannot,
    so the blocks are split here instead.

    Boxes are apportioned along the line by character count. That is an
    approximation -- Devanagari glyphs are not equal width -- but it is a far
    better one than giving every word the whole line's box, and the label is
    decided by overlap, which tolerates a few pixels of drift.
    """
    text = (block.get("text") or "").strip()
    if not text:
        return []
    parts = text.split()
    x1, y1, x2, y2 = block["bbox"]
    if len(parts) <= 1:
        return [{"text": text, "bbox": (x1, y1, x2, y2),
                 "reading_order": block.get("reading_order"),
                 "confidence": block.get("confidence", 0.0)}]

    span = max(1, x2 - x1)
    # +1 per gap, so the spaces between words are accounted for.
    total_chars = sum(len(p) for p in parts) + (len(parts) - 1)
    words, cursor = [], 0
    for part in parts:
        start = x1 + span * cursor / total_chars
        cursor += len(part)
        end = x1 + span * cursor / total_chars
        cursor += 1  # the space
        words.append({
            "text": part,
            "bbox": (int(round(start)), y1, int(round(end)), y2),
            "reading_order": block.get("reading_order"),
            "confidence": block.get("confidence", 0.0),
        })
    return words


def normalise_box(box: tuple, width: int, height: int) -> list[int]:
    """LayoutLM-family models expect boxes on a 0-1000 grid."""
    x1, y1, x2, y2 = box
    return [
        max(0, min(1000, int(1000 * x1 / max(width, 1)))),
        max(0, min(1000, int(1000 * y1 / max(height, 1)))),
        max(0, min(1000, int(1000 * x2 / max(width, 1)))),
        max(0, min(1000, int(1000 * y2 / max(height, 1)))),
    ]


def build_page(cache: dict, annotation: dict) -> dict | None:
    blocks = cache.get("blocks") or []
    if not blocks:
        return None

    width, height = cache["prepared_size"]
    scale_x, scale_y = cache["scale_x"], cache["scale_y"]

    # Ground-truth boxes are in ORIGINAL image coordinates; OCR boxes are in
    # PREPARED coordinates. Preprocessing may upscale, so one set has to move
    # into the other's frame before any overlap means anything.
    # Reconstruct the deskew the pipeline applied, so ground truth can be
    # mapped through the same geometry the OCR boxes went through.
    matrix = None
    angle = float(cache.get("skew_angle") or 0.0)
    if abs(angle) >= 0.15:
        original_width, original_height = cache["original_size"]
        matrix = deskew_matrix(angle, original_width, original_height)

    targets = []
    for entry in annotation.get("fields", []):
        if entry["field"] not in LABEL_TO_ID and f"B-{entry['field']}" not in LABEL_TO_ID:
            continue
        if f"B-{entry['field']}" not in LABEL_TO_ID:
            continue
        targets.append({
            "field": entry["field"],
            "box": map_box_to_prepared(entry["bbox"], matrix, scale_x, scale_y),
            "row": entry.get("row"),
            "matched": False,
        })

    words, boxes, labels = [], [], []
    # Reading order, so B- and I- mean something: a value's first word must
    # come first, or every multi-word value is labelled inside-out.
    ordered = sorted(
        blocks,
        key=lambda b: (b.get("reading_order") if b.get("reading_order") is not None
                       else (b["bbox"][1], b["bbox"][0])),
    )

    units = [word for block in ordered for word in split_into_words(block)]
    words = [u["text"] for u in units]
    boxes_px = [tuple(u["bbox"]) for u in units]
    labels = [LABEL_TO_ID["O"]] * len(units)

    # FIELD-first, not word-first.
    #
    # Assigning each word to its best-overlapping field let a word claim a
    # field it merely brushed: on DOC-00001 the village 'रामपुर' came out
    # labelled B-DISTRICT, and the model was then trained to believe it. Going
    # the other way -- each field claims the words that are actually inside it
    # -- cannot produce that, because a field only ever labels words within its
    # own box.
    #
    # Smallest fields first: a small value box sitting inside a larger one
    # should win its own words rather than lose them to the container.
    claimed: set[int] = set()
    for target in sorted(targets, key=lambda t: (t["box"][2] - t["box"][0]) *
                                                (t["box"][3] - t["box"][1])):
        inside = [
            i for i, box in enumerate(boxes_px)
            if i not in claimed and containment(box, target["box"]) >= MIN_CONTAINMENT
        ]
        if not inside:
            # Nothing sits inside the value: either OCR missed it, or OCR
            # returned one block spanning the whole line. Fall back to the
            # single block that best covers the field box, and only if it
            # covers most of it.
            best, score = None, 0.0
            for i, box in enumerate(boxes_px):
                if i in claimed:
                    continue
                covered = coverage(box, target["box"])
                if covered > score:
                    best, score = i, covered
            if best is None or score < 0.6:
                continue
            inside = [best]

        target["matched"] = True
        for position, index in enumerate(sorted(inside)):
            labels[index] = LABEL_TO_ID[
                f"{'B' if position == 0 else 'I'}-{target['field']}"
            ]
            claimed.add(index)

    boxes = [normalise_box(b, width, height) for b in boxes_px]

    return {
        "document_id": cache["document_id"],
        "split": cache["split"],
        "image": annotation.get("_image"),
        "width": width,
        "height": height,
        "words": words,
        "boxes": boxes,
        "labels": labels,
        "difficulty": annotation.get("difficulty"),
        # Fields whose box no OCR word reached. The ceiling on recall.
        "unreachable_fields": [t["field"] for t in targets if not t["matched"]],
        "total_fields": len(targets),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", default="v1")
    parser.add_argument("--cache", default="ocr-cache")
    parser.add_argument("--out", default="extraction-dataset")
    args = parser.parse_args()

    cache_root = DATASETS / args.cache
    if not cache_root.exists():
        raise SystemExit(f"missing {cache_root}; run scripts/cache_ocr.py first")

    out_root = DATASETS / args.out
    out_root.mkdir(parents=True, exist_ok=True)
    (out_root / "labels.json").write_text(json.dumps(LABELS, indent=1))

    per_split: dict[str, list] = {}
    label_counts: Counter[str] = Counter()
    unreachable: Counter[str] = Counter()
    total_fields = 0

    for split in ("train", "val", "test"):
        rows = [
            json.loads(line) for line in
            (DATASETS / "splits" / f"{split}.{args.profile}.jsonl").read_text().splitlines()
            if line.strip()
        ]
        examples = []
        for row in rows:
            cache_file = cache_root / f"{row['document_id']}.json"
            if not cache_file.exists():
                continue
            cache = json.loads(cache_file.read_text())
            annotation = json.loads((DATASETS / row["annotation"]).read_text())
            annotation["_image"] = row["degraded_image"]

            page = build_page(cache, annotation)
            if page is None:
                continue
            examples.append(page)
            for label_id in page["labels"]:
                label_counts[LABELS[label_id]] += 1
            unreachable.update(page["unreachable_fields"])
            total_fields += page["total_fields"]

        per_split[split] = examples
        path = out_root / f"{split}.jsonl"
        path.write_text("\n".join(json.dumps(e, ensure_ascii=False) for e in examples) + "\n")

    print(f"wrote {out_root}")
    for split, examples in per_split.items():
        words = sum(len(e["words"]) for e in examples)
        print(f"  {split:5s} {len(examples):4d} pages, {words:6d} words")

    labelled = sum(v for k, v in label_counts.items() if k != "O")
    print(f"\n  labelled words: {labelled} of {sum(label_counts.values())}")
    missed = sum(unreachable.values())
    print(f"  fields OCR never reached: {missed} of {total_fields} "
          f"({missed / max(total_fields, 1):.1%}) -- the ceiling on recall")
    for field, count in unreachable.most_common(8):
        print(f"     {field:12s} {count}")


if __name__ == "__main__":
    main()
