from __future__ import annotations

import json

import pandas as pd
import streamlit as st

from nitikube.home_optimizer import (
    RoomGeometryConstraint,
    RoomPolicy,
    ScoreWeights,
    load_room_options_json,
    optimize_budget_scenarios,
    optimize_home,
    result_rows,
)
from nitikube.verified_geometry import geometry_from_project_json


st.set_page_config(page_title="NitiKube — Whole Home Optimizer", page_icon="⌂", layout="wide")
st.title("Whole-Home Design Optimizer")
st.caption(
    "Choose one feasible design package per verified room under one home budget. Geometry, must-not-compromise rules, user locks and budget are hard constraints; weighted scores only rank combinations that survive those constraints."
)

st.warning(
    "Quality/durability/aesthetics/comfort/maintainability scores are ranking inputs, not scientific measurements unless their source is independently documented. "
    "The optimizer never uses a high score to override a failed geometry or policy constraint."
)

st.subheader("1 · Verified home geometry")
geometry_file = st.file_uploader("Upload `nitikube_verified_geometry.json`", type=["json"], key="home_geometry_json")
rooms = []
geometries = {}
room_name_lookup = {}
if geometry_file:
    try:
        project_name, rooms, openings, metadata = geometry_from_project_json(geometry_file.getvalue().decode("utf-8"))
        verified_rooms = [room for room in rooms if room.verified]
        for room in verified_rooms:
            min_x, min_y, max_x, max_y = room.bounds_ft
            geometries[room.room_id] = RoomGeometryConstraint(
                room_id=room.room_id,
                area_ft2=room.area_ft2,
                width_ft=max_x - min_x,
                height_ft=max_y - min_y,
            )
            room_name_lookup[room.room_id] = room.name
        geometry_df = pd.DataFrame(
            [
                {
                    "room_id": room.room_id,
                    "room": room.name,
                    "area_ft2": round(room.area_ft2, 2),
                    "width_ft": round(geometries[room.room_id].width_ft or 0, 3),
                    "height_ft": round(geometries[room.room_id].height_ft or 0, 3),
                    "ceiling_height_ft": room.ceiling_height_ft,
                    "source": room.source,
                }
                for room in verified_rooms
            ]
        )
        st.success(f"Loaded {len(verified_rooms)} verified room(s) from {project_name}.")
        st.dataframe(geometry_df, use_container_width=True, hide_index=True)
    except Exception as exc:
        st.error(f"Verified geometry could not be loaded: {exc}")
else:
    st.info("Upload the authoritative geometry exported by the Verified Geometry Editor. Options that require geometry must not be approved without it.")

st.subheader("2 · Candidate room design packages")
template = {
    "options": [
        {
            "room_id": "R1",
            "option_id": "R1-value",
            "name": "Example package — replace with real/user-defined package",
            "cost": 0,
            "quality": 0,
            "durability": 0,
            "aesthetics": 0,
            "comfort": 0,
            "maintainability": 0,
            "min_area_ft2": None,
            "min_width_ft": None,
            "min_height_ft": None,
            "features": [],
            "feasible": True,
            "score_source": "template_only",
            "notes": ["All zero values are placeholders, not recommendations or market prices."]
        }
    ]
}
st.download_button(
    "Download room-option JSON template",
    json.dumps(template, indent=2).encode("utf-8"),
    "nitikube_room_design_options_template.json",
    "application/json",
)
options_file = st.file_uploader("Upload room design option JSON", type=["json"], key="home_options_json")
options = []
if options_file:
    try:
        options = load_room_options_json(options_file.getvalue())
        option_df = pd.DataFrame(
            [
                {
                    "room_id": option.room_id,
                    "room": room_name_lookup.get(option.room_id, option.room_id),
                    "option_id": option.option_id,
                    "name": option.name,
                    "cost": option.cost,
                    "quality": option.quality,
                    "durability": option.durability,
                    "aesthetics": option.aesthetics,
                    "comfort": option.comfort,
                    "maintainability": option.maintainability,
                    "min_area_ft2": option.min_area_ft2,
                    "min_width_ft": option.min_width_ft,
                    "min_height_ft": option.min_height_ft,
                    "features": ", ".join(option.features),
                    "score_source": option.score_source,
                }
                for option in options
            ]
        )
        st.dataframe(option_df, use_container_width=True, hide_index=True)
    except Exception as exc:
        st.error(f"Candidate options could not be loaded: {exc}")

room_ids = [room.room_id for room in rooms if room.verified] if rooms else sorted({option.room_id for option in options})

st.subheader("3 · Must-not-compromise room policies")
st.write(
    "These are explicit user/design-brief constraints. A candidate that violates them is removed before scoring. Required features use exact tags from the option file."
)
policy_defaults = pd.DataFrame(
    [
        {
            "room_id": room_id,
            "max_cost": None,
            "min_quality": None,
            "min_durability": None,
            "min_comfort": None,
            "min_maintainability": None,
            "required_features": "",
        }
        for room_id in room_ids
    ]
)
policy_df = st.data_editor(policy_defaults, num_rows="fixed", use_container_width=True, hide_index=True, key="home_policies")
policies = {}
for _, row in policy_df.iterrows():
    room_id = str(row.get("room_id") or "").strip()
    if not room_id:
        continue

    def optional_number(value):
        return None if pd.isna(value) or value == "" else float(value)

    features = tuple(part.strip() for part in str(row.get("required_features") or "").split(",") if part.strip())
    policies[room_id] = RoomPolicy(
        room_id=room_id,
        max_cost=optional_number(row.get("max_cost")),
        min_quality=optional_number(row.get("min_quality")),
        min_durability=optional_number(row.get("min_durability")),
        min_comfort=optional_number(row.get("min_comfort")),
        min_maintainability=optional_number(row.get("min_maintainability")),
        required_features=features,
    )

st.subheader("4 · Ranking priorities and locks")
w1, w2, w3, w4, w5 = st.columns(5)
weights = ScoreWeights(
    quality=w1.number_input("Quality weight", min_value=0.0, value=0.25, step=0.05),
    durability=w2.number_input("Durability weight", min_value=0.0, value=0.25, step=0.05),
    aesthetics=w3.number_input("Aesthetics weight", min_value=0.0, value=0.15, step=0.05),
    comfort=w4.number_input("Comfort weight", min_value=0.0, value=0.15, step=0.05),
    maintainability=w5.number_input("Maintainability weight", min_value=0.0, value=0.20, step=0.05),
)

locked_choices = {}
if room_ids and options:
    with st.expander("Lock room choices before re-optimisation", expanded=False):
        for room_id in room_ids:
            candidates = [option for option in options if option.room_id == room_id]
            option_map = {"— unlocked —": None, **{f"{option.option_id} · {option.name}": option.option_id for option in candidates}}
            label = st.selectbox(
                f"{room_name_lookup.get(room_id, room_id)} ({room_id})",
                list(option_map),
                key=f"lock_{room_id}",
            )
            selected_id = option_map[label]
            if selected_id:
                locked_choices[room_id] = selected_id

st.subheader("5 · Cross-room budget optimisation")
b1, b2 = st.columns(2)
total_budget = b1.number_input("Whole-home budget ₹", min_value=1.0, value=1_000_000.0, step=50_000.0)
reserve = b2.number_input("Protected reserve ₹", min_value=0.0, value=50_000.0, step=10_000.0)

if options and room_ids and st.button("Optimize whole home", type="primary"):
    try:
        result = optimize_home(
            options,
            budget=float(total_budget),
            reserve=float(reserve),
            weights=weights,
            geometries=geometries,
            policies=policies,
            locked_choices=locked_choices,
            required_room_ids=room_ids,
        )
        st.session_state["whole_home_result"] = result
    except Exception as exc:
        st.error(f"Whole-home optimization failed: {exc}")

result = st.session_state.get("whole_home_result")
if result:
    if result.feasible:
        st.success(result.message)
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Selected design cost", f"₹{result.selected_cost:,.0f}")
        m2.metric("Protected reserve", f"₹{result.reserve:,.0f}")
        m3.metric("Budget remaining", f"₹{result.budget_remaining:,.0f}")
        m4.metric("Total utility", f"{result.total_utility:.2f}")
        selected_df = pd.DataFrame(result_rows(result))
        selected_df["room"] = selected_df["room_id"].map(room_name_lookup).fillna(selected_df["room_id"])
        st.dataframe(selected_df, use_container_width=True, hide_index=True)
        st.caption(f"Optimizer explored/pruned {result.states_considered:,} additive states. Geometry/policy failures were removed before this utility optimization.")

        package = {
            "schema": "nitikube.whole_home_selection",
            "schema_version": "0.11",
            "budget": result.budget,
            "reserve": result.reserve,
            "selected_cost": result.selected_cost,
            "budget_remaining": result.budget_remaining,
            "weights": {
                "quality": weights.quality,
                "durability": weights.durability,
                "aesthetics": weights.aesthetics,
                "comfort": weights.comfort,
                "maintainability": weights.maintainability,
            },
            "locked_choices": locked_choices,
            "selected": result_rows(result),
            "note": "Ranking scores are explicit inputs; geometry, policies and budget are hard constraints.",
        }
        st.download_button(
            "Download selected whole-home package JSON",
            json.dumps(package, indent=2, ensure_ascii=False).encode("utf-8"),
            "nitikube_whole_home_selection.json",
            "application/json",
        )
    else:
        st.error(result.message)
        st.write(f"Spendable budget after reserve: ₹{result.spendable_budget:,.0f}")

st.subheader("6 · Value / Balanced / Full-budget scenario frontier")
st.caption("Scenario spend fractions are editable budget envelopes, not market claims. Each scenario reruns the exact same hard constraints and weights.")
s1, s2, s3, s4 = st.columns(4)
value_fraction = s1.number_input("Value budget fraction", min_value=0.1, max_value=1.0, value=0.75, step=0.05)
balanced_fraction = s2.number_input("Balanced budget fraction", min_value=0.1, max_value=1.0, value=0.90, step=0.05)
premium_fraction = s3.number_input("Full-budget fraction", min_value=0.1, max_value=1.0, value=1.00, step=0.05)
reserve_fraction = s4.number_input("Reserve fraction in each", min_value=0.0, max_value=0.5, value=0.05, step=0.01)

if options and room_ids and st.button("Compare budget scenarios"):
    try:
        scenarios = optimize_budget_scenarios(
            options,
            total_budget=float(total_budget),
            scenario_fractions={
                "Value": float(value_fraction),
                "Balanced": float(balanced_fraction),
                "Full budget": float(premium_fraction),
            },
            reserve_fraction=float(reserve_fraction),
            weights=weights,
            geometries=geometries,
            policies=policies,
            locked_choices=locked_choices,
            required_room_ids=room_ids,
        )
        scenario_rows = []
        for scenario in scenarios:
            opt = scenario.optimization
            scenario_rows.append(
                {
                    "scenario": scenario.name,
                    "budget_fraction": scenario.budget_fraction,
                    "scenario_budget": opt.budget,
                    "reserve": opt.reserve,
                    "feasible": opt.feasible,
                    "selected_cost": opt.selected_cost,
                    "utility": opt.total_utility,
                    "budget_remaining": opt.budget_remaining,
                    "message": opt.message,
                }
            )
        st.dataframe(pd.DataFrame(scenario_rows), use_container_width=True, hide_index=True)
    except Exception as exc:
        st.error(f"Scenario comparison failed: {exc}")

st.caption(
    "This optimizer chooses among candidate room packages; it does not yet generate every room package automatically. "
    "The next planner layer will generate those candidates from verified geometry, room function, lifestyle, climate/material constraints and procurement evidence."
)
