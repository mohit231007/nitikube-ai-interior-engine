from __future__ import annotations

import json

import streamlit as st

from nitikube.network_aware_factory import (
    build_network_aware_whole_home_candidates,
    network_aware_factory_audit_json,
    network_aware_factory_rows,
)
from nitikube.service_network import service_network_template
from nitikube.service_points import service_points_template_from_geometry
from nitikube.whole_home_factory import brief_template_from_geometry, room_options_json


st.set_page_config(page_title="NitiKube — Network-Aware Whole Home", page_icon="⌂", layout="wide")
st.title("Verified-Network Whole-Home Candidate Factory")
st.caption(
    "Verified geometry + explicit room brief + verified service points + verified routing graph → candidate-specific routed service gates → whole-home optimization → hashed design package."
)
st.warning(
    "This workflow routes only through explicit graph edges. It does not infer a penetrable wall/shaft/sleeve from proximity, and it still does not perform hydraulic, electrical, gas or ventilation engineering."
)

st.subheader("1 · Authoritative inputs")
geometry_file = st.file_uploader("Verified geometry JSON", type=["json"], key="net_home_geometry")
service_file = st.file_uploader("Verified service-point JSON", type=["json"], key="net_home_points")
network_file = st.file_uploader("Verified service-network JSON", type=["json"], key="net_home_network")
brief_file = st.file_uploader("Network-aware whole-home brief JSON", type=["json"], key="net_home_brief")
brief_text = st.text_area("Or paste the network-aware whole-home brief", value="", height=280)

geometry_bytes = geometry_file.getvalue() if geometry_file else None
if geometry_bytes:
    try:
        base_template = json.loads(brief_template_from_geometry(geometry_bytes))
        # v0.28 intentionally extends the v0.26 service-aware brief contract so
        # existing room planner/service-rule tooling remains compatible.
        base_template["schema"] = "nitikube.service_aware_whole_home_brief"
        base_template["schema_version"] = "0.28"
        base_template["network_routing"] = {
            "max_target_access_ft": None,
            "require_verified_network": True,
            "same_room_target_access": True,
        }
        for room_profile in base_template.get("rooms", {}).values():
            room_profile["service_rules"] = {
                "schema": "nitikube.candidate_service_rules",
                "schema_version": "0.25",
                "allow_shared_points": False,
                "distance_mode": "plan",
                "requirements": [],
            }
        template_text = json.dumps(base_template, indent=2, ensure_ascii=False)
        d1, d2, d3 = st.columns(3)
        d1.download_button(
            "Download network-aware whole-home brief template",
            template_text.encode("utf-8"),
            "nitikube_network_aware_whole_home_brief_template.json",
            "application/json",
        )
        d2.download_button(
            "Download empty verified service-point template",
            service_points_template_from_geometry(geometry_bytes).encode("utf-8"),
            "nitikube_service_points_template.json",
            "application/json",
        )
        d3.download_button(
            "Download empty verified service-network template",
            service_network_template().encode("utf-8"),
            "nitikube_service_network_template.json",
            "application/json",
        )
        st.caption(
            "`max_target_access_ft` is deliberately left null. Supply an explicit project or room value; configured service rooms fail closed when that access policy is missing."
        )
    except Exception as exc:
        st.error(f"Could not build room-aware templates: {exc}")

if geometry_bytes and service_file and network_file and (brief_file or brief_text.strip()) and st.button(
    "Build verified-network whole-home candidates",
    type="primary",
):
    try:
        brief_payload = brief_file.getvalue() if brief_file else brief_text.strip()
        result = build_network_aware_whole_home_candidates(
            geometry_bytes,
            brief_payload,
            service_file.getvalue(),
            network_file.getvalue(),
            geometry_artifact_name=geometry_file.name,
            service_points_artifact_name=service_file.name,
            service_network_artifact_name=network_file.name,
            brief_artifact_name=brief_file.name if brief_file else "pasted_network_aware_whole_home_brief.json",
        )
        st.session_state["network_aware_whole_home_result"] = result
    except Exception as exc:
        st.error(f"Verified-network whole-home factory failed: {exc}")

result = st.session_state.get("network_aware_whole_home_result")
if result:
    st.subheader("2 · Room + routed-service audit")
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Required rooms", len(result.required_room_ids))
    m2.metric("Optimizer options", len(result.optimizer_options))
    m3.metric("Optimizer-ready", "YES" if result.optimizer_ready else "NO")
    m4.metric(
        "Network-evaluated rooms",
        sum(audit.service_status == "network_evaluated" for audit in result.room_service_audits),
    )
    st.dataframe(network_aware_factory_rows(result), use_container_width=True, hide_index=True)
    for diagnostic in result.diagnostics:
        st.warning(diagnostic)

    st.subheader("3 · Whole-home optimization")
    if result.optimization is None:
        st.info(
            "Optimization was not run. This occurs when no optimization block was supplied or a required room has no feasible optimizer option after geometry + verified-network service filtering."
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
    st.write(f"**Service network SHA-256:** `{result.service_network_sha256}`")
    st.write(f"**Network-aware brief SHA-256:** `{result.brief_sha256}`")
    if result.option_artifact_sha256:
        st.write(f"**Generated room options SHA-256:** `{result.option_artifact_sha256}`")

    d1, d2, d3 = st.columns(3)
    d1.download_button(
        "Download network-aware factory audit",
        network_aware_factory_audit_json(result).encode("utf-8"),
        "nitikube_network_aware_whole_home_factory_audit.json",
        "application/json",
    )
    if result.optimizer_options:
        d2.download_button(
            "Download verified-network optimizer options",
            room_options_json(result.optimizer_options, project_name=result.project_name).encode("utf-8"),
            "nitikube_network_aware_room_options.json",
            "application/json",
        )
    if result.design_package:
        d3.download_button(
            "Download verified-network hashed design package",
            json.dumps(result.design_package, indent=2, ensure_ascii=False).encode("utf-8"),
            "nitikube_network_aware_design_package.json",
            "application/json",
        )
        st.success(
            "The package hash covers geometry, generated options, verified service points, the verified service-network artifact and the network-aware brief."
        )

    st.subheader("5 · Decision boundary")
    st.write(
        "For rooms with service rules, candidate feasibility now requires both room geometry and a verified graph route. A high geometry score cannot compensate for a missing route. Rooms without service rules stay `not_configured`, not PASS. Routed distance is still only geometric path length; discipline-specific pressure/slope/load/voltage/duct/gas checks remain separate."
    )
else:
    st.info(
        "Upload verified geometry, service points, a verified service-network artifact and the completed room-aware brief. The three starter templates can be generated from geometry above."
    )
