from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True)
class DesignOption:
    name: str
    cost: float
    quality: float
    durability: float
    aesthetics: float
    comfort: float
    maintainability: float
    feasible: bool = True

    def metrics(self) -> tuple[float, float, float, float, float]:
        return (self.quality, self.durability, self.aesthetics, self.comfort, self.maintainability)


def validate_option(option: DesignOption) -> None:
    if option.cost < 0:
        raise ValueError("cost cannot be negative")
    if any(not 0 <= value <= 100 for value in option.metrics()):
        raise ValueError("option scores must be in [0, 100]")


def weighted_rank(
    options: Iterable[DesignOption],
    *,
    budget: float,
    weights: tuple[float, float, float, float, float] = (0.25, 0.25, 0.15, 0.15, 0.20),
) -> list[tuple[DesignOption, float]]:
    if budget < 0:
        raise ValueError("budget cannot be negative")
    if any(w < 0 for w in weights) or sum(weights) <= 0:
        raise ValueError("invalid weights")

    ranked = []
    for option in options:
        validate_option(option)
        if not option.feasible or option.cost > budget:
            continue
        score = sum(v * w for v, w in zip(option.metrics(), weights)) / sum(weights)
        ranked.append((option, score))
    return sorted(ranked, key=lambda pair: pair[1], reverse=True)


def dominates(a: DesignOption, b: DesignOption) -> bool:
    """True when a is no worse on cost/metrics and strictly better somewhere."""
    validate_option(a)
    validate_option(b)
    a_metrics = a.metrics()
    b_metrics = b.metrics()
    no_worse = a.cost <= b.cost and all(x >= y for x, y in zip(a_metrics, b_metrics))
    strictly_better = a.cost < b.cost or any(x > y for x, y in zip(a_metrics, b_metrics))
    return no_worse and strictly_better


def pareto_front(options: Iterable[DesignOption], *, budget: float | None = None) -> list[DesignOption]:
    pool = []
    for option in options:
        validate_option(option)
        if option.feasible and (budget is None or option.cost <= budget):
            pool.append(option)
    return [candidate for candidate in pool if not any(dominates(other, candidate) for other in pool if other is not candidate)]
