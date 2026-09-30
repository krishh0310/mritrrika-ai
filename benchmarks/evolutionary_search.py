"""Emit reproducible evidence for the deep evolutionary search."""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any, Sequence

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services" / "ai-worker"))

from optimization.deep_evolutionary_network import (
    EvolutionResult,
    EvolutionConfig,
    make_nonstationary_classification,
    evolve_deep_network,
    random_search_deep_network,
)


def _metrics(result: EvolutionResult, name: str) -> dict[str, Any]:
    metrics = getattr(result, name)
    return {
        "accuracy": metrics.accuracy,
        "brier_score": metrics.brier_score,
        "calibration_error": metrics.calibration_error,
        "worst_group_calibration_error": metrics.worst_group_calibration_error,
        "group_calibration_gap": metrics.group_calibration_gap,
        "group_calibration_errors": dict(metrics.group_calibration_errors),
    }


def _result_summary(result: EvolutionResult) -> dict[str, Any]:
    return {
        "validation": _metrics(result, "validation_metrics"),
        "test": _metrics(result, "test_metrics"),
    }


def _frontier(result: EvolutionResult) -> list[dict[str, Any]]:
    return [
        {
            "hidden_layers": candidate.genome.hidden_layers,
            "learning_rate": candidate.genome.learning_rate,
            "l2_penalty": candidate.genome.l2_penalty,
            "label_smoothing": candidate.genome.label_smoothing,
            "parameter_count": candidate.parameter_count,
            "validation": {
                "accuracy": candidate.validation_metrics.accuracy,
                "worst_group_calibration_error": candidate.validation_metrics.worst_group_calibration_error,
            },
        }
        for candidate in result.pareto_front
    ]


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--train-size", type=int, default=320)
    parser.add_argument("--split-size", type=int, default=160)
    parser.add_argument("--population-size", type=int, default=8)
    parser.add_argument("--generations", type=int, default=4)
    parser.add_argument("--epochs", type=int, default=60)
    parser.add_argument("--parameter-budget", type=int, default=256)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)

    dataset = make_nonstationary_classification(
        seed=args.seed, train_size=args.train_size, split_size=args.split_size
    )
    config = EvolutionConfig(
        seed=args.seed,
        population_size=args.population_size,
        generations=args.generations,
        epochs=args.epochs,
        parameter_budget=args.parameter_budget,
    )
    started = time.perf_counter()
    selected = evolve_deep_network(dataset, config)
    random = random_search_deep_network(dataset, config, trials=args.population_size)
    elapsed = max(time.perf_counter() - started, 1e-9)

    report = {
        "scope": "deterministic synthetic nonstationary classification",
        "seed": args.seed,
        "selected": _result_summary(selected),
        "validation_pareto_front": _frontier(selected),
        "optimization_cost": {
            "evaluated_genomes": selected.evaluated_genomes,
            "elapsed_seconds": elapsed,
            "generation_evidence": [evidence.__dict__ for evidence in selected.generation_evidence],
        },
        "baselines": {
            "fixed_configuration": _result_summary(selected),
            "equal_budget_random_search": _result_summary(random),
        },
        "held_out_ood": {"selected": _metrics(selected, "test_metrics")},
        "regularization_ablation": {
            "validation": _metrics(selected, "regularization_ablation_metrics"),
            "test": _metrics(selected, "regularization_ablation_test_metrics"),
        },
        "limitations": [
            "Evidence uses deterministic synthetic data, not real land registers.",
            "The held-out shifted split is evaluated after selection and is not used for tuning.",
        ],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())