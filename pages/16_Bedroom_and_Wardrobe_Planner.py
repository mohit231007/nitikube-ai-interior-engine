from __future__ import annotations

import json

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

from nitikube.bedroom_planner import (
    BedSpec,
    BedroomRequirements,
    DeskSpec,
    WardrobeSpec,
    bedroom_svg,
    evaluation_rows,
    generate_bedroom_candidates,
    rank_bedrooms,
)
from nitikube.room_layout import OpeningSegment, Rect, opening_keepout
from nitikube.verified_geometry import geometry_from_project_json


st.set_page_config(page_title="NitiKube — Bedroom + Wardrobe Planner", page_icon="▱", layout="wide")
st.title("Deterministic Bedroom + Wardrobe Planner")
st.caption(
    "Generate bed/wardrobe/desk wall arrangements from verified/manual room geometry, then reject collisions, blocked bed-side/foot clearance, wardrobe-front obstruction, opening conflicts and fragmented passage space."
)
st.warning(
    "Clearance and passage values are explicit design-scenario inputs. They are not universal ergonomic/accessibility standards unless a sourced standards layer supplies that provenance."
)

st.subheader("1 · Room geometry")
mode = st.radio("Geometry source", ["Manual rectangular bedroom", "Verified NitiKube geometry"], horizontal=True)
room = None
selected_verified_room = None
verified_openings = []
origin = (0.0, 0.0)
room_name = "Bedroom"

if mode == "Manual rectangular bedroom":
    g1, g2, g3 = st.columns(3)
    width = g1.number_input("Bedroom width ft", min_value=4.0, value=12.0, step=0.25)
    depth = g2.number_input("Bedroom length/depth ft", min_value=4.0, value=14.0, step=0.25)
    room_name = g3.text_input("Room name", "Bedroom")
    room = Rect(0.0, 0.0, float(width), float(depth))
else:
    uploaded = st.file_uploader("Upload `nitikube_verified_geometry.json`", type=["json"], key="bedroom_geometry")
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
                    st.error("Current bedroom generator supports axis-aligned rectangular verified rooms. NitiKube will not silently replace an arbitrary polygon with its bounding box.")
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

st.subheader("2 · Furniture dimensions")
b1, b2 = st.columns(2)
bed_width = b1.number_input("Bed/headboard width ft", min_value=2.0, value=6.0, step=0.25)
bed_length = b2.number_input("Bed length into room ft", min_value=4.0, value=6.5, step=0.25)
bed = BedSpec(float(bed_width), float(bed_length))

w1, w2, w3 = st.columns(3)
wardrobe_run = w1.number_input("Wardrobe run length ft", min_value=1.0, value=6.0, step=0.25)
wardrobe_depth = w2.number_input("Wardrobe depth ft", min_value=0.5, value=2.0, step=0.25)
wardrobe_height = w3.number_input("Wardrobe height ft", min_value=1.0, value=8.0, step=0.25)
wardrobe = WardrobeSpec(float(wardrobe_run), float(wardrobe_depth), float(wardrobe_height))

use_desk = st.checkbox("Include a desk/workstation", value=True)
desk = None
if use_desk:
    d1, d2 = st.columns(2)
    desk_width = d1.number_input("Desk width ft", min_value=1.0, value=4.0, step=0.25)
    desk_depth = d2.number_input("Desk depth ft", min_value=0.5, value=2.0, step=0.25)
    desk = DeskSpec(float(desk_width), float(desk_depth))

st.subheader("3 · Explicit clearance / circulation scenario")
c1, c2, c3, c4 = st.columns(4)
wall_margin = c1.number_input("Furniture wall margin ft", min_value=0.0, value=0.0, step=0.25)
side_clearance = c2.number_input("Bed side-clearance target ft", min_value=0.0, value=2.0, step=0.25)
foot_clearance = c3.number_input("Bed foot-clearance target ft", min_value=0.0, value=2.5, step=0.25)
wardrobe_front_clearance = c4.number_input("Wardrobe front-clearance target ft", min_value=0.0, value=3.0, step=0.25)

p1, p2, p3 = st.columns(3)
passage_width = p1.number_input("Passage width to test ft", min_value=0.0, value=2.5, step=0.25)
grid_step = p2.number_input("Circulation raster step ft", min_value=0.10, max_value=1.0, value=0.25, step=0.05)
opening_depth = p3.number_input("Verified opening keepout depth ft", min_value=0.1, value=3.0, step=0.25)
require_connected = st.checkbox("Require connected walkable space at requested passage width", value=True)

requirements = BedroomRequirements(
    side_clearance_ft=float(side_clearance),
    foot_clearance_ft=float(foot_clearance),
    wardrobe_front_clearance_ft=float(wardrobe_front_clearance),
    passage_width_ft=float(passage_width),
    grid_step_ft=float(grid_step),
    require_connected_passage=require_connected,
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
if keepouts:
    st.dataframe(pd.DataFrame([{
        "opening": zone.zone_id,
        "x_ft": zone.rect.x_ft,
        "y_ft": zone.rect.y_ft,
        "width_ft": zone.rect.width_ft,
        "depth_ft": zone.rect.depth_ft,
    } for zone in keepouts]), use_container_width=True, hide_index=True)

st.subheader("4 · Generate and evaluate layouts")
if room is not None and st.button("Generate bedroom layouts", type="primary"):
    try:
        candidates = generate_bedroom_candidates(
            room,
            bed=bed,
            wardrobe=wardrobe,
            desk=desk,
            wall_margin_ft=float(wall_margin),
            side_clearance_ft=float(side_clearance),
            foot_clearance_ft=float(foot_clearance),
            wardrobe_front_clearance_ft=float(wardrobe_front_clearance),
        )
        st.session_state["bedroom_ranked"] = rank_bedrooms(
            room,
            candidates,
            wardrobe,
            keepouts=keepouts,
            requirements=requirements,
        )
    except Exception as exc:
        st.error(f"Bedroom generation failed: {exc}")

ranked = st.session_state.get("bedroom_ranked")
if ranked and room is not None:
    table = pd.DataFrame(evaluation_rows(ranked))
    st.dataframe(table, use_container_width=True, hide_index=True)
    feasible = [(c, e) for c, e in ranked if e.feasible]
    st.metric("Feasible generated layouts", f"{len(feasible)} / {len(ranked)}")

    if feasible:
        option_map = {f"{c.layout_id} · {c.name} · score {e.geometry_score:.1f}": (c, e) for c, e in feasible}
        selected_label = st.selectbox("Inspect feasible bedroom", list(option_map))
        candidate, evaluation = option_map[selected_label]
        svg = bedroom_svg(room, candidate, evaluation, keepouts=keepouts)
        components.html(svg, height=min(1000, int(room.depth_ft * 32 + 140)), scrolling=True)

        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Geometry score", f"{evaluation.geometry_score:.1f}/100")
        m2.metric("Open floor area", f"{evaluation.open_area_ratio:.1%}")
        m3.metric("Wardrobe front area", f"{evaluation.wardrobe_front_area_ft2:.1f} ft²")
        m4.metric("Wardrobe internal volume", f"{evaluation.wardrobe_internal_volume_ft3:.1f} ft³")
        if evaluation.circulation_connectivity is not None:
            st.write(f"Walkable connectivity at requested passage width: **{evaluation.circulation_connectivity:.1%}**")
        for warning in evaluation.warnings:
            st.warning(warning)

        st.download_button("Download bedroom layout SVG", svg.encode("utf-8"), f"{candidate.layout_id}_bedroom.svg", "image/svg+xml")

        st.subheader("5 · Promote bedroom package to whole-home optimisation")
        e1, e2 = st.columns(2)
        package_cost = e1.number_input("Bedroom package cost ₹", min_value=0.0, value=0.0, step=10_000.0)
        score_source = e2.text_input("Score source/label", "user assessment")
        s1, s2, s3, s4, s5 = st.columns(5)
        quality = s1.number_input("Quality score", min_value=0.0, max_value=100.0, value=50.0, step=5.0)
        durability = s2.number_input("Durability score", min_value=0.0, max_value=100.0, value=50.0, step=5.0)
        aesthetics = s3.number_input("Aesthetics score", min_value=0.0, max_value=100.0, value=50.0, step=5.0)
        comfort = s4.number_input("Comfort score", min_value=0.0, max_value=100.0, value=50.0, step=5.0)
        maintainability = s5.number_input("Maintainability score", min_value=0.0, max_value=100.0, value=50.0, step=5.0)
        room_id = selected_verified_room.room_id if selected_verified_room else "manual-bedroom"
        payload = {"options": [{
            "room_id": room_id,
            "option_id": f"bedroom-{candidate.layout_id}",
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
            "features": ["geometry-checked-bedroom", "wardrobe-quantity-calculated", "circulation-evaluated"],
            "feasible": evaluation.feasible,
            "score_source": score_source,
            "notes": [
                f"geometry_score={evaluation.geometry_score}",
                f"wardrobe_run_ft={evaluation.wardrobe_run_ft}",
                "User/evidence scores remain separate from geometry score.",
            ],
        }]}
        st.download_button(
            "Download optimizer-compatible bedroom package",
            json.dumps(payload, indent=2, ensure_ascii=False).encode("utf-8"),
            f"{candidate.layout_id}_whole_home_bedroom_option.json",
            "application/json",
        )
    else:
        st.error("No generated bedroom survives the current geometry/opening/clearance/passage constraints. Change explicit assumptions or furniture sizes; NitiKube will not force an invalid arrangement.")
else:
    st.info("Provide room geometry and generate candidates. No bedroom arrangement is preselected.")

st.caption("Next fidelity steps: bedside-table placement, window/radiator/electrical constraints, TV sightlines, wardrobe internal compartment optimisation, sliding-vs-hinged-door clearance, storage demand modelling, arbitrary polygon rooms and product-linked furniture dimensions.")
