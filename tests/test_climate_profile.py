from datetime import date

import pytest

from nitikube.climate_profile import (
    ClimateThresholds,
    DailyClimateRecord,
    build_climate_profile,
    climate_design_drivers,
    compare_climate_profiles,
    degree_days,
    historical_daily_open_meteo,
    monthly_climate_summary,
    percentile,
)


def _records(values):
    return [
        DailyClimateRecord(
            date=date(2025, 1, index + 1),
            temperature_mean_c=value[0],
            temperature_max_c=value[1],
            temperature_min_c=value[2],
            precipitation_mm=value[3],
            shortwave_radiation_mj_m2=value[4],
            wind_speed_max_kmh=value[5],
            relative_humidity_mean_pct=value[6] if len(value) > 6 else None,
        )
        for index, value in enumerate(values)
    ]


def test_percentile_is_linear_interpolated():
    assert percentile([0.0, 10.0], 0.5) == pytest.approx(5.0)
    assert percentile([0.0, 10.0, 20.0], 0.25) == pytest.approx(5.0)
    with pytest.raises(ValueError):
        percentile([], 0.5)


def test_profile_uses_explicit_thresholds_and_real_arithmetic():
    records = _records(
        [
            (20.0, 36.0, 12.0, 0.0, 22.0, 15.0, 55.0),
            (10.0, 18.0, 4.0, 25.0, 8.0, 35.0, 85.0),
            (25.0, 33.0, 16.0, 2.0, 24.0, 20.0, 70.0),
            (15.0, 20.0, 8.0, 30.0, 10.0, 45.0, 90.0),
        ]
    )
    thresholds = ClimateThresholds(
        hot_day_max_c=35.0,
        cold_day_min_c=5.0,
        heavy_rain_day_mm=20.0,
        high_solar_day_mj_m2=20.0,
        high_humidity_pct=80.0,
    )
    profile = build_climate_profile(records, thresholds, heating_base_c=18.0, cooling_base_c=24.0)

    assert profile.mean_temperature_c == pytest.approx(17.5)
    assert profile.hottest_day_c == pytest.approx(36.0)
    assert profile.coldest_day_c == pytest.approx(4.0)
    assert profile.mean_daily_shortwave_mj_m2 == pytest.approx(16.0)
    assert profile.hot_days_per_year == pytest.approx(365.2425 / 4)
    assert profile.cold_days_per_year == pytest.approx(365.2425 / 4)
    assert profile.heavy_rain_days_per_year == pytest.approx(2 * 365.2425 / 4)
    assert profile.high_solar_days_per_year == pytest.approx(2 * 365.2425 / 4)
    assert profile.high_humidity_days_per_year == pytest.approx(2 * 365.2425 / 4)
    assert profile.heating_degree_days_per_year == pytest.approx((8.0 + 3.0) * 365.2425 / 4)
    assert profile.cooling_degree_days_per_year == pytest.approx(1.0 * 365.2425 / 4)


def test_degree_day_bases_are_explicit_inputs():
    records = _records([(20.0, 25.0, 15.0, 0.0, 10.0, 10.0)])
    heating, cooling = degree_days(records, heating_base_c=18.0, cooling_base_c=24.0)
    assert heating == pytest.approx(0.0)
    assert cooling == pytest.approx(0.0)
    none_heating, none_cooling = degree_days(records, heating_base_c=None, cooling_base_c=None)
    assert none_heating is None
    assert none_cooling is None


def test_monthly_summary_keeps_month_shape():
    records = [
        DailyClimateRecord(date=date(2025, 1, 1), temperature_mean_c=10.0, precipitation_mm=1.0),
        DailyClimateRecord(date=date(2025, 1, 2), temperature_mean_c=12.0, precipitation_mm=3.0),
        DailyClimateRecord(date=date(2025, 2, 1), temperature_mean_c=20.0, precipitation_mm=0.0),
    ]
    monthly = monthly_climate_summary(records)
    assert [item.month for item in monthly] == [1, 2]
    assert monthly[0].sample_days == 2
    assert monthly[0].mean_temperature_c == pytest.approx(11.0)
    assert monthly[0].mean_precipitation_mm_day == pytest.approx(2.0)


def test_location_profiles_produce_quantified_differences_not_city_rules():
    warm = _records(
        [
            (30.0, 40.0, 22.0, 1.0, 24.0, 15.0),
            (31.0, 41.0, 23.0, 0.0, 25.0, 16.0),
        ]
    )
    cool = [
        DailyClimateRecord(date=date(2025, 1, 1), temperature_mean_c=8.0, temperature_max_c=14.0, temperature_min_c=2.0, precipitation_mm=4.0, shortwave_radiation_mj_m2=12.0, wind_speed_max_kmh=20.0),
        DailyClimateRecord(date=date(2025, 1, 2), temperature_mean_c=9.0, temperature_max_c=15.0, temperature_min_c=3.0, precipitation_mm=5.0, shortwave_radiation_mj_m2=13.0, wind_speed_max_kmh=21.0),
    ]
    thresholds = ClimateThresholds(35.0, 5.0, 3.0, 20.0)
    profile_warm = build_climate_profile(warm, thresholds, heating_base_c=18.0, cooling_base_c=24.0)
    profile_cool = build_climate_profile(cool, thresholds, heating_base_c=18.0, cooling_base_c=24.0)
    comparison = {item.metric: item for item in compare_climate_profiles(profile_warm, profile_cool)}

    assert comparison["mean_temperature"].difference_b_minus_a == pytest.approx(8.5 - 30.5)
    assert profile_warm.cooling_degree_days_per_year > profile_cool.cooling_degree_days_per_year
    assert profile_cool.heating_degree_days_per_year > profile_warm.heating_degree_days_per_year

    warm_drivers = {item["driver"] for item in climate_design_drivers(profile_warm)}
    cool_drivers = {item["driver"] for item in climate_design_drivers(profile_cool)}
    assert "heat exposure" in warm_drivers
    assert "cold exposure" in cool_drivers
    assert "heavy-rain exposure" in cool_drivers


def test_duplicate_dates_are_rejected():
    records = [
        DailyClimateRecord(date=date(2025, 1, 1), temperature_mean_c=10.0),
        DailyClimateRecord(date=date(2025, 1, 1), temperature_mean_c=11.0),
    ]
    with pytest.raises(ValueError, match="duplicate dates"):
        build_climate_profile(records, ClimateThresholds(35.0, 5.0, 20.0, 20.0))


class _FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


def test_historical_adapter_preserves_provider_metadata_and_parses_daily(monkeypatch):
    captured = {}

    def fake_get(url, params, timeout):
        captured["url"] = url
        captured["params"] = params
        captured["timeout"] = timeout
        return _FakeResponse(
            {
                "latitude": 28.6,
                "longitude": 77.2,
                "elevation": 220.0,
                "timezone": "Asia/Kolkata",
                "daily": {
                    "time": ["2025-01-01", "2025-01-02"],
                    "temperature_2m_mean": [20.0, 21.0],
                    "temperature_2m_max": [28.0, 29.0],
                    "temperature_2m_min": [12.0, 13.0],
                    "precipitation_sum": [0.0, 2.0],
                    "shortwave_radiation_sum": [15.0, 16.0],
                    "wind_speed_10m_max": [10.0, 12.0],
                },
            }
        )

    monkeypatch.setattr("nitikube.climate_profile.requests.get", fake_get)
    dataset = historical_daily_open_meteo(
        28.6,
        77.2,
        date(2025, 1, 1),
        date(2025, 1, 2),
        model="era5_land",
        timezone_name="Asia/Kolkata",
    )

    assert captured["url"] == "https://archive-api.open-meteo.com/v1/archive"
    assert captured["params"]["models"] == "era5_land"
    assert "temperature_2m_mean" in captured["params"]["daily"]
    assert len(dataset.records) == 2
    assert dataset.records[1].precipitation_mm == pytest.approx(2.0)
    assert dataset.source.provider == "Open-Meteo"
    assert dataset.source.dataset == "era5_land"
    assert dataset.source.timezone == "Asia/Kolkata"
    assert dataset.source.source_url.endswith("historical-weather-api")


def test_historical_adapter_does_not_create_synthetic_fallback(monkeypatch):
    def fake_get(url, params, timeout):
        return _FakeResponse({"daily": {"time": []}})

    monkeypatch.setattr("nitikube.climate_profile.requests.get", fake_get)
    with pytest.raises(ValueError, match="no daily records"):
        historical_daily_open_meteo(28.6, 77.2, date(2025, 1, 1), date(2025, 1, 2))
