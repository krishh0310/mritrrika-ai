"""Measure the heuristic on synthetic font styles and cached printed pages.

Font styles are proxies, NOT human handwriting. These are development
measurements (the threshold was selected using these font families).
No network calls, training, private records or persisted images.
"""

import argparse
import json
import sys
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services" / "ai-worker"))
from ocr.handwriting import flag_blocks, is_handwritten
from ocr.provider import TextBlock
from preprocessing.enhance import enhance_for_quality
from quality.assessment import assess

FONTS = {
    "Arial.ttf": False,
    "Times New Roman.ttf": False,
    "Arial Italic.ttf": False,
    "Devanagari Sangam MN.ttc": False,
    "Bradley Hand Bold.ttf": True,
    "Brush Script.ttf": True,
    "Chalkboard.ttc": True,
    "Comic Sans MS.ttf": True,
    "SnellRoundhand.ttc": True,
}


def evaluate(font_dir, printed_cache=False):
    report = {"synthetic_only": True, "development_set": True, "fonts": {}}
    for name, handwriting_style in FONTS.items():
        path = font_dir / name
        if not path.exists():
            raise FileNotFoundError(f"Missing evaluation font: {path}")
        texts = (
            ["राम प्रसाद सिंह", "खसरा संख्या १४२/२", "क्षेत्रफल २.७५ बीघा"]
            if name.startswith("Devanagari")
            else ["Ram Prasad Singh", "Khasra number 142/2", "Area 2.75 bigha"]
        )
        detected = total = 0
        for size in (28, 40, 56):
            font = ImageFont.truetype(str(path), size)
            for text in texts:
                canvas = Image.new("L", (900, 160), 255)
                ImageDraw.Draw(canvas).text((15, 20), text, font=font, fill=0)
                for sigma in (0, 0.8):
                    image = np.array(canvas)
                    if sigma:
                        image = cv2.GaussianBlur(image, (3, 3), sigma)
                    detected += is_handwritten(image)
                    total += 1
        report["fonts"][name] = {
            "handwriting_style_proxy": handwriting_style,
            "detected": detected, "total": total,
        }
    if printed_cache:
        datasets = ROOT / "datasets"
        docs = json.loads((datasets / "metadata/documents.slice1.json").read_text())
        index = {d["document_id"]: d for d in docs}
        total = flagged = pages = flagged_pages = 0
        for path in sorted((datasets / "ocr-cache").glob("*.json")):
            cache = json.loads(path.read_text())
            if cache["split"] != "val" or cache["document_id"] not in index:
                continue
            doc = index[cache["document_id"]]
            image = cv2.imread(str(datasets / doc["degraded_image"]))
            if image is None:
                raise ValueError(f"Missing synthetic page for {path.name}")
            prepared = enhance_for_quality(image, assess(image)).image
            if list(prepared.shape[1::-1]) != cache["prepared_size"]:
                raise ValueError(f"Cache image size mismatch: {path.name}")
            blocks = [TextBlock(b["text"], b["confidence"], tuple(b["bbox"]))
                      for b in cache["blocks"]]
            flag_blocks(prepared, blocks)
            count = sum(b.is_handwritten for b in blocks)
            total += len(blocks)
            flagged += count
            flagged_pages += bool(count)
            pages += 1
        report["printed_validation_cache"] = {
            "pages": pages, "blocks": total,
            "false_positive_blocks": flagged, "false_positive_pages": flagged_pages,
            "scope": "slice1 validation pages with cached OCR; not the whole corpus",
        }
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--font-dir", type=Path,
                        default=Path("/System/Library/Fonts/Supplemental"))
    parser.add_argument("--printed-cache", action="store_true")
    args = parser.parse_args()
    print(json.dumps(evaluate(args.font_dir, args.printed_cache), indent=2))
