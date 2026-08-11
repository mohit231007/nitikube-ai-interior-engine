from __future__ import annotations

import streamlit as st

from nitikube.service_points import (
    assignment_rows,
    evaluate_service_routing,
    load_service_points_json,
    routing_brief_template,
    routing_result_json,
    service_point_rows,
    service_points_template_from_geometry,
)
from nitikube.service_routing_io import load_service_routing_brief
from nitikube.verified_geometry import geometry_from_project_json


st.set_page_config(page_title="NitiKube — Service Points + Routing", page_icon="⌁", layout="wide")
st.title("Verified Service Points + Routing Lab")
st.caption(
    "Bind surveyed plumbing/electrical/gas/exhaust points to actual planner targets using deterministic minimum-distance assignment and explicit routing limits."
)
st.warning(
    "Routing distance is currently a straight-line lower bound. It is not a pipe/cable/duct path, pressure-drop calculation, drainage hydraulic model, voltage-drop result, ventilation design, gas-safety check or code certificate."
)

st.subheader("1 · Verified geometry")
geometry_file = st.file_uploader(
    "Upload `nitikube_verified_geometry.json`",
    type=["json"],
    key="service_geometry",
)
geometry_bytes = geometry_file.getvalue() if geometry_file else None
rooms = None
if geometry_bytes:
    try:
        project_name, parsed_rooms, _openings, _metadata = geometry_from_project_json(geometry_bytes.decode("utf-8"))
        rooms = parsed_rooms
        st.success(f"Loaded verified geometry for {project_name}.")
        st.download_button(
            "Download service-point template",
            service_points_template_from_geometry(geometry_bytes).encode("utf-8"),
            "nitikube_service_points_template.json",
            "application/json",
        )
    except Exception as exc:
        st.error(f"Geometry is invalid/incompatible: {exc}")

st.subheader("2 · Surveyed / verified service points")
service_file = st.file_uploader(
    "Upload `nitikube.service_points` JSON",
    type=["json"],
    key="service_points_file",
)
points = None
if service_file:
    try:
        points = load_service_points_json(service_file.getvalue(), rooms=rooms)
        st.success(f"Loaded {len(points)} service points.")
        st.dataframe(service_point_rows(points), use_container_width=True, hide_index=True)
    except Exception as exc:
        st.error(f"Service-point artifact is invalid: {exc}")

st.subheader("3 · Targets + requirements")
st.download_button(
    "Download routing-brief template",
    routing_brief_template().encode("utf-8"),
    "nitikube_service_routing_brief_template.json",
    "application/json",
)
routing_file = st.file_uploader(
    "Upload `nitikube.service_routing_brief` JSON",
    type=["json"],
    key="service_routing_brief_file",
)
routing_text = st.text_area(
    "Or paste a completed routing brief",
    value="",
    height=240,
    placeholder="Define actual target coordinates, allowed service kinds, optional max-route limits and whether service points may be shared.",
)

if points is not None and (routing_file or routing_text.strip()) and st.button("Evaluate service routing", type="primary"):
    try:
        payload = routing_file.getvalue() if routing_file else routing_text.strip()
        targets, requirements, allow_shared, distance_mode = load_service_routing_brief(payload)
        result = evaluate_service_routing(
            points,
            targets,
            requirements,
            allow_shared_points=allow_shared,
            distance_mode=distance_mode,
        )
        st.session_state["service_routing_result"] = result
    except Exception as exc:
        st.error(f"Routing evaluation could not run: {exc}")

result = st.session_state.get("service_routing_result")
if result:
    st.subheader("4 · Routing audit")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Feasible", "YES" if result.feasible else "NO")
    c2.metric("Assignments", len(result.assignments))
    c3.metric("Total straight-line route", f"{result.total_route_ft:.2f} ft" if result.total_route_ft is not None else "—")
    c4.metric("Longest assigned link", f"{result.max_route_ft:.2f} ft" if result.max_route_ft is not None else "—")

    if result.assignments:
        st.dataframe(assignment_rows(result), use_container_width=True, hide_index=True)
    for item in result.failed:
        st.error(item)
    for item in result.warnings:
        st.warning(item)

    st.download_button(
        "Download routing evaluation JSON",
        routing_result_json(result).encode("utf-8"),
        "nitikube_service_routing_evaluation.json",
        "application/json",
    )

    if result.feasible:
        st.success(
            "All required service requirements found an admissible assignment under the supplied room/kind/distance/sharing constraints."
        )
    else:
        st.info(
            "A failed result is intentional: required missing/too-distant/height-unknown/non-uniquely-assignable services are not silently accepted."
        )
else:
    st.info(
        "Load verified geometry and surveyed service points, then supply target/requirement coordinates. Kitchen/bathroom/bedroom/layout adapters are available in the deterministic core for planner integration."
    )

st.subheader("5 · Model boundary")
st.write(
    "The service engine answers a narrow question: which verified service point can satisfy each explicit target requirement, and what is the geometric lower-bound distance? Real routing must still account for walls, shafts, bends, slopes, diameters, load, pressure, voltage drop, ventilation losses, gas rules, waterproofing and local code/professional requirements."
)
