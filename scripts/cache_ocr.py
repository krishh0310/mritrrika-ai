#!/usr/bin/env python
"""Cache real OCR output for every page in a split (§65, §66).

    python scripts/cache_ocr.py --profile v1

Why this exists: a field-extraction model must be trained on what it will
actually SEE. The generator's annotations contain perfect text at perfect
boxes; PaddleOCR on a degraded page produces neither (measured CER 0.391).
Training on ground-truth text and running inference on real OCR is the classic
way to build a model that scores beautifully in training and fails in
production -- the model learns to read text the pipeline never hands it.

So this runs the real pipeline -- quality assessment, OpenCV enhancement,
PaddleOCR -- over every page once, and stores the blocks. Training then sees
exactly the input the worker sees.

The cache also makes the training loop cheap to iterate on: OCR is minutes per
hundred pages, everything after it is seconds.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DATASETS = REPO_ROOT / "datasets"
sys.path.insert(0, str(REPO_ROOT / "services" / "ai-worker"))

import cv2  # noqa: E402
from ocr.provider import build_default_engine  # noqa: E402
from preprocessing.enhance import enhance_for_quality  # noqa: E402
from quality.assessment import assess  # noqa: E402

SPLITS = ("train", "val", "test")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", default="v1")
    parser.add_argument("--splits", nargs="*", default=list(SPLITS))
    parser.add_argument("--out", default="ocr-cache")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--force", action="store_true",
                        help="re-OCR pages already cached")
    args = parser.parse_args()

    out_root = DATASETS / args.out
    out_root.mkdir(parents=True, exist_ok=True)
    engine = build_default_engine()

    rows = []
    for split in args.splits:
        path = DATASETS / "splits" / f"{split}.{args.profile}.jsonl"
        if not path.exists():
            raise SystemExit(f"missing {path}; run scripts/split_dataset.py")
        for line in path.read_text().splitlines():
            if line.strip():
                rows.append((split, json.loads(line)))
    if args.limit:
        rows = rows[: args.limit]

    started = time.time()
    done = skipped = failed = 0

    for index, (split, row) in enumerate(rows, 1):
        document_id = row["document_id"]
        target = out_root / f"{document_id}.json"
        if target.exists() and not args.force:
            skipped += 1
            continue

        image = cv2.imread(str(DATASETS / row["degraded_image"]))
        if image is None:
            failed += 1
            continue

        prepared = enhance_for_quality(image, assess(image)).image
        try:
            result = engine.recognize(prepared)
        except Exception as exc:  # a page the engine refuses is recorded, not dropped
            target.write_text(json.dumps(
                {"document_id": document_id, "split": split,
                 "error": str(exc), "blocks": []}, ensure_ascii=False))
            failed += 1
            continue

        target.write_text(json.dumps({
            "document_id": document_id,
            "split": split,
            # Blocks are in PREPARED-image coordinates. The scale factors map
            # the annotation's original-image boxes into the same frame, which
            # is what makes label alignment possible at all.
            "prepared_size": [prepared.shape[1], prepared.shape[0]],
            "original_size": [image.shape[1], image.shape[0]],
            "scale_x": prepared.shape[1] / image.shape[1],
            "scale_y": prepared.shape[0] / image.shape[0],
            "provider": result.provider,
            "degraded": result.degraded,
            "blocks": [
                {"text": b.text, "confidence": round(b.confidence, 4),
                 "bbox": list(b.bbox), "reading_order": b.reading_order}
                for b in result.blocks
            ],
        }, ensure_ascii=False))
        done += 1

        if index % 20 == 0:
            rate = (time.time() - started) / max(done, 1)
            remaining = (len(rows) - index) * rate
            print(f"  {index}/{len(rows)}  ({rate:.1f}s/page, "
                  f"~{remaining / 60:.0f} min left)", flush=True)

    print(f"\ncached {done}, skipped {skipped}, failed {failed} -> {out_root}")


if __name__ == "__main__":
    main()
