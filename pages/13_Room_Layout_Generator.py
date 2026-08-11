from __future__ import annotations

import json

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

from nitikube.room_layout import (
    FurnitureSpec,
    LayoutRequirements,
    OpeningSegment,
    Rect,
    evaluation_rows,
    generate_drawing_dining_candidates,
    layout_svg,
    opening_keepout,
    rank_layouts,
)
from nitikube.verified_geometry import geometry_from_project_json


st.set_page_config(page_title="NitiKube — Room Layout Generator", page_icon="▤", layout="wide")
st.title("Deterministic Drawing / Dining Layout Generator")
st.caption(
    "Generate and reject furniture arrangements using verified room dimensions, collisions, opening keepouts, explicit clearances and approximate circulation connectivity. "
    "This is geometry-first candidate generation—not an image model guessing where furniture should go."
)

st.warning(
    "All furniture dimensions, clearances, passage widths and zone splits on this page are explicit scenario inputs. "
    "They are not automatically presented as ergonomic standards or building-code requirements."
)

st.subheader("1 · Room geometry")
mode = st.radio("Geometry source", ["Verified NitiKube geometry", "Manual rectangular room"], horizontal=True)
room = None
room_name = "Drawing / Dining"
selected_verified_room = None
verified_openings = []
room_global_origin = (0.0, 0.0)

if mode == "Verified NitiKube geometry":
    uploaded = st.file_uploader("Upload `nitikube_verified_geometry.json`", type=["json"], key="layout_geometry")
    if uploaded:
        try:
            project_name, rooms, openings, metadata = geometry_from_project_json(uploaded.getvalue().decode("utf-8"))
            selectable = [r for r in rooms if r.verified]
            labels = {f"{r.name} · {r.room_id}": r for r in selectable}
            if labels:
                selected_label = st.selectbox("Room", list(labels))
                selected_verified_room = labels[selected_label]
                min_x, min_y, max_x, max_y = selected_verified_room.bounds_ft
                # This generator is intentionally axis-aligned/rectangular in v0.12.
                unique_x = {round(point[0], 8) for point in selected_verified_room.polygon_ft}
                unique_y = {round(point[1], 8) for point in selected_verified_room.polygon_ft}
                if len(selected_verified_room.polygon_ft) != 4 or len(unique_x) != 2 or len(unique_y) != 2:
                    st.error("The selected verified room is not an axis-aligned rectangle. Use the geometry editor or wait for the polygon-aware layout generator; NitiKube will not silently replace it with its bounding box.")
                else:
                    room = Rect(0.0, 0.0, max_x - min_x, max_y - min_y)
                    room_global_origin = (min_x, min_y)
                    room_name = selected_verified_room.name
                    verified_openings = [
                        opening
                        for opening in openings
                        if opening.verified and selected_verified_room.room_id in {opening.room_a, opening.room_b}
                    ]
                    st.success(f"Using verified room {room_name}: {room.width_ft:.3f} × {room.depth_ft:.3f} ft ({room.area_ft2:.1f} ft²).")
            else:
                st.warning("No verified rooms found in the geometry document.")
        except Exception as exc:
            st.error(f"Could not load verified geometry: {exc}")
else:
    c1, c2 = st.columns(2)
    width_ft = c1.number_input("Room width ft", min_value=1.0, value=10 + 7 / 12, step=0.25)
    depth_ft = c2.number_input("Room length/depth ft", min_value=1.0, value=22 + 9 / 12, step=0.25)
    room_name = st.text_input("Room name", "Drawing / Dining")
    room = Rect(0.0, 0.0, float(width_ft), float(depth_ft))

st.subheader("2 · Furniture dimensions")
st.caption("Enter actual or intended product dimensions. `Reserved clearance` expands an item's envelope for chairs/pull-back/service space; it is not automatically treated as a standard.")

f1, f2, f3, f4 = st.columns(4)
with f1:
    st.write("**Sofa**")
    sofa_length = st.number_input("Sofa length", min_value=0.5, value=7.0, step=0.25)
    sofa_depth = st.number_input("Sofa depth", min_value=0.5, value=3.0, step=0.25)
    sofa_clearance = st.number_input("Sofa reserved clearance", min_value=0.0, value=0.25, step=0.25)
with f2:
    st.write("**TV console**")
    tv_length = st.number_input("TV console length", min_value=0.5, value=5.0, step=0.25)
    tv_depth = st.number_input("TV console depth", min_value=0.25, value=1.25, step=0.25)
    tv_clearance = st.number_input("TV console reserved clearance", min_value=0.0, value=0.25, step=0.25)
with f3:
    st.write("**Coffee table**")
    coffee_width = st.number_input("Coffee table width", min_value=0.5, value=4.0, step=0.25)
    coffee_depth = st.number_input("Coffee table depth", min_value=0.5, value=2.0, step=0.25)
    coffee_clearance = st.number_input("Coffee table reserved clearance", min_value=0.0, value=0.0, step=0.25)
with f4:
    st.write("**Dining table**")
    dining_length = st.number_input("Dining table length", min_value=0.5, value=6.0, step=0.25)
    dining_width = st.number_input("Dining table width", min_value=0.5, value=3.0, step=0.25)
    dining_clearance = st.number_input("Dining reserved clearance", min_value=0.0, value=2.0, step=0.25)

sofa = FurnitureSpec("sofa", "Sofa", float(sofa_length), float(sofa_depth), float(sofa_clearance))
tv_console = FurnitureSpec("tv", "TV console", float(tv_length), float(tv_depth), float(tv_clearance))
coffee = FurnitureSpec("coffee", "Coffee table", float(coffee_width), float(coffee_depth), float(coffee_clearance))
dining = FurnitureSpec("dining", "Dining table", float(dining_length), float(dining_width), float(dining_clearance))

st.subheader("3 · Explicit layout constraints")
a1, a2, a3, a4 = st.columns(4)
living_fraction = a1.number_input("Living-zone fraction", min_value=0.25, max_value=0.75, value=0.58, step=0.02)
zone_gap = a2.number_input("Gap between living/dining zones ft", min_value=0.0, value=0.5, step=0.25)
wall_margin = a3.number_input("Furniture wall margin ft", min_value=0.0, value=0.25, step=0.25)
min_pair_gap = a4.number_input("Minimum pairwise furniture gap ft", min_value=0.0, value=0.25, step=0.25)

b1, b2, b3 = st.columns(3)
passage_width = b1.number_input("Circulation passage width to test ft", min_value=0.0, value=2.5, step=0.25)
grid_step = b2.number_input("Circulation raster step ft", min_value=0.10, max_value=1.0, value=0.25, step=0.05)
opening_depth = b3.number_input("Opening keepout depth ft", min_value=0.1, value=3.0, step=0.25)

keepouts = []
if room is not None and verified_openings:
    st.write("**Verified opening keepouts**")
    origin_x, origin_y = room_global_origin
    keepout_errors = []
    for opening in verified_openings:
        local_opening = OpeningSegment(
            opening_id=opening.opening_id,
            kind=opening.kind,
            start_ft=(opening.start_ft[0] - origin_x, opening.start_ft[1] - origin_y),
            end_ft=(opening.end_ft[0] - origin_x, opening.end_ft[1] - origin_y),
        )
        try:
            keepouts.append(opening_keepout(room, local_opening, inward_depth_ft=float(opening_depth)))
        except Exception as exc:
            keepout_errors.append(f"{opening.opening_id}: {exc}")
    if keepouts:
        st.dataframe(
            pd.DataFrame(
                [
                    {
                        "opening": zone.zone_id,
                        "label": zone.label,
                        "x_ft": zone.rect.x_ft,
                        "y_ft": zone.rect.y_ft,
                        "width_ft": zone.rect.width_ft,
                        "depth_ft": zone.rect.depth_ft,
                    }
                    for zone in keepouts
                ]
            ),
            use_container_width=True,
            hide_index=True,
        )
    for error in keepout_errors:
        st.warning(f"Opening keepout not generated: {error}")
elif room is not None:
    st.caption("No verified openings are attached to this room, so no opening keepout zones are applied.")

requirements = LayoutRequirements(
    wall_margin_ft=float(wall_margin),
    min_pair_gap_ft=float(min_pair_gap),
    passage_width_ft=float(passage_width),
    grid_step_ft=float(grid_step),
    require_reserved_clearance_inside_room=True,
)

st.subheader("4 · Generate, reject and rank arrangements")
if room is not None and st.button("Generate drawing/dining layouts", type="primary"):
    try:
        candidates = generate_drawing_dining_candidates(
            room,
            sofa=sofa,
            tv_console=tv_console,
            coffee_table=coffee,
            dining_table=dining,
            living_fraction=float(living_fraction),
            zone_gap_ft=float(zone_gap),
            wall_margin_ft=float(wall_margin),
        )
        ranked = rank_layouts(room, candidates, keepouts=keepouts, requirements=requirements)
        st.session_state["ranked_room_layouts"] = ranked
    except Exception as exc:
        st.error(f"Layout generation failed: {exc}")

ranked = st.session_state.get("ranked_room_layouts")
if ranked and room is not None:
    ranking_df = pd.DataFrame(evaluation_rows(ranked))
    st.dataframe(ranking_df, use_container_width=True, hide_index=True)
    feasible = [(candidate, evaluation) for candidate, evaluation in ranked if evaluation.feasible]
    st.metric("Feasible generated layouts", f"{len(feasible)} / {len(ranked)}")

    if feasible:
        option_labels = {
            f"{candidate.layout_id} · {candidate.name} · score {evaluation.geometry_score:.1f}": (candidate, evaluation)
            for candidate, evaluation in feasible
        }
        selected_label = st.selectbox("Inspect feasible layout", list(option_labels))
        candidate, evaluation = option_labels[selected_label]
        svg = layout_svg(room, candidate, evaluation, keepouts=keepouts)
        components.html(svg, height=min(950, int(room.depth_ft * 28 + 150)), scrolling=True)

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Geometry score", f"{evaluation.geometry_score:.1f}/100")
        c2.metric("Open area", f"{evaluation.open_area_ratio:.1%}")
        c3.metric("Min furniture gap", f"{evaluation.minimum_pair_gap_ft:.2f} ft" if evaluation.minimum_pair_gap_ft is not None else "N/A")
        c4.metric(
            "Walkable connectivity",
            f"{evaluation.circulation_largest_component_ratio:.1%}" if evaluation.circulation_largest_component_ratio is not None else "Not tested",
        )
        for warning in evaluation.warnings:
            st.warning(warning)

        st.download_button(
            "Download selected layout SVG",
            svg.encode("utf-8"),
            f"{candidate.layout_id}_nitikube_layout.svg",
            "image/svg+xml",
        )

        st.subheader("5 · Promote this layout into the whole-home optimizer")
        st.write(
            "Geometry feasibility does not create quality/aesthetic/cost scores automatically. Supply those separately so the next optimizer can distinguish objective layout geometry from subjective or market/evidence inputs."
        )
        p1, p2, p3 = st.columns(3)
        package_cost = p1.number_input("Package cost ₹", min_value=0.0, value=0.0, step=5000.0)
        score_source = p2.text_input("Score source/label", "user assessment")
        package_name = p3.text_input("Package name", candidate.name)
        q1, q2, q3, q4, q5 = st.columns(5)
        quality = q1.number_input("Quality", min_value=0.0, max_value=100.0, value=50.0, step=5.0)
        durability = q2.number_input("Durability", min_value=0.0, max_value=100.0, value=50.0, step=5.0)
        aesthetics = q3.number_input("Aesthetics", min_value=0.0, max_value=100.0, value=50.0, step=5.0)
        comfort = q4.number_input("Comfort", min_value=0.0, max_value=100.0, value=50.0, step=5.0)
        maintainability = q5.number_input("Maintainability", min_value=0.0, max_value=100.0, value=50.0, step=5.0)

        optimizer_option = {
            "options": [
                {
                    "room_id": selected_verified_room.room_id if selected_verified_room else "manual-room",
                    "option_id": f"layout-{candidate.layout_id}",
                    "name": package_name,
                    "cost": float(package_cost),
                    "quality": float(quality),
                    "durability": float(durability),
                    "aesthetics": float(aesthetics),
                    "comfort": float(comfort),
                    "maintainability": float(maintainability),
                    "min_area_ft2": room.area_ft2,
                    "min_width_ft": room.width_ft,
                    "min_height_ft": room.depth_ft,
                    "features": ["geometry-checked-layout", "circulation-evaluated"],
                    "feasible": evaluation.feasible,
                    "score_source": score_source,
                    "notes": [
                        f"NitiKube source layout: {candidate.layout_id}",
                        f"geometry_score={evaluation.geometry_score}",
                        "Geometry score is not reused as an aesthetic/quality score.",
                    ],
                }
            ]
        }
        st.download_button(
            "Download optimizer-compatible room package",
            json.dumps(optimizer_option, indent=2, ensure_ascii=False).encode("utf-8"),
            f"{candidate.layout_id}_whole_home_option.json",
            "application/json",
        )
    else:
        st.error("Every generated arrangement violates at least one current geometry/clearance/keepout requirement. Adjust the explicit scenario inputs or furniture sizes; NitiKube will not force a layout through failed constraints.")

st.caption(
    "Current generator scope is deliberately narrow: axis-aligned rectangular drawing/dining rooms with four core furniture items. "
    "Next iterations can add polygon rooms, bedrooms, kitchens, wardrobes, chairs, door-swing arcs, window access, TV sightlines and more sophisticated route/clearance objectives on the same deterministic geometry foundation."
)
