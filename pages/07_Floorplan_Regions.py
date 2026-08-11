from __future__ import annotations

import cv2
import pandas as pd
import streamlit as st

from nitikube.calibration import scale_from_reference
from nitikube.floorplan_regions import candidate_dimensions_ft, detect_candidate_regions


st.set_page_config(page_title="NitiKube — Floor-plan Region Proposals", page_icon="▦", layout="wide")
st.title("Floor-plan Region Proposals")
st.caption("Computer vision proposes enclosed spaces; the homeowner verifies them. Heuristic scores are not probabilities, and no detected region becomes engineering geometry until scale and boundaries are confirmed.")

uploaded = st.file_uploader("Upload floor plan", type=["png", "jpg", "jpeg"], key="region_plan")

c1, c2, c3 = st.columns(3)
dark_threshold = c1.slider("Dark-pixel threshold", 50, 250, 200, 5)
wall_dilation = c2.slider("Wall/gap dilation (px)", 0, 12, 2, 1)
min_rect = c3.slider("Minimum rectangularity", 0.20, 0.95, 0.45, 0.05)

with st.expander("Optional verified scale calibration", expanded=False):
    st.write("Provide one known plan distance and its pixel distance. This converts candidate pixel dimensions and image-relative positions to feet. Use the multi-reference calibration page when precision matters.")
    s1, s2 = st.columns(2)
    px_reference = s1.number_input("Verified reference pixel distance", min_value=0.01, value=500.0, step=1.0)
    ft_reference = s2.number_input("Known physical distance (ft)", min_value=0.01, value=10.0, step=0.25)
    feet_per_pixel = scale_from_reference(px_reference, ft_reference)
    st.caption(f"Current scale = {feet_per_pixel:.6f} ft/pixel")

if uploaded:
    try:
        result = detect_candidate_regions(
            uploaded.getvalue(),
            dark_threshold=dark_threshold,
            wall_dilation_px=wall_dilation,
            min_area_fraction=0.005,
            max_area_fraction=0.80,
            min_rectangularity=min_rect,
        )

        left, right = st.columns(2)
        with left:
            st.image(cv2.cvtColor(result.image_bgr, cv2.COLOR_BGR2RGB), caption="Original floor plan", use_container_width=True)
        with right:
            st.image(cv2.cvtColor(result.overlay_bgr, cv2.COLOR_BGR2RGB), caption=f"Proposed regions ({len(result.candidates)})", use_container_width=True)

        rows = []
        for c in result.candidates:
            width_ft, height_ft, area_ft2 = candidate_dimensions_ft(c, feet_per_pixel)
            rows.append({
                "candidate": f"R{c.candidate_id}",
                "room_name": f"Room {c.candidate_id}",
                "x_px": c.x,
                "y_px": c.y,
                "width_px": c.width_px,
                "height_px": c.height_px,
                "component_area_px": c.area_px,
                "rectangularity": round(c.rectangularity, 3),
                "heuristic_score": round(c.heuristic_score, 1),
                "x_ft_from_scale": round(c.x * feet_per_pixel, 3),
                "y_ft_from_scale": round(c.y * feet_per_pixel, 3),
                "width_ft_from_scale": round(width_ft, 3),
                "height_ft_from_scale": round(height_ft, 3),
                "component_area_ft2": round(area_ft2, 2),
            })
        df = pd.DataFrame(rows)
        if not df.empty:
            st.dataframe(df, use_container_width=True, hide_index=True)
            selected = st.multiselect("Which proposed regions have you visually verified?", options=df["candidate"].tolist())
            if selected:
                verified_df = df[df["candidate"].isin(selected)].copy()
                st.success(f"{len(selected)} region(s) marked user-verified for this session.")
                st.dataframe(verified_df, use_container_width=True, hide_index=True)
                st.download_button(
                    "Download verified region table for Geometry Editor",
                    verified_df.to_csv(index=False).encode("utf-8"),
                    "nitikube_verified_regions.csv",
                    "text/csv",
                )
                st.caption("The CSV now carries image-relative x/y coordinates converted through the same verified scale, so the next Geometry Editor can preserve relative room positions instead of laying regions out arbitrarily.")
            else:
                st.warning("No regions are verified yet. NitiKube should not route these CV proposals into final BOQ/lighting/material calculations as authoritative room geometry.")
        else:
            st.warning("No candidate enclosed regions passed the current filters. Try adjusting the dark threshold or wall/gap dilation, or use manual plan calibration/geometry.")

        with st.expander("See CV masks"):
            m1, m2 = st.columns(2)
            m1.image(result.wall_mask, caption="Wall/dark-feature mask", use_container_width=True)
            m2.image(result.free_space_mask, caption="Free-space mask", use_container_width=True)

        st.info("Known limitation: open doorways, furniture lines, text, scan shadows and perspective distortion can merge or split free-space components. This is why NitiKube treats CV as a proposal layer and makes verification explicit.")
    except Exception as exc:
        st.error(f"Region detection error: {exc}")
else:
    st.info("Upload a plan to generate candidate room/open-space regions. The original line-detection baseline remains available on the main app page.")
