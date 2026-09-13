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

#: Minimum share of an OCR word's area that must fall inside a field's
#: ground-truth box for the word to carry that field's label.
#:
#: Measured against the word, not the field: a field box usually spans several
#: words, so intersection-over-union would reject every one of them. What
#: matters is "is this word inside that value", not "is this word that value".
MIN_CONTAINMENT = 0.45


def overlap(a: tuple, b: tuple) -> float:
    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b
    ix1, iy1 = max(ax1, bx1), max(ay1, by1)
    ix2, iy2 = min(ax2, bx2), min(ay2, by2)
    if ix2 <= ix1 or iy2 <= iy1:
        return 0.0
    intersection = (ix2 - ix1) * (iy2 - iy1)
    area = max(1, (ax2 - ax1) * (ay2 - ay1))
    return intersection / area


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
    targets = []
    for entry in annotation.get("fields", []):
        if entry["field"] not in LABEL_TO_ID and f"B-{entry['field']}" not in LABEL_TO_ID:
            continue
        if f"B-{entry['field']}" not in LABEL_TO_ID:
            continue
        x1, y1, x2, y2 = entry["bbox"]
        targets.append({
            "field": entry["field"],
            "box": (x1 * scale_x, y1 * scale_y, x2 * scale_x, y2 * scale_y),
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

    open_target: int | None = None
    for block in ordered:
        text = (block.get("text") or "").strip()
        if not text:
            continue
        box = tuple(block["bbox"])

        best_index, best_score = None, 0.0
        for index, target in enumerate(targets):
            score = overlap(box, target["box"])
            if score > best_score:
                best_index, best_score = index, score

        if best_index is not None and best_score >= MIN_CONTAINMENT:
            target = targets[best_index]
            target["matched"] = True
            prefix = "I" if open_target == best_index else "B"
            labels.append(LABEL_TO_ID[f"{prefix}-{target['field']}"])
            open_target = best_index
        else:
            labels.append(LABEL_TO_ID["O"])
            open_target = None

        words.append(text)
        boxes.append(normalise_box(box, width, height))

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
