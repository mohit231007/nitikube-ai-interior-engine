from __future__ import annotations

from dataclasses import dataclass
from math import hypot
from statistics import mean, pstdev
from typing import Iterable, Sequence

from .geometry import polygon_area


@dataclass(frozen=True)
class ScaleCalibration:
    feet_per_pixel: float
    pixels_per_foot: float
    reference_count: int
    relative_spread: float


def pixel_distance(p1: tuple[float, float], p2: tuple[float, float]) -> float:
    return hypot(p2[0] - p1[0], p2[1] - p1[1])


def scale_from_reference(pixel_distance_value: float, known_distance_ft: float) -> float:
    """Return feet per pixel from one user-verified dimension reference."""
    if pixel_distance_value <= 0 or known_distance_ft <= 0:
        raise ValueError("pixel and known distances must be positive")
    return known_distance_ft / pixel_distance_value


def calibrate_scale(references: Iterable[tuple[float, float]]) -> ScaleCalibration:
    """Calibrate scale from (pixel_distance, known_distance_ft) pairs.

    Multiple references expose disagreement instead of silently averaging a
    potentially bad OCR/CV measurement.
    """
    refs = list(references)
    if not refs:
        raise ValueError("at least one scale reference is required")
    scales = [scale_from_reference(px, ft) for px, ft in refs]
    avg = mean(scales)
    spread = 0.0 if len(scales) == 1 else pstdev(scales) / avg
    return ScaleCalibration(
        feet_per_pixel=avg,
        pixels_per_foot=1.0 / avg,
        reference_count=len(scales),
        relative_spread=spread,
    )


def pixels_to_feet(pixel_distance_value: float, feet_per_pixel: float) -> float:
    if pixel_distance_value < 0 or feet_per_pixel <= 0:
        raise ValueError("invalid distance/scale")
    return pixel_distance_value * feet_per_pixel


def pixel_polygon_area_ft2(points_px: Sequence[tuple[float, float]], feet_per_pixel: float) -> float:
    if feet_per_pixel <= 0:
        raise ValueError("feet_per_pixel must be positive")
    return polygon_area(points_px) * feet_per_pixel**2
