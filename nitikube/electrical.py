from __future__ import annotations

from dataclasses import dataclass


def single_phase_current_a(real_power_w: float, voltage_v: float, power_factor: float = 1.0, efficiency: float = 1.0) -> float:
    """I = P / (V × PF × efficiency) for a single-phase load."""
    if real_power_w < 0 or voltage_v <= 0:
        raise ValueError("power must be non-negative and voltage positive")
    if not 0 < power_factor <= 1:
        raise ValueError("power_factor must be in (0, 1]")
    if not 0 < efficiency <= 1:
        raise ValueError("efficiency must be in (0, 1]")
    return real_power_w / (voltage_v * power_factor * efficiency)


def energy_kwh(power_w: float, hours: float) -> float:
    if power_w < 0 or hours < 0:
        raise ValueError("power and hours must be non-negative")
    return power_w * hours / 1000.0


def conductor_resistance_ohm(resistivity_ohm_m: float, one_way_length_m: float, conductor_area_mm2: float, *, round_trip: bool = True) -> float:
    """R = ρL/A using explicitly supplied resistivity.

    No conductor-material constant is hardcoded; the caller must use a sourced
    resistivity appropriate to conductor material and design temperature.
    """
    if resistivity_ohm_m <= 0 or one_way_length_m < 0 or conductor_area_mm2 <= 0:
        raise ValueError("invalid conductor inputs")
    length = one_way_length_m * (2.0 if round_trip else 1.0)
    area_m2 = conductor_area_mm2 * 1e-6
    return resistivity_ohm_m * length / area_m2


def voltage_drop_v(current_a: float, resistance_ohm: float) -> float:
    if current_a < 0 or resistance_ohm < 0:
        raise ValueError("current and resistance must be non-negative")
    return current_a * resistance_ohm


def voltage_drop_percent(source_voltage_v: float, drop_v: float) -> float:
    if source_voltage_v <= 0 or drop_v < 0:
        raise ValueError("invalid voltage values")
    return 100.0 * drop_v / source_voltage_v


@dataclass(frozen=True)
class LoadItem:
    name: str
    watts_each: float
    quantity: int = 1
    diversity_factor: float = 1.0

    @property
    def connected_load_w(self) -> float:
        if self.watts_each < 0 or self.quantity < 0:
            raise ValueError("load watts/quantity cannot be negative")
        if not 0 <= self.diversity_factor <= 1:
            raise ValueError("diversity_factor must be in [0, 1]")
        return self.watts_each * self.quantity

    @property
    def diversified_load_w(self) -> float:
        return self.connected_load_w * self.diversity_factor


def aggregate_load(items: list[LoadItem]) -> tuple[float, float]:
    return (
        sum(item.connected_load_w for item in items),
        sum(item.diversified_load_w for item in items),
    )
