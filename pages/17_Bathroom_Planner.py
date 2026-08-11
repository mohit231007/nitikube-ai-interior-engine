from __future__ import annotations

import json

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

from nitikube.bathroom_planner import (
    BathroomRequirements,
    FixtureSpec,
    ShowerSpec,
    bathroom_quantities,
    bathroom_svg,
    evaluation_rows,
    generate_bathroom_candidates,
    rank_bathrooms,
)
from nitikube.room_layout import OpeningSegment, Rect, opening_keepout
from nitikube.verified_geometry import geometry_from_project_json


st.set_page_config(page_title="NitiKube — Bathroom Planner", page_icon="▣", layout="wide")
st.title("Deterministic Bathroom Planner")
st.caption(
    "Generate shower/WC/basin arrangements from verified/manual room geometry, then reject collisions, opening conflicts, blocked fixture-front clearance and fragmented passage space. Quantities, ventilation airflow and drainage fall are calculated from explicit inputs."
)
st.warning(
    "Fixture clearances, passage width, ventilation ACH and drainage slope are scenario inputs. They are not universal plumbing/accessibility/building standards unless a sourced standards layer supplies that provenance."
)

st.subheader("1 · Bathroom geometry")
mode = st.radio("Geometry source", ["Manual rectangular bathroom", "Verified NitiKube geometry"], horizontal=True)
room = None
selected_verified_room = None
verified_openings = []
origin = (0.0, 0.0)
room_name = "Bathroom"

if mode == "Manual rectangular bathroom":
    g1, g2, g3 = st.columns(3)
    width = g1.number_input("Bathroom width ft", min_value=3.0, value=7.0, step=0.25)
    depth = g2.number_input("Bathroom length/depth ft", min_value=3.0, value=9.0, step=0.25)
    room_name = g3.text_input("Room name", "Bathroom")
    room = Rect(0.0, 0.0, float(width), float(depth))
else:
    uploaded = st.file_uploader("Upload `nitikube_verified_geometry.json`", type=["json"], key="bathroom_geometry")
    if uploaded:
        try:
            _, rooms, openings, _ = geometry_from_project_json(uploaded.getvalue().decode("utf-8"))
            verified = [r for r in rooms if r.verified]
            labels = {f"{r.name} · {r.room_id}": r for r in verified}
            if labels:
                selected_verified_room = labels[st.selectbox("Verified room", list(labels))]
                min_x, min_y, max_x, max_y = selected_verified_room.bounds_ft
                unique_x = {round(point[0], 8) for point in selected_verified_room.polygon_ft}
                unique_y = {round(point[1], 8) for point in selected_verified_room.polygon_ft}
                if len(selected_verified_room.polygon_ft) != 4 or len(unique_x) != 2 or len(unique_y) != 2:
                    st.error("Current bathroom generator supports axis-aligned rectangular verified rooms. NitiKube will not silently replace an arbitrary polygon with its bounding box.")
                else:
                    room = Rect(0.0, 0.0, max_x - min_x, max_y - min_y)
                    origin = (min_x, min_y)
                    room_name = selected_verified_room.name
                    verified_openings = [o for o in openings if o.verified and selected_verified_room.room_id in {o.room_a, o.room_b}]
                    st.success(f"Using {room_name}: {room.width_ft:.2f} × {room.depth_ft:.2f} ft ({room.area_ft2:.1f} ft²)")
            else:
                st.warning("No verified rooms found.")
        except Exception as exc:
            st.error(f"Verified geometry could not be loaded: {exc}")

st.subheader("2 · Fixture dimensions")
s1, s2 = st.columns(2)
shower_width = s1.number_input("Shower-zone width ft", min_value=1.0, value=3.0, step=0.25)
shower_depth = s2.number_input("Shower-zone depth ft", min_value=1.0, value=3.0, step=0.25)
shower = ShowerSpec(float(shower_width), float(shower_depth))

w1, w2, w3 = st.columns(3)
wc_width = w1.number_input("WC width along wall ft", min_value=0.5, value=2.0, step=0.25)
wc_depth = w2.number_input("WC projection/depth ft", min_value=0.5, value=2.5, step=0.25)
wc_front = w3.number_input("WC front-clearance target ft", min_value=0.0, value=2.5, step=0.25)
wc = FixtureSpec("wc", "WC", float(wc_width), float(wc_depth), float(wc_front))

b1, b2, b3 = st.columns(3)
basin_width = b1.number_input("Basin/vanity width along wall ft", min_value=0.5, value=2.5, step=0.25)
basin_depth = b2.number_input("Basin/vanity depth ft", min_value=0.5, value=1.75, step=0.25)
basin_front = b3.number_input("Basin front-clearance target ft", min_value=0.0, value=2.0, step=0.25)
basin = FixtureSpec("basin", "Basin", float(basin_width), float(basin_depth), float(basin_front))

st.subheader("3 · Opening / passage constraints")
c1, c2, c3, c4 = st.columns(4)
wall_margin = c1.number_input("Fixture wall margin ft", min_value=0.0, value=0.0, step=0.25)
passage_width = c2.number_input("Passage width to test ft", min_value=0.0, value=2.0, step=0.25)
grid_step = c3.number_input("Circulation raster step ft", min_value=0.10, max_value=1.0, value=0.20, step=0.05)
opening_depth = c4.number_input("Verified opening keepout depth ft", min_value=0.1, value=2.5, step=0.25)
require_connected = st.checkbox("Require connected walkable space at requested passage width", value=True)
requirements = BathroomRequirements(
    passage_width_ft=float(passage_width),
    grid_step_ft=float(grid_step),
    require_connected_passage=require_connected,
    require_fixture_front_clearance_inside_room=True,
)

keepouts = []
if room is not None and verified_openings:
    ox, oy = origin
    for opening in verified_openings:
        try:
            local = OpeningSegment(
                opening.opening_id,
                (opening.start_ft[0] - ox, opening.start_ft[1] - oy),
                (opening.end_ft[0] - ox, opening.end_ft[1] - oy),
                opening.kind,
            )
            keepouts.append(opening_keepout(room, local, inward_depth_ft=float(opening_depth)))
        except Exception as exc:
            st.warning(f"Could not construct keepout for {opening.opening_id}: {exc}")

st.subheader("4 · Generate and evaluate bathroom layouts")
if room is not None and st.button("Generate bathroom candidates", type="primary"):
    try:
        candidates = generate_bathroom_candidates(
            room,
            shower=shower,
            wc=wc,
            basin=basin,
            wall_margin_ft=float(wall_margin),
        )
        st.session_state["bathroom_ranked"] = rank_bathrooms(room, candidates, keepouts=keepouts, requirements=requirements)
    except Exception as exc:
        st.error(f"Bathroom generation failed: {exc}")

ranked = st.session_state.get("bathroom_ranked")
if ranked and room is not None:
    table = pd.DataFrame(evaluation_rows(ranked))
    st.dataframe(table, use_container_width=True, hide_index=True)
    feasible = [(c, e) for c, e in ranked if e.feasible]
    st.metric("Feasible generated layouts", f"{len(feasible)} / {len(ranked)}")

    if feasible:
        option_map = {f"{c.layout_id} · {c.name} · score {e.geometry_score:.1f}": (c, e) for c, e in feasible}
        selected_label = st.selectbox("Inspect feasible bathroom", list(option_map))
        candidate, evaluation = option_map[selected_label]
        svg = bathroom_svg(room, candidate, evaluation, keepouts=keepouts)
        components.html(svg, height=min(950, int(room.depth_ft * 42 + 140)), scrolling=True)

        m1, m2, m3 = st.columns(3)
        m1.metric("Geometry score", f"{evaluation.geometry_score:.1f}/100")
        m2.metric("Open floor area", f"{evaluation.open_area_ratio:.1%}")
        m3.metric("Walkable connectivity", f"{evaluation.circulation_connectivity:.1%}" if evaluation.circulation_connectivity is not None else "Not tested")
        for warning in evaluation.warnings:
            st.warning(warning)

        st.subheader("5 · Tile, waterproofing, exhaust and drainage maths")
        q1, q2, q3, q4 = st.columns(4)
        floor_waste = q1.number_input("Floor tile waste fraction", min_value=0.0, max_value=1.0, value=0.10, step=0.01)
        wall_tile_height = q2.number_input("Wall tile height ft", min_value=0.0, value=7.0, step=0.25)
        opening_deduction = q3.number_input("Known wall-opening deduction ft²", min_value=0.0, value=0.0, step=1.0)
        waterproof_floor_fraction = q4.number_input("Floor waterproof fraction", min_value=0.0, max_value=1.0, value=1.0, step=0.05)

        q5, q6, q7, q8 = st.columns(4)
        wet_wall_height = q5.number_input("Shower wet-wall waterproof height ft", min_value=0.0, value=7.0, step=0.25)
        ceiling_height = q6.number_input("Ceiling height ft", min_value=1.0, value=9.0, step=0.25)
        ach = q7.number_input("Scenario air changes per hour", min_value=0.1, value=8.0, step=0.5)
        drainage_run = q8.number_input("Drainage fall run ft", min_value=0.0, value=4.0, step=0.25)
        slope_percent = st.number_input("Scenario drainage slope percent", min_value=0.0, value=1.5, step=0.1)

        quantities = bathroom_quantities(
            room,
            candidate,
            floor_waste_fraction=float(floor_waste),
            wall_tile_height_ft=float(wall_tile_height),
            wall_opening_deduction_ft2=float(opening_deduction),
            waterproof_floor_fraction=float(waterproof_floor_fraction),
            shower_wet_wall_height_ft=float(wet_wall_height),
            ceiling_height_ft=float(ceiling_height),
            air_changes_per_hour=float(ach),
            drainage_run_ft=float(drainage_run),
            drainage_slope_percent=float(slope_percent),
        )
        qdf = pd.DataFrame([{field: getattr(quantities, field) for field in quantities.__dataclass_fields__}])
        st.dataframe(qdf, use_container_width=True, hide_index=True)
        st.write(
            f"At `{ach:.2f}` ACH, required idealized exhaust airflow = **{quantities.required_exhaust_cfm:.1f} CFM** from `room volume × ACH / 60`. "
            f"At `{slope_percent:.2f}%` over `{drainage_run:.2f} ft`, vertical fall = **{quantities.drainage_fall_in:.2f} in**."
        )
        st.caption("ACH and drainage slope are user/sourced scenario values. Fan selection also needs real duct/static-pressure/noise data; drainage design needs plumbing/waterproofing verification and local practice/standards.")

        st.download_button("Download bathroom layout SVG", svg.encode("utf-8"), f"{candidate.layout_id}_bathroom.svg", "image/svg+xml")

        st.subheader("6 · Promote bathroom to whole-home optimisation")
        e1, e2 = st.columns(2)
        package_cost = e1.number_input("Bathroom package cost ₹", min_value=0.0, value=0.0, step=10_000.0)
        score_source = e2.text_input("Score source/label", "user assessment")
        s1, s2, s3, s4, s5 = st.columns(5)
        quality = s1.number_input("Quality score", min_value=0.0, max_value=100.0, value=50.0, step=5.0)
        durability = s2.number_input("Durability score", min_value=0.0, max_value=100.0, value=50.0, step=5.0)
        aesthetics = s3.number_input("Aesthetics score", min_value=0.0, max_value=100.0, value=50.0, step=5.0)
        comfort = s4.number_input("Comfort score", min_value=0.0, max_value=100.0, value=50.0, step=5.0)
        maintainability = s5.number_input("Maintainability score", min_value=0.0, max_value=100.0, value=50.0, step=5.0)
        room_id = selected_verified_room.room_id if selected_verified_room else "manual-bathroom"
        payload = {"options": [{
            "room_id": room_id,
            "option_id": f"bathroom-{candidate.layout_id}",
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
            "features": ["geometry-checked-bathroom", "wet-area-quantity-calculated", "circulation-evaluated"],
            "feasible": evaluation.feasible,
            "score_source": score_source,
            "notes": [
                f"geometry_score={evaluation.geometry_score}",
                f"waterproof_area_ft2={quantities.total_waterproof_area_ft2}",
                "User/evidence scores remain separate from geometry score.",
            ],
        }]}
        st.download_button(
            "Download optimizer-compatible bathroom package",
            json.dumps(payload, indent=2, ensure_ascii=False).encode("utf-8"),
            f"{candidate.layout_id}_whole_home_bathroom_option.json",
            "application/json",
        )
    else:
        st.error("No generated bathroom survives the current geometry/opening/clearance/passage constraints. Change explicit assumptions or fixture sizes; NitiKube will not force an invalid arrangement.")
else:
    st.info("Provide room geometry and generate candidates. No bathroom arrangement is preselected.")

st.caption("Next fidelity steps: plumbing stack/drain coordinates, exact door swings, shower-screen/door geometry, floor-drain location, slope field rather than one run, fixture manufacturer clearances, electrical wet-zone rules, moisture/surface-temperature modelling and sourced local plumbing/accessibility standards.")
