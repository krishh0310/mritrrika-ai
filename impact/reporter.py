"""Derived processing metrics; no hardcoded impact claims or energy conversion."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path


@dataclass
class ImpactReporter:
    """Compare two measured extraction runs on equal workloads."""

    current: dict
    baseline: dict

    def report(self) -> dict:
        """Return time and throughput deltas derived from benchmark measurements."""
        if (self.current["iterations"] != self.baseline["iterations"]
                or self.current["blocks_per_page"] != self.baseline["blocks_per_page"]):
            raise ValueError("benchmark workloads must match")
        current_time = self.current["total_seconds"]
        baseline_time = self.baseline["total_seconds"]
        if (not math.isfinite(current_time) or not math.isfinite(baseline_time)
                or current_time <= 0 or baseline_time <= 0):
            raise ValueError("elapsed times must be positive")
        pages = self.current["iterations"]
        if not isinstance(pages, int) or isinstance(pages, bool) or pages <= 0:
            raise ValueError("page count must be a positive integer")
        return {
            "pages": pages,
            "blocks_per_page": self.current["blocks_per_page"],
            "seconds_saved": round(baseline_time - current_time, 4),
            "seconds_saved_per_1000_pages": round(
                (baseline_time - current_time) / pages * 1000, 2),
            "throughput_gain_pct": round((baseline_time / current_time - 1) * 100, 1),
            "time_reduction_pct": round((1 - current_time / baseline_time) * 100, 1),
        }


def pipeline_metrics(report: dict) -> dict:
    """Compute observable resource and review counts from raw pipeline results.

    Review counts are machine flags on extracted fields, not measured human
    effort. No energy, financial, or citizen-benefit conversion is performed.
    """
    observations = report["observations"]
    if not observations:
        raise ValueError("at least one observation is required")
    for row in observations:
        if not math.isfinite(row["total_seconds"]) or row["total_seconds"] <= 0:
            raise ValueError("processing times must be finite and positive")
        if not 0 <= row["review_fields"] <= row["fields"]:
            raise ValueError("review counts must be within extracted field counts")
    elapsed = sum(row["total_seconds"] for row in observations)
    successes = sum(row["error"] is None for row in observations)
    fields = sum(row["fields"] for row in observations)
    reviews = sum(row["review_fields"] for row in observations)
    return {
        "scope": report["scope"],
        "documents": len(observations),
        "successful_documents": successes,
        "processing_seconds": elapsed,
        "successful_documents_per_second": successes / elapsed,
        "extracted_fields": fields,
        "fields_flagged_for_review": reviews,
        "flagged_fraction_of_extracted_fields": reviews / fields if fields else None,
        "empty_pages": sum(row["empty_pages"] for row in observations),
        "measured_peak_process_rss_mib": report["peak_process_rss_mib"],
        "human_review_seconds_saved": None,
        "energy_saved": None,
    }


def main() -> None:
    """Print computed impact metrics from a benchmark JSON path."""
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("benchmark", type=Path)
    parser.add_argument("baseline", type=Path, nargs="?")
    parser.add_argument("--pipeline", action="store_true")
    args = parser.parse_args()
    data = json.loads(args.benchmark.read_text())
    if args.pipeline:
        print(json.dumps(pipeline_metrics(data), indent=2))
        return
    if args.baseline is None:
        parser.error("baseline is required unless --pipeline is selected")
    baseline = json.loads(args.baseline.read_text())
    print(json.dumps(ImpactReporter(data["profiled_repeat"], baseline).report(), indent=2))


if __name__ == "__main__":
    main()
