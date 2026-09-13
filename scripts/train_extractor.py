#!/usr/bin/env python
"""Fine-tune the layout-aware field extractor (§6, §66).

    python scripts/cache_ocr.py --profile v1
    python scripts/build_extraction_dataset.py --profile v1
    python scripts/train_extractor.py --epochs 20

Trains on what the pipeline actually produces -- real PaddleOCR output over
degraded pages -- not on the generator's perfect text. See cache_ocr.py for why
that distinction decides whether the resulting number means anything.

The metric printed here is token-level and is NOT the result. The result comes
from scripts/evaluate_extraction.py --extractor model, which scores whole
fields against ground truth using the same harness the rule-based extractor is
scored with. A token-level F1 flatters any sequence labeller, because most
tokens are O.
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from datetime import UTC, datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DATASETS = REPO_ROOT / "datasets"
CHECKPOINTS = REPO_ROOT / "models" / "checkpoints"
sys.path.insert(0, str(REPO_ROOT / "services" / "ai-worker"))

import torch  # noqa: E402
from extraction.layout_model import (  # noqa: E402
    BASE_MODEL,
    LABELS,
    LayoutAwareTokenClassifier,
)
from torch.utils.data import DataLoader, Dataset  # noqa: E402

MAX_LENGTH = 512

#: Pages average ~60 tokens. Padding every one to 512 spent roughly eight times
#: the compute on [PAD], which is why the first run underfitted: it could
#: afford only 20 epochs in the time dynamic padding buys 100+.


class PageDataset(Dataset):
    def __init__(self, path: Path, tokenizer):
        self.rows = [
            json.loads(line) for line in path.read_text().splitlines() if line.strip()
        ]
        self.tokenizer = tokenizer

    def __len__(self) -> int:
        return len(self.rows)

    def __getitem__(self, index: int):
        row = self.rows[index]
        encoding = self.tokenizer(
            row["words"],
            is_split_into_words=True,
            truncation=True,
            max_length=MAX_LENGTH,
            return_tensors="pt",
        )
        word_ids = encoding.word_ids(0)

        labels, boxes = [], []
        previous = None
        for word_id in word_ids:
            if word_id is None:
                labels.append(-100)
                # Special tokens get the zero box: they belong to no position
                # on the page, and giving them a real one would teach the model
                # that [CLS] sits in the top-left corner of every document.
                boxes.append([0, 0, 0, 0])
                continue
            boxes.append(row["boxes"][word_id])
            # Label only the FIRST sub-token of a word. Labelling every piece
            # weights long words more heavily purely because the tokenizer
            # split them further.
            labels.append(row["labels"][word_id] if word_id != previous else -100)
            previous = word_id

        return {
            "input_ids": encoding["input_ids"][0],
            "attention_mask": encoding["attention_mask"][0],
            "boxes": torch.tensor(boxes, dtype=torch.long),
            "labels": torch.tensor(labels, dtype=torch.long),
        }


def collate(batch: list[dict]) -> dict:
    """Pad to the longest page in the BATCH, not to the model maximum."""
    longest = max(item["input_ids"].shape[0] for item in batch)
    out: dict[str, list] = {k: [] for k in batch[0]}
    for item in batch:
        pad = longest - item["input_ids"].shape[0]
        out["input_ids"].append(
            torch.nn.functional.pad(item["input_ids"], (0, pad), value=0))
        out["attention_mask"].append(
            torch.nn.functional.pad(item["attention_mask"], (0, pad), value=0))
        # -100 so padding is never supervised.
        out["labels"].append(
            torch.nn.functional.pad(item["labels"], (0, pad), value=-100))
        out["boxes"].append(
            torch.nn.functional.pad(item["boxes"], (0, 0, 0, pad), value=0))
    return {k: torch.stack(v) for k, v in out.items()}


def evaluate(model, loader, device) -> dict:
    """Token-level precision/recall/F1 over non-O labels."""
    model.eval()
    tp = fp = fn = 0
    with torch.no_grad():
        for batch in loader:
            batch = {k: v.to(device) for k, v in batch.items()}
            logits = model(batch["input_ids"], batch["attention_mask"],
                           batch["boxes"])["logits"]
            predictions = logits.argmax(-1)
            labels = batch["labels"]
            mask = labels != -100

            predicted = predictions[mask]
            actual = labels[mask]
            # O is class 0; everything else is a field.
            tp += int(((predicted == actual) & (actual != 0)).sum())
            fp += int(((predicted != actual) & (predicted != 0)).sum())
            fn += int(((predicted != actual) & (actual != 0)).sum())

    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {"precision": precision, "recall": recall, "f1": f1,
            "tp": tp, "fp": fp, "fn": fn}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", default=str(DATASETS / "extraction-dataset"))
    parser.add_argument("--epochs", type=int, default=80)
    parser.add_argument("--batch", type=int, default=8)
    parser.add_argument("--lr", type=float, default=3e-4)
    parser.add_argument("--device", default=None)
    parser.add_argument("--name", default="extractor-v1")
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    random.seed(args.seed)
    torch.manual_seed(args.seed)

    data = Path(args.data)
    if not (data / "train.jsonl").exists():
        raise SystemExit(
            f"missing {data}/train.jsonl; run scripts/build_extraction_dataset.py"
        )

    device = args.device or (
        "mps" if torch.backends.mps.is_available()
        else "cuda" if torch.cuda.is_available() else "cpu"
    )
    print(f"training on device={device}")

    from transformers import AutoTokenizer

    tokenizer = AutoTokenizer.from_pretrained(BASE_MODEL)
    train = PageDataset(data / "train.jsonl", tokenizer)
    val = PageDataset(data / "val.jsonl", tokenizer)
    print(f"train {len(train)} pages, val {len(val)} pages")

    train_loader = DataLoader(
        train, batch_size=args.batch, shuffle=True, collate_fn=collate)
    val_loader = DataLoader(val, batch_size=args.batch, collate_fn=collate)

    model = LayoutAwareTokenClassifier().to(device)
    optimiser = torch.optim.AdamW(model.parameters(), lr=args.lr)
    total_steps = max(1, len(train_loader) * args.epochs)
    scheduler = torch.optim.lr_scheduler.OneCycleLR(
        optimiser, max_lr=args.lr, total_steps=total_steps, pct_start=0.1
    )

    run_dir = CHECKPOINTS / "extraction" / args.name
    run_dir.mkdir(parents=True, exist_ok=True)
    best_f1 = -1.0
    history = []

    for epoch in range(1, args.epochs + 1):
        model.train()
        running = 0.0
        for batch in train_loader:
            batch = {k: v.to(device) for k, v in batch.items()}
            out = model(batch["input_ids"], batch["attention_mask"],
                        batch["boxes"], batch["labels"])
            out["loss"].backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            optimiser.step()
            scheduler.step()
            optimiser.zero_grad()
            running += out["loss"].item()

        metrics = evaluate(model, val_loader, device)
        history.append({"epoch": epoch, "loss": running / len(train_loader), **metrics})
        # flush: redirected stdout is block-buffered, so without this a run
        # that is progressing normally looks hung for its whole duration.
        print(f"  epoch {epoch:3d}  loss {running / len(train_loader):.4f}  "
              f"val P {metrics['precision']:.3f} R {metrics['recall']:.3f} "
              f"F1 {metrics['f1']:.3f}", flush=True)

        if metrics["f1"] > best_f1:
            best_f1 = metrics["f1"]
            torch.save({
                "model_state": model.state_dict(),
                "labels": LABELS,
                "base_model": BASE_MODEL,
                "epoch": epoch,
                "val_token_f1": metrics["f1"],
            }, run_dir / "best.pt")
            tokenizer.save_pretrained(run_dir / "tokenizer")

    report = {
        "trained_at": datetime.now(UTC).isoformat(),
        "base_model": BASE_MODEL,
        "epochs": args.epochs,
        "train_pages": len(train),
        "val_pages": len(val),
        "best_val_token_f1": round(best_f1, 4),
        "history": history,
        "note": (
            "Token-level metric only, and it flatters any sequence labeller "
            "because most tokens are O. The real number comes from "
            "scripts/evaluate_extraction.py --extractor model."
        ),
    }
    out = DATASETS / "reports" / f"extractor_train.{args.name}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=1) + "\n")

    print(f"\nbest val token F1 {best_f1:.4f}")
    print(f"weights: {run_dir / 'best.pt'}")
    print(f"report:  {out}")


if __name__ == "__main__":
    main()
