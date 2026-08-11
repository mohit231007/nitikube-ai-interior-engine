from __future__ import annotations

from collections import defaultdict
from dataclasses import asdict, dataclass
from datetime import date, datetime, timezone
import math
from typing import Iterable, Sequence

import requests


@dataclass(frozen=True)
class DailyClimateRecord:
    date: date
    temperature_mean_c: float | None = None
    temperature_max_c: float | None = None
    temperature_min_c: float | None = None
    precipitation_mm: float | None = None
    shortwave_radiation_mj_m2: float | None = None
    wind_speed_max_kmh: float | None = None
    relative_humidity_mean_pct: float | None = None


@dataclass(frozen=True)
class ClimateSource:
    provider: str
    dataset: str
    latitude: float
    longitude: float
    elevation_m: float | None
    timezone: str | None
    start_date: date
    end_date: date
    checked_at: str
    source_url: str


@dataclass(frozen=True)
class ClimateDataset:
    records: tuple[DailyClimateRecord, ...]
    source: ClimateSource


@dataclass(frozen=True)
class ClimateThresholds:
    hot_day_max_c: float
    cold_day_min_c: float
    heavy_rain_day_mm: float
    high_solar_day_mj_m2: float
    high_humidity_pct: float | None = None


@dataclass(frozen=True)
class ClimateProfile:
    days: int
    start_date: date
    end_date: date
    years_equivalent: float
    mean_temperature_c: float | None
    p05_mean_temperature_c: float | None
    p95_mean_temperature_c: float | None
    mean_daily_max_c: float | None
    mean_daily_min_c: float | None
    hottest_day_c: float | None
    coldest_day_c: float | None
    annualized_precipitation_mm: float | None
    wet_days_per_year: float | None
    mean_daily_shortwave_mj_m2: float | None
    annualized_shortwave_kwh_m2: float | None
    mean_max_wind_kmh: float | None
    p95_max_wind_kmh: float | None
    mean_relative_humidity_pct: float | None
    hot_days_per_year: float
    cold_days_per_year: float
    heavy_rain_days_per_year: float
    high_solar_days_per_year: float
    high_humidity_days_per_year: float | None
    heating_degree_days_per_year: float | None
    cooling_degree_days_per_year: float | None
    heating_base_c: float | None
    cooling_base_c: float | None


@dataclass(frozen=True)
class MonthlyClimateSummary:
    month: int
    sample_days: int
    mean_temperature_c: float | None
    mean_daily_max_c: float | None
    mean_daily_min_c: float | None
    mean_precipitation_mm_day: float | None
    mean_shortwave_mj_m2_day: float | None
    mean_relative_humidity_pct: float | None


@dataclass(frozen=True)
class ClimateComparison:
    metric: str
    unit: str
    location_a: float | None
    location_b: float | None
    difference_b_minus_a: float | None


def _finite(values: Iterable[float | None]) -> list[float]:
    return [float(v) for v in values if v is not None and math.isfinite(float(v))]


def percentile(values: Sequence[float], q: float) -> float:
    """Linear-interpolated percentile with q in [0, 1]."""
    if not values:
        raise ValueError("percentile requires at least one value")
    if not 0 <= q <= 1:
        raise ValueError("q must be in [0,1]")
    ordered = sorted(float(v) for v in values)
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * q
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    weight = position - lower
    return ordered[lower] * (1 - weight) + ordered[upper] * weight


def _mean_or_none(values: Iterable[float | None]) -> float | None:
    valid = _finite(values)
    return sum(valid) / len(valid) if valid else None


def _annualize(total_or_count: float, days: int) -> float:
    if days <= 0:
        raise ValueError("days must be positive")
    return total_or_count * 365.2425 / days


def degree_days(
    records: Sequence[DailyClimateRecord],
    *,
    heating_base_c: float | None,
    cooling_base_c: float | None,
) -> tuple[float | None, float | None]:
    temperatures = [r.temperature_mean_c for r in records]
    valid = _finite(temperatures)
    if not valid:
        return None, None
    heating = None
    cooling = None
    if heating_base_c is not None:
        heating_total = sum(max(0.0, heating_base_c - float(t)) for t in temperatures if t is not None)
        heating = _annualize(heating_total, len(records))
    if cooling_base_c is not None:
        cooling_total = sum(max(0.0, float(t) - cooling_base_c) for t in temperatures if t is not None)
        cooling = _annualize(cooling_total, len(records))
    return heating, cooling


def build_climate_profile(
    records: Sequence[DailyClimateRecord],
    thresholds: ClimateThresholds,
    *,
    heating_base_c: float | None = None,
    cooling_base_c: float | None = None,
) -> ClimateProfile:
    if not records:
        raise ValueError("at least one climate record is required")
    ordered = sorted(records, key=lambda r: r.date)
    if len({r.date for r in ordered}) != len(ordered):
        raise ValueError("duplicate dates are not allowed")

    n_days = len(ordered)
    t_mean = _finite(r.temperature_mean_c for r in ordered)
    t_max = _finite(r.temperature_max_c for r in ordered)
    t_min = _finite(r.temperature_min_c for r in ordered)
    precip = _finite(r.precipitation_mm for r in ordered)
    solar = _finite(r.shortwave_radiation_mj_m2 for r in ordered)
    wind = _finite(r.wind_speed_max_kmh for r in ordered)
    humidity = _finite(r.relative_humidity_mean_pct for r in ordered)

    hot_count = sum(
        1 for r in ordered if r.temperature_max_c is not None and r.temperature_max_c >= thresholds.hot_day_max_c
    )
    cold_count = sum(
        1 for r in ordered if r.temperature_min_c is not None and r.temperature_min_c <= thresholds.cold_day_min_c
    )
    heavy_rain_count = sum(
        1 for r in ordered if r.precipitation_mm is not None and r.precipitation_mm >= thresholds.heavy_rain_day_mm
    )
    high_solar_count = sum(
        1
        for r in ordered
        if r.shortwave_radiation_mj_m2 is not None
        and r.shortwave_radiation_mj_m2 >= thresholds.high_solar_day_mj_m2
    )
    high_humidity_count = None
    if thresholds.high_humidity_pct is not None and humidity:
        high_humidity_count = sum(
            1
            for r in ordered
            if r.relative_humidity_mean_pct is not None
            and r.relative_humidity_mean_pct >= thresholds.high_humidity_pct
        )

    heating_dd, cooling_dd = degree_days(
        ordered,
        heating_base_c=heating_base_c,
        cooling_base_c=cooling_base_c,
    )

    return ClimateProfile(
        days=n_days,
        start_date=ordered[0].date,
        end_date=ordered[-1].date,
        years_equivalent=n_days / 365.2425,
        mean_temperature_c=sum(t_mean) / len(t_mean) if t_mean else None,
        p05_mean_temperature_c=percentile(t_mean, 0.05) if t_mean else None,
        p95_mean_temperature_c=percentile(t_mean, 0.95) if t_mean else None,
        mean_daily_max_c=sum(t_max) / len(t_max) if t_max else None,
        mean_daily_min_c=sum(t_min) / len(t_min) if t_min else None,
        hottest_day_c=max(t_max) if t_max else None,
        coldest_day_c=min(t_min) if t_min else None,
        annualized_precipitation_mm=_annualize(sum(precip), n_days) if precip else None,
        wet_days_per_year=_annualize(sum(v > 0 for v in precip), n_days) if precip else None,
        mean_daily_shortwave_mj_m2=sum(solar) / len(solar) if solar else None,
        annualized_shortwave_kwh_m2=_annualize(sum(solar) / 3.6, n_days) if solar else None,
        mean_max_wind_kmh=sum(wind) / len(wind) if wind else None,
        p95_max_wind_kmh=percentile(wind, 0.95) if wind else None,
        mean_relative_humidity_pct=sum(humidity) / len(humidity) if humidity else None,
        hot_days_per_year=_annualize(hot_count, n_days),
        cold_days_per_year=_annualize(cold_count, n_days),
        heavy_rain_days_per_year=_annualize(heavy_rain_count, n_days),
        high_solar_days_per_year=_annualize(high_solar_count, n_days),
        high_humidity_days_per_year=_annualize(high_humidity_count, n_days) if high_humidity_count is not None else None,
        heating_degree_days_per_year=heating_dd,
        cooling_degree_days_per_year=cooling_dd,
        heating_base_c=heating_base_c,
        cooling_base_c=cooling_base_c,
    )


def monthly_climate_summary(records: Sequence[DailyClimateRecord]) -> tuple[MonthlyClimateSummary, ...]:
    grouped: dict[int, list[DailyClimateRecord]] = defaultdict(list)
    for record in records:
        grouped[record.date.month].append(record)
    return tuple(
        MonthlyClimateSummary(
            month=month,
            sample_days=len(group),
            mean_temperature_c=_mean_or_none(r.temperature_mean_c for r in group),
            mean_daily_max_c=_mean_or_none(r.temperature_max_c for r in group),
            mean_daily_min_c=_mean_or_none(r.temperature_min_c for r in group),
            mean_precipitation_mm_day=_mean_or_none(r.precipitation_mm for r in group),
            mean_shortwave_mj_m2_day=_mean_or_none(r.shortwave_radiation_mj_m2 for r in group),
            mean_relative_humidity_pct=_mean_or_none(r.relative_humidity_mean_pct for r in group),
        )
        for month, group in sorted(grouped.items())
    )


def compare_climate_profiles(a: ClimateProfile, b: ClimateProfile) -> tuple[ClimateComparison, ...]:
    metrics = [
        ("mean_temperature", "°C", a.mean_temperature_c, b.mean_temperature_c),
        ("hottest_day", "°C", a.hottest_day_c, b.hottest_day_c),
        ("coldest_day", "°C", a.coldest_day_c, b.coldest_day_c),
        ("annualized_precipitation", "mm/year", a.annualized_precipitation_mm, b.annualized_precipitation_mm),
        ("hot_days", "days/year", a.hot_days_per_year, b.hot_days_per_year),
        ("cold_days", "days/year", a.cold_days_per_year, b.cold_days_per_year),
        ("heavy_rain_days", "days/year", a.heavy_rain_days_per_year, b.heavy_rain_days_per_year),
        ("high_solar_days", "days/year", a.high_solar_days_per_year, b.high_solar_days_per_year),
        ("annualized_shortwave", "kWh/m²/year", a.annualized_shortwave_kwh_m2, b.annualized_shortwave_kwh_m2),
        ("heating_degree_days", "K·day/year", a.heating_degree_days_per_year, b.heating_degree_days_per_year),
        ("cooling_degree_days", "K·day/year", a.cooling_degree_days_per_year, b.cooling_degree_days_per_year),
    ]
    result = []
    for name, unit, av, bv in metrics:
        diff = None if av is None or bv is None else bv - av
        result.append(ClimateComparison(name, unit, av, bv, diff))
    return tuple(result)


def climate_design_drivers(profile: ClimateProfile, *, tolerance_days_per_year: float = 1.0) -> list[dict[str, str | float]]:
    """Translate computed climate exposures into *questions to design for*.

    These are not material prescriptions or code requirements. They identify
    which engineering checks deserve attention based on user-selected exposure
    thresholds used to create the profile.
    """
    drivers: list[dict[str, str | float]] = []
    if profile.hot_days_per_year >= tolerance_days_per_year:
        drivers.append(
            {
                "driver": "heat exposure",
                "annual_frequency": profile.hot_days_per_year,
                "check": "solar control, glazing, shading, ventilation and cooling-load assumptions",
            }
        )
    if profile.cold_days_per_year >= tolerance_days_per_year:
        drivers.append(
            {
                "driver": "cold exposure",
                "annual_frequency": profile.cold_days_per_year,
                "check": "insulation, thermal bridging, glazing and heating-load assumptions",
            }
        )
    if profile.heavy_rain_days_per_year >= tolerance_days_per_year:
        drivers.append(
            {
                "driver": "heavy-rain exposure",
                "annual_frequency": profile.heavy_rain_days_per_year,
                "check": "waterproofing details, drainage, exterior finishes and opening protection",
            }
        )
    if profile.high_solar_days_per_year >= tolerance_days_per_year:
        drivers.append(
            {
                "driver": "high solar exposure",
                "annual_frequency": profile.high_solar_days_per_year,
                "check": "orientation-specific shading, UV exposure and solar heat gain",
            }
        )
    if profile.high_humidity_days_per_year is not None and profile.high_humidity_days_per_year >= tolerance_days_per_year:
        drivers.append(
            {
                "driver": "high humidity exposure",
                "annual_frequency": profile.high_humidity_days_per_year,
                "check": "condensation, mould, ventilation and moisture-sensitive materials",
            }
        )
    return drivers


def historical_daily_open_meteo(
    latitude: float,
    longitude: float,
    start_date: date,
    end_date: date,
    *,
    model: str = "era5_land",
    timezone_name: str = "auto",
    timeout_s: int = 30,
) -> ClimateDataset:
    """Fetch daily historical reanalysis data through the replaceable Open-Meteo adapter.

    The endpoint and variables follow Open-Meteo's Historical Weather API. The
    returned source metadata is persisted so downstream explanations can state
    which provider/model and time range were used. Network/provider failures are
    surfaced to the caller; no synthetic fallback is created.
    """
    if start_date > end_date:
        raise ValueError("start_date must be on or before end_date")
    if not -90 <= latitude <= 90 or not -180 <= longitude <= 180:
        raise ValueError("invalid latitude/longitude")

    endpoint = "https://archive-api.open-meteo.com/v1/archive"
    daily_variables = [
        "temperature_2m_mean",
        "temperature_2m_max",
        "temperature_2m_min",
        "precipitation_sum",
        "shortwave_radiation_sum",
        "wind_speed_10m_max",
    ]
    params = {
        "latitude": latitude,
        "longitude": longitude,
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "daily": ",".join(daily_variables),
        "timezone": timezone_name,
        "models": model,
    }
    response = requests.get(endpoint, params=params, timeout=timeout_s)
    response.raise_for_status()
    payload = response.json()
    daily = payload.get("daily") or {}
    dates = daily.get("time") or []
    if not dates:
        raise ValueError("historical climate provider returned no daily records")

    def value_at(name: str, idx: int) -> float | None:
        values = daily.get(name) or []
        if idx >= len(values) or values[idx] is None:
            return None
        return float(values[idx])

    records = tuple(
        DailyClimateRecord(
            date=date.fromisoformat(day),
            temperature_mean_c=value_at("temperature_2m_mean", i),
            temperature_max_c=value_at("temperature_2m_max", i),
            temperature_min_c=value_at("temperature_2m_min", i),
            precipitation_mm=value_at("precipitation_sum", i),
            shortwave_radiation_mj_m2=value_at("shortwave_radiation_sum", i),
            wind_speed_max_kmh=value_at("wind_speed_10m_max", i),
        )
        for i, day in enumerate(dates)
    )
    source = ClimateSource(
        provider="Open-Meteo",
        dataset=model,
        latitude=float(payload.get("latitude", latitude)),
        longitude=float(payload.get("longitude", longitude)),
        elevation_m=float(payload["elevation"]) if payload.get("elevation") is not None else None,
        timezone=payload.get("timezone"),
        start_date=start_date,
        end_date=end_date,
        checked_at=datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        source_url="https://open-meteo.com/en/docs/historical-weather-api",
    )
    return ClimateDataset(records=records, source=source)


def profile_rows(profile: ClimateProfile) -> list[dict[str, object]]:
    return [
        {"metric": key, "value": value}
        for key, value in asdict(profile).items()
    ]
