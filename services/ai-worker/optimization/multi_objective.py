"""Choose measured OCR settings within accuracy and memory deployment budgets.

Latency, memory, and extraction F1 remain separate objectives. A faster model
cannot compensate for violating the minimum quality requirement. This is a
Pareto selection heuristic, not evolutionary training or a generalization bound.
"""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class OperatingPoint:
    """Measured outcomes for one configuration on an identical workload."""

    name: str
    f1: float
    latency_ms: float
    memory_mib: float

    def __post_init__(self) -> None:
        if not self.name or not all(
            math.isfinite(v) for v in (self.f1, self.latency_ms, self.memory_mib)
        ):
            raise ValueError("configuration and finite measured objectives are required")
        if not 0 <= self.f1 <= 1 or self.latency_ms <= 0 or self.memory_mib <= 0:
            raise ValueError("F1 must be in [0, 1]; latency and memory must be positive")

    def dominates(self, other: OperatingPoint) -> bool:
        """True only when no objective is worse and at least one is better."""
        return (
            self.f1 >= other.f1
            and self.latency_ms <= other.latency_ms
            and self.memory_mib <= other.memory_mib
            and (
                self.f1 > other.f1
                or self.latency_ms < other.latency_ms
                or self.memory_mib < other.memory_mib
            )
        )


def pareto_front(points: list[OperatingPoint]) -> list[OperatingPoint]:
    """Return nondominated measured options in stable order; O(configurations²)."""
    return sorted(
        (p for p in points if not any(q.dominates(p) for q in points)),
        key=lambda p: (p.latency_ms, p.memory_mib, -p.f1, p.name),
    )


def select_configuration(
    points: list[OperatingPoint], *, min_f1: float, max_memory_mib: float
) -> OperatingPoint | None:
    """Choose the fastest feasible Pareto option, or explicitly return no solution."""
    if not math.isfinite(min_f1) or not 0 <= min_f1 <= 1:
        raise ValueError("minimum F1 must be finite and in [0, 1]")
    if not math.isfinite(max_memory_mib) or max_memory_mib <= 0:
        raise ValueError("memory budget must be finite and positive")
    feasible = [
        p for p in pareto_front(points) if p.f1 >= min_f1 and p.memory_mib <= max_memory_mib
    ]
    return feasible[0] if feasible else None
