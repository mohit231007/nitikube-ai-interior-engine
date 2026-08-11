from __future__ import annotations

from dataclasses import dataclass
from math import ceil, radians, tan

from .geometry import GridLayout, choose_grid, ft2_to_m2


def beam_diameter(distance_ft: float, beam_angle_deg: float) -> float:
    """Diameter of the nominal beam cone at a plane below the fixture.

    D = 2 h tan(theta / 2)
    """
    if distance_ft <= 0:
        raise ValueError("distance_ft must be positive")
    if not (0 < beam_angle_deg < 180):
        raise ValueError("beam_angle_deg must be between 0 and 180")
    return 2.0 * distance_ft * tan(radians(beam_angle_deg / 2.0))


def installed_lumens_required(
    area_m2: float,
    target_lux: float,
    coefficient_of_utilisation: float = 0.65,
    maintenance_factor: float = 0.80,
) -> float:
    """Lumen-method estimate for total installed luminous flux.

    Phi = E * A / (CU * MF)
    """
    if area_m2 <= 0 or target_lux <= 0:
        raise ValueError("area and target lux must be positive")
    if not (0 < coefficient_of_utilisation <= 1):
        raise ValueError("coefficient_of_utilisation must be in (0, 1]")
    if not (0 < maintenance_factor <= 1):
        raise ValueError("maintenance_factor must be in (0, 1]")
    return target_lux * area_m2 / (coefficient_of_utilisation * maintenance_factor)


def fixture_count(required_lumens: float, lumens_per_fixture: float) -> int:
    if required_lumens <= 0 or lumens_per_fixture <= 0:
        raise ValueError("lumen values must be positive")
    return ceil(required_lumens / lumens_per_fixture)


def estimated_maintained_lux(
    area_m2: float,
    fixtures: int,
    lumens_per_fixture: float,
    coefficient_of_utilisation: float = 0.65,
    maintenance_factor: float = 0.80,
) -> float:
    if area_m2 <= 0 or fixtures < 1 or lumens_per_fixture <= 0:
        raise ValueError("invalid lighting inputs")
    return fixtures * lumens_per_fixture * coefficient_of_utilisation * maintenance_factor / area_m2


@dataclass(frozen=True)
class LightingRecommendation:
    area_ft2: float
    area_m2: float
    target_lux: float
    installed_lumens_required: float
    fixtures: int
    lumens_per_fixture: float
    estimated_lux: float
    beam_diameter_workplane_ft: float
    grid: GridLayout
    width_spacing_to_beam: float
    length_spacing_to_beam: float
    uniformity_note: str


def recommend_lighting(
    *,
    length_ft: float,
    width_ft: float,
    ceiling_height_ft: float,
    workplane_height_ft: float,
    target_lux: float,
    lumens_per_fixture: float,
    beam_angle_deg: float,
    coefficient_of_utilisation: float = 0.65,
    maintenance_factor: float = 0.80,
    preferred_rows: int | None = None,
) -> LightingRecommendation:
    if ceiling_height_ft <= workplane_height_ft:
        raise ValueError("ceiling must be above the work plane")

    area_ft2 = length_ft * width_ft
    area_m2 = ft2_to_m2(area_ft2)
    required = installed_lumens_required(
        area_m2,
        target_lux,
        coefficient_of_utilisation,
        maintenance_factor,
    )
    n = fixture_count(required, lumens_per_fixture)
    grid = choose_grid(length_ft, width_ft, n, preferred_rows=preferred_rows)
    distance = ceiling_height_ft - workplane_height_ft
    beam = beam_diameter(distance, beam_angle_deg)
    width_ratio = grid.width_spacing_ft / beam
    length_ratio = grid.length_spacing_ft / beam
    worst = max(width_ratio, length_ratio)

    if worst <= 1.0:
        note = "Nominal beams overlap at the selected work plane."
    elif worst <= 1.25:
        note = "Moderate nominal-beam gaps are expected; real fixture spill may still provide acceptable ambient uniformity."
    else:
        note = "Nominal beam spacing is wide for this beam angle; add fixtures, use a wider beam, or provide diffuse/cove fill lighting."

    return LightingRecommendation(
        area_ft2=area_ft2,
        area_m2=area_m2,
        target_lux=target_lux,
        installed_lumens_required=required,
        fixtures=n,
        lumens_per_fixture=lumens_per_fixture,
        estimated_lux=estimated_maintained_lux(
            area_m2,
            n,
            lumens_per_fixture,
            coefficient_of_utilisation,
            maintenance_factor,
        ),
        beam_diameter_workplane_ft=beam,
        grid=grid,
        width_spacing_to_beam=width_ratio,
        length_spacing_to_beam=length_ratio,
        uniformity_note=note,
    )
