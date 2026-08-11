from __future__ import annotations

from datetime import date

import pandas as pd
import streamlit as st

from nitikube.climate_profile import (
    ClimateThresholds,
    build_climate_profile,
    climate_design_drivers,
    compare_climate_profiles,
    historical_daily_open_meteo,
    monthly_climate_summary,
)
from nitikube.geography import geocode_location


st.set_page_config(page_title="NitiKube — Climate Comparison", page_icon="◉", layout="wide")
st.title("Geography → Climate → Design Pressure")
st.caption(
    "Compare locations using historical reanalysis, not city-name rules. The same design brief can therefore expose different heat, cold, rain, solar and degree-day pressures in different geographies."
)

st.info(
    "Live historical data is optional and fetched only when you press the button. NitiKube stores provider/dataset/date metadata with the result. "
    "If the free external provider is unavailable, the app fails visibly rather than inventing climate values."
)

with st.expander("Data-source semantics", expanded=False):
    st.write(
        "The live adapter uses Open-Meteo's Historical Weather API and requests daily reanalysis variables. Reanalysis combines observations with numerical weather models and is appropriate for long-term consistent climate analysis; it is not the same thing as a weather station measurement at the exact property."
    )
    st.write(
        "Current implementation uses temperature, precipitation, shortwave radiation and maximum wind from daily historical data. Long-term humidity is intentionally left blank until an evidence-efficient daily humidity source/aggregation path is connected."
    )

st.subheader("1 · Locations and historical period")
c1, c2 = st.columns(2)
location_a_name = c1.text_input("Location A", "Delhi")
location_b_name = c2.text_input("Location B", "Shimla")

d1, d2, d3 = st.columns(3)
start_date = d1.date_input("Start date", date(2021, 1, 1), min_value=date(1950, 1, 1), max_value=date.today())
end_date = d2.date_input("End date", date(2025, 12, 31), min_value=date(1950, 1, 1), max_value=date.today())
model = d3.selectbox("Historical dataset/model", ["era5_land", "era5"], index=0)

st.subheader("2 · Explicit scenario thresholds")
st.caption(
    "These editable thresholds define what *this analysis* calls hot/cold/heavy-rain/high-solar. They are not hidden NitiKube standards or building-code limits."
)
t1, t2, t3, t4 = st.columns(4)
hot_threshold = t1.number_input("Hot day: max ≥ °C", value=35.0, step=1.0)
cold_threshold = t2.number_input("Cold day: min ≤ °C", value=10.0, step=1.0)
heavy_rain = t3.number_input("Heavy-rain day ≥ mm", value=20.0, min_value=0.0, step=1.0)
high_solar = t4.number_input("High-solar day ≥ MJ/m²", value=20.0, min_value=0.0, step=1.0)

b1, b2 = st.columns(2)
heating_base = b1.number_input("Heating degree-day base °C", value=18.0, step=0.5)
cooling_base = b2.number_input("Cooling degree-day base °C", value=24.0, step=0.5)
st.caption("Degree-day base temperatures are also scenario inputs, not regulatory defaults. Change them to match the thermal-comfort/modeling brief.")

thresholds = ClimateThresholds(
    hot_day_max_c=float(hot_threshold),
    cold_day_min_c=float(cold_threshold),
    heavy_rain_day_mm=float(heavy_rain),
    high_solar_day_mj_m2=float(high_solar),
)


def _resolve_location(name: str):
    results = geocode_location(name, count=5)
    if not results:
        raise ValueError(f"No geocoding result found for {name!r}")
    return results[0]


if st.button("Fetch and compare historical climate", type="primary"):
    if start_date > end_date:
        st.error("Start date must be on or before end date.")
    else:
        try:
            with st.spinner("Resolving locations and fetching daily historical data..."):
                geo_a = _resolve_location(location_a_name)
                geo_b = _resolve_location(location_b_name)
                data_a = historical_daily_open_meteo(
                    geo_a.latitude,
                    geo_a.longitude,
                    start_date,
                    end_date,
                    model=model,
                    timezone_name=geo_a.timezone or "auto",
                )
                data_b = historical_daily_open_meteo(
                    geo_b.latitude,
                    geo_b.longitude,
                    start_date,
                    end_date,
                    model=model,
                    timezone_name=geo_b.timezone or "auto",
                )
                profile_a = build_climate_profile(
                    data_a.records,
                    thresholds,
                    heating_base_c=float(heating_base),
                    cooling_base_c=float(cooling_base),
                )
                profile_b = build_climate_profile(
                    data_b.records,
                    thresholds,
                    heating_base_c=float(heating_base),
                    cooling_base_c=float(cooling_base),
                )
            st.session_state["climate_compare_result"] = {
                "geo_a": geo_a,
                "geo_b": geo_b,
                "data_a": data_a,
                "data_b": data_b,
                "profile_a": profile_a,
                "profile_b": profile_b,
                "thresholds": thresholds,
            }
        except Exception as exc:
            st.error(f"Climate comparison could not be completed: {exc}")

result = st.session_state.get("climate_compare_result")
if result:
    geo_a = result["geo_a"]
    geo_b = result["geo_b"]
    data_a = result["data_a"]
    data_b = result["data_b"]
    profile_a = result["profile_a"]
    profile_b = result["profile_b"]

    st.subheader("3 · Resolved geographic context")
    g1, g2 = st.columns(2)
    with g1:
        st.write(f"**A: {geo_a.label}**")
        st.write(f"Lat/Lon: `{geo_a.latitude:.5f}, {geo_a.longitude:.5f}`")
        st.write(f"Geocoder elevation: `{geo_a.elevation_m}` m")
        st.write(f"Timezone: `{geo_a.timezone}`")
    with g2:
        st.write(f"**B: {geo_b.label}**")
        st.write(f"Lat/Lon: `{geo_b.latitude:.5f}, {geo_b.longitude:.5f}`")
        st.write(f"Geocoder elevation: `{geo_b.elevation_m}` m")
        st.write(f"Timezone: `{geo_b.timezone}`")

    st.subheader("4 · Measured/modelled climate difference")
    comparison = compare_climate_profiles(profile_a, profile_b)
    comparison_df = pd.DataFrame(
        [
            {
                "metric": item.metric,
                "unit": item.unit,
                geo_a.name: item.location_a,
                geo_b.name: item.location_b,
                f"{geo_b.name} minus {geo_a.name}": item.difference_b_minus_a,
            }
            for item in comparison
        ]
    )
    st.dataframe(comparison_df, use_container_width=True, hide_index=True)

    m1, m2, m3, m4 = st.columns(4)
    m1.metric(f"{geo_a.name} mean temp", f"{profile_a.mean_temperature_c:.1f} °C" if profile_a.mean_temperature_c is not None else "N/A")
    m2.metric(f"{geo_b.name} mean temp", f"{profile_b.mean_temperature_c:.1f} °C" if profile_b.mean_temperature_c is not None else "N/A")
    m3.metric(f"{geo_a.name} hot days/yr", f"{profile_a.hot_days_per_year:.1f}")
    m4.metric(f"{geo_b.name} hot days/yr", f"{profile_b.hot_days_per_year:.1f}")

    st.subheader("5 · Monthly climate shape")
    monthly_a = pd.DataFrame([vars(x) for x in monthly_climate_summary(data_a.records)])
    monthly_a["location"] = geo_a.name
    monthly_b = pd.DataFrame([vars(x) for x in monthly_climate_summary(data_b.records)])
    monthly_b["location"] = geo_b.name
    monthly = pd.concat([monthly_a, monthly_b], ignore_index=True)
    st.dataframe(monthly, use_container_width=True, hide_index=True)
    if not monthly.empty:
        pivot = monthly.pivot(index="month", columns="location", values="mean_temperature_c")
        st.line_chart(pivot, y=list(pivot.columns))

    st.subheader("6 · Design pressures, not aesthetic guesses")
    driver_a = climate_design_drivers(profile_a)
    driver_b = climate_design_drivers(profile_b)
    da, db = st.columns(2)
    with da:
        st.write(f"**{geo_a.name}**")
        if driver_a:
            st.dataframe(pd.DataFrame(driver_a), use_container_width=True, hide_index=True)
        else:
            st.info("No driver exceeded the current user-defined frequency/threshold combination.")
    with db:
        st.write(f"**{geo_b.name}**")
        if driver_b:
            st.dataframe(pd.DataFrame(driver_b), use_container_width=True, hide_index=True)
        else:
            st.info("No driver exceeded the current user-defined frequency/threshold combination.")

    st.caption(
        "A climate driver tells the next NitiKube engine what must be checked; it does not automatically prescribe a material. "
        "For example, high rain exposure should trigger waterproofing/drainage/material evidence checks, while high solar exposure should trigger orientation/SHGC/UV checks."
    )

    st.subheader("7 · Provenance")
    source_df = pd.DataFrame(
        [
            {
                "location": geo_a.label,
                "provider": data_a.source.provider,
                "dataset": data_a.source.dataset,
                "provider_elevation_m": data_a.source.elevation_m,
                "start_date": data_a.source.start_date,
                "end_date": data_a.source.end_date,
                "checked_at": data_a.source.checked_at,
                "source_url": data_a.source.source_url,
                "records": len(data_a.records),
            },
            {
                "location": geo_b.label,
                "provider": data_b.source.provider,
                "dataset": data_b.source.dataset,
                "provider_elevation_m": data_b.source.elevation_m,
                "start_date": data_b.source.start_date,
                "end_date": data_b.source.end_date,
                "checked_at": data_b.source.checked_at,
                "source_url": data_b.source.source_url,
                "records": len(data_b.records),
            },
        ]
    )
    st.dataframe(source_df, use_container_width=True, hide_index=True)
    st.download_button(
        "Download climate comparison CSV",
        comparison_df.to_csv(index=False).encode("utf-8"),
        "nitikube_climate_comparison.csv",
        "text/csv",
    )

    st.warning(
        "Climate reanalysis is regional gridded data, not a site survey. Local slope, urban heat, neighbouring buildings, vegetation, drainage, construction details and microclimate can still matter. NitiKube must expose those uncertainties rather than pretending a city coordinate is the whole building."
    )
else:
    st.info("Set the locations, historical period and explicit scenario thresholds, then fetch the comparison. No climate numbers are pre-baked into this page.")
