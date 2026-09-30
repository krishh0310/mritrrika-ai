"""Derived processing metrics; no hardcoded impact claims or energy conversion."""

from __future__ import annotations

import json
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
        if current_time <= 0 or baseline_time <= 0:
            raise ValueError("elapsed times must be positive")
        pages = self.current["iterations"]
        return {
            "pages": pages,
            "blocks_per_page": self.current["blocks_per_page"],
            "seconds_saved": round(baseline_time - current_time, 4),
            "seconds_saved_per_1000_pages": round(
                (baseline_time - current_time) / pages * 1000, 2),
            "throughput_gain_pct": round((baseline_time / current_time - 1) * 100, 1),
            "time_reduction_pct": round((1 - current_time / baseline_time) * 100, 1),
        }


def main() -> None:
    """Print computed impact metrics from a benchmark JSON path."""
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("benchmark", type=Path)
    parser.add_argument("baseline", type=Path)
    args = parser.parse_args()
    data = json.loads(args.benchmark.read_text())
    baseline = json.loads(args.baseline.read_text())
    print(json.dumps(ImpactReporter(data["profiled_repeat"], baseline).report(), indent=2))


if __name__ == "__main__":
    main()
