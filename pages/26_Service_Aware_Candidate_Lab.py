from __future__ import annotations

import json

import streamlit as st

from nitikube.kitchen_planner import (
    KitchenLayoutKind,
    KitchenRequirements,
    WorkCenterSpec,
    generate_kitchen_candidates,
)
from nitikube.service_aware_candidates import (
    candidate_service_rules_template,
    load_candidate_service_rules_json,
    rank_service_aware_kitchens,
    service_aware_evaluation_json,
    service_aware_rows,
)
from nitikube.service_points import load_service_points_json
from nitikube.verified_geometry import geometry_from_project_json
from nitikube.whole_home_factory import verified_room_rect


st.set_page_config(page_title="NitiKube — Service-Aware Candidates", page_icon="⇄", layout="wide")
st.title("Service-Aware Candidate Lab")
st.caption(
    "Make verified services a hard candidate-feasibility layer. This first UI workflow applies it to kitchen candidates; the deterministic core also supports bathroom, bedroom and drawing/dining candidates."
)
st.warning(
    "No kitchen/service standard is hidden here. Furniture/appliance dimensions, passage constraints, service kinds and maximum route distances are explicit scenario/evidence inputs. Service distance is still a straight-line lower bound."
)

st.subheader("1 · Verified room + service evidence")
geometry_file = st.file_uploader("Upload verified geometry JSON", type=["json"], key="svc_candidate_geometry")
service_file = st.file_uploader("Upload verified service-point JSON", type=["json"], key="svc_candidate_points")

room = None
rect = None
points = None
room_id = None
if geometry_file:
    try:
        _project, rooms, _openings, _metadata = geometry_from_project_json(geometry_file.getvalue().decode("utf-8"))
        verified_rooms = [item for item in rooms if item.verified]
        if not verified_rooms:
            st.error("Geometry contains no verified rooms.")
        else:
            labels = {f"{item.room_id} — {item.name}": item for item in verified_rooms}
            selected_label = st.selectbox("Room", list(labels), key="svc_candidate_room")
            room = labels[selected_label]
            room_id = room.room_id
            try:
                rect = verified_room_rect(room)
                st.success(f"Exact rectangular room loaded: {rect.width_ft:.2f} × {rect.depth_ft:.2f} ft.")
            except Exception as exc:
                st.error(f"Current candidate generator cannot use this verified room without approximation: {exc}")
            if service_file:
                points = load_service_points_json(service_file.getvalue(), rooms=verified_rooms)
                room_points = [point for point in points if point.room_id == room_id and point.verified]
                st.info(f"{len(room_points)} verified service points are available in the selected room.")
    except Exception as exc:
        st.error(f"Input evidence is invalid/incompatible: {exc}")

st.subheader("2 · Explicit kitchen candidate geometry")
c1, c2, c3 = st.columns(3)
with c1:
    counter_depth = st.number_input("Counter depth (ft)", min_value=0.0, value=0.0, step=0.1)
    wall_margin = st.number_input("Wall/end margin (ft)", min_value=0.0, value=0.0, step=0.1)
with c2:
    sink_width = st.number_input("Sink module width (ft)", min_value=0.0, value=0.0, step=0.1)
    sink_depth = st.number_input("Sink module depth (ft)", min_value=0.0, value=0.0, step=0.1)
    hob_width = st.number_input("Hob module width (ft)", min_value=0.0, value=0.0, step=0.1)
    hob_depth = st.number_input("Hob module depth (ft)", min_value=0.0, value=0.0, step=0.1)
with c3:
    fridge_width = st.number_input("Fridge module width (ft)", min_value=0.0, value=0.0, step=0.1)
    fridge_depth = st.number_input("Fridge module depth (ft)", min_value=0.0, value=0.0, step=0.1)
    passage_width = st.number_input("Requested passage width (ft, 0 disables)", min_value=0.0, value=0.0, step=0.1)

selected_kinds = st.multiselect(
    "Candidate families",
    options=[kind.value for kind in KitchenLayoutKind],
    default=[kind.value for kind in KitchenLayoutKind],
)

st.subheader("3 · Candidate service rules")
st.download_button(
    "Download candidate-service-rule template",
    candidate_service_rules_template().encode("utf-8"),
    "nitikube_candidate_service_rules_template.json",
    "application/json",
)
rule_file = st.file_uploader("Upload completed candidate-service-rule JSON", type=["json"], key="svc_candidate_rules")
rule_text = st.text_area("Or paste candidate-service-rule JSON", value="", height=220)

ready_dimensions = all(
    value > 0
    for value in (counter_depth, sink_width, sink_depth, hob_width, hob_depth, fridge_width, fridge_depth)
)

if rect is not None and points is not None and (rule_file or rule_text.strip()) and ready_dimensions and selected_kinds:
    if st.button("Generate + service-filter kitchen candidates", type="primary"):
        try:
            rules_payload = rule_file.getvalue() if rule_file else rule_text.strip()
            rules = load_candidate_service_rules_json(rules_payload)
            candidates = generate_kitchen_candidates(
                rect,
                counter_depth_ft=counter_depth,
                wall_margin_ft=wall_margin,
                sink=WorkCenterSpec("sink", "Sink", sink_width, sink_depth),
                hob=WorkCenterSpec("hob", "Hob", hob_width, hob_depth),
                fridge=WorkCenterSpec("fridge", "Fridge", fridge_width, fridge_depth),
                include_kinds=tuple(KitchenLayoutKind(value) for value in selected_kinds),
            )
            ranked = rank_service_aware_kitchens(
                rect,
                room_id,
                candidates,
                points,
                rules,
                requirements=KitchenRequirements(passage_width_ft=passage_width),
            )
            st.session_state["service_aware_kitchen_ranked"] = ranked
        except Exception as exc:
            st.error(f"Service-aware candidate evaluation failed: {exc}")
else:
    st.caption(
        "To run: select a supported verified room, load verified service points, provide all positive module dimensions, keep at least one candidate family, and supply service rules."
    )

ranked = st.session_state.get("service_aware_kitchen_ranked")
if ranked:
    st.subheader("4 · Combined candidate audit")
    rows = service_aware_rows(ranked)
    st.dataframe(rows, use_container_width=True, hide_index=True)
    overall = sum(item.evaluation.overall_feasible for item in ranked)
    m1, m2, m3 = st.columns(3)
    m1.metric("Candidates evaluated", len(ranked))
    m2.metric("Overall feasible", overall)
    m3.metric("Rejected by geometry or services", len(ranked) - overall)

    selected_id = st.selectbox(
        "Inspect candidate",
        [item.evaluation.candidate_id for item in ranked],
        format_func=lambda value: next(
            f"{item.evaluation.candidate_id} — {item.evaluation.candidate_name}"
            for item in ranked
            if item.evaluation.candidate_id == value
        ),
    )
    selected = next(item for item in ranked if item.evaluation.candidate_id == selected_id)
    st.write(
        {
            "geometry_feasible": selected.evaluation.geometry_feasible,
            "service_feasible": selected.evaluation.service_feasible,
            "overall_feasible": selected.evaluation.overall_feasible,
            "geometry_score": selected.evaluation.geometry_score,
            "service_total_route_ft": selected.evaluation.service_total_route_ft,
            "service_max_route_ft": selected.evaluation.service_max_route_ft,
        }
    )
    if selected.evaluation.service_assignments:
        st.dataframe(
            [assignment.__dict__ for assignment in selected.evaluation.service_assignments],
            use_container_width=True,
            hide_index=True,
        )
    for failure in selected.evaluation.geometry_failed:
        st.error(f"Geometry: {failure}")
    for failure in selected.evaluation.service_failed:
        st.error(f"Service: {failure}")
    for warning in selected.evaluation.geometry_warnings:
        st.warning(f"Geometry: {warning}")
    for warning in selected.evaluation.service_warnings:
        st.warning(f"Service: {warning}")

    st.download_button(
        "Download selected combined evaluation",
        service_aware_evaluation_json(selected.evaluation).encode("utf-8"),
        f"nitikube_{selected.evaluation.candidate_id}_service_aware_evaluation.json",
        "application/json",
    )

st.subheader("5 · Decision boundary")
st.write(
    "Service feasibility is a hard gate layered beside geometry feasibility: `overall_feasible = geometry_feasible AND service_feasible`. Service distance does not rewrite the planner's geometry score. Among candidates with equal feasibility, the ranking keeps geometry score primary and uses the shorter straight-line service distance only as a transparent tie-breaker."
)
