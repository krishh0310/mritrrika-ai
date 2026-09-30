"""Deterministic multi-objective evolution of a compact deep classifier.

The search evolves a two-hidden-layer network's architecture, learning rate,
L2 penalty, and label smoothing on training and validation data. Accuracy,
worst-group calibration error, and parameter count remain separate objectives.
The shifted test split is evaluated only after selection.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

FloatArray = NDArray[np.float64]

_ARCHITECTURES = ((4, 2), (6, 3), (8, 4), (10, 5), (12, 6))
_LEARNING_RATES = (0.03, 0.06, 0.1)
_L2_PENALTIES = (0.0, 0.001, 0.01)
_LABEL_SMOOTHING = (0.0, 0.03, 0.06)
_FIXED_BASELINE = (8, 4), 0.06, 0.001, 0.03


@dataclass(frozen=True)
class DataSplit:
    """Features, binary labels, and heterogeneous subgroup identifiers."""

    features: FloatArray
    labels: FloatArray
    groups: NDArray[np.int64]

    def __post_init__(self) -> None:
        rows = len(self.features)
        if self.features.ndim != 2 or rows == 0:
            raise ValueError("features must be a non-empty matrix")
        if self.labels.shape != (rows,) or self.groups.shape != (rows,):
            raise ValueError("labels and groups must match feature rows")
        if not np.isfinite(self.features).all() or not np.isfinite(self.labels).all():
            raise ValueError("dataset values must be finite")
        if not np.isin(self.labels, (0.0, 1.0)).all():
            raise ValueError("labels must be binary")


@dataclass(frozen=True)
class NonStationaryDataset:
    """Training, shifted validation, and untouched out-of-distribution test data."""

    train: DataSplit
    validation: DataSplit
    test: DataSplit

    def __post_init__(self) -> None:
        widths = {split.features.shape[1] for split in (self.train, self.validation, self.test)}
        if len(widths) != 1:
            raise ValueError("all splits must have the same feature width")


@dataclass(frozen=True)
class Genome:
    """Evolvable architecture and robust training hyperparameters."""

    hidden_layers: tuple[int, int]
    learning_rate: float
    l2_penalty: float
    label_smoothing: float


@dataclass(frozen=True)
class BinaryMetrics:
    """Predictive and calibration outcomes for one split."""

    accuracy: float
    brier_score: float
    calibration_error: float
    worst_group_calibration_error: float
    group_calibration_gap: float


@dataclass(frozen=True)
class Candidate:
    """One genome evaluated on validation data within a parameter budget."""

    genome: Genome
    validation_metrics: BinaryMetrics
    parameter_count: int


@dataclass(frozen=True)
class EvolutionConfig:
    """Bounded deterministic search controls."""

    seed: int = 42
    population_size: int = 8
    generations: int = 4
    epochs: int = 60
    parameter_budget: int = 256
    gradient_clip: float = 5.0

    def __post_init__(self) -> None:
        if self.population_size < 2 or self.generations < 1 or self.epochs < 1:
            raise ValueError("population, generations, and epochs must be positive")
        if self.parameter_budget < 1 or not math.isfinite(self.gradient_clip):
            raise ValueError("parameter budget and finite gradient clipping are required")
        if self.gradient_clip <= 0:
            raise ValueError("gradient clipping must be positive")


@dataclass(frozen=True)
class _Network:
    weights: tuple[FloatArray, FloatArray, FloatArray]
    biases: tuple[FloatArray, FloatArray, FloatArray]

    def predict_proba(self, features: FloatArray) -> FloatArray:
        first = np.maximum(features @ self.weights[0] + self.biases[0], 0.0)
        second = np.maximum(first @ self.weights[1] + self.biases[1], 0.0)
        logits = second @ self.weights[2] + self.biases[2]
        return _sigmoid(logits[:, 0])


@dataclass(frozen=True)
class EvolutionResult:
    """Selected model plus validation-only search and one-shot OOD evidence."""

    selected: Candidate
    validation_metrics: BinaryMetrics
    test_metrics: BinaryMetrics
    fixed_baseline_metrics: BinaryMetrics
    fixed_baseline_test_metrics: BinaryMetrics
    regularization_ablation_metrics: BinaryMetrics
    regularization_ablation_test_metrics: BinaryMetrics
    pareto_front: tuple[Candidate, ...]
    evaluated_genomes: int
    _network: _Network

    def predict_proba(self, features: FloatArray) -> FloatArray:
        """Return calibrated class-one probabilities for new feature rows."""
        matrix = np.asarray(features, dtype=np.float64)
        if matrix.ndim != 2 or matrix.shape[1] != self._network.weights[0].shape[0]:
            raise ValueError("features must match the trained input width")
        if not np.isfinite(matrix).all():
            raise ValueError("features must be finite")
        return self._network.predict_proba(matrix)


def make_nonstationary_classification(
    *, seed: int = 42, train_size: int = 320, split_size: int = 160
) -> NonStationaryDataset:
    """Create deterministic nonlinear train, shifted-validation, and OOD splits."""
    if train_size < 16 or split_size < 16:
        raise ValueError("each split needs at least 16 samples")
    rng = np.random.default_rng(seed)

    def build(size: int, location: FloatArray, scale: FloatArray, rotation: float) -> DataSplit:
        raw = rng.normal(size=(size, 4)) * scale + location
        if rotation:
            cosine, sine = math.cos(rotation), math.sin(rotation)
            raw[:, :2] = raw[:, :2] @ np.array(((cosine, -sine), (sine, cosine)))
        score = 1.25 * raw[:, 0] * raw[:, 1] + 0.8 * np.sin(raw[:, 2]) - 0.45 * raw[:, 3]
        noise = rng.normal(0.0, 0.18, size)
        labels = (score + noise > 0.0).astype(np.float64)
        groups = (raw[:, 3] >= np.median(raw[:, 3])).astype(np.int64)
        return DataSplit(raw.astype(np.float64), labels, groups)

    train = build(train_size, np.zeros(4), np.ones(4), 0.0)
    validation = build(
        split_size,
        np.array((0.25, -0.2, 0.15, 0.0)),
        np.array((1.1, 0.9, 1.15, 1.0)),
        0.18,
    )
    test = build(
        split_size,
        np.array((0.55, -0.4, 0.3, 0.15)),
        np.array((1.25, 0.8, 1.3, 1.1)),
        0.35,
    )
    mean, std = train.features.mean(axis=0), train.features.std(axis=0)

    def standardize(split: DataSplit) -> DataSplit:
        return DataSplit((split.features - mean) / np.maximum(std, 1e-8), split.labels, split.groups)

    return NonStationaryDataset(standardize(train), standardize(validation), standardize(test))


def evolve_deep_network(
    dataset: NonStationaryDataset, config: EvolutionConfig = EvolutionConfig()
) -> EvolutionResult:
    """Evolve feasible deep networks on validation objectives, then test once."""
    return _search(dataset, config, evolutionary=True)


def random_search_deep_network(
    dataset: NonStationaryDataset,
    config: EvolutionConfig = EvolutionConfig(),
    *,
    trials: int,
) -> EvolutionResult:
    """Evaluate unique random genomes as a non-evolutionary comparison baseline."""
    if trials < 2:
        raise ValueError("random search needs at least two trials")
    random_config = EvolutionConfig(
        seed=config.seed,
        population_size=trials,
        generations=config.generations,
        epochs=config.epochs,
        parameter_budget=config.parameter_budget,
        gradient_clip=config.gradient_clip,
    )
    return _search(dataset, random_config, evolutionary=False)


def _search(
    dataset: NonStationaryDataset, config: EvolutionConfig, *, evolutionary: bool
) -> EvolutionResult:
    input_width = dataset.train.features.shape[1]
    feasible_architectures = tuple(
        architecture
        for architecture in _ARCHITECTURES
        if _parameter_count(input_width, architecture) <= config.parameter_budget
    )
    if not feasible_architectures:
        raise ValueError("parameter budget cannot fit the smallest deep network")

    baseline_architecture, baseline_rate, baseline_l2, baseline_smoothing = _FIXED_BASELINE
    if baseline_architecture not in feasible_architectures:
        baseline_architecture = feasible_architectures[0]
    baseline = Genome(baseline_architecture, baseline_rate, baseline_l2, baseline_smoothing)
    rng = np.random.default_rng(config.seed)
    population = [baseline]
    while len(population) < config.population_size:
        candidate = _random_genome(rng, feasible_architectures)
        if evolutionary or candidate not in population:
            population.append(candidate)

    cache: dict[Genome, tuple[Candidate, _Network]] = {}

    def evaluate(genome: Genome) -> tuple[Candidate, _Network]:
        if genome not in cache:
            network = _fit(dataset.train, genome, config)
            metrics = _metrics(
                dataset.validation.labels,
                network.predict_proba(dataset.validation.features),
                dataset.validation.groups,
            )
            cache[genome] = (
                Candidate(genome, metrics, _parameter_count(input_width, genome.hidden_layers)),
                network,
            )
        return cache[genome]

    for _ in range(config.generations if evolutionary else 0):
        evaluated = [evaluate(genome)[0] for genome in population]
        parents = _ranked_parents(evaluated, max(2, config.population_size // 2))
        population = [candidate.genome for candidate in parents]
        while len(population) < config.population_size:
            left, right = rng.choice(parents, size=2, replace=True)
            child = _mutate(_crossover(left.genome, right.genome, rng), rng, feasible_architectures)
            population.append(child)

    evaluated = [evaluate(genome)[0] for genome in population]
    all_candidates = [pair[0] for pair in cache.values()]
    frontier = tuple(_pareto_front(all_candidates))
    selected = max(
        evaluated + list(frontier),
        key=lambda candidate: (
            candidate.validation_metrics.accuracy,
            -candidate.validation_metrics.worst_group_calibration_error,
            -candidate.parameter_count,
        ),
    )
    network = cache[selected.genome][1]
    test_metrics = _metrics(
        dataset.test.labels, network.predict_proba(dataset.test.features), dataset.test.groups
    )
    search_evaluated_genomes = len(cache)
    baseline_candidate, baseline_network = evaluate(baseline)
    baseline_test_metrics = _metrics(
        dataset.test.labels,
        baseline_network.predict_proba(dataset.test.features),
        dataset.test.groups,
    )
    ablation = Genome(selected.genome.hidden_layers, selected.genome.learning_rate, 0.0, 0.0)
    ablation_candidate, ablation_network = evaluate(ablation)
    ablation_test_metrics = _metrics(
        dataset.test.labels,
        ablation_network.predict_proba(dataset.test.features),
        dataset.test.groups,
    )
    return EvolutionResult(
        selected=selected,
        validation_metrics=selected.validation_metrics,
        test_metrics=test_metrics,
        fixed_baseline_metrics=baseline_candidate.validation_metrics,
        fixed_baseline_test_metrics=baseline_test_metrics,
        regularization_ablation_metrics=ablation_candidate.validation_metrics,
        regularization_ablation_test_metrics=ablation_test_metrics,
        pareto_front=frontier,
        evaluated_genomes=search_evaluated_genomes,
        _network=network,
    )


def _parameter_count(input_width: int, layers: tuple[int, int]) -> int:
    first, second = layers
    return (input_width + 1) * first + (first + 1) * second + second + 1


def _genome_seed(seed: int, genome: Genome) -> int:
    fields = (
        _ARCHITECTURES.index(genome.hidden_layers),
        _LEARNING_RATES.index(genome.learning_rate),
        _L2_PENALTIES.index(genome.l2_penalty),
        _LABEL_SMOOTHING.index(genome.label_smoothing),
    )
    value = seed & 0xFFFFFFFF
    for field in fields:
        value = (value * 1_664_525 + field + 1_013_904_223) & 0xFFFFFFFF
    return value


def _fit(split: DataSplit, genome: Genome, config: EvolutionConfig) -> _Network:
    rng = np.random.default_rng(_genome_seed(config.seed, genome))
    widths = (split.features.shape[1], *genome.hidden_layers, 1)
    weights = [
        rng.normal(0.0, math.sqrt(2.0 / widths[index]), (widths[index], widths[index + 1]))
        for index in range(3)
    ]
    biases = [np.zeros(width, dtype=np.float64) for width in widths[1:]]
    targets = split.labels * (1.0 - genome.label_smoothing) + 0.5 * genome.label_smoothing
    rows = len(split.labels)

    for _ in range(config.epochs):
        first_logits = split.features @ weights[0] + biases[0]
        first = np.maximum(first_logits, 0.0)
        second_logits = first @ weights[1] + biases[1]
        second = np.maximum(second_logits, 0.0)
        probabilities = _sigmoid((second @ weights[2] + biases[2])[:, 0])

        output_delta = ((probabilities - targets) / rows)[:, None]
        gradients_w = [np.empty_like(weight) for weight in weights]
        gradients_b = [np.empty_like(bias) for bias in biases]
        gradients_w[2] = second.T @ output_delta + genome.l2_penalty * weights[2]
        gradients_b[2] = output_delta.sum(axis=0)
        second_delta = output_delta @ weights[2].T * (second_logits > 0.0)
        gradients_w[1] = first.T @ second_delta + genome.l2_penalty * weights[1]
        gradients_b[1] = second_delta.sum(axis=0)
        first_delta = second_delta @ weights[1].T * (first_logits > 0.0)
        gradients_w[0] = split.features.T @ first_delta + genome.l2_penalty * weights[0]
        gradients_b[0] = first_delta.sum(axis=0)

        norm = math.sqrt(
            sum(float(np.square(gradient).sum()) for gradient in (*gradients_w, *gradients_b))
        )
        scale = min(1.0, config.gradient_clip / max(norm, 1e-12))
        for index in range(3):
            weights[index] -= genome.learning_rate * gradients_w[index] * scale
            biases[index] -= genome.learning_rate * gradients_b[index] * scale

    return _Network(tuple(weights), tuple(biases))  # type: ignore[arg-type]


def _sigmoid(values: FloatArray) -> FloatArray:
    clipped = np.clip(values, -30.0, 30.0)
    return 1.0 / (1.0 + np.exp(-clipped))


def _calibration_error(labels: FloatArray, probabilities: FloatArray, bins: int = 8) -> float:
    error = 0.0
    edges = np.linspace(0.0, 1.0, bins + 1)
    for index in range(bins):
        selected = (probabilities >= edges[index]) & (
            probabilities <= edges[index + 1] if index == bins - 1 else probabilities < edges[index + 1]
        )
        if selected.any():
            error += selected.mean() * abs(labels[selected].mean() - probabilities[selected].mean())
    return float(error)


def _metrics(labels: FloatArray, probabilities: FloatArray, groups: NDArray[np.int64]) -> BinaryMetrics:
    group_errors = [
        _calibration_error(labels[groups == group], probabilities[groups == group])
        for group in np.unique(groups)
    ]
    return BinaryMetrics(
        accuracy=float(np.mean((probabilities >= 0.5) == labels)),
        brier_score=float(np.mean(np.square(probabilities - labels))),
        calibration_error=_calibration_error(labels, probabilities),
        worst_group_calibration_error=max(group_errors),
        group_calibration_gap=max(group_errors) - min(group_errors),
    )


def _dominates(left: Candidate, right: Candidate) -> bool:
    left_metrics, right_metrics = left.validation_metrics, right.validation_metrics
    no_worse = (
        left_metrics.accuracy >= right_metrics.accuracy
        and left_metrics.worst_group_calibration_error
        <= right_metrics.worst_group_calibration_error
        and left.parameter_count <= right.parameter_count
    )
    better = (
        left_metrics.accuracy > right_metrics.accuracy
        or left_metrics.worst_group_calibration_error
        < right_metrics.worst_group_calibration_error
        or left.parameter_count < right.parameter_count
    )
    return no_worse and better


def _pareto_front(candidates: list[Candidate]) -> list[Candidate]:
    unique = {candidate.genome: candidate for candidate in candidates}
    return sorted(
        (
            candidate
            for candidate in unique.values()
            if not any(_dominates(other, candidate) for other in unique.values())
        ),
        key=lambda candidate: (
            -candidate.validation_metrics.accuracy,
            candidate.validation_metrics.worst_group_calibration_error,
            candidate.parameter_count,
        ),
    )


def _ranked_parents(candidates: list[Candidate], count: int) -> list[Candidate]:
    frontier = _pareto_front(candidates)
    remainder = sorted(
        (candidate for candidate in candidates if candidate not in frontier),
        key=lambda candidate: (
            -candidate.validation_metrics.accuracy,
            candidate.validation_metrics.worst_group_calibration_error,
            candidate.parameter_count,
        ),
    )
    return (frontier + remainder)[:count]


def _random_genome(
    rng: np.random.Generator, architectures: tuple[tuple[int, int], ...]
) -> Genome:
    return Genome(
        architectures[int(rng.integers(len(architectures)))],
        _LEARNING_RATES[int(rng.integers(len(_LEARNING_RATES)))],
        _L2_PENALTIES[int(rng.integers(len(_L2_PENALTIES)))],
        _LABEL_SMOOTHING[int(rng.integers(len(_LABEL_SMOOTHING)))],
    )


def _crossover(left: Genome, right: Genome, rng: np.random.Generator) -> Genome:
    return Genome(
        left.hidden_layers if rng.random() < 0.5 else right.hidden_layers,
        left.learning_rate if rng.random() < 0.5 else right.learning_rate,
        left.l2_penalty if rng.random() < 0.5 else right.l2_penalty,
        left.label_smoothing if rng.random() < 0.5 else right.label_smoothing,
    )


def _mutate(
    genome: Genome,
    rng: np.random.Generator,
    architectures: tuple[tuple[int, int], ...],
) -> Genome:
    values: list[object] = [
        genome.hidden_layers,
        genome.learning_rate,
        genome.l2_penalty,
        genome.label_smoothing,
    ]
    choices: tuple[tuple[object, ...], ...] = (
        architectures,
        _LEARNING_RATES,
        _L2_PENALTIES,
        _LABEL_SMOOTHING,
    )
    index = int(rng.integers(4))
    values[index] = choices[index][int(rng.integers(len(choices[index])))]
    return Genome(values[0], values[1], values[2], values[3])  # type: ignore[arg-type]
