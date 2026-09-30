"""Behavioral checks for deterministic multi-objective neural evolution."""

from dataclasses import replace

import numpy as np

from optimization.deep_evolutionary_network import (
    EvolutionConfig,
    evolve_deep_network,
    make_nonstationary_classification,
)


FAST_CONFIG = EvolutionConfig(
    seed=19,
    population_size=6,
    generations=3,
    epochs=40,
    parameter_budget=180,
)


def test_evolution_is_deterministic_and_respects_the_deployment_budget():
    """Catches random search drift, shallow models, and budget bypasses."""
    data = make_nonstationary_classification(seed=7, train_size=160, split_size=96)

    first = evolve_deep_network(data, FAST_CONFIG)
    second = evolve_deep_network(data, FAST_CONFIG)

    assert first.selected.genome == second.selected.genome
    assert first.validation_metrics == second.validation_metrics
    assert first.test_metrics == second.test_metrics
    assert first.selected.parameter_count <= FAST_CONFIG.parameter_budget
    assert len(first.selected.genome.hidden_layers) == 2
    assert first.validation_metrics.accuracy >= first.fixed_baseline_metrics.accuracy
    assert len(first.generation_evidence) == FAST_CONFIG.generations + 1
    assert first.generation_evidence[-1].evaluated_genomes == first.evaluated_genomes
    assert first.validation_metrics.group_calibration_errors
    assert sum(error for _, error in first.validation_metrics.group_calibration_errors) >= 0.0
    probabilities = first.predict_proba(data.test.features[:5])
    assert probabilities.shape == (5,)
    assert np.all((0.0 <= probabilities) & (probabilities <= 1.0))


def test_held_out_ood_labels_cannot_influence_evolutionary_selection():
    """Catches leakage from the one-shot held-out OOD evaluation into tuning."""
    data = make_nonstationary_classification(seed=23, train_size=144, split_size=80)
    flipped_test = replace(data, test=replace(data.test, labels=1.0 - data.test.labels))

    original = evolve_deep_network(data, FAST_CONFIG)
    flipped = evolve_deep_network(flipped_test, FAST_CONFIG)

    assert original.selected.genome == flipped.selected.genome
    assert original.validation_metrics == flipped.validation_metrics
    assert original.test_metrics.accuracy != flipped.test_metrics.accuracy


def test_impossible_parameter_budget_fails_before_training():
    """Catches silently exceeding an infeasible runtime deployment budget."""
    data = make_nonstationary_classification(seed=3, train_size=64, split_size=32)

    with np.testing.assert_raises_regex(ValueError, "parameter budget"):
        evolve_deep_network(data, replace(FAST_CONFIG, parameter_budget=1))
