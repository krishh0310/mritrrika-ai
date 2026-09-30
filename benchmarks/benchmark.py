"""Reproducible CPU benchmark for the field extraction hot path.

Run from the repository root: `.venv/bin/python benchmarks/benchmark.py`.
This measures OCR-block processing only; it does not include OCR or database I/O.
"""

from __future__ import annotations

import cProfile
import json
import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services" / "ai-worker"))

from extraction.field_extractor import (  # noqa: E402
    _cached_label_score,
    _chrome_text,
    extract_scalar_fields,
)
from ocr.provider import TextBlock  # noqa: E402


def sample_page(block_count: int = 150, page_index: int | None = 0) -> list[TextBlock]:
    """Build a dense, deterministic page with a real label and noisy OCR blocks."""
    blocks = [TextBlock("जिला", .95, (0, 0, 80, 20)),
              TextBlock("लखनऊ", .93, (90, 0, 180, 20))]
    for i in range(block_count - 2):
        x, y = i % 10 * 100, 30 + i // 10 * 25
        suffix = str(i) if page_index is None else f"{page_index}-{i}"
        blocks.append(TextBlock(f"अभिलेख {suffix}", .8, (x, y, x + 80, y + 20)))
    return blocks


def run(iterations: int = 30, block_count: int = 150, cold: bool = False) -> dict:
    """Return measured latency and throughput for the current extractor."""
    pages = [sample_page(block_count, i) for i in range(iterations)]
    timings = []
    for blocks in pages:
        if cold:
            _cached_label_score.cache_clear()
            _chrome_text.cache_clear()
        start = time.perf_counter()
        result = extract_scalar_fields(blocks, 1200)
        timings.append(time.perf_counter() - start)
    assert any(value.field == "DISTRICT" for value in result)
    elapsed = sum(timings)
    return {
        "iterations": iterations,
        "blocks_per_page": block_count,
        "cache": "cold" if cold else "warm",
        "median_ms": round(statistics.median(timings) * 1000, 3),
        "p95_ms": round(sorted(timings)[int(.95 * (iterations - 1))] * 1000, 3),
        "pages_per_second": round(iterations / elapsed, 2),
        "total_seconds": round(elapsed, 4),
    }


def profiled_repeat() -> dict:
    """Match the ten-call cProfile workload captured before remediation."""
    blocks = sample_page(150, None)
    _cached_label_score.cache_clear()
    _chrome_text.cache_clear()
    profile = cProfile.Profile()
    profile.enable()
    for _ in range(10):
        extract_scalar_fields(blocks, 1200)
    profile.disable()
    return {"iterations": 10, "blocks_per_page": 150,
            "total_seconds": round(sum(entry.inlinetime for entry in profile.getstats()), 4)}


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--iterations", type=int, default=30)
    parser.add_argument("--blocks", type=int, default=150)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.iterations < 2 or args.blocks < 2:
        parser.error("iterations and blocks must be at least 2")
    result = {"warm": run(args.iterations, args.blocks),
              "cold": run(args.iterations, args.blocks, cold=True),
              "profiled_repeat": profiled_repeat()}
    output = json.dumps(result, indent=2) + "\n"
    if args.output:
        args.output.write_text(output)
    print(output, end="")
