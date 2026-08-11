from __future__ import annotations

import pandas as pd
import streamlit as st

from nitikube.acoustics import (
    AbsorbingSurface,
    absorption_needed_for_target_rt60,
    free_field_level_change_db,
    room_volume_m3,
    sabine_rt60_seconds,
    total_absorption_area_m2,
)
from nitikube.electrical import (
    LoadItem,
    aggregate_load,
    conductor_resistance_ohm,
    energy_kwh,
    single_phase_current_a,
    voltage_drop_percent,
    voltage_drop_v,
)
from nitikube.solar import (
    horizontal_shadow_length,
    solar_position,
)


st.set_page_config(page_title="NitiKube — Building Physics", page_icon="∿", layout="wide")
st.title("Building Physics")
st.caption("Transparent first-principles calculators for sun, acoustics and electrical loads. Design assumptions remain visible and regulated final design remains subject to the applicable professional/code verification.")

solar_tab, acoustic_tab, electrical_tab = st.tabs(["Solar Geometry", "Room Acoustics", "Electrical Load Sandbox"])

with solar_tab:
    st.subheader("Latitude-aware solar geometry")
    st.write("Unlike a generic city-style recommendation, these calculations respond directly to latitude, day of year and solar time.")
    c1, c2, c3 = st.columns(3)
    latitude = c1.number_input("Latitude (°)", min_value=-90.0, max_value=90.0, value=28.46, step=0.01)
    day = c2.number_input("Day of year", min_value=1, max_value=366, value=172, step=1)
    solar_time = c3.number_input("Solar time (hours)", min_value=0.0, max_value=24.0, value=12.0, step=0.25)

    pos = solar_position(latitude, int(day), solar_time)
    p1, p2, p3, p4 = st.columns(4)
    p1.metric("Declination", f"{pos.declination_deg:.2f}°")
    p2.metric("Hour angle", f"{pos.hour_angle_deg:.2f}°")
    p3.metric("Solar altitude", f"{pos.altitude_deg:.2f}°")
    p4.metric("Azimuth from south", f"{pos.azimuth_from_south_deg:.2f}°")

    if 0 < pos.altitude_deg < 90:
        height = st.number_input("Object / shading height (m)", min_value=0.01, value=1.5, step=0.1)
        shadow = horizontal_shadow_length(height, pos.altitude_deg)
        st.metric("Idealized horizontal shadow length", f"{shadow:.2f} m")
        st.latex(r"L_{shadow}=\frac{H}{\tan(\alpha)}")
    else:
        st.warning("Sun is at/below the modeled horizon at this solar time, so the simple horizontal-shadow calculation is not applicable.")

    st.info("This v0.4 model uses approximate solar geometry and solar time. A production façade/daylight engine should later add wall orientation, civil-clock ↔ solar-time correction, local horizon/obstructions, weather/cloud data and higher-fidelity ephemeris calculations.")

with acoustic_tab:
    st.subheader("First-order reverberation model")
    a1, a2, a3 = st.columns(3)
    length_m = a1.number_input("Room length (m)", min_value=0.1, value=6.934, step=0.1)
    width_m = a2.number_input("Room width (m)", min_value=0.1, value=3.226, step=0.1)
    height_m = a3.number_input("Room height (m)", min_value=0.1, value=2.743, step=0.1)
    volume = room_volume_m3(length_m, width_m, height_m)
    st.metric("Room volume", f"{volume:.2f} m³")

    st.write("Enter surface absorption assumptions from a sourced material datasheet/reference. NitiKube does not invent absorption coefficients.")
    default_surfaces = pd.DataFrame([
        {"label": "Floor", "area_m2": length_m * width_m, "absorption_coefficient": 0.10},
        {"label": "Ceiling", "area_m2": length_m * width_m, "absorption_coefficient": 0.10},
        {"label": "Walls combined", "area_m2": 2 * (length_m + width_m) * height_m, "absorption_coefficient": 0.10},
    ])
    edited = st.data_editor(default_surfaces, use_container_width=True, num_rows="dynamic", key="acoustic_surfaces")
    try:
        surfaces = [
            AbsorbingSurface(float(row["area_m2"]), float(row["absorption_coefficient"]), str(row["label"]))
            for _, row in edited.iterrows()
        ]
        absorption = total_absorption_area_m2(surfaces)
        rt60 = sabine_rt60_seconds(volume, absorption)
        r1, r2 = st.columns(2)
        r1.metric("Equivalent absorption area", f"{absorption:.2f} m² sabins")
        r2.metric("Sabine RT60 estimate", f"{rt60:.2f} s")
        st.latex(r"T_{60}=0.161\frac{V}{A}")

        target_rt = st.number_input("Optional target RT60 (s)", min_value=0.05, value=0.50, step=0.05)
        needed = absorption_needed_for_target_rt60(volume, target_rt)
        st.caption(f"Equivalent absorption required for the entered target ≈ {needed:.2f} m² sabins; additional absorption relative to this model ≈ {max(needed-absorption, 0):.2f} m² sabins.")

        d1, d2 = st.columns(2)
        near_m = d1.number_input("Sound distance 1 (m)", min_value=0.01, value=1.0, step=0.1)
        far_m = d2.number_input("Sound distance 2 (m)", min_value=0.01, value=2.0, step=0.1)
        delta_db = free_field_level_change_db(near_m, far_m)
        st.caption(f"Ideal free-field level change from {near_m:g} m to {far_m:g} m: {delta_db:+.2f} dB. A reflective room will not behave like a perfect free field.")
    except Exception as exc:
        st.error(f"Acoustics input error: {exc}")

with electrical_tab:
    st.subheader("Connected load, energy and transparent voltage-drop math")
    st.warning("This is not a breaker/cable-sizing code engine. Circuit protection, earthing, conductor ampacity, installation method and final electrical design require the applicable standards and qualified verification.")

    load_df = pd.DataFrame([
        {"name": "COB lights", "watts_each": 7.0, "quantity": 12, "diversity_factor": 1.0},
        {"name": "Ceiling fan", "watts_each": 55.0, "quantity": 1, "diversity_factor": 1.0},
        {"name": "TV", "watts_each": 120.0, "quantity": 1, "diversity_factor": 1.0},
    ])
    loads_edited = st.data_editor(load_df, use_container_width=True, num_rows="dynamic", key="electrical_loads")
    try:
        loads = [
            LoadItem(str(row["name"]), float(row["watts_each"]), int(row["quantity"]), float(row["diversity_factor"]))
            for _, row in loads_edited.iterrows()
        ]
        connected, diversified = aggregate_load(loads)
        e1, e2, e3 = st.columns(3)
        source_voltage = e1.number_input("Nominal voltage (V)", min_value=1.0, value=230.0, step=1.0)
        pf = e2.number_input("Power factor assumption", min_value=0.01, max_value=1.0, value=0.95, step=0.01)
        efficiency = e3.number_input("Efficiency assumption", min_value=0.01, max_value=1.0, value=1.0, step=0.01)
        current = single_phase_current_a(diversified, source_voltage, pf, efficiency)

        m1, m2, m3 = st.columns(3)
        m1.metric("Connected load", f"{connected:.0f} W")
        m2.metric("Diversified load", f"{diversified:.0f} W")
        m3.metric("Calculated current", f"{current:.2f} A")
        st.latex(r"I=\frac{P}{V\,PF\,\eta}")

        daily_hours = st.number_input("Equivalent operating hours/day for energy illustration", min_value=0.0, max_value=24.0, value=5.0, step=0.5)
        st.caption(f"Illustrative daily energy at diversified load × hours = {energy_kwh(diversified, daily_hours):.2f} kWh/day. Individual device duty cycles should replace this simplification for real forecasts.")

        st.markdown("#### Generic conductor voltage-drop calculation")
        v1, v2, v3 = st.columns(3)
        resistivity = v1.number_input("Resistivity ρ (Ω·m) — sourced input", min_value=1e-12, value=1.724e-8, format="%.4e")
        length = v2.number_input("One-way conductor length (m)", min_value=0.0, value=20.0, step=1.0)
        area_mm2 = v3.number_input("Conductor cross-section (mm²)", min_value=0.01, value=1.5, step=0.25)
        resistance = conductor_resistance_ohm(resistivity, length, area_mm2, round_trip=True)
        drop = voltage_drop_v(current, resistance)
        drop_pct = voltage_drop_percent(source_voltage, drop)
        st.caption(f"Round-trip conductor R = {resistance:.4f} Ω • V-drop = {drop:.3f} V • {drop_pct:.2f}% of entered source voltage. The default resistivity is merely an editable calculation input; verify conductor material/temperature data and code requirements before design use.")
        st.latex(r"R=\rho\frac{L}{A},\quad \Delta V=IR")
    except Exception as exc:
        st.error(f"Electrical input error: {exc}")
