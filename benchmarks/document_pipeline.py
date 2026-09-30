"""Measure the actual local OCR pipeline on synthetic PNG and PDF scans.

python benchmarks/document_pipeline.py --languages hi te ta kn --repeats 5 \
    --output benchmarks/document-pipeline-results.json
No provider uploads. API, broker, storage, and database are explicitly excluded.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import platform
import resource
import sys
import time
from collections import defaultdict
from importlib.metadata import version
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "services/ai-worker"), str(ROOT / "packages/domain")]

import numpy as np  # noqa: E402
from extraction_pipeline import run  # noqa: E402
from ingest.rasterize import decode_pages, encode_png  # noqa: E402
from mrittika_domain.fonts import find_font  # noqa: E402
from normalization.normalizers import normalize_field  # noqa: E402
from ocr.provider import OcrEngine, PaddleOcrProvider  # noqa: E402
from PIL import Image, ImageDraw, ImageFilter, ImageFont, features  # noqa: E402

SAMPLES = {
    "hi": ("devanagari", ["जिला : लखनऊ", "ग्राम : रामपुर", "खसरा : 142/2", "क्षेत्रफल : 2.75"]),
    "te": ("telugu", ["జిల్లా : హైదరాబాద్", "గ్రామం : రామపురం", "సర్వే నంబర్ : 142/2", "విస్తీర్ణం : 2.75"]),
    "ta": ("tamil", ["மாவட்டம் : சென்னை", "கிராமம் : ராமபுரம்", "சர்வே எண் : 142/2", "பரப்பளவு : 2.75"]),
    "kn": ("kannada", ["ಜಿಲ್ಲೆ : ಬೆಂಗಳೂರು", "ಗ್ರಾಮ : ರಾಮಪುರ", "ಸರ್ವೆ ಸಂಖ್ಯೆ : 142/2", "ವಿಸ್ತೀರ್ಣ : 2.75"]),
}


def summary(seconds: list[float]) -> dict:
    """Linear-interpolated percentiles; report sample count to expose small runs."""
    if not seconds:
        return {"count": 0, "p50_ms": None, "p95_ms": None, "p99_ms": None}
    return {
        "count": len(seconds),
        **{f"p{q}_ms": round(float(np.percentile(seconds, q)) * 1000, 3) for q in (50, 95, 99)},
    }


def corpus(languages: list[str]) -> list[tuple[dict, bytes]]:
    """Render fixed clean/blurred records as single PNG and two-page PDF scans."""
    if not features.check("raqm"):
        raise RuntimeError("libraqm is required to generate correctly shaped fixtures")
    documents = []
    for lang in languages:
        script, lines = SAMPLES[lang]
        font_path = find_font(script)
        font = ImageFont.truetype(font_path, 34)
        for quality in ("clean", "blurred"):
            image = Image.new("RGB", (1200, 900), "white")
            draw = ImageDraw.Draw(image)
            for i, line in enumerate(lines):
                draw.text((70, 100 + i * 100), line, font=font, fill="black")
            draw.text((70, 650), "SYNTHETIC BENCHMARK — NOT A LAND RECORD", font=font, fill="black")
            if quality == "blurred":
                image = image.filter(ImageFilter.GaussianBlur(1.2))
            for fmt in ("PNG", "PDF"):
                buffer = io.BytesIO()
                if fmt == "PDF":
                    image.save(
                        buffer,
                        format=fmt,
                        save_all=True,
                        append_images=[image],
                        resolution=150,
                        creationDate="D:20260101000000Z",
                        modDate="D:20260101000000Z",
                    )
                else:
                    image.save(buffer, format=fmt)
                payload = buffer.getvalue()
                documents.append(
                    (
                        {
                            "language": lang,
                            "quality": quality,
                            "format": fmt,
                            "pages": 2 if fmt == "PDF" else 1,
                            "pixels": [1200, 900],
                            "sha256": hashlib.sha256(payload).hexdigest(),
                            "font_sha256": hashlib.sha256(Path(font_path).read_bytes()).hexdigest(),
                        },
                        payload,
                    )
                )
    return documents


def benchmark(languages: list[str], repeats: int, detector: str | None = None) -> dict:
    """Time ingestion, model loads, and production pipeline stages without mocks."""
    documents = corpus(languages)
    engines, model_loads = {}, {}
    for lang in languages:
        provider = PaddleOcrProvider(lang=lang, detection_model=detector)
        start = time.perf_counter()
        provider._get_engine()
        cold = time.perf_counter() - start
        start = time.perf_counter()
        provider._get_engine()
        model_loads[lang] = {"cold_seconds": cold, "warm_seconds": time.perf_counter() - start}
        engines[lang] = OcrEngine(provider)  # Local only: no external fallback.
    observations = []
    wall_start = time.perf_counter()
    for repeat in range(repeats):
        for config, payload in documents:
            start = time.perf_counter()
            record = {
                **config,
                "repeat": repeat,
                "stages_seconds": {},
                "fields": 0,
                "review_fields": 0,
                "empty_pages": 0,
                "true_positive": 0,
                "false_positive": 0,
                "false_negative": 0,
                "error": None,
            }
            durations: defaultdict[str, float] = defaultdict(float)
            try:
                mark = time.perf_counter()
                pages = decode_pages(payload)
                durations["ingestion"] = time.perf_counter() - mark
                for page in pages:
                    mark = time.perf_counter()
                    encoded = encode_png(page)
                    durations["page_encoding"] += time.perf_counter() - mark
                    previous = ("image_decode", time.perf_counter())

                    def progress(
                        stage: str, _percent: int, _message: str, _durations=durations
                    ) -> None:
                        nonlocal previous
                        now = time.perf_counter()
                        _durations[previous[0]] += now - previous[1]
                        previous = (stage, now)

                    result = run(encoded, engines[config["language"]], progress=progress)
                    record["fields"] += len(result.fields)
                    record["review_fields"] += result.needs_review_count()
                    record["empty_pages"] += int(not result.fields)
                    expected = {
                        (field, normalize_field(field, line.split(" : ", 1)[1]))
                        for field, line in zip(
                            ("DISTRICT", "VILLAGE", "KHASRA", "AREA"),
                            SAMPLES[config["language"]][1],
                            strict=True,
                        )
                    }
                    predicted = {(f.field, f.normalized_value) for f in result.fields}
                    record["true_positive"] += len(expected & predicted)
                    record["false_positive"] += len(predicted - expected)
                    record["false_negative"] += len(expected - predicted)
                record["stages_seconds"] = dict(durations)
            except Exception as exc:
                record["error"] = type(exc).__name__
            record["total_seconds"] = time.perf_counter() - start
            observations.append(record)
    wall = time.perf_counter() - wall_start
    stages: defaultdict[str, list[float]] = defaultdict(list)
    for record in observations:
        for stage, seconds in record["stages_seconds"].items():
            stages[stage].append(seconds)
    failures = sum(r["error"] is not None for r in observations)
    rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    tp, fp, fn = (
        sum(r[key] for r in observations)
        for key in ("true_positive", "false_positive", "false_negative")
    )
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    return {
        "scope": "local production document pipeline; synthetic printed pages",
        "excluded": [
            "API",
            "queue",
            "database",
            "object storage",
            "concurrency",
            "handwritten scans",
        ],
        "environment": {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "dependencies": {
                p: version(p) for p in ("paddleocr", "paddlepaddle", "Pillow", "numpy")
            },
        },
        "workload": {"repeats": repeats, "documents": [c for c, _ in documents]},
        "detector": detector or "PP-OCRv5_server_det",
        "quality": {
            "precision": precision,
            "recall": recall,
            "f1": 2 * precision * recall / (precision + recall) if precision + recall else 0.0,
            "true_positive": tp,
            "false_positive": fp,
            "false_negative": fn,
        },
        "model_loading": model_loads,
        "total_latency": summary([r["total_seconds"] for r in observations]),
        "stages": {name: summary(times) for name, times in stages.items()},
        "documents_per_second": (len(observations) - failures) / wall,
        "peak_process_rss_mib": rss / (1024 * 1024 if sys.platform == "darwin" else 1024),
        "failure_rate": failures / len(observations),
        "empty_pages": sum(r["empty_pages"] for r in observations),
        "observations": observations,
        "limits": (
            "Stage percentiles are per-document totals. Small runs do not estimate "
            "tail latency reliably. RSS includes models and fixture generation. "
            "Review counts are not human time saved."
        ),
    }


def main() -> int:
    """Write machine-readable raw observations; fail the run on processing errors."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--languages", nargs="+", choices=list(SAMPLES), default=["hi"])
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--detector", choices=["server", "mobile"], default="server")
    args = parser.parse_args()
    if args.repeats < 1:
        parser.error("repeats must be positive")
    result = benchmark(
        args.languages, args.repeats, "PP-OCRv5_mobile_det" if args.detector == "mobile" else None
    )
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(
        json.dumps(
            {k: v for k, v in result.items() if k not in ("observations", "workload")}, indent=2
        )
    )
    return int(result["failure_rate"] > 0)


if __name__ == "__main__":
    raise SystemExit(main())
