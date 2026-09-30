"""Compare identical pipeline workloads and select a feasible measured OCR option."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services/ai-worker"))
from optimization.multi_objective import (  # noqa: E402
    OperatingPoint,
    pareto_front,
    select_configuration,
)


def compare(reports: list[dict], *, min_f1: float, max_memory_mib: float) -> dict:
    """Reject incomparable or failed runs before deriving trade-offs."""
    if len(reports) < 2:
        raise ValueError("at least two measured runs are required")
    for report in reports:
        if any(report[key] != reports[0][key] for key in ("workload", "environment", "scope")):
            raise ValueError("workload, environment, and measurement scope must match")
        if report["failure_rate"] != 0:
            raise ValueError("failed runs cannot be recommended")
    points = [
        OperatingPoint(
            r["detector"],
            r["quality"]["f1"],
            r["total_latency"]["p50_ms"],
            r["peak_process_rss_mib"],
        )
        for r in reports
    ]
    choice = select_configuration(points, min_f1=min_f1, max_memory_mib=max_memory_mib)
    return {
        "objectives": {"maximize": ["extraction_f1"], "minimize": ["latency_ms", "memory_mib"]},
        "budget": {"min_f1": min_f1, "max_memory_mib": max_memory_mib},
        "operating_points": [asdict(p) for p in points],
        "pareto_front": [asdict(p) for p in pareto_front(points)],
        "recommendation": asdict(choice) if choice else None,
        "status": "feasible" if choice else "no measured configuration meets the budget",
        "limits": ("Offline synthetic workload only; this does not change production "
                   "configuration, authorize records, or establish OOD fairness or accuracy."),
    }


def main() -> None:
    """Write a reproducible deployment recommendation from benchmark JSON files."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("reports", nargs="+", type=Path)
    parser.add_argument("--min-f1", type=float, required=True)
    parser.add_argument("--max-memory-mib", type=float, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = compare(
        [json.loads(p.read_text()) for p in args.reports],
        min_f1=args.min_f1,
        max_memory_mib=args.max_memory_mib,
    )
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
