from __future__ import annotations

from dataclasses import dataclass
from math import log

import requests


@dataclass(frozen=True)
class ClimateSnapshot:
    latitude: float
    longitude: float
    elevation_m: float | None
    temperature_c: float | None
    relative_humidity_pct: float | None
    apparent_temperature_c: float | None
    wind_speed_kmh: float | None
    source: str = "Open-Meteo"


def dew_point_c(temperature_c: float, relative_humidity_pct: float) -> float:
    """Magnus approximation for dew point in Celsius."""
    if not (0 < relative_humidity_pct <= 100):
        raise ValueError("relative humidity must be in (0, 100]")
    a = 17.62
    b = 243.12
    gamma = (a * temperature_c) / (b + temperature_c) + log(relative_humidity_pct / 100.0)
    return (b * gamma) / (a - gamma)


def layer_r_value(thickness_m: float, conductivity_w_mk: float) -> float:
    if thickness_m <= 0 or conductivity_w_mk <= 0:
        raise ValueError("thickness and conductivity must be positive")
    return thickness_m / conductivity_w_mk


def u_value(r_layers: list[float], r_inside: float = 0.13, r_outside: float = 0.04) -> float:
    total_r = r_inside + r_outside + sum(r_layers)
    if total_r <= 0:
        raise ValueError("total thermal resistance must be positive")
    return 1.0 / total_r


def conductive_heat_flow_w(u_value_w_m2k: float, area_m2: float, delta_t_k: float) -> float:
    if u_value_w_m2k < 0 or area_m2 < 0:
        raise ValueError("U-value and area must be non-negative")
    return u_value_w_m2k * area_m2 * abs(delta_t_k)


def condensation_risk(surface_temperature_c: float, room_temperature_c: float, relative_humidity_pct: float) -> tuple[bool, float]:
    dp = dew_point_c(room_temperature_c, relative_humidity_pct)
    return surface_temperature_c <= dp, dp


def current_climate(latitude: float, longitude: float, timeout_s: int = 8) -> ClimateSnapshot:
    """Fetch a current climate snapshot from Open-Meteo's no-key endpoint.

    External providers are adapters: if this service or its licence changes,
    the science core remains independent and another provider can replace it.
    """
    params = {
        "latitude": latitude,
        "longitude": longitude,
        "current": "temperature_2m,relative_humidity_2m,apparent_temperature,wind_speed_10m",
        "timezone": "auto",
    }
    response = requests.get("https://api.open-meteo.com/v1/forecast", params=params, timeout=timeout_s)
    response.raise_for_status()
    payload = response.json()
    cur = payload.get("current", {})
    return ClimateSnapshot(
        latitude=float(payload.get("latitude", latitude)),
        longitude=float(payload.get("longitude", longitude)),
        elevation_m=payload.get("elevation"),
        temperature_c=cur.get("temperature_2m"),
        relative_humidity_pct=cur.get("relative_humidity_2m"),
        apparent_temperature_c=cur.get("apparent_temperature"),
        wind_speed_kmh=cur.get("wind_speed_10m"),
    )
