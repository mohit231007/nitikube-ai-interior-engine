from __future__ import annotations

import re

import streamlit as st
import streamlit.components.v1 as components

from nitikube.calibration import calibrate_scale, pixel_polygon_area_ft2
from nitikube.drawing import SvgFurniture, room_lighting_svg
from nitikube.lighting import beam_diameter


st.set_page_config(page_title="NitiKube — Plan Calibration + Export", page_icon="⌗", layout="wide")
st.title("Plan Calibration + Drawing Export")
st.caption("Turn verified plan dimensions into a physical scale, then export deterministic geometry. CV/OCR may propose references later, but the user confirms the dimensions before calculations use them.")

calibration_tab, svg_tab = st.tabs(["Scale Calibration", "SVG Lighting Plan"])


def parse_polygon(text: str) -> list[tuple[float, float]]:
    """Parse `x,y; x,y; ...` pixel coordinates supplied by the user."""
    points: list[tuple[float, float]] = []
    for token in [x.strip() for x in text.split(";") if x.strip()]:
        pieces = [x.strip() for x in token.split(",")]
        if len(pieces) != 2:
            raise ValueError(f"Invalid point '{token}'. Use x,y pairs separated by semicolons.")
        points.append((float(pieces[0]), float(pieces[1])))
    if len(points) < 3:
        raise ValueError("At least three polygon points are required.")
    return points


with calibration_tab:
    st.subheader("Calibrate pixels → physical distance")
    st.write("Enter one or more **user-verified** reference dimensions from the floor plan. NitiKube calculates each implied scale and reports disagreement instead of hiding it.")

    refs = []
    default_refs = [(500.0, 10.0), (1137.5, 22.75)]
    reference_count = st.number_input("Number of verified dimension references", min_value=1, max_value=8, value=2, step=1)
    for idx in range(int(reference_count)):
        c1, c2 = st.columns(2)
        default_px, default_ft = default_refs[idx] if idx < len(default_refs) else (500.0, 10.0)
        px = c1.number_input(f"Reference {idx+1}: pixel distance", min_value=0.01, value=default_px, step=1.0, key=f"px_{idx}")
        ft = c2.number_input(f"Reference {idx+1}: verified real distance (ft)", min_value=0.01, value=default_ft, step=0.25, key=f"ft_{idx}")
        refs.append((px, ft))

    try:
        calibration = calibrate_scale(refs)
        m1, m2, m3 = st.columns(3)
        m1.metric("Feet per pixel", f"{calibration.feet_per_pixel:.6f}")
        m2.metric("Pixels per foot", f"{calibration.pixels_per_foot:.3f}")
        m3.metric("Reference spread", f"{calibration.relative_spread*100:.2f}%")

        if calibration.relative_spread <= 0.01:
            st.success("The verified references are highly consistent (≤1% relative scale spread).")
        elif calibration.relative_spread <= 0.03:
            st.warning("References differ by 1–3%. Review image perspective, line endpoints and dimension transcription before precision-sensitive work.")
        else:
            st.error("References differ by more than 3%. Do not trust derived room areas until the scale references are corrected.")

        st.markdown("#### Pixel polygon → physical area")
        polygon_text = st.text_area(
            "Polygon points in pixels (`x,y; x,y; ...`)",
            value="0,0; 500,0; 500,300; 0,300",
            height=100,
        )
        points = parse_polygon(polygon_text)
        area_ft2 = pixel_polygon_area_ft2(points, calibration.feet_per_pixel)
        st.metric("Derived polygon area", f"{area_ft2:,.2f} ft²")
        st.caption("Area uses the shoelace formula in pixel space and multiplies by (feet-per-pixel)². The result is only as reliable as the verified calibration and polygon boundaries.")
    except Exception as exc:
        st.error(f"Calibration error: {exc}")

with svg_tab:
    st.subheader("Export a deterministic lighting-plan SVG")
    st.write("The SVG is generated directly from room dimensions and grid geometry, so it can be downloaded without a paid rendering or image-generation service.")

    c1, c2, c3, c4 = st.columns(4)
    room_name = c1.text_input("Room name", value="Drawing / Dining")
    length_ft = c2.number_input("Length (ft)", min_value=1.0, value=22.75, step=0.25, key="svg_length")
    width_ft = c3.number_input("Width (ft)", min_value=1.0, value=10.583, step=0.25, format="%.3f", key="svg_width")
    ceiling_ft = c4.number_input("Ceiling height (ft)", min_value=6.0, value=9.0, step=0.25, key="svg_ceiling")

    d1, d2, d3, d4 = st.columns(4)
    rows = d1.number_input("Rows across width", min_value=1, max_value=10, value=3, step=1)
    cols = d2.number_input("Columns along length", min_value=1, max_value=15, value=4, step=1)
    beam_angle = d3.number_input("Beam angle (°)", min_value=1.0, max_value=120.0, value=36.0, step=1.0)
    evaluation_plane = d4.number_input("Evaluation plane height (ft)", min_value=0.0, value=2.5, step=0.25)

    show_furniture = st.checkbox("Add simple furniture blocks", value=True)
    furniture: list[SvgFurniture] = []
    if show_furniture:
        # These are visual placeholders with editable geometric assumptions, not automatic design recommendations.
        f1, f2 = st.columns(2)
        sofa_width = f1.number_input("Sofa width in plan (ft)", min_value=1.0, value=2.8, step=0.1)
        sofa_length = f2.number_input("Sofa length in plan (ft)", min_value=1.0, value=7.0, step=0.25)
        furniture.append(SvgFurniture("Sofa", 0.7, 6.0, sofa_width, sofa_length))

        table_width = f1.number_input("Dining table width (ft)", min_value=1.0, value=3.0, step=0.1)
        table_length = f2.number_input("Dining table length (ft)", min_value=1.0, value=6.0, step=0.25)
        table_x = max((width_ft - table_width) / 2, 0)
        table_y = max(length_ft - table_length - 2.0, 0)
        furniture.append(SvgFurniture("Dining", table_x, table_y, table_width, table_length))

    try:
        if ceiling_ft <= evaluation_plane:
            raise ValueError("Ceiling height must be greater than the evaluation-plane height.")
        beam_ft = beam_diameter(ceiling_ft - evaluation_plane, beam_angle)
        svg = room_lighting_svg(
            room_name=room_name,
            length_ft=length_ft,
            width_ft=width_ft,
            rows=int(rows),
            cols=int(cols),
            beam_diameter_ft=beam_ft,
            furniture=furniture,
        )
        st.metric("Nominal beam diameter at evaluation plane", f"{beam_ft:.2f} ft")
        components.html(svg, height=760, scrolling=True)
        st.download_button(
            "Download SVG lighting plan",
            data=svg.encode("utf-8"),
            file_name="nitikube_lighting_plan.svg",
            mime="image/svg+xml",
        )
        st.info("This export is an engineering/design aid, not a stamped construction drawing. Dimensions, product photometrics, structural scope and regulated work still require the appropriate verification before execution.")
    except Exception as exc:
        st.error(f"Could not generate plan: {exc}")
