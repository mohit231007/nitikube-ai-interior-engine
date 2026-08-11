from __future__ import annotations

from dataclasses import dataclass
from math import log10
from typing import Iterable


@dataclass(frozen=True)
class AbsorbingSurface:
    area_m2: float
    absorption_coefficient: float
    label: str = "surface"

    @property
    def equivalent_absorption_area_m2(self) -> float:
        if self.area_m2 < 0:
            raise ValueError("surface area cannot be negative")
        if not 0 <= self.absorption_coefficient <= 1:
            raise ValueError("absorption coefficient must be in [0, 1]")
        return self.area_m2 * self.absorption_coefficient


def total_absorption_area_m2(surfaces: Iterable[AbsorbingSurface]) -> float:
    return sum(surface.equivalent_absorption_area_m2 for surface in surfaces)


def sabine_rt60_seconds(volume_m3: float, equivalent_absorption_area_m2: float) -> float:
    """Sabine reverberation-time estimate in SI units.

    T60 = 0.161 V / A

    Appropriate as a transparent first-order room-acoustics estimate. It is
    less accurate when absorption is very high/nonuniform or room geometry is
    strongly non-diffuse; more detailed models can be added later.
    """
    if volume_m3 <= 0:
        raise ValueError("room volume must be positive")
    if equivalent_absorption_area_m2 <= 0:
        raise ValueError("equivalent absorption area must be positive")
    return 0.161 * volume_m3 / equivalent_absorption_area_m2


def room_volume_m3(length_m: float, width_m: float, height_m: float) -> float:
    if min(length_m, width_m, height_m) <= 0:
        raise ValueError("room dimensions must be positive")
    return length_m * width_m * height_m


def absorption_needed_for_target_rt60(volume_m3: float, target_rt60_s: float) -> float:
    if volume_m3 <= 0 or target_rt60_s <= 0:
        raise ValueError("volume and target RT60 must be positive")
    return 0.161 * volume_m3 / target_rt60_s


def free_field_level_change_db(distance_1_m: float, distance_2_m: float) -> float:
    """Sound-pressure level change under ideal free-field inverse-distance spreading.

    ΔL = -20 log10(r2/r1). Real rooms include reflections and absorption, so
    this is a geometry/physics diagnostic rather than a prediction of lived SPL.
    """
    if distance_1_m <= 0 or distance_2_m <= 0:
        raise ValueError("distances must be positive")
    return -20.0 * log10(distance_2_m / distance_1_m)
