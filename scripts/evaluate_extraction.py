#!/usr/bin/env python
"""Measure OCR + extraction against ground truth (§65).

    python scripts/evaluate_extraction.py --split test

Reports per-field and per-difficulty precision / recall / F1, plus OCR CER.
No accuracy figure is claimed anywhere in this project until this harness
produces it (§69).

Ground truth comes from the generator's annotations, which were written BEFORE
the page was rendered (§44) -- never from reading the image back.
"""

from __future__ import annotations

import argparse
import json
import sys
import unicodedata
from collections import defaultdict
from dataclasses import replace as dc_replace
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DATASETS = REPO_ROOT / "datasets"
sys.path.insert(0, str(REPO_ROOT / "services" / "ai-worker"))

import cv2  # noqa: E402
from extraction.field_extractor import extract  # noqa: E402
from normalization.normalizers import normalize_field  # noqa: E402
from ocr.provider import build_default_engine  # noqa: E402
from preprocessing.enhance import enhance_for_quality  # noqa: E402
from quality.assessment import assess  # noqa: E402

#: Fields the extractor targets. OWNER/GUARDIAN/SHARE are multi-valued (one
#: per owners-table row).
SCALAR_FIELDS = [
    "DISTRICT", "TEHSIL", "VILLAGE", "KHASRA", "KHATA",
    "AREA", "AREA_UNIT", "LAND_CLASS", "RECORD_YEAR", "MUTATION", "DATE",
]
#: GUARDIAN was annotated on every page but never scored, so the extractor
#: could return 'ति' -- the tail of the column heading 'पिता / पति' -- for
#: every document without any number here moving.
MULTI_FIELDS = ["OWNER", "GUARDIAN", "SHARE"]


def nfc(text: str | None) -> str:
    return unicodedata.normalize("NFC", (text or "").strip())


def edit_distance(a: str, b: str) -> int:
    if a == b:
        return 0
    previous = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        current = [i]
        for j, cb in enumerate(b, 1):
            current.append(
                min(previous[j] + 1, current[j - 1] + 1, previous[j - 1] + (ca != cb))
            )
        previous = current
    return previous[-1]


def load_split(name: str, profile: str) -> list[dict]:
    # Splits are namespaced by profile; an un-namespaced path silently pointed
    # at a file that has not existed since the dataset gained a second profile.
    path = DATASETS / "splits" / f"{name}.{profile}.jsonl"
    if not path.exists():
        raise SystemExit(f"missing {path}; run scripts/split_dataset.py")
    return [json.loads(line) for line in path.read_text().splitlines() if line]


def truth_for(doc: dict) -> tuple[dict[str, str], dict[str, list[str]]]:
    """Ground-truth values, normalised the same way the extractor's are."""
    annotation = json.loads((DATASETS / doc["annotation"]).read_text())
    scalars: dict[str, str] = {}
    multi: dict[str, list[str]] = defaultdict(list)
    for entry in annotation["fields"]:
        field = entry["field"]
        value = normalize_field(field, entry.get("raw_value"))
        if value is None:
            continue
        if field in MULTI_FIELDS:
            multi[field].append(nfc(value))
        elif field not in scalars:
            scalars[field] = nfc(value)
    return scalars, dict(multi)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--split", default="test", choices=["train", "val", "test"])
    parser.add_argument("--profile", default="v1")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--det-model", default=None,
                        help="text detection model (default: the pipeline's DETECTION_MODEL)")
    parser.add_argument("--no-preprocess", action="store_true",
                        help="skip OpenCV enhancement, to measure its effect")
    parser.add_argument("--layout", action="store_true",
                        help="scope extraction with the YOLOv8 region detector")
    parser.add_argument("--tag", default=None,
                        help="suffix for the report filename, to keep runs apart")
    args = parser.parse_args()

    docs = load_split(args.split, args.profile)
    if args.limit:
        docs = docs[: args.limit]

    engine = (
        build_default_engine(detection_model=args.det_model)
        if args.det_model else build_default_engine()
    )

    # Built once: loading the weights per page would dominate the run.
    detector = None
    if args.layout:
        from layout import build_default_detector

        detector = build_default_detector()
        if not detector.available:
            raise SystemExit(
                f"--layout requested but the detector is unavailable: "
                f"{detector.unavailable_reason}"
            )
        print("layout scoping: ON")

    per_field = defaultdict(lambda: {"tp": 0, "fp": 0, "fn": 0})
    per_tier = defaultdict(lambda: {"tp": 0, "fp": 0, "fn": 0})
    cer_num = cer_den = 0
    ocr_conf_total = ocr_blocks = 0

    for index, doc in enumerate(docs, 1):
        image = cv2.imread(str(DATASETS / doc["degraded_image"]))
        if image is None:
            continue

        if args.no_preprocess:
            prepared = image
        else:
            prepared = enhance_for_quality(image, assess(image)).image
        result = engine.recognize(prepared)
        ocr_conf_total += sum(b.confidence for b in result.blocks)
        ocr_blocks += len(result.blocks)

        # Detection runs on the ORIGINAL page (what the detector was trained
        # on), then the boxes are scaled into prepared coordinates so they
        # share a frame with the OCR blocks.
        regions = []
        if detector is not None:
            sx = prepared.shape[1] / image.shape[1]
            sy = prepared.shape[0] / image.shape[0]
            for region in detector.detect(image):
                x1, y1, x2, y2 = region.bbox
                regions.append(dc_replace(region, bbox=(
                    round(x1 * sx), round(y1 * sy),
                    round(x2 * sx), round(y2 * sy),
                )))

        predicted_all = extract(result.blocks, prepared.shape[1], regions=regions)
        truth_scalars, truth_multi = truth_for(doc)
        tier = doc["difficulty"]

        predicted_scalars: dict[str, str] = {}
        predicted_multi: dict[str, list[str]] = defaultdict(list)
        for value in predicted_all.values:
            normalized = normalize_field(value.field, value.raw_value)
            if normalized is None:
                continue
            if value.field in MULTI_FIELDS:
                predicted_multi[value.field].append(nfc(normalized))
            elif value.field not in predicted_scalars:
                predicted_scalars[value.field] = nfc(normalized)

        for field in SCALAR_FIELDS:
            expected = truth_scalars.get(field)
            got = predicted_scalars.get(field)
            if expected is not None:
                cer_num += edit_distance(got or "", expected)
                cer_den += len(expected)
            if expected is None and got is None:
                continue
            if expected is not None and got == expected:
                per_field[field]["tp"] += 1
                per_tier[tier]["tp"] += 1
            else:
                if got is not None:
                    per_field[field]["fp"] += 1
                    per_tier[tier]["fp"] += 1
                if expected is not None:
                    per_field[field]["fn"] += 1
                    per_tier[tier]["fn"] += 1

        for field in MULTI_FIELDS:
            expected_set = set(truth_multi.get(field, []))
            got_set = set(predicted_multi.get(field, []))
            per_field[field]["tp"] += len(expected_set & got_set)
            per_field[field]["fp"] += len(got_set - expected_set)
            per_field[field]["fn"] += len(expected_set - got_set)
            per_tier[tier]["tp"] += len(expected_set & got_set)
            per_tier[tier]["fp"] += len(got_set - expected_set)
            per_tier[tier]["fn"] += len(expected_set - got_set)

        if index % 5 == 0:
            print(f"  {index}/{len(docs)}", file=sys.stderr)

    def prf(counts: dict) -> tuple[float, float, float]:
        tp, fp, fn = counts["tp"], counts["fp"], counts["fn"]
        precision = tp / (tp + fp) if tp + fp else 0.0
        recall = tp / (tp + fn) if tp + fn else 0.0
        f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
        return precision, recall, f1

    print(f"\nExtraction evaluation -- split '{args.split}', {len(docs)} documents")
    print("(synthetic data; these numbers do not transfer to real records)\n")

    print(f"{'field':14s} {'P':>6s} {'R':>6s} {'F1':>6s} {'tp':>4s} {'fp':>4s} {'fn':>4s}")
    for field in SCALAR_FIELDS + MULTI_FIELDS:
        counts = per_field[field]
        if not any(counts.values()):
            continue
        p, r, f = prf(counts)
        print(f"{field:14s} {p:6.2f} {r:6.2f} {f:6.2f} "
              f"{counts['tp']:4d} {counts['fp']:4d} {counts['fn']:4d}")

    overall = {k: sum(per_field[f][k] for f in per_field) for k in ("tp", "fp", "fn")}
    p, r, f = prf(overall)
    print(f"\n{'OVERALL':14s} {p:6.2f} {r:6.2f} {f:6.2f}")

    print(f"\n{'difficulty':14s} {'P':>6s} {'R':>6s} {'F1':>6s}   n")
    for tier in ("clean", "moderate", "hard", "extreme"):
        counts = per_tier.get(tier)
        if not counts:
            continue
        p, r, f = prf(counts)
        n = sum(1 for d in docs if d["difficulty"] == tier)
        print(f"{tier:14s} {p:6.2f} {r:6.2f} {f:6.2f}   {n}")

    cer = cer_num / cer_den if cer_den else 0.0
    mean_conf = ocr_conf_total / ocr_blocks if ocr_blocks else 0.0
    print(f"\nfield-level CER      {cer:.3f}")
    print(f"mean OCR confidence  {mean_conf:.3f}")

    suffix = f".{args.tag}" if args.tag else ""
    report = (
        DATASETS / "reports" / f"extraction_eval.{args.split}.{args.profile}{suffix}.json"
    )
    report.write_text(json.dumps({
        "split": args.split,
        "layout_scoping": bool(args.layout),
        "documents": len(docs),
        "per_field": {k: dict(v) for k, v in per_field.items()},
        "per_difficulty": {k: dict(v) for k, v in per_tier.items()},
        "overall": overall,
        "cer": round(cer, 4),
        "mean_ocr_confidence": round(mean_conf, 4),
        "note": "synthetic data only; not a real-world accuracy claim",
    }, indent=2, ensure_ascii=False))
    print(f"\nwrote {report.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
