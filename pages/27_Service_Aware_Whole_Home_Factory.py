from __future__ import annotations

import json

import streamlit as st

from nitikube.service_aware_factory import (
    build_service_aware_whole_home_candidates,
    service_aware_factory_audit_json,
    service_aware_factory_rows,
)
from nitikube.service_points import service_points_template_from_geometry
from nitikube.whole_home_factory import brief_template_from_geometry, room_options_json


st.set_page_config(page_title="NitiKube — Service-Aware Whole Home", page_icon="⌂", layout="wide")
st.title("Service-Aware Whole-Home Candidate Factory")
st.caption(
    "Verified geometry + explicit whole-home brief + verified service points → room candidates → candidate-specific service gates → whole-home optimization → hashed design package."
)
st.warning(
    "Service evidence is a hard gate only where a room profile contains `service_rules`. A room without `service_rules` is reported as NOT CONFIGURED, never as a fake service PASS."
)

st.subheader("1 · Authoritative inputs")
geometry_file = st.file_uploader("Verified geometry JSON", type=["json"], key="svc_home_geometry")
service_file = st.file_uploader("Verified service-point JSON", type=["json"], key="svc_home_points")
brief_file = st.file_uploader("Service-aware whole-home brief JSON", type=["json"], key="svc_home_brief")
brief_text = st.text_area("Or paste the service-aware whole-home brief", value="", height=260)

geometry_bytes = geometry_file.getvalue() if geometry_file else None
if geometry_bytes:
    try:
        base_template = json.loads(brief_template_from_geometry(geometry_bytes))
        base_template["schema"] = "nitikube.service_aware_whole_home_brief"
        base_template["schema_version"] = "0.26"
        for room_profile in base_template.get("rooms", {}).values():
            room_profile["service_rules"] = {
                "schema": "nitikube.candidate_service_rules",
                "schema_version": "0.25",
                "allow_shared_points": False,
                "distance_mode": "plan",
                "requirements": [],
            }
        template_text = json.dumps(base_template, indent=2, ensure_ascii=False)
        d1, d2 = st.columns(2)
        d1.download_button(
            "Download service-aware whole-home brief template",
            template_text.encode("utf-8"),
            "nitikube_service_aware_whole_home_brief_template.json",
            "application/json",
        )
        d2.download_button(
            "Download empty verified service-point template",
            service_points_template_from_geometry(geometry_bytes).encode("utf-8"),
            "nitikube_service_points_template.json",
            "application/json",
        )
        st.caption(
            "The generated template adds an empty `service_rules` block per room. Populate only requirements supported by product/homeowner/professional evidence; do not turn the empty block into guessed services."
        )
    except Exception as exc:
        st.error(f"Could not build room-aware templates: {exc}")

if geometry_bytes and service_file and (brief_file or brief_text.strip()) and st.button(
    "Build service-aware whole-home candidates",
    type="primary",
):
    try:
        brief_payload = brief_file.getvalue() if brief_file else brief_text.strip()
        result = build_service_aware_whole_home_candidates(
            geometry_bytes,
            brief_payload,
            service_file.getvalue(),
            geometry_artifact_name=geometry_file.name,
            service_points_artifact_name=service_file.name,
            brief_artifact_name=brief_file.name if brief_file else "pasted_service_aware_whole_home_brief.json",
        )
        st.session_state["service_aware_whole_home_result"] = result
    except Exception as exc:
        st.error(f"Service-aware whole-home factory failed: {exc}")

result = st.session_state.get("service_aware_whole_home_result")
if result:
    st.subheader("2 · Room + service audit")
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Required rooms", len(result.required_room_ids))
    m2.metric("Optimizer options", len(result.optimizer_options))
    m3.metric("Optimizer-ready", "YES" if result.optimizer_ready else "NO")
    m4.metric(
        "Service-evaluated rooms",
        sum(audit.service_status == "evaluated" for audit in result.room_service_audits),
    )
    st.dataframe(service_aware_factory_rows(result), use_container_width=True, hide_index=True)
    for diagnostic in result.diagnostics:
        st.warning(diagnostic)

    st.subheader("3 · Whole-home optimization")
    if result.optimization is None:
        st.info(
            "Optimization was not run. This occurs when no optimization block was supplied or a required room has no feasible optimizer option after geometry/service filtering."
        )
    else:
        optimization = result.optimization
        o1, o2, o3, o4 = st.columns(4)
        o1.metric("Feasible", "YES" if optimization.feasible else "NO")
        o2.metric("Selected cost", f"{optimization.selected_cost:,.2f}" if optimization.selected_cost is not None else "—")
        o3.metric("Budget remaining", f"{optimization.budget_remaining:,.2f}" if optimization.budget_remaining is not None else "—")
        o4.metric("States considered", optimization.states_considered)
        st.write(optimization.message)
        if optimization.selected:
            st.dataframe(
                [
                    {
                        "room_id": item.room_id,
                        "option_id": item.option_id,
                        "option_name": item.option_name,
                        "cost": item.cost,
                        "utility": item.utility,
                    }
                    for item in optimization.selected
                ],
                use_container_width=True,
                hide_index=True,
            )

    st.subheader("4 · Evidence hashes + outputs")
    st.write(f"**Geometry SHA-256:** `{result.geometry_sha256}`")
    st.write(f"**Service points SHA-256:** `{result.service_points_sha256}`")
    st.write(f"**Service-aware brief SHA-256:** `{result.brief_sha256}`")
    if result.option_artifact_sha256:
        st.write(f"**Generated room options SHA-256:** `{result.option_artifact_sha256}`")

    d1, d2, d3 = st.columns(3)
    d1.download_button(
        "Download service-aware factory audit",
        service_aware_factory_audit_json(result).encode("utf-8"),
        "nitikube_service_aware_whole_home_factory_audit.json",
        "application/json",
    )
    if result.optimizer_options:
        d2.download_button(
            "Download service-filtered optimizer options",
            room_options_json(result.optimizer_options, project_name=result.project_name).encode("utf-8"),
            "nitikube_service_aware_room_options.json",
            "application/json",
        )
    if result.design_package:
        d3.download_button(
            "Download service-aware hashed design package",
            json.dumps(result.design_package, indent=2, ensure_ascii=False).encode("utf-8"),
            "nitikube_service_aware_design_package.json",
            "application/json",
        )
        st.success(
            "The final design package hash now covers the verified service-point artifact and service-aware brief in addition to geometry/options. It remains compatible with the existing final-report hash verification contract."
        )

    st.subheader("5 · Decision boundary")
    st.write(
        "Candidates fail before optimization when geometry or configured required-service evidence fails. Rooms without a service rule remain explicitly `not_configured`; this workflow does not assume every room needs a service check. Straight-line service distance remains a lower bound and cannot substitute for routed discipline engineering."
    )
else:
    st.info(
        "Upload verified geometry, verified service points and a service-aware whole-home brief. The room-aware template can be generated from geometry above."
    )
