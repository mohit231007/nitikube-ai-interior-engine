from __future__ import annotations

from datetime import datetime, timezone
import re

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from nitikube.photometry import (
    FT_TO_M,
    even_fixture_grid_from_feet,
    grid_matrix,
    illuminance_grid,
    parse_ies,
    points_rows,
    summarize_illuminance,
)
from nitikube.verified_geometry import geometry_from_project_json


st.set_page_config(page_title="NitiKube — IES Photometry Lab", page_icon="◉", layout="wide")
st.title("IES Point-by-Point Lighting Lab")
st.caption(
    "Use a manufacturer's IES photometric file to calculate direct horizontal illuminance from actual candela distribution instead of treating wattage, beam angle or lumens as a complete lighting design."
)

st.warning(
    "Current verified calculation scope: downward IES Type-C, TILT=NONE photometry. The point-by-point engine computes direct illuminance only; it does not yet model wall/ceiling interreflection, daylight, obstructions, fixture tilt or glare metrics such as UGR."
)

st.subheader("1 · Photometric evidence")
ies_file = st.file_uploader("Upload manufacturer/product `.ies` file", type=["ies"], key="ies_upload")
source_col1, source_col2 = st.columns(2)
source_url = source_col1.text_input("IES/source URL (recommended for provenance)")
checked_at = source_col2.text_input(
    "Source checked_at",
    datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
)

photometry = None
if ies_file:
    try:
        photometry = parse_ies(ies_file.getvalue())
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Vertical angles", len(photometry.vertical_angles_deg))
        m2.metric("Horizontal planes", len(photometry.horizontal_angles_deg))
        m3.metric("Input watts in IES", f"{photometry.input_watts:g}")
        nominal_lumens = photometry.total_nominal_lamp_lumens
        m4.metric("Nominal lamp lumens", f"{nominal_lumens:g}" if nominal_lumens is not None else "Absolute/unknown")
        st.success(
            "IES parsed as rotationally symmetric Type-C photometry."
            if photometry.rotationally_symmetric
            else "IES parsed as full 0°–360° Type-C horizontal photometry."
        )
        with st.expander("IES metadata / angles", expanded=False):
            st.write("Header:")
            st.code("\n".join(photometry.header_lines) or "(no metadata header lines)")
            st.write({
                "TILT": photometry.tilt,
                "photometric_type": photometry.photometric_type,
                "units_type": photometry.units_type,
                "ballast_factor": photometry.ballast_factor,
                "vertical_angles_deg": photometry.vertical_angles_deg,
                "horizontal_angles_deg": photometry.horizontal_angles_deg,
            })
    except Exception as exc:
        st.error(f"IES file cannot be used by the current verified calculation scope: {exc}")

st.subheader("2 · Verified/manual room geometry")
geometry_mode = st.radio("Geometry source", ["Manual rectangular room", "Verified NitiKube geometry"], horizontal=True)
room_width_ft = None
room_length_ft = None
room_name = "Drawing / Dining"
if geometry_mode == "Manual rectangular room":
    r1, r2, r3 = st.columns(3)
    room_width_ft = r1.number_input("Room width ft", min_value=1.0, value=10 + 7 / 12, step=0.25)
    room_length_ft = r2.number_input("Room length ft", min_value=1.0, value=22 + 9 / 12, step=0.25)
    room_name = r3.text_input("Room name", "Drawing / Dining")
else:
    geometry_file = st.file_uploader("Upload `nitikube_verified_geometry.json`", type=["json"], key="photometry_geometry")
    if geometry_file:
        try:
            project_name, rooms, openings, metadata = geometry_from_project_json(geometry_file.getvalue().decode("utf-8"))
            verified = [room for room in rooms if room.verified]
            labels = {f"{room.name} · {room.room_id}": room for room in verified}
            if labels:
                selected = labels[st.selectbox("Verified room", list(labels))]
                min_x, min_y, max_x, max_y = selected.bounds_ft
                unique_x = {round(point[0], 8) for point in selected.polygon_ft}
                unique_y = {round(point[1], 8) for point in selected.polygon_ft}
                if len(selected.polygon_ft) != 4 or len(unique_x) != 2 or len(unique_y) != 2:
                    st.error("Current IES room sampler supports axis-aligned rectangular verified rooms only. NitiKube will not silently use a polygon bounding box as authoritative area geometry.")
                else:
                    room_width_ft = max_x - min_x
                    room_length_ft = max_y - min_y
                    room_name = selected.name
                    st.success(f"Using {room_name}: {room_width_ft:.3f} × {room_length_ft:.3f} ft")
            else:
                st.warning("No verified rooms found.")
        except Exception as exc:
            st.error(f"Verified geometry could not be loaded: {exc}")

st.subheader("3 · Fixture and evaluation plane")
f1, f2, f3, f4 = st.columns(4)
rows = f1.number_input("Fixture rows across width", min_value=1, max_value=20, value=3, step=1)
cols = f2.number_input("Fixture columns along length", min_value=1, max_value=30, value=4, step=1)
ceiling_height_ft = f3.number_input("Fixture/false-ceiling height ft", min_value=1.0, value=9.0, step=0.25)
plane_height_ft = f4.number_input("Evaluation plane height ft", min_value=0.0, value=2.5, step=0.25)

p1, p2, p3 = st.columns(3)
maintenance_factor = p1.number_input(
    "Maintenance factor",
    min_value=0.01,
    max_value=1.0,
    value=1.0,
    step=0.05,
    help="Explicit multiplier for maintained direct illuminance. 1.0 means no depreciation allowance is applied in this calculation.",
)
x_samples = p2.number_input("Grid samples across width", min_value=3, max_value=101, value=21, step=2)
y_samples = p3.number_input("Grid samples along length", min_value=3, max_value=151, value=41, step=2)

t1, t2 = st.columns(2)
target_min_lux = t1.number_input("Scenario target minimum lux", min_value=0.0, value=120.0, step=10.0)
target_max_lux = t2.number_input("Scenario target maximum lux", min_value=0.0, value=220.0, step=10.0)
st.caption("The target band is a visible scenario input, not a hidden NitiKube standard. A later standards layer can supply sourced room/task targets with jurisdiction/version provenance.")

if photometry is not None and room_width_ft is not None and room_length_ft is not None:
    if ceiling_height_ft <= plane_height_ft:
        st.error("Fixture height must be above the evaluation plane.")
    elif target_min_lux > target_max_lux:
        st.error("Target minimum lux cannot exceed target maximum lux.")
    elif st.button("Calculate point-by-point illuminance", type="primary"):
        try:
            fixtures = even_fixture_grid_from_feet(
                room_length_ft=float(room_length_ft),
                room_width_ft=float(room_width_ft),
                rows=int(rows),
                cols=int(cols),
                ceiling_height_ft=float(ceiling_height_ft),
                evaluation_plane_height_ft=float(plane_height_ft),
            )
            points = illuminance_grid(
                photometry,
                fixtures,
                room_width_m=float(room_width_ft) * FT_TO_M,
                room_length_m=float(room_length_ft) * FT_TO_M,
                x_samples=int(x_samples),
                y_samples=int(y_samples),
                maintenance_factor=float(maintenance_factor),
            )
            summary = summarize_illuminance(
                points,
                maintenance_factor=float(maintenance_factor),
                target_min_lux=float(target_min_lux),
                target_max_lux=float(target_max_lux),
            )
            st.session_state["photometry_result"] = {
                "fixtures": fixtures,
                "points": points,
                "summary": summary,
                "x_samples": int(x_samples),
                "y_samples": int(y_samples),
                "room_width_ft": float(room_width_ft),
                "room_length_ft": float(room_length_ft),
                "room_name": room_name,
                "rows": int(rows),
                "cols": int(cols),
            }
        except Exception as exc:
            st.error(f"Point-by-point calculation failed: {exc}")
else:
    st.info("Provide both a supported IES file and room geometry to run the photometric calculation.")

result = st.session_state.get("photometry_result")
if result:
    points = result["points"]
    summary = result["summary"]
    xs = result["x_samples"]
    ys = result["y_samples"]
    matrix = grid_matrix(points, x_samples=xs, y_samples=ys)
    x_axis_ft = [result["room_width_ft"] * i / (xs - 1) for i in range(xs)]
    y_axis_ft = [result["room_length_ft"] * i / (ys - 1) for i in range(ys)]

    st.subheader("4 · Direct illuminance result")
    s1, s2, s3, s4, s5 = st.columns(5)
    s1.metric("Minimum", f"{summary.minimum_lux:.1f} lux")
    s2.metric("Average", f"{summary.average_lux:.1f} lux")
    s3.metric("Maximum", f"{summary.maximum_lux:.1f} lux")
    s4.metric("Min / Avg", f"{summary.min_to_avg:.3f}")
    s5.metric("Inside target band", f"{summary.target_band_fraction:.1%}" if summary.target_band_fraction is not None else "N/A")

    fig = go.Figure(
        data=go.Heatmap(
            z=matrix,
            x=x_axis_ft,
            y=y_axis_ft,
            colorbar={"title": "lux"},
            hovertemplate="x=%{x:.2f} ft<br>y=%{y:.2f} ft<br>%{z:.1f} lux<extra></extra>",
        )
    )
    fig.update_layout(
        title=f"{result['room_name']} — {result['rows']}×{result['cols']} IES direct illuminance",
        xaxis_title="Room width (ft)",
        yaxis_title="Room length (ft)",
        yaxis={"scaleanchor": "x", "scaleratio": 1},
    )
    st.plotly_chart(fig, use_container_width=True)

    fixture_df = pd.DataFrame(
        [
            {
                "fixture_id": fixture.fixture_id,
                "x_ft": fixture.x_m / FT_TO_M,
                "y_ft": fixture.y_m / FT_TO_M,
                "height_above_plane_ft": fixture.height_above_plane_m / FT_TO_M,
                "multiplier": fixture.multiplier,
            }
            for fixture in result["fixtures"]
        ]
    )
    with st.expander("Fixture coordinates and point grid"):
        st.dataframe(fixture_df, use_container_width=True, hide_index=True)
        point_df = pd.DataFrame(points_rows(points))
        point_df["x_ft"] = point_df["x_m"] / FT_TO_M
        point_df["y_ft"] = point_df["y_m"] / FT_TO_M
        st.dataframe(point_df[["x_ft", "y_ft", "lux"]], use_container_width=True, hide_index=True)

    export_df = pd.DataFrame(points_rows(points))
    export_df["x_ft"] = export_df["x_m"] / FT_TO_M
    export_df["y_ft"] = export_df["y_m"] / FT_TO_M
    export_df["room"] = result["room_name"]
    export_df["fixture_grid"] = f"{result['rows']}x{result['cols']}"
    export_df["source_url"] = source_url or None
    export_df["source_checked_at"] = checked_at or None
    st.download_button(
        "Download point-by-point lux CSV",
        export_df.to_csv(index=False).encode("utf-8"),
        "nitikube_ies_illuminance_grid.csv",
        "text/csv",
    )

    st.info(
        "Interpretation boundary: this map is direct maintained illuminance from the uploaded candela distribution. Real room illuminance can change with wall/ceiling reflectance, furniture, mounting details, diffuser/lens differences, obstruction, daylight, voltage/driver behaviour and luminaire aging."
    )

st.subheader("5 · Compare fixture grids using the same IES")
scenario_text = st.text_input("Grid scenarios (comma-separated `rows x columns`)", "2x4, 3x4, 3x5")
if photometry is not None and room_width_ft is not None and room_length_ft is not None and st.button("Compare fixture grids"):
    try:
        scenarios = []
        for token in scenario_text.split(","):
            match = re.fullmatch(r"\s*(\d+)\s*[xX×]\s*(\d+)\s*", token)
            if not match:
                raise ValueError(f"Could not parse grid scenario {token!r}")
            scenario_rows = int(match.group(1))
            scenario_cols = int(match.group(2))
            if scenario_rows < 1 or scenario_cols < 1:
                raise ValueError("Grid rows/columns must be positive")
            fixtures = even_fixture_grid_from_feet(
                room_length_ft=float(room_length_ft),
                room_width_ft=float(room_width_ft),
                rows=scenario_rows,
                cols=scenario_cols,
                ceiling_height_ft=float(ceiling_height_ft),
                evaluation_plane_height_ft=float(plane_height_ft),
            )
            # Use a modest common comparison grid so every scenario is evaluated on identical sample points.
            points = illuminance_grid(
                photometry,
                fixtures,
                room_width_m=float(room_width_ft) * FT_TO_M,
                room_length_m=float(room_length_ft) * FT_TO_M,
                x_samples=17,
                y_samples=33,
                maintenance_factor=float(maintenance_factor),
            )
            summary = summarize_illuminance(
                points,
                maintenance_factor=float(maintenance_factor),
                target_min_lux=float(target_min_lux),
                target_max_lux=float(target_max_lux),
            )
            scenarios.append(
                {
                    "grid": f"{scenario_rows}×{scenario_cols}",
                    "fixtures": scenario_rows * scenario_cols,
                    "minimum_lux": summary.minimum_lux,
                    "average_lux": summary.average_lux,
                    "maximum_lux": summary.maximum_lux,
                    "min_to_avg": summary.min_to_avg,
                    "target_band_fraction": summary.target_band_fraction,
                }
            )
        comparison_df = pd.DataFrame(scenarios).sort_values(["target_band_fraction", "min_to_avg"], ascending=False)
        st.dataframe(comparison_df, use_container_width=True, hide_index=True)
        st.caption("The table does not automatically choose a winner. A grid with higher average lux can still have worse uniformity or exceed the user-defined target band; product cost, glare and aesthetics remain separate constraints.")
    except Exception as exc:
        st.error(f"Grid comparison failed: {exc}")

st.caption(
    "Why IES matters: two nominally '36° / 500 lm' COBs can have different real candela distributions. NitiKube should use manufacturer photometry when available rather than pretending the beam-angle label completely defines the illumination field."
)
