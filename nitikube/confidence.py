from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ConfidenceInputs:
    source_reliability: float
    measurement_confidence: float
    data_freshness: float
    constraint_completeness: float


def confidence_score(
    inputs: ConfidenceInputs,
    weights: tuple[float, float, float, float] = (0.30, 0.30, 0.20, 0.20),
) -> float:
    values = (
        inputs.source_reliability,
        inputs.measurement_confidence,
        inputs.data_freshness,
        inputs.constraint_completeness,
    )
    if any(not 0 <= v <= 100 for v in values):
        raise ValueError("confidence components must be in [0, 100]")
    if any(w < 0 for w in weights) or sum(weights) <= 0:
        raise ValueError("invalid confidence weights")
    return round(sum(v * w for v, w in zip(values, weights)) / sum(weights), 2)


def confidence_label(score: float) -> str:
    if not 0 <= score <= 100:
        raise ValueError("score must be in [0, 100]")
    if score >= 90:
        return "High"
    if score >= 75:
        return "Moderate-high"
    if score >= 60:
        return "Moderate"
    return "Low / verify inputs"
