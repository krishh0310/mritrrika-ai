#!/usr/bin/env python
"""Export reviewed verifier corrections as training pages (§30, §67).

    python scripts/export_feedback_dataset.py
    python scripts/train_extractor.py            # picks up feedback.jsonl

This is the step that turns "a verifier fixed a field" into "the model saw
the fix". Only corrections a reviewer ACCEPTED, on documents a verifier has
finished with, are exported (see feedback_service for why both conditions).

Each exported page is labelled the same way the synthetic corpus is --
build_extraction_dataset.build_page, over the page's real OCR blocks -- so a
feedback page and a generated page are the same kind of example and can be
mixed in one training run. The difference is where the field boxes come from:

  * a field the AI got right: the box the AI extracted it from.
  * a field a verifier CORRECTED: the OCR block that actually carries the
    corrected value, when one does. The AI's own box is exactly the wrong
    answer when it read the wrong block, so it is used only when no block
    carries the corrected value (typically: OCR misread the right block, so
    the location was right and the text was not).

Every accepted row is exported on every run, so the file always reflects the
current pool; each row is stamped with the first dataset tag it went into.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "packages" / "domain"))
sys.path.insert(0, str(REPO_ROOT / "apps" / "api"))
sys.path.insert(0, str(REPO_ROOT / "services" / "ai-worker"))

from app.db import SessionLocal  # noqa: E402
from app.services import feedback_service  # noqa: E402
from build_extraction_dataset import LABELS, build_page  # noqa: E402
from normalization.normalizers import canonicalise_indic, normalize_field  # noqa: E402

DEFAULT_OUT = REPO_ROOT / "datasets" / "extraction-dataset" / "feedback.jsonl"


def _centre(box) -> tuple[float, float]:
    return ((box[0] + box[2]) / 2, (box[1] + box[3]) / 2)


def locate(field: dict, blocks: list[dict]) -> tuple[list[int] | None, str]:
    """The box to label for one field, and how it was chosen."""
    if not field["corrected"]:
        return field["bbox"], "extraction-box"

    wanted = canonicalise_indic(field["value"] or "").strip()
    carriers = [
        block for block in blocks
        if normalize_field(field["field"], block["text"]) == field["value"]
        or (len(wanted) >= 2 and wanted in canonicalise_indic(block["text"]))
    ]
    if carriers:
        if field["bbox"] is None:
            return carriers[0]["bbox"], "corrected-value-block"
        # Several blocks can carry a short value ('1/2' in every share cell):
        # the one nearest where the AI looked is the one it should have read.
        ax, ay = _centre(field["bbox"])
        nearest = min(
            carriers,
            key=lambda b: (_centre(b["bbox"])[0] - ax) ** 2 + (_centre(b["bbox"])[1] - ay) ** 2,
        )
        return nearest["bbox"], "corrected-value-block"
    return field["bbox"], "extraction-box-fallback"


def to_training_row(page: dict, tag: str, sources: Counter) -> dict | None:
    blocks = page["blocks"]
    if not blocks:
        return None
    width = page["width"] or max(b["bbox"][2] for b in blocks)
    height = page["height"] or max(b["bbox"][3] for b in blocks)

    annotation_fields = []
    for field in page["fields"]:
        box, source = locate(field, blocks)
        if box is None:
            sources["no-box"] += 1
            continue
        sources[source] += 1
        annotation_fields.append({"field": field["field"], "bbox": box, "row": field["row"]})

    # Page coordinates throughout: stored OCR boxes are already mapped back to
    # the original page, so there is no preprocessing scale or skew to undo.
    cache = {
        "document_id": page["document_id"],
        "split": "feedback",
        "blocks": blocks,
        "prepared_size": [width, height],
        "original_size": [width, height],
        "scale_x": 1.0,
        "scale_y": 1.0,
        "skew_angle": 0.0,
    }
    row = build_page(cache, {"fields": annotation_fields, "_image": None})
    if row is None:
        return None
    row.update({
        "source": "verifier-feedback",
        "dataset_tag": tag,
        "page_number": page["page_number"],
        "feedback_ids": page["feedback_ids"],
    })
    return row


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    parser.add_argument(
        "--tag", default=f"feedback-{datetime.now(UTC):%Y%m%dT%H%M%SZ}",
        help="recorded on each feedback row the first time it is exported",
    )
    parser.add_argument("--dry-run", action="store_true",
                        help="report what would be exported; write and stamp nothing")
    args = parser.parse_args()

    sources: Counter = Counter()
    with SessionLocal() as session:
        readiness = feedback_service.readiness(session)
        pages = feedback_service.training_pages(session)
        rows = [r for r in (to_training_row(p, args.tag, sources) for p in pages) if r]

        print(f"accepted corrections: {readiness.accepted} "
              f"(threshold for a worthwhile run: {readiness.threshold})")
        print(f"pages exported:       {len(rows)}")
        labelled = sum(1 for r in rows for label in r["labels"] if label != 0)
        print(f"labelled words:       {labelled}")
        for source, count in sorted(sources.items()):
            print(f"  fields via {source:26s} {count}")
        unreachable = Counter(f for r in rows for f in r["unreachable_fields"])
        if unreachable:
            print("  fields no OCR word reached (not learnable from these pages):")
            for field, count in unreachable.most_common():
                print(f"     {field:12s} {count}")

        if not readiness.ready:
            print(f"\nnote: below the {readiness.threshold}-row threshold. The file is "
                  "still written; training on it is a judgement call, not a default.")

        if args.dry_run:
            print("\ndry run: nothing written")
            return 0

        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(
            "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows)
        )
        # The label vocabulary the rows were written against. train_extractor
        # refuses a feedback file whose vocabulary differs from its own.
        out.with_suffix(".labels.json").write_text(json.dumps(LABELS, indent=1))

        stamped = feedback_service.mark_included(
            session, [fid for r in rows for fid in r["feedback_ids"]], args.tag
        )
        print(f"\nwrote {out}")
        print(f"stamped {stamped} feedback rows with {args.tag}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
