from __future__ import annotations

import json

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

from nitikube.kitchen_planner import (
    KitchenLayoutKind,
    KitchenRequirements,
    OpeningSegment,
    WorkCenterSpec,
    evaluation_rows,
    generate_kitchen_candidates,
    kitchen_quantity_summary,
    kitchen_svg,
    opening_keepout,
    rank_kitchens,
)
from nitikube.room_layout import Rect
from nitikube.verified_geometry import geometry_from_project_json


st.set_page_config(page_title="NitiKube — Kitchen Planner", page_icon="▥", layout="wide")
st.title("Deterministic Kitchen Planner")
st.caption(
    "Generate one-wall, galley, L-shaped and U-shaped kitchen candidates from verified/manual room geometry, then reject them using explicit opening, work-triangle, counter-run and circulation constraints."
)

st.warning(
    "Counter depth, aisle/passage width and work-triangle thresholds are visible design-scenario inputs. "
    "They are not presented as universal ergonomic/building standards unless a later sourced standards layer supplies that provenance."
)

st.subheader("1 · Kitchen geometry")
geometry_mode = st.radio("Geometry source", ["Manual rectangular kitchen", "Verified NitiKube geometry"], horizontal=True)
room = None
selected_verified_room = None
verified_openings = []
origin = (0.0, 0.0)
room_name = "Kitchen"

if geometry_mode == "Manual rectangular kitchen":
    g1, g2, g3 = st.columns(3)
    width_ft = g1.number_input("Kitchen width ft", min_value=3.0, value=10.0, step=0.25)
    depth_ft = g2.number_input("Kitchen length/depth ft", min_value=3.0, value=12.0, step=0.25)
    room_name = g3.text_input("Room name", "Kitchen")
    room = Rect(0.0, 0.0, float(width_ft), float(depth_ft))
else:
    geometry_file = st.file_uploader("Upload `nitikube_verified_geometry.json`", type=["json"], key="kitchen_geometry")
    if geometry_file:
        try:
            project_name, rooms, openings, metadata = geometry_from_project_json(geometry_file.getvalue().decode("utf-8"))
            verified_rooms = [r for r in rooms if r.verified]
            labels = {f"{r.name} · {r.room_id}": r for r in verified_rooms}
            if labels:
                selected_verified_room = labels[st.selectbox("Verified room", list(labels))]
                min_x, min_y, max_x, max_y = selected_verified_room.bounds_ft
                unique_x = {round(point[0], 8) for point in selected_verified_room.polygon_ft}
                unique_y = {round(point[1], 8) for point in selected_verified_room.polygon_ft}
                if len(selected_verified_room.polygon_ft) != 4 or len(unique_x) != 2 or len(unique_y) != 2:
                    st.error("Current kitchen candidate generator supports axis-aligned rectangular verified rooms. NitiKube will not silently replace an arbitrary verified polygon with its bounding box.")
                else:
                    room = Rect(0.0, 0.0, max_x - min_x, max_y - min_y)
                    origin = (min_x, min_y)
                    room_name = selected_verified_room.name
                    verified_openings = [
                        opening for opening in openings
                        if opening.verified and selected_verified_room.room_id in {opening.room_a, opening.room_b}
                    ]
                    st.success(f"Using {room_name}: {room.width_ft:.2f} × {room.depth_ft:.2f} ft ({room.area_ft2:.1f} ft²)")
            else:
                st.warning("No verified rooms found in the uploaded geometry.")
        except Exception as exc:
            st.error(f"Verified geometry could not be loaded: {exc}")

st.subheader("2 · Counter and work-center dimensions")
c1, c2, c3 = st.columns(3)
counter_depth = c1.number_input("Counter depth ft", min_value=0.5, value=2.0, step=0.25)
wall_margin = c2.number_input("Counter wall/end margin ft", min_value=0.0, value=0.0, step=0.25)
min_counter_run = c3.number_input("Minimum acceptable run length ft", min_value=0.0, value=4.0, step=0.5)

w1, w2, w3 = st.columns(3)
with w1:
    st.write("**Sink module**")
    sink_width = st.number_input("Sink module width along run ft", min_value=0.5, value=3.0, step=0.25)
    sink_depth = st.number_input("Sink module depth ft", min_value=0.5, value=2.0, step=0.25)
with w2:
    st.write("**Hob/cooktop module**")
    hob_width = st.number_input("Hob module width along run ft", min_value=0.5, value=2.5, step=0.25)
    hob_depth = st.number_input("Hob module depth ft", min_value=0.5, value=2.0, step=0.25)
with w3:
    st.write("**Fridge/tall module**")
    fridge_width = st.number_input("Fridge module width along run ft", min_value=0.5, value=3.0, step=0.25)
    fridge_depth = st.number_input("Fridge module depth ft", min_value=0.5, value=2.0, step=0.25)

sink = WorkCenterSpec("sink", "Sink", float(sink_width), float(sink_depth))
hob = WorkCenterSpec("hob", "Hob", float(hob_width), float(hob_depth))
fridge = WorkCenterSpec("fridge", "Fridge", float(fridge_width), float(fridge_depth))

st.subheader("3 · Candidate families and explicit constraints")
family_labels = {
    "One-wall": KitchenLayoutKind.ONE_WALL,
    "Galley": KitchenLayoutKind.GALLEY,
    "L-shape": KitchenLayoutKind.L_SHAPE,
    "U-shape": KitchenLayoutKind.U_SHAPE,
}
selected_families = st.multiselect("Generate layout families", list(family_labels), default=list(family_labels))
include_kinds = tuple(family_labels[label] for label in selected_families)

p1, p2, p3 = st.columns(3)
passage_width = p1.number_input("Passage/aisle width to test ft", min_value=0.0, value=3.0, step=0.25)
grid_step = p2.number_input("Circulation raster step ft", min_value=0.10, max_value=1.0, value=0.25, step=0.05)
opening_keepout_depth = p3.number_input("Verified opening keepout depth ft", min_value=0.1, value=3.0, step=0.25)
require_connected = st.checkbox("Require connected walkable space at requested passage width", value=True)

with st.expander("Work-triangle constraints", expanded=True):
    st.write("Leave a limit disabled when you do not want it treated as a hard constraint. Values are scenario inputs, not hidden NitiKube standards.")
    t1, t2 = st.columns(2)
    enable_leg_min = t1.checkbox("Enable minimum triangle leg", value=False)
    leg_min = t1.number_input("Minimum leg ft", min_value=0.0, value=4.0, step=0.5, disabled=not enable_leg_min)
    enable_leg_max = t2.checkbox("Enable maximum triangle leg", value=False)
    leg_max = t2.number_input("Maximum leg ft", min_value=0.0, value=9.0, step=0.5, disabled=not enable_leg_max)
    t3, t4 = st.columns(2)
    enable_total_min = t3.checkbox("Enable minimum triangle perimeter", value=False)
    total_min = t3.number_input("Minimum perimeter ft", min_value=0.0, value=12.0, step=0.5, disabled=not enable_total_min)
    enable_total_max = t4.checkbox("Enable maximum triangle perimeter", value=False)
    total_max = t4.number_input("Maximum perimeter ft", min_value=0.0, value=26.0, step=0.5, disabled=not enable_total_max)

requirements = KitchenRequirements(
    wall_margin_ft=float(wall_margin),
    min_counter_run_ft=float(min_counter_run),
    passage_width_ft=float(passage_width),
    grid_step_ft=float(grid_step),
    require_connected_passage=require_connected,
    work_triangle_leg_min_ft=float(leg_min) if enable_leg_min else None,
    work_triangle_leg_max_ft=float(leg_max) if enable_leg_max else None,
    work_triangle_total_min_ft=float(total_min) if enable_total_min else None,
    work_triangle_total_max_ft=float(total_max) if enable_total_max else None,
)

keepouts = []
if room is not None and verified_openings:
    origin_x, origin_y = origin
    for opening in verified_openings:
        try:
            local = OpeningSegment(
                opening.opening_id,
                (opening.start_ft[0] - origin_x, opening.start_ft[1] - origin_y),
                (opening.end_ft[0] - origin_x, opening.end_ft[1] - origin_y),
                opening.kind,
            )
            keepouts.append(opening_keepout(room, local, inward_depth_ft=float(opening_keepout_depth)))
        except Exception as exc:
            st.warning(f"Could not construct keepout for {opening.opening_id}: {exc}")
if keepouts:
    st.dataframe(
        pd.DataFrame([
            {
                "opening": zone.zone_id,
                "x_ft": zone.rect.x_ft,
                "y_ft": zone.rect.y_ft,
                "width_ft": zone.rect.width_ft,
                "depth_ft": zone.rect.depth_ft,
            }
            for zone in keepouts
        ]),
        use_container_width=True,
        hide_index=True,
    )

st.subheader("4 · Generate and evaluate kitchens")
if room is not None and st.button("Generate kitchen candidates", type="primary", disabled=not bool(include_kinds)):
    try:
        candidates = generate_kitchen_candidates(
            room,
            counter_depth_ft=float(counter_depth),
            wall_margin_ft=float(wall_margin),
            sink=sink,
            hob=hob,
            fridge=fridge,
            include_kinds=include_kinds,
        )
        ranked = rank_kitchens(room, candidates, keepouts=keepouts, requirements=requirements)
        st.session_state["kitchen_ranked"] = ranked
    except Exception as exc:
        st.error(f"Kitchen generation failed: {exc}")

ranked = st.session_state.get("kitchen_ranked")
if ranked and room is not None:
    ranked_df = pd.DataFrame(evaluation_rows(ranked))
    st.dataframe(ranked_df, use_container_width=True, hide_index=True)
    feasible = [(candidate, evaluation) for candidate, evaluation in ranked if evaluation.feasible]
    st.metric("Feasible candidates", f"{len(feasible)} / {len(ranked)}")

    if feasible:
        options = {
            f"{candidate.layout_id} · {candidate.name} · {evaluation.geometry_score:.1f}": (candidate, evaluation)
            for candidate, evaluation in feasible
        }
        selected_label = st.selectbox("Inspect feasible kitchen", list(options))
        candidate, evaluation = options[selected_label]
        svg = kitchen_svg(room, candidate, evaluation, keepouts=keepouts)
        components.html(svg, height=min(1000, int(room.depth_ft * 32 + 130)), scrolling=True)

        k1, k2, k3, k4 = st.columns(4)
        k1.metric("Geometry score", f"{evaluation.geometry_score:.1f}/100")
        k2.metric("Counter run", f"{evaluation.gross_counter_run_ft:.1f} ft")
        k3.metric("Countertop area", f"{evaluation.countertop_union_area_ft2:.1f} ft²")
        k4.metric(
            "Walkable connectivity",
            f"{evaluation.circulation_connectivity:.1%}" if evaluation.circulation_connectivity is not None else "Not tested",
        )
        if evaluation.work_triangle:
            triangle = evaluation.work_triangle
            st.write(
                f"**Work triangle:** sink↔hob `{triangle.sink_to_hob_ft:.2f} ft`, hob↔fridge `{triangle.hob_to_fridge_ft:.2f} ft`, fridge↔sink `{triangle.fridge_to_sink_ft:.2f} ft`, total `{triangle.perimeter_ft:.2f} ft`."
            )

        st.subheader("5 · Quantity geometry")
        q1, q2, q3, q4 = st.columns(4)
        base_height = q1.number_input("Base cabinet front height ft", min_value=0.1, value=2.75, step=0.25)
        wall_height = q2.number_input("Wall cabinet front height ft", min_value=0.0, value=2.5, step=0.25)
        wall_fraction = q3.number_input("Fraction of run receiving wall cabinets", min_value=0.0, max_value=1.0, value=0.7, step=0.05)
        countertop_waste = q4.number_input("Countertop waste fraction", min_value=0.0, max_value=1.0, value=0.1, step=0.01)
        quantities = kitchen_quantity_summary(
            candidate,
            evaluation,
            base_cabinet_height_ft=float(base_height),
            wall_cabinet_height_ft=float(wall_height),
            wall_cabinet_run_fraction=float(wall_fraction),
            countertop_waste_fraction=float(countertop_waste),
        )
        st.dataframe(pd.DataFrame([quantities]), use_container_width=True, hide_index=True)
        st.caption("These are geometric quantity envelopes. Actual board/module counts must later account for cabinet carcass construction, appliance voids, corner hardware, panel thickness, standard sheet/module sizes and manufacturer installation rules.")

        st.download_button(
            "Download kitchen layout SVG",
            svg.encode("utf-8"),
            f"{candidate.layout_id}_kitchen.svg",
            "image/svg+xml",
        )

        st.subheader("6 · Promote kitchen to whole-home optimisation")
        e1, e2 = st.columns(2)
        package_cost = e1.number_input("Kitchen package cost ₹", min_value=0.0, value=0.0, step=10_000.0)
        score_source = e2.text_input("Score source/label", "user assessment")
        s1, s2, s3, s4, s5 = st.columns(5)
        quality = s1.number_input("Quality score", min_value=0.0, max_value=100.0, value=50.0, step=5.0)
        durability = s2.number_input("Durability score", min_value=0.0, max_value=100.0, value=50.0, step=5.0)
        aesthetics = s3.number_input("Aesthetics score", min_value=0.0, max_value=100.0, value=50.0, step=5.0)
        comfort = s4.number_input("Comfort score", min_value=0.0, max_value=100.0, value=50.0, step=5.0)
        maintainability = s5.number_input("Maintainability score", min_value=0.0, max_value=100.0, value=50.0, step=5.0)
        room_id = selected_verified_room.room_id if selected_verified_room else "manual-kitchen"
        optimizer_payload = {
            "options": [
                {
                    "room_id": room_id,
                    "option_id": f"kitchen-{candidate.layout_id}",
                    "name": candidate.name,
                    "cost": float(package_cost),
                    "quality": float(quality),
                    "durability": float(durability),
                    "aesthetics": float(aesthetics),
                    "comfort": float(comfort),
                    "maintainability": float(maintainability),
                    "min_area_ft2": room.area_ft2,
                    "min_width_ft": room.width_ft,
                    "min_height_ft": room.depth_ft,
                    "features": [
                        "geometry-checked-kitchen",
                        f"layout-kind:{candidate.kind.value}",
                        "work-triangle-calculated",
                        "counter-quantity-calculated",
                    ],
                    "feasible": evaluation.feasible,
                    "score_source": score_source,
                    "notes": [
                        f"geometry_score={evaluation.geometry_score}",
                        f"counter_run_ft={evaluation.gross_counter_run_ft}",
                        "User/evidence scores remain separate from geometry score.",
                    ],
                }
            ]
        }
        st.download_button(
            "Download optimizer-compatible kitchen package",
            json.dumps(optimizer_payload, indent=2, ensure_ascii=False).encode("utf-8"),
            f"{candidate.layout_id}_whole_home_kitchen_option.json",
            "application/json",
        )
    else:
        st.error("No generated kitchen survives the current geometry/opening/passage/work-triangle constraints. Change explicit inputs or room/furniture assumptions; NitiKube will not force an invalid kitchen through the optimizer.")
else:
    st.info("Provide room geometry and generate candidates. No kitchen recommendation is precomputed or hardcoded.")

st.caption(
    "Next fidelity steps: exact door-swing/window constraints, plumbing/drain/gas/electrical service points, cabinet module libraries, corner-cabinet logic, countertop slab nesting, appliance manufacturer clearances, ventilation/hood requirements and sourced kitchen ergonomics/standards."
)
