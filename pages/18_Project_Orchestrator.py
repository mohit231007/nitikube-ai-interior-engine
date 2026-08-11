from __future__ import annotations

import json

import pandas as pd
import streamlit as st

from nitikube.home_optimizer import RoomGeometryConstraint, RoomPolicy, ScoreWeights, optimize_home, result_rows
from nitikube.project_orchestrator import (
    artifact_rows,
    build_design_package,
    coverage_rows,
    merge_option_payloads,
    room_coverage,
    validate_option_room_links,
    verified_geometry_inventory,
    verify_design_package_hash,
)
from nitikube.verified_geometry import geometry_from_project_json


st.set_page_config(page_title="NitiKube — Project Orchestrator", page_icon="⌂", layout="wide")
st.title("NitiKube Project Orchestrator")
st.caption(
    "Assemble verified geometry plus multiple room-planner option artifacts into one cross-room budget optimization and reproducible design-package manifest. Input files are hashed so the final package can state exactly which geometry/options produced the selection."
)
st.info(
    "A reproducibility hash proves that the package manifest has not changed; it does not prove that a source measurement, price, material fact or subjective score is true. Those remain governed by their own verification/evidence states."
)

st.subheader("1 · Authoritative verified geometry")
geometry_file = st.file_uploader("Upload `nitikube_verified_geometry.json`", type=["json"], key="orchestrator_geometry")
geometry_ref = None
project_name = None
verified_rooms = ()
geometries = {}
room_name_lookup = {}
geometry_text = None
if geometry_file:
    try:
        geometry_text = geometry_file.getvalue().decode("utf-8")
        geometry_ref, project_name, verified_rooms = verified_geometry_inventory(geometry_text)
        _, rooms, _, _ = geometry_from_project_json(geometry_text)
        for room in rooms:
            if not room.verified:
                continue
            min_x, min_y, max_x, max_y = room.bounds_ft
            geometries[room.room_id] = RoomGeometryConstraint(
                room_id=room.room_id,
                area_ft2=room.area_ft2,
                width_ft=max_x - min_x,
                height_ft=max_y - min_y,
            )
            room_name_lookup[room.room_id] = room.name
        st.success(f"Loaded {len(verified_rooms)} verified room(s) from project `{project_name}`. Geometry SHA-256: `{geometry_ref.sha256[:16]}…`")
    except Exception as exc:
        st.error(f"Verified geometry could not be loaded: {exc}")

st.subheader("2 · Merge room-planner option artifacts")
option_files = st.file_uploader(
    "Upload one or more optimizer-compatible room-option JSON files",
    type=["json"],
    accept_multiple_files=True,
    key="orchestrator_options",
)
bundle = None
coverage = ()
if option_files:
    try:
        bundle = merge_option_payloads([(file.name, file.getvalue()) for file in option_files])
        if verified_rooms:
            validate_option_room_links(bundle.options, [room_id for room_id, _ in verified_rooms])
            coverage = room_coverage(verified_rooms, bundle.options)
            st.dataframe(pd.DataFrame(coverage_rows(coverage)), use_container_width=True, hide_index=True)
        st.write(f"Merged **{len(bundle.options)}** globally unique option(s) from **{len(bundle.artifacts)}** artifact(s).")
        if geometry_ref is not None:
            st.dataframe(pd.DataFrame(artifact_rows(geometry_ref, bundle)), use_container_width=True, hide_index=True)
    except Exception as exc:
        st.error(f"Room option artifacts could not be merged/linked: {exc}")
        bundle = None

if bundle is not None:
    with st.expander("Merged option inventory", expanded=False):
        st.dataframe(pd.DataFrame([{
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
            "score_source": option.score_source,
        } for option in bundle.options]), use_container_width=True, hide_index=True)

st.subheader("3 · Define scope and hard room policies")
required_room_ids = []
policies = {}
if verified_rooms:
    room_label_to_id = {f"{name} · {room_id}": room_id for room_id, name in verified_rooms}
    covered_ids = {item.room_id for item in coverage if item.status == "covered"} if coverage else set()
    default_labels = [label for label, room_id in room_label_to_id.items() if room_id in covered_ids]
    selected_labels = st.multiselect(
        "Rooms included in this optimization run",
        list(room_label_to_id),
        default=default_labels,
        help="Rooms with no candidate options cannot be optimized. Leaving a room out means this is a partial-home package, not a complete-home package.",
    )
    required_room_ids = [room_label_to_id[label] for label in selected_labels]
    if len(required_room_ids) < len(verified_rooms):
        st.warning("This run does not include every verified room. The exported package will truthfully list only the selected required_room_ids.")

    policy_df = pd.DataFrame([{
        "room_id": room_id,
        "room": room_name_lookup.get(room_id, room_id),
        "max_cost": None,
        "min_quality": None,
        "min_durability": None,
        "min_comfort": None,
        "min_maintainability": None,
        "required_features": "",
    } for room_id in required_room_ids])
    policy_df = st.data_editor(policy_df, use_container_width=True, hide_index=True, num_rows="fixed", key="orchestrator_policies")

    def optional_number(value):
        return None if pd.isna(value) or value == "" else float(value)

    for _, row in policy_df.iterrows():
        room_id = str(row["room_id"])
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
else:
    st.caption("Upload verified geometry to define authoritative room scope.")

st.subheader("4 · Budget, priorities and homeowner locks")
b1, b2 = st.columns(2)
budget = b1.number_input("Project budget ₹", min_value=1.0, value=1_500_000.0, step=50_000.0)
reserve = b2.number_input("Protected reserve ₹", min_value=0.0, value=100_000.0, step=10_000.0)

w1, w2, w3, w4, w5 = st.columns(5)
weights = ScoreWeights(
    quality=w1.number_input("Quality weight", min_value=0.0, value=0.25, step=0.05, key="or_q"),
    durability=w2.number_input("Durability weight", min_value=0.0, value=0.25, step=0.05, key="or_d"),
    aesthetics=w3.number_input("Aesthetics weight", min_value=0.0, value=0.15, step=0.05, key="or_a"),
    comfort=w4.number_input("Comfort weight", min_value=0.0, value=0.15, step=0.05, key="or_c"),
    maintainability=w5.number_input("Maintainability weight", min_value=0.0, value=0.20, step=0.05, key="or_m"),
)

locked_choices = {}
if bundle is not None and required_room_ids:
    with st.expander("Lock selected room packages", expanded=False):
        for room_id in required_room_ids:
            candidates = [option for option in bundle.options if option.room_id == room_id]
            choices = {"— unlocked —": None, **{f"{option.option_id} · {option.name}": option.option_id for option in candidates}}
            label = st.selectbox(room_name_lookup.get(room_id, room_id), list(choices), key=f"or_lock_{room_id}")
            if choices[label]:
                locked_choices[room_id] = choices[label]

st.subheader("5 · Optimize and package")
professional_flags_text = st.text_area(
    "Professional-verification flags carried into package (one per line)",
    value="",
    help="Use this for project-specific scopes that still require licensed/regulated verification. The orchestrator records the flags; it does not clear them.",
)
professional_flags = tuple(line.strip() for line in professional_flags_text.splitlines() if line.strip())

if geometry_ref and bundle and required_room_ids and st.button("Optimize project and build package", type="primary"):
    try:
        optimization = optimize_home(
            bundle.options,
            budget=float(budget),
            reserve=float(reserve),
            weights=weights,
            geometries=geometries,
            policies=policies,
            locked_choices=locked_choices,
            required_room_ids=required_room_ids,
        )
        if not optimization.feasible:
            st.error(optimization.message)
            st.session_state.pop("orchestrated_package", None)
        else:
            package = build_design_package(
                project_name=project_name or "NitiKube Project",
                geometry_artifact=geometry_ref,
                option_bundle=bundle,
                optimization=optimization,
                weights=weights,
                required_room_ids=required_room_ids,
                locked_choices=locked_choices,
                professional_verification_flags=professional_flags,
            )
            st.session_state["orchestrated_optimization"] = optimization
            st.session_state["orchestrated_package"] = package
    except Exception as exc:
        st.error(f"Project optimization/package build failed: {exc}")

optimization = st.session_state.get("orchestrated_optimization")
package = st.session_state.get("orchestrated_package")
if optimization and package:
    st.success("Reproducible design package built from the uploaded geometry and option artifacts.")
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Selected cost", f"₹{optimization.selected_cost:,.0f}")
    m2.metric("Budget remaining", f"₹{optimization.budget_remaining:,.0f}")
    m3.metric("Total utility", f"{optimization.total_utility:.2f}")
    m4.metric("Rooms selected", len(optimization.selected))
    st.dataframe(pd.DataFrame(result_rows(optimization)), use_container_width=True, hide_index=True)
    st.write(f"**Package ID (SHA-256):** `{package['package_id']}`")
    st.write(f"Hash self-check: **{'PASS' if verify_design_package_hash(package) else 'FAIL'}**")
    st.download_button(
        "Download NitiKube design package JSON",
        json.dumps(package, indent=2, ensure_ascii=False).encode("utf-8"),
        "nitikube_design_package.json",
        "application/json",
    )
    selected_df = pd.DataFrame(package["selected_options"])
    st.download_button(
        "Download selected room packages CSV",
        selected_df.to_csv(index=False).encode("utf-8"),
        "nitikube_selected_room_packages.csv",
        "text/csv",
    )

st.caption(
    "The orchestrator is intentionally artifact-driven. A kitchen/bedroom/bathroom planner can change without changing the package contract, as long as it emits deterministic optimizer-compatible options with truthful evidence/source labels."
)
