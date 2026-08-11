from __future__ import annotations

from dataclasses import dataclass
from math import inf
from typing import Iterable

from .geometry import factor_grids, ft2_to_m2, grid_layout
from .lighting import beam_diameter, estimated_maintained_lux


@dataclass(frozen=True)
class LightingCandidate:
    fixtures: int
    rows: int
    cols: int
    lumens_per_fixture: float
    maintained_lux: float
    beam_diameter_ft: float
    width_spacing_ft: float
    length_spacing_ft: float
    worst_spacing_to_beam: float
    score: float


def optimise_lighting_layouts(
    *,
    length_ft: float,
    width_ft: float,
    ceiling_height_ft: float,
    evaluation_plane_height_ft: float,
    beam_angle_deg: float,
    lumen_options: Iterable[float],
    min_lux: float,
    max_lux: float,
    max_spacing_to_beam: float = 1.20,
    coefficient_of_utilisation: float = 0.65,
    maintenance_factor: float = 0.80,
    min_fixtures: int = 4,
    max_fixtures: int = 30,
) -> list[LightingCandidate]:
    """Enumerate feasible fixture/grid combinations under explicit constraints.

    The caller owns the target lux range and acceptable spacing/beam ratio.
    NitiKube does not silently convert those assumptions into universal rules.
    """
    if length_ft <= 0 or width_ft <= 0:
        raise ValueError("room dimensions must be positive")
    if ceiling_height_ft <= evaluation_plane_height_ft:
        raise ValueError("ceiling must be above evaluation plane")
    if min_lux <= 0 or max_lux < min_lux:
        raise ValueError("invalid lux range")
    if max_spacing_to_beam <= 0:
        raise ValueError("max_spacing_to_beam must be positive")
    if min_fixtures < 1 or max_fixtures < min_fixtures:
        raise ValueError("invalid fixture-count range")

    lumen_options = sorted({float(x) for x in lumen_options if float(x) > 0})
    if not lumen_options:
        raise ValueError("at least one positive lumen option is required")

    area_m2 = ft2_to_m2(length_ft * width_ft)
    beam = beam_diameter(ceiling_height_ft - evaluation_plane_height_ft, beam_angle_deg)
    target_mid = (min_lux + max_lux) / 2.0
    room_aspect = length_ft / width_ft
    candidates: list[LightingCandidate] = []

    for n in range(min_fixtures, max_fixtures + 1):
        for rows, cols in factor_grids(n):
            layout = grid_layout(length_ft, width_ft, rows, cols)
            worst_ratio = max(layout.width_spacing_ft / beam, layout.length_spacing_ft / beam)
            if worst_ratio > max_spacing_to_beam:
                continue

            grid_aspect_error = abs((cols / rows) - room_aspect)
            for lumens in lumen_options:
                lux = estimated_maintained_lux(
                    area_m2,
                    n,
                    lumens,
                    coefficient_of_utilisation,
                    maintenance_factor,
                )
                if not (min_lux <= lux <= max_lux):
                    continue

                lux_error = abs(lux - target_mid) / target_mid
                # Smaller is better: prioritize target brightness, then
                # efficient fixture count, balanced geometry and beam overlap.
                score = (
                    lux_error * 100
                    + n * 0.20
                    + grid_aspect_error * 2.0
                    + worst_ratio * 2.0
                )
                candidates.append(
                    LightingCandidate(
                        fixtures=n,
                        rows=rows,
                        cols=cols,
                        lumens_per_fixture=lumens,
                        maintained_lux=lux,
                        beam_diameter_ft=beam,
                        width_spacing_ft=layout.width_spacing_ft,
                        length_spacing_ft=layout.length_spacing_ft,
                        worst_spacing_to_beam=worst_ratio,
                        score=score,
                    )
                )

    return sorted(candidates, key=lambda x: x.score)
