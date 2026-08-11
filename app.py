from __future__ import annotations

import os

import cv2
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from nitikube.budget import build_scenarios
from nitikube.climate import (
    condensation_risk,
    conductive_heat_flow_w,
    current_climate,
    layer_r_value,
    u_value,
)
from nitikube.confidence import ConfidenceInputs, confidence_label, confidence_score
from nitikube.floorplan_cv import detect_structural_lines
from nitikube.geometry import feet_inches, ft2_to_m2, grid_layout, grid_positions, rectangle_area
from nitikube.lighting import (
    beam_diameter,
    estimated_maintained_lux,
    installed_lumens_required,
    recommend_lighting,
)
from nitikube.materials import material_units, paint_litres
from nitikube.product_search import brave_web_search, retailer_search_links, specification_query


st.set_page_config(
    page_title="NitiKube AI — Interior DesignOS",
    page_icon="◫",
    layout="wide",
)

st.markdown(
    """
    <style>
      .block-container {padding-top: 1.6rem; padding-bottom: 3rem;}
      .nk-hero {padding: 1.2rem 1.35rem; border: 1px solid rgba(128,128,128,.25); border-radius: 16px; margin-bottom: 1rem;}
      .nk-kicker {font-size: .82rem; letter-spacing: .12em; text-transform: uppercase; opacity:.65;}
      .nk-title {font-size: 2.25rem; font-weight: 750; margin:.2rem 0;}
      .nk-sub {font-size: 1.05rem; opacity:.78; max-width: 920px;}
      .evidence {border-left:4px solid currentColor; padding:.7rem 1rem; background:rgba(128,128,128,.06); border-radius:8px;}
    </style>
    <div class="nk-hero">
      <div class="nk-kicker">NitiKube Interior DesignOS • v0.1 foundation</div>
      <div class="nk-title">Measured interiors. Verified decisions.</div>
      <div class="nk-sub">Geometry, lighting, thermal and quantity calculations are deterministic. AI/CV may extract or explain inputs, but engineering arithmetic is never delegated to an LLM.</div>
    </div>
    """,
    unsafe_allow_html=True,
)

with st.sidebar:
    st.header("Project guardrails")
    st.success("No recommendation without reasoning.")
    st.caption("Structural changes, load-bearing work, statutory approvals, fire-code certification, gas systems and major electrical-service design require qualified professional verification.")
    st.divider()
    st.caption("Zero-cost design: deterministic local calculations first; optional external data/search adapters have hard fallbacks.")


def lighting_plan_figure(length_ft: float, width_ft: float, rows: int, cols: int, beam_ft: float | None = None) -> go.Figure:
    points = grid_positions(length_ft, width_ft, rows, cols)
    fig = go.Figure()
    fig.add_shape(type="rect", x0=0, y0=0, x1=width_ft, y1=length_ft, line_width=2)

    if beam_ft:
        radius = beam_ft / 2
        for x, y in points:
            fig.add_shape(
                type="circle",
                x0=x-radius,
                x1=x+radius,
                y0=y-radius,
                y1=y+radius,
                line=dict(width=1, dash="dot"),
                opacity=0.35,
            )

    fig.add_trace(
        go.Scatter(
            x=[p[0] for p in points],
            y=[p[1] for p in points],
            mode="markers+text",
            marker=dict(size=13, symbol="circle"),
            text=[str(i+1) for i in range(len(points))],
            textposition="top center",
            name="COB",
        )
    )
    fig.update_yaxes(scaleanchor="x", scaleratio=1, title="Length (ft)")
    fig.update_xaxes(title="Width (ft)")
    fig.update_layout(
        height=620,
        margin=dict(l=40, r=20, t=30, b=40),
        title=f"Top-view fixture centres — {rows} × {cols}",
        showlegend=False,
    )
    return fig


tabs = st.tabs([
    "Floor Plan / CV",
    "Room + Lighting",
    "Materials",
    "Climate + Thermal",
    "Budget",
    "Products",
    "Evidence",
])

with tabs[0]:
    st.subheader("Floor-plan computer vision — verification first")
    st.write("Upload a floor-plan image. V0.1 detects candidate structural/dimension lines and overlays them. These detections are **not** used as engineering measurements until you verify the dimensions manually.")
    upload = st.file_uploader("Floor plan image", type=["png", "jpg", "jpeg"], key="floorplan")
    if upload:
        data = upload.getvalue()
        try:
            result = detect_structural_lines(data)
            left, right = st.columns(2)
            with left:
                st.image(cv2.cvtColor(result.image_bgr, cv2.COLOR_BGR2RGB), caption="Uploaded plan", use_container_width=True)
            with right:
                st.image(cv2.cvtColor(result.line_overlay_bgr, cv2.COLOR_BGR2RGB), caption=f"Candidate line overlay ({result.line_count} lines)", use_container_width=True)
            st.info("Next CV milestone: room polygons, doors/windows, scale extraction, dimension OCR and confidence-aware user correction. The verification gate remains mandatory.")
        except Exception as exc:
            st.error(f"Could not analyse image: {exc}")

with tabs[1]:
    st.subheader("Room geometry + lighting engineering")
    st.caption("Default values reproduce the current 10′7″ × 22′9″ drawing/dining-room case with a 9 ft false ceiling and 36° COBs.")

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        width_ft_whole = st.number_input("Width — feet", min_value=1, value=10, step=1)
        width_in = st.number_input("Width — inches", min_value=0.0, max_value=11.99, value=7.0, step=0.25)
    with c2:
        length_ft_whole = st.number_input("Length — feet", min_value=1, value=22, step=1)
        length_in = st.number_input("Length — inches", min_value=0.0, max_value=11.99, value=9.0, step=0.25)
    with c3:
        ceiling_height = st.number_input("False-ceiling height (ft)", min_value=6.0, value=9.0, step=0.25)
        workplane = st.number_input("Evaluation plane height (ft)", min_value=0.0, value=2.5, step=0.25)
    with c4:
        target_lux = st.number_input("Target maintained lux", min_value=50.0, value=160.0, step=10.0)
        beam_angle = st.number_input("COB beam angle (°)", min_value=10.0, max_value=120.0, value=36.0, step=1.0)

    width_ft = feet_inches(width_ft_whole, width_in)
    length_ft = feet_inches(length_ft_whole, length_in)
    area_ft2 = rectangle_area(length_ft, width_ft)
    area_m2 = ft2_to_m2(area_ft2)

    s1, s2, s3 = st.columns(3)
    with s1:
        lumens_fixture = st.number_input("Lumens per COB", min_value=100.0, value=500.0, step=25.0)
    with s2:
        cu = st.slider("Coefficient of utilisation (CU)", 0.30, 0.90, 0.65, 0.01)
    with s3:
        mf = st.slider("Maintenance factor (MF)", 0.50, 1.00, 0.80, 0.01)

    rec = recommend_lighting(
        length_ft=length_ft,
        width_ft=width_ft,
        ceiling_height_ft=ceiling_height,
        workplane_height_ft=workplane,
        target_lux=target_lux,
        lumens_per_fixture=lumens_fixture,
        beam_angle_deg=beam_angle,
        coefficient_of_utilisation=cu,
        maintenance_factor=mf,
    )

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Room area", f"{area_ft2:,.1f} ft²", f"{area_m2:,.2f} m²")
    m2.metric("Calculated installed lumens", f"{rec.installed_lumens_required:,.0f} lm")
    m3.metric("Auto fixture count", f"{rec.fixtures}")
    m4.metric("Nominal beam @ plane", f"{rec.beam_diameter_workplane_ft:.2f} ft")

    st.markdown("#### Evaluate a chosen layout")
    o1, o2 = st.columns(2)
    with o1:
        chosen_fixtures = st.number_input("Fixtures to evaluate", min_value=1, max_value=60, value=12, step=1)
    with o2:
        valid_rows = [r for r in range(1, chosen_fixtures + 1) if chosen_fixtures % r == 0]
        default_idx = valid_rows.index(3) if 3 in valid_rows else 0
        rows = st.selectbox("Rows across room width", valid_rows, index=default_idx)
    cols = chosen_fixtures // rows
    layout = grid_layout(length_ft, width_ft, rows, cols)
    beam = beam_diameter(ceiling_height - workplane, beam_angle)
    chosen_lux = estimated_maintained_lux(area_m2, chosen_fixtures, lumens_fixture, cu, mf)

    a, b, c, d = st.columns(4)
    a.metric("Grid", f"{rows} × {cols}")
    b.metric("Width c/c", f"{layout.width_spacing_ft:.2f} ft")
    c.metric("Length c/c", f"{layout.length_spacing_ft:.2f} ft")
    d.metric("Estimated maintained lux", f"{chosen_lux:.0f} lx")

    worst_ratio = max(layout.width_spacing_ft / beam, layout.length_spacing_ft / beam)
    if worst_ratio <= 1.0:
        st.success("Nominal 36° beam footprints overlap on the selected evaluation plane in both axes.")
    elif worst_ratio <= 1.25:
        st.warning("Some nominal-beam gaps are predicted. Fixture spill may soften them, but verify photometric data or add wider/diffuse fill light.")
    else:
        st.error("Spacing is large relative to the nominal beam. Increase fixture count, use a wider beam, or add cove/diffuse ambient lighting.")

    st.plotly_chart(lighting_plan_figure(length_ft, width_ft, rows, cols, beam), use_container_width=True)

    st.markdown("#### Math used")
    st.latex(r"A=L\times W")
    st.latex(r"\Phi_{installed}=\frac{E\times A}{CU\times MF}")
    st.latex(r"D=2h\tan(\theta/2)")
    st.caption(f"For this configuration: A = {area_m2:.2f} m²; required installed flux ≈ {installed_lumens_required(area_m2, target_lux, cu, mf):,.0f} lm; beam diameter at {ceiling_height-workplane:.2f} ft below the COB ≈ {beam:.2f} ft.")

with tabs[2]:
    st.subheader("Material quantity calculators")
    c1, c2 = st.columns(2)
    with c1:
        st.markdown("#### Tiles / boards / panels")
        net_area = st.number_input("Net area (ft²)", min_value=1.0, value=180.0, step=1.0)
        unit_w = st.number_input("Unit width (ft)", min_value=0.1, value=2.0, step=0.1)
        unit_l = st.number_input("Unit length (ft)", min_value=0.1, value=4.0, step=0.1)
        waste = st.slider("Cutting/waste allowance", 0, 30, 8, 1) / 100
        qty = material_units(net_area, unit_w * unit_l, waste)
        st.metric("Units to buy", qty.units_required)
        st.caption(f"Gross required area = {qty.gross_area:.1f} ft² including {waste:.0%} allowance.")

    with c2:
        st.markdown("#### Paint")
        paint_area = st.number_input("Paintable area (ft²)", min_value=1.0, value=740.0, step=10.0)
        coats = st.number_input("Coats", min_value=1, value=2, step=1)
        coverage = st.number_input("Coverage (ft²/L/coat)", min_value=10.0, value=120.0, step=5.0)
        paint_waste = st.slider("Paint allowance", 0, 25, 10, 1) / 100
        p = paint_litres(paint_area, coats, coverage, paint_waste)
        st.metric("Calculated paint", f"{p.litres_required:.2f} L")
        st.caption("Round up to available manufacturer pack sizes only after checking the selected product's stated coverage.")

with tabs[3]:
    st.subheader("Geography-aware climate + thermal checks")
    st.write("The deterministic thermal functions remain local. Current weather is an optional external adapter and is never silently substituted for long-term climate design data.")
    lat_col, lon_col = st.columns(2)
    latitude = lat_col.number_input("Latitude", value=28.4595, format="%.4f")
    longitude = lon_col.number_input("Longitude", value=77.0266, format="%.4f")
    if st.button("Fetch current climate snapshot"):
        try:
            snap = current_climate(latitude, longitude)
            st.session_state["climate"] = snap
        except Exception as exc:
            st.error(f"Climate provider unavailable: {exc}")
    if "climate" in st.session_state:
        snap = st.session_state["climate"]
        cols = st.columns(4)
        cols[0].metric("Temperature", f"{snap.temperature_c} °C")
        cols[1].metric("Humidity", f"{snap.relative_humidity_pct} %")
        cols[2].metric("Apparent", f"{snap.apparent_temperature_c} °C")
        cols[3].metric("Elevation", f"{snap.elevation_m} m")

    st.markdown("#### Condensation / wall heat-flow sandbox")
    q1, q2, q3 = st.columns(3)
    room_t = q1.number_input("Room temperature (°C)", value=24.0)
    rh = q2.number_input("Relative humidity (%)", min_value=1.0, max_value=100.0, value=60.0)
    surface_t = q3.number_input("Interior surface temperature (°C)", value=18.0)
    risk, dp = condensation_risk(surface_t, room_t, rh)
    if risk:
        st.error(f"Condensation risk: surface {surface_t:.1f} °C ≤ dew point {dp:.1f} °C.")
    else:
        st.success(f"No simple dew-point crossing: surface {surface_t:.1f} °C > dew point {dp:.1f} °C.")

    t1, t2, t3, t4 = st.columns(4)
    thickness_mm = t1.number_input("Layer thickness (mm)", min_value=1.0, value=100.0)
    conductivity = t2.number_input("Conductivity k (W/m·K)", min_value=0.01, value=0.72, step=0.01)
    wall_area = t3.number_input("Wall area (m²)", min_value=0.1, value=20.0)
    delta_t = t4.number_input("Indoor/outdoor ΔT (K)", min_value=0.0, value=15.0)
    r_layer = layer_r_value(thickness_mm / 1000.0, conductivity)
    u = u_value([r_layer])
    heat = conductive_heat_flow_w(u, wall_area, delta_t)
    st.caption(f"Layer R = {r_layer:.3f} m²K/W • Assembly U ≈ {u:.3f} W/m²K using default surface resistances • Conductive heat flow ≈ {heat:.0f} W. Use verified material k-values for design decisions.")

with tabs[4]:
    st.subheader("Budget scenarios — optimisation envelopes, not fake prices")
    budget = st.number_input("Total interior budget (₹)", min_value=50_000.0, value=1_200_000.0, step=50_000.0)
    scenarios = build_scenarios(budget)
    rows_out = []
    for scenario in scenarios:
        row = {"Scenario": scenario.name, "Reserve": scenario.reserve}
        row.update(scenario.allocations)
        row["Planned spend"] = scenario.reserve + sum(scenario.allocations.values())
        rows_out.append(row)
    df = pd.DataFrame(rows_out)
    st.dataframe(df, use_container_width=True, hide_index=True)
    st.info("These category allocations are planning priors only. NitiKube must replace them with verified BOQ + local product/labour evidence before calling a project cost 'estimated'.")

with tabs[5]:
    st.subheader("Product discovery with specification-first queries")
    st.write("NitiKube searches for the engineering specification, not merely a brand. Prices/stock must be marked live-verified or left unclaimed.")
    pc1, pc2, pc3 = st.columns(3)
    category = pc1.text_input("Product category", value="COB downlight")
    location = pc2.text_input("Location", value="Gurugram India")
    watts = pc3.number_input("Watts", min_value=0.0, value=7.0, step=0.5)
    p1, p2, p3, p4 = st.columns(4)
    kelvin = p1.number_input("Kelvin", min_value=1000, value=3000, step=100)
    p2_angle = p2.number_input("Beam angle", min_value=1.0, value=36.0, step=1.0)
    cri = p3.number_input("Minimum CRI", min_value=0, max_value=100, value=90, step=1)
    lumen_text = p4.text_input("Lumen target", value="450-550")
    query = specification_query(category=category, watts=watts, kelvin=kelvin, beam_angle_deg=p2_angle, cri_min=cri, lumens=lumen_text, location=location)
    st.code(query)

    api_key = os.getenv("BRAVE_SEARCH_API_KEY", "")
    if st.button("Search products"):
        live = []
        if api_key:
            try:
                live = brave_web_search(query, api_key)
            except Exception as exc:
                st.warning(f"Live search unavailable; using zero-cost retailer links. Reason: {exc}")
        results = live or retailer_search_links(query, country="IN")
        for item in results:
            badge = "LIVE SEARCH" if item.live_verified else "SEARCH LINK — PRICE NOT VERIFIED"
            st.markdown(f"**{item.title}**  \n{badge}  \n{item.description or ''}  \n{item.url}")
            st.divider()

with tabs[6]:
    st.subheader("Evidence and confidence contract")
    st.markdown(
        """
        <div class="evidence"><b>NitiKube Evidence Rule</b><br>
        Every recommendation must expose a calculation, verified measurement, rule/standard, product/material specification, geographic/climate evidence, or be explicitly labelled as a subjective design preference.</div>
        """,
        unsafe_allow_html=True,
    )
    st.markdown("#### Recommendation confidence")
    c1, c2, c3, c4 = st.columns(4)
    sr = c1.slider("Source reliability", 0, 100, 95)
    mc = c2.slider("Measurement confidence", 0, 100, 95)
    dfresh = c3.slider("Data freshness", 0, 100, 85)
    cc = c4.slider("Constraint completeness", 0, 100, 80)
    score = confidence_score(ConfidenceInputs(sr, mc, dfresh, cc))
    st.metric("Evidence confidence", f"{score:.1f}%", confidence_label(score))
    st.caption("This score describes evidence quality/completeness; it is not a probability that an interior design is 'correct'.")

st.divider()
st.caption("NitiKube AI • deterministic science core + verification-first AI/CV • MIT licensed")
