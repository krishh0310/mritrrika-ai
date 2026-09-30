"""Deployment selection cannot trade away hard quality or memory constraints."""

import math

import pytest
from optimization.multi_objective import OperatingPoint, pareto_front, select_configuration

from benchmarks.compare_pipeline import compare


def test_pareto_retains_tradeoffs_and_selection_enforces_hard_budgets():
    accurate = OperatingPoint("server", 0.95, 1000, 8000)
    fast = OperatingPoint("mobile", 0.8, 300, 2000)
    inferior = OperatingPoint("inferior", 0.7, 400, 3000)
    assert set(pareto_front([inferior, accurate, fast])) == {accurate, fast}
    assert select_configuration([accurate, fast], min_f1=0.9, max_memory_mib=4096) is None
    assert select_configuration([accurate, fast], min_f1=0.8, max_memory_mib=4096) == fast
    assert select_configuration([accurate, fast], min_f1=0.9, max_memory_mib=8192) == accurate
    with pytest.raises(ValueError):
        OperatingPoint("invalid", math.nan, 1, 1)
    with pytest.raises(ValueError):
        select_configuration([accurate], min_f1=0.9, max_memory_mib=math.inf)


def test_comparison_rejects_different_workloads_and_failed_runs():
    report = {"workload": {"sha256": "same"}, "environment": {"python": "3.12"},
              "scope": "offline", "failure_rate": 0, "detector": "server",
              "quality": {"f1": 0.9}, "total_latency": {"p50_ms": 100},
              "peak_process_rss_mib": 1000}
    assert compare([report, report], min_f1=0.95, max_memory_mib=2000)["recommendation"] is None
    with pytest.raises(ValueError, match="must match"):
        compare([report, report | {"workload": {"sha256": "different"}}],
                min_f1=0.8, max_memory_mib=2000)
    with pytest.raises(ValueError, match="failed runs"):
        compare([report, report | {"failure_rate": 0.1}], min_f1=0.8, max_memory_mib=2000)
