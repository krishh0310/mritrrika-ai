"""The evolutionary benchmark emits reproducible, honestly scoped evidence."""

import json

from benchmarks.evolutionary_search import main


def test_benchmark_reports_baselines_pareto_cost_and_ood_evidence(tmp_path):
    """Catches reports that omit comparison evidence or imply real-scan validation."""
    output = tmp_path / "evolution.json"

    assert main(
        [
            "--seed",
            "11",
            "--train-size",
            "80",
            "--split-size",
            "48",
            "--population-size",
            "4",
            "--generations",
            "2",
            "--epochs",
            "20",
            "--parameter-budget",
            "180",
            "--output",
            str(output),
        ]
    ) == 0
    report = json.loads(output.read_text())

    assert report["scope"] == "deterministic synthetic nonstationary classification"
    assert report["seed"] == 11
    assert report["optimization_cost"]["evaluated_genomes"] >= 4
    assert report["optimization_cost"]["elapsed_seconds"] > 0
    assert report["validation_pareto_front"]
    assert report["baselines"]["fixed_configuration"]["validation"]
    assert report["baselines"]["equal_budget_random_search"]["validation"]
    assert report["held_out_ood"]["selected"]["accuracy"] >= 0.0
    assert "group_calibration_gap" in report["held_out_ood"]["selected"]
    assert report["regularization_ablation"]["validation"]
    assert report["limitations"]
