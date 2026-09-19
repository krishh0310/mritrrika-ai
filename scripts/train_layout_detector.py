#!/usr/bin/env python
"""Fine-tune YOLO11 to localise structural regions on a record page (§6).

    python scripts/export_layout_dataset.py --profile v1
    python scripts/train_layout_detector.py --epochs 60

Why a detector at all: extraction is label-anchored (see
services/ai-worker/extraction/field_extractor.py), and a label anchor is only
as good as the region it is searched within. Knowing where the owners table
ends stops a KHASRA label in the header from claiming a value out of a table
row three hundred pixels below it.

What this is NOT: a page classifier, a text recogniser, or a replacement for
OCR. It emits two region types -- header and table -- and nothing downstream is
permitted to treat a region as evidence of content.

Honesty constraints (§69, §64):

  * The reported numbers come from `model.val()` on the held-out val split of
    the SAME grouped split the extractor is measured on. No figure is written
    down that this script did not produce.
  * The corpus is 500 synthetic pages with two classes. That is small. The
    metrics file records the corpus size next to the metric so the number is
    never quoted without it.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "services" / "ai-worker"))

from config.cv_config import LAYOUT_CHECKPOINT, YOLO_MODEL  # noqa: E402

DATASETS = REPO_ROOT / "datasets"
CHECKPOINTS = REPO_ROOT / "models" / "checkpoints"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", default=str(DATASETS / "yolo-layout" / "data.yaml"))
    parser.add_argument("--model", default=YOLO_MODEL,
                        help="pretrained weights to fine-tune from")
    parser.add_argument("--epochs", type=int, default=60)
    parser.add_argument("--imgsz", type=int, default=960,
                        help="pages are ~1250px wide; 640 loses thin table rules")
    parser.add_argument("--batch", type=int, default=8)
    parser.add_argument("--device", default=None,
                        help="'mps' on Apple Silicon, 'cpu', or a CUDA index")
    parser.add_argument("--name", default=LAYOUT_CHECKPOINT)
    parser.add_argument("--eval-only", action="store_true",
                        help="skip training; validate the run's existing best.pt")
    args = parser.parse_args()

    data_path = Path(args.data)
    if not data_path.exists():
        raise SystemExit(
            f"missing {data_path}; run scripts/export_layout_dataset.py first"
        )

    from ultralytics import YOLO

    device = args.device
    if device is None:
        import torch
        if torch.backends.mps.is_available():
            device = "mps"
        elif torch.cuda.is_available():
            device = "0"
        else:
            device = "cpu"
    print(f"training on device={device}")

    model = YOLO(args.model)
    if not args.eval_only:
        model.train(
            data=str(data_path),
            epochs=args.epochs,
            imgsz=args.imgsz,
            batch=args.batch,
            device=device,
            project=str(CHECKPOINTS / "layout"),
            name=args.name,
            exist_ok=True,
            # The pages are already degraded by the generator with rotation,
            # perspective and rescale. Letting Ultralytics add its own
            # photometric and flip augmentation on top would train the detector
            # on documents that cannot arrive: a land record is never mirrored.
            fliplr=0.0,
            flipud=0.0,
            mosaic=0.0,
            seed=42,
        )

    # Validate the saved checkpoint from a temporary copy. Ultralytics strips
    # an apostrophe from the path it re-derives after training ("PROTOTYPE'S"
    # -> "PROTOTYPES"), so validating in place failed after a completed run.
    import shutil
    import tempfile

    best = CHECKPOINTS / "layout" / args.name / "weights" / "best.pt"
    with tempfile.TemporaryDirectory() as scratch:
        copy = Path(scratch) / "best.pt"
        shutil.copy(best, copy)
        metrics = YOLO(str(copy)).val(data=str(data_path), split="val", device=device)

    run_dir = CHECKPOINTS / "layout" / args.name
    weights = run_dir / "weights" / "best.pt"

    def per_class(attr: str) -> dict:
        values = getattr(metrics.box, attr, None)
        if values is None:
            return {}
        return {str(metrics.names[i]): round(float(v), 4)
                for i, v in enumerate(values)}

    report = {
        "trained_at": datetime.now(UTC).isoformat(),
        "model": args.model,
        "epochs": args.epochs,
        "imgsz": args.imgsz,
        "weights": str(weights),
        "split": "val",
        "metrics": {
            "map50_95": round(float(metrics.box.map), 4),
            "map50": round(float(metrics.box.map50), 4),
            "precision": round(float(metrics.box.mp), 4),
            "recall": round(float(metrics.box.mr), 4),
        },
        "per_class_map50_95": per_class("maps"),
        "note": (
            "Synthetic corpus only. Two classes (header, table) over 500 "
            "generated pages; not a real-world accuracy claim."
        ),
    }

    out = DATASETS / "reports" / f"layout_eval.{args.name}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=1) + "\n")

    print(json.dumps(report["metrics"], indent=1))
    print(f"weights:  {weights}")
    print(f"report:   {out}")


if __name__ == "__main__":
    main()
