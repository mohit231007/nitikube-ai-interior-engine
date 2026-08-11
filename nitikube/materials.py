from __future__ import annotations

from dataclasses import dataclass
from math import ceil


@dataclass(frozen=True)
class QuantityEstimate:
    net_area: float
    waste_fraction: float
    gross_area: float
    unit_area: float
    units_required: int


def material_units(net_area: float, unit_area: float, waste_fraction: float = 0.10) -> QuantityEstimate:
    """Calculate purchasable units for tile/board/panel-like materials."""
    if net_area <= 0 or unit_area <= 0:
        raise ValueError("areas must be positive")
    if not (0 <= waste_fraction < 1):
        raise ValueError("waste_fraction must be in [0, 1)")
    gross = net_area * (1 + waste_fraction)
    return QuantityEstimate(
        net_area=net_area,
        waste_fraction=waste_fraction,
        gross_area=gross,
        unit_area=unit_area,
        units_required=ceil(gross / unit_area),
    )


@dataclass(frozen=True)
class PaintEstimate:
    paintable_area_ft2: float
    coats: int
    coverage_ft2_per_litre_per_coat: float
    waste_fraction: float
    litres_required: float


def paint_litres(
    paintable_area_ft2: float,
    coats: int,
    coverage_ft2_per_litre_per_coat: float,
    waste_fraction: float = 0.10,
) -> PaintEstimate:
    if paintable_area_ft2 <= 0 or coats < 1 or coverage_ft2_per_litre_per_coat <= 0:
        raise ValueError("invalid paint inputs")
    if not (0 <= waste_fraction < 1):
        raise ValueError("waste_fraction must be in [0, 1)")
    litres = (
        paintable_area_ft2 * coats / coverage_ft2_per_litre_per_coat
    ) * (1 + waste_fraction)
    return PaintEstimate(
        paintable_area_ft2=paintable_area_ft2,
        coats=coats,
        coverage_ft2_per_litre_per_coat=coverage_ft2_per_litre_per_coat,
        waste_fraction=waste_fraction,
        litres_required=litres,
    )


@dataclass(frozen=True)
class MaterialProfile:
    name: str
    moisture_resistance: float
    thermal_stability: float
    maintenance_ease: float
    durability: float
    indoor_emissions: float
    relative_cost: float


def suitability_score(
    material: MaterialProfile,
    *,
    moisture_weight: float = 0.25,
    thermal_weight: float = 0.15,
    maintenance_weight: float = 0.20,
    durability_weight: float = 0.25,
    emissions_weight: float = 0.15,
) -> float:
    """0-100 material suitability score from explicitly supplied properties.

    Properties are expected on a 0-100 scale. This deliberately does not
    contain invented material facts; the database/provenance layer supplies
    those separately.
    """
    weights = [moisture_weight, thermal_weight, maintenance_weight, durability_weight, emissions_weight]
    if any(w < 0 for w in weights) or sum(weights) <= 0:
        raise ValueError("weights must be non-negative and sum to > 0")
    values = [
        material.moisture_resistance,
        material.thermal_stability,
        material.maintenance_ease,
        material.durability,
        100 - material.indoor_emissions,
    ]
    if any(not 0 <= x <= 100 for x in values):
        raise ValueError("material properties must be on a 0-100 scale")
    weighted = sum(v * w for v, w in zip(values, weights)) / sum(weights)
    return round(weighted, 2)


def value_index(suitability: float, relative_cost: float) -> float:
    if suitability < 0 or relative_cost <= 0:
        raise ValueError("invalid value-index inputs")
    return suitability / relative_cost
