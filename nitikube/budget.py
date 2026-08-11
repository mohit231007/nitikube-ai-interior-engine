from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping


DEFAULT_WEIGHTS = {
    "kitchen": 0.25,
    "wardrobes_storage": 0.18,
    "furniture": 0.20,
    "lighting_electrical": 0.10,
    "ceiling_paint": 0.09,
    "flooring_surfaces": 0.08,
    "soft_furnishings": 0.04,
    "contingency": 0.06,
}


@dataclass(frozen=True)
class BudgetScenario:
    name: str
    total_budget: float
    allocations: dict[str, float]
    reserve: float


def normalize_weights(weights: Mapping[str, float]) -> dict[str, float]:
    if not weights:
        raise ValueError("weights are required")
    if any(v < 0 for v in weights.values()):
        raise ValueError("weights must be non-negative")
    total = sum(weights.values())
    if total <= 0:
        raise ValueError("weights must sum to > 0")
    return {k: v / total for k, v in weights.items()}


def allocate_budget(total_budget: float, weights: Mapping[str, float] | None = None) -> dict[str, float]:
    if total_budget <= 0:
        raise ValueError("total_budget must be positive")
    normalized = normalize_weights(weights or DEFAULT_WEIGHTS)
    return {k: round(total_budget * w, 2) for k, w in normalized.items()}


def build_scenarios(total_budget: float) -> list[BudgetScenario]:
    """Produce three deterministic budget envelopes.

    These are envelopes, not market-price claims. Actual BOQ/product prices
    must come from verified supplier/product data.
    """
    if total_budget <= 0:
        raise ValueError("total_budget must be positive")

    variants = [
        ("Value", 0.82, 0.08),
        ("Balanced", 0.92, 0.06),
        ("Premium within budget", 1.00, 0.05),
    ]
    scenarios: list[BudgetScenario] = []
    for name, spend_fraction, reserve_fraction in variants:
        usable = total_budget * spend_fraction
        reserve = total_budget * reserve_fraction
        allocations = allocate_budget(max(usable - reserve, 1.0))
        scenarios.append(BudgetScenario(name, total_budget, allocations, round(reserve, 2)))
    return scenarios


def weighted_option_score(
    *,
    quality: float,
    durability: float,
    aesthetics: float,
    comfort: float,
    maintainability: float,
    cost: float,
    budget: float,
    weights: tuple[float, float, float, float, float] = (0.25, 0.25, 0.15, 0.15, 0.20),
) -> float:
    """Score a feasible option; over-budget options receive -inf."""
    if cost > budget:
        return float("-inf")
    values = (quality, durability, aesthetics, comfort, maintainability)
    if any(not 0 <= v <= 100 for v in values):
        raise ValueError("scores must be in [0, 100]")
    if any(w < 0 for w in weights) or sum(weights) <= 0:
        raise ValueError("invalid weights")
    return sum(v * w for v, w in zip(values, weights)) / sum(weights)
