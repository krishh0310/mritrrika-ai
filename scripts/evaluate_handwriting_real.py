#!/usr/bin/env python
"""How well handwriting is read on REAL scans: the only number that counts.

IIIT-HW-Dev test scores say the reader learned handwritten Hindi. This says
whether it reads land records. Two inputs, use either or both:

  --lines DIR   Cropped handwritten lines (any image type) and DIR/labels.tsv,
                one `filename<TAB>exact text` per line. Reports character
                error rate and exact-match for the reader AND for PaddleOCR
                on the same crops, so the comparison is like for like.

  --pages DIR   Whole page scans, each with a same-named .json of the values
                on it, e.g. {"KHASRA": "123/4", "OWNER": "राम प्रसाद"}.
                Runs the full pipeline twice -- with the handwriting models and
                without -- and reports per-field exact matches (after the same
                normalisation the pipeline applies).

    python scripts/evaluate_handwriting_real.py --lines datasets/handwriting/real/lines
    python scripts/evaluate_handwriting_real.py --pages datasets/handwriting/real/pages

  --gemini      Also score Gemini on the same lines (needs GEMINI_API_KEY).
                This SENDS the crops to Google; without the flag nothing leaves
                the machine.

Real records stay local otherwise: datasets/handwriting/ is not tracked.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import unicodedata
from pathlib import Path

import cv2

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "services" / "ai-worker"))
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from train_handwriting import score  # noqa: E402

IMAGE_TYPES = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".webp"}


def _nfc(text: str) -> str:
    return unicodedata.normalize("NFC", " ".join(text.split()))


def evaluate_lines(directory: Path, reader, paddle, gemini=None) -> dict:
    rows = [line.split("\t", 1) for line in
            (directory / "labels.tsv").read_text(encoding="utf-8").splitlines() if "\t" in line]
    reader_pairs, paddle_pairs, gemini_pairs = [], [], []
    for name, truth in rows:
        image = cv2.imread(str(directory / name))
        if image is None:
            print(f"skipped unreadable {name}")
            continue
        truth = _nfc(truth)
        reader_pairs.append((_nfc(reader.read(image)[0]), truth))
        paddle_pairs.append((_nfc(paddle.recognize(image).text), truth))
        if gemini is not None:
            gemini_pairs.append((_nfc(gemini.read(image)[0]), truth))
    report = {"lines": len(reader_pairs), "reader": score(reader_pairs),
              "paddleocr": score(paddle_pairs)}
    if gemini is not None:
        report["gemini"] = score(gemini_pairs)
    return report


def evaluate_pages(directory: Path, engine, detector, reader) -> dict:
    import extraction_pipeline
    from normalization.normalizers import normalize_field

    tallies = {"with_handwriting_models": {}, "paddleocr_only": {}}
    pages = 0
    for image_path in sorted(p for p in directory.iterdir() if p.suffix.lower() in IMAGE_TYPES):
        truth_path = image_path.with_suffix(".json")
        if not truth_path.exists():
            continue
        truth = json.loads(truth_path.read_text(encoding="utf-8"))
        pages += 1
        runs = {
            "with_handwriting_models": dict(handwriting_detector=detector,
                                            handwriting_reader=reader),
            "paddleocr_only": {},
        }
        for label, models in runs.items():
            result = extraction_pipeline.run(image_path.read_bytes(), engine, **models)
            found = {}
            for outcome in result.fields:
                found.setdefault(outcome.field, outcome.normalized_value or outcome.raw_value)
            for field, expected in truth.items():
                tally = tallies[label].setdefault(field, {"correct": 0, "total": 0})
                tally["total"] += 1
                want = normalize_field(field, expected) or _nfc(expected)
                tally["correct"] += _nfc(str(found.get(field) or "")) == _nfc(want)
    for fields in tallies.values():
        correct = sum(t["correct"] for t in fields.values())
        total = sum(t["total"] for t in fields.values())
        fields["_overall"] = {"correct": correct, "total": total,
                              "accuracy": round(correct / total, 4) if total else None}
    return {"pages": pages, **tallies}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--lines", type=Path)
    parser.add_argument("--pages", type=Path)
    parser.add_argument("--gemini", action="store_true",
                        help="also score Gemini on --lines (sends crops to Google)")
    args = parser.parse_args()
    if not (args.lines or args.pages):
        parser.error("give --lines and/or --pages")

    from ocr.handwriting_model import GeminiHandwritingReader, load_detector, load_reader
    from ocr.provider import OcrEngine, PaddleOcrProvider

    reader, detector = load_reader(), load_detector()
    if reader is None:
        raise SystemExit("no reader weights; run scripts/train_handwriting.py --task reader")
    paddle = PaddleOcrProvider(lang="hi")
    report = {"reader": reader.version,
              "detector": detector.version if detector else "geometry heuristic"}
    gemini = None
    if args.gemini:
        key = os.environ.get("GEMINI_API_KEY")
        if not key:
            raise SystemExit("--gemini needs GEMINI_API_KEY in the environment")
        gemini = GeminiHandwritingReader(key, os.environ.get("GEMINI_LLM_MODEL",
                                                             "gemini-3.6-flash"))
    if args.lines:
        report["lines"] = evaluate_lines(args.lines, reader, paddle, gemini)
    if args.pages:
        report["pages"] = evaluate_pages(args.pages, OcrEngine(paddle), detector, reader)

    out = REPO_ROOT / "datasets" / "reports" / "handwriting_real.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2))
    print(json.dumps(report, ensure_ascii=False, indent=2))
    print(f"report: {out.relative_to(REPO_ROOT)}")


if __name__ == "__main__":
    main()
