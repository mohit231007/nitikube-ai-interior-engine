from __future__ import annotations

import pandas as pd
import streamlit as st

from nitikube.service_network import (
    NetworkRoutingPolicy,
    evaluate_network_routing,
    load_service_network_json,
    network_routing_result_json,
    service_network_template,
)
from nitikube.service_points import load_service_points_json
from nitikube.service_routing_io import load_service_routing_brief
from nitikube.verified_geometry import geometry_from_project_json


st.set_page_config(page_title="NitiKube — Verified Service Network", page_icon="⌁", layout="wide")
st.title("Verified Wall / Shaft / Riser Service Network")
st.caption(
    "Replace straight-line service assumptions with shortest paths constrained to explicit surveyed routing corridors such as wall channels, shafts, risers and sleeves."
)
st.warning(
    "This is a routing-geometry model, not discipline engineering. A graph route does not prove pipe diameter, drainage fall, pressure, cable sizing, voltage drop, duct loss, gas safety or code compliance."
)

st.subheader("1 · Authoritative project geometry")
geometry_file = st.file_uploader(
    "Upload `nitikube_verified_geometry.json`",
    type=["json"],
    key="network_geometry",
)
rooms = None
if geometry_file:
    try:
        project_name, parsed_rooms, _openings, _metadata = geometry_from_project_json(
            geometry_file.getvalue().decode("utf-8")
        )
        rooms = parsed_rooms
        st.success(f"Loaded geometry for {project_name} · {sum(room.verified for room in rooms)} verified rooms")
    except Exception as exc:
        st.error(f"Geometry is invalid/incompatible: {exc}")

st.subheader("2 · Verified service points")
service_file = st.file_uploader(
    "Upload `nitikube.service_points` JSON",
    type=["json"],
    key="network_service_points",
)
points = None
if service_file:
    try:
        points = load_service_points_json(service_file.getvalue(), rooms=rooms)
        st.success(f"Loaded {len(points)} verified/surveyed service points.")
        st.dataframe(
            pd.DataFrame(
                [
                    {
                        "point_id": point.point_id,
                        "room_id": point.room_id,
                        "kind": point.kind.value,
                        "x_ft": point.x_ft,
                        "y_ft": point.y_ft,
                        "z_ft": point.z_ft,
                        "verified": point.verified,
                        "source": point.source,
                    }
                    for point in points
                ]
            ),
            use_container_width=True,
            hide_index=True,
        )
    except Exception as exc:
        st.error(f"Service points are invalid/incompatible: {exc}")

st.subheader("3 · Verified routing graph")
st.download_button(
    "Download empty routing-network template",
    service_network_template().encode("utf-8"),
    "nitikube_service_network_template.json",
    "application/json",
)
network_file = st.file_uploader(
    "Upload `nitikube.service_network` JSON",
    type=["json"],
    key="network_graph",
)
network = None
if network_file:
    try:
        network = load_service_network_json(
            network_file.getvalue(),
            rooms=rooms,
            service_points=points,
        )
        st.success(
            f"Loaded {len(network.nodes)} route nodes, {len(network.edges)} verified corridor edges and {len(network.attachments)} service-point attachments."
        )
        n1, n2 = st.columns(2)
        with n1:
            st.dataframe(
                pd.DataFrame(
                    [
                        {
                            "node_id": node.node_id,
                            "room_id": node.room_id,
                            "route_class": node.route_class,
                            "x_ft": node.x_ft,
                            "y_ft": node.y_ft,
                            "z_ft": node.z_ft,
                            "target_access": node.can_accept_targets,
                            "verified": node.verified,
                        }
                        for node in network.nodes
                    ]
                ),
                use_container_width=True,
                hide_index=True,
            )
        with n2:
            st.dataframe(
                pd.DataFrame(
                    [
                        {
                            "edge_id": edge.edge_id,
                            "from": edge.start_node_id,
                            "to": edge.end_node_id,
                            "route_class": edge.route_class,
                            "kinds": ", ".join(kind.value for kind in edge.allowed_kinds),
                            "bidirectional": edge.bidirectional,
                            "length_override_ft": edge.explicit_length_ft,
                            "verified": edge.verified,
                        }
                        for edge in network.edges
                    ]
                ),
                use_container_width=True,
                hide_index=True,
            )
    except Exception as exc:
        st.error(f"Routing graph is invalid/incompatible: {exc}")

st.subheader("4 · Targets + service requirements")
routing_file = st.file_uploader(
    "Upload the existing `nitikube.service_routing_brief` JSON",
    type=["json"],
    key="network_routing_brief",
)
max_access = st.number_input(
    "Maximum target → verified network access-node connector (ft)",
    min_value=0.0,
    value=2.0,
    step=0.25,
    help="Explicitly limits the short final connector from the candidate target to the surveyed routing graph. The graph itself supplies the rest of the path.",
)
use_brief_sharing = st.checkbox("Use allow_shared_points from routing brief", value=True)
require_verified = st.checkbox("Require verified network nodes/edges/attachments", value=True)
same_room_access = st.checkbox("Target may enter network only through a node in the same room", value=True)

if points is not None and network is not None and routing_file and st.button("Evaluate constrained network routing", type="primary"):
    try:
        targets, requirements, allow_shared, distance_mode = load_service_routing_brief(routing_file.getvalue())
        policy = NetworkRoutingPolicy(
            max_target_access_ft=float(max_access),
            distance_mode=distance_mode,
            allow_shared_points=allow_shared if use_brief_sharing else False,
            require_verified_network=require_verified,
            same_room_target_access=same_room_access,
        )
        result = evaluate_network_routing(points, targets, requirements, network, policy)
        st.session_state["network_routing_result"] = result
    except Exception as exc:
        st.error(f"Network routing could not run: {exc}")

result = st.session_state.get("network_routing_result")
if result:
    st.subheader("5 · Network routing audit")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Feasible", "YES" if result.feasible else "NO")
    c2.metric("Assignments", len(result.assignments))
    c3.metric("Total routed geometry", f"{result.total_route_ft:.2f} ft" if result.total_route_ft is not None else "—")
    c4.metric("Longest routed requirement", f"{result.max_route_ft:.2f} ft" if result.max_route_ft is not None else "—")

    if result.assignments:
        st.dataframe(
            pd.DataFrame(
                [
                    {
                        "requirement_id": item.requirement_id,
                        "target_id": item.target_id,
                        "service_point": item.point_id,
                        "kind": item.kind,
                        "access_node": item.target_access_node_id,
                        "target_access_ft": round(item.target_access_distance_ft, 3),
                        "network_ft": round(item.network_distance_ft, 3),
                        "total_ft": round(item.total_route_ft, 3),
                        "path_nodes": " → ".join(item.path_node_ids),
                        "path_edges": " → ".join(item.path_edge_ids),
                    }
                    for item in result.assignments
                ]
            ),
            use_container_width=True,
            hide_index=True,
        )
    for failure in result.failed:
        st.error(failure)
    for warning in result.warnings:
        st.warning(warning)

    st.download_button(
        "Download network routing evaluation",
        network_routing_result_json(result).encode("utf-8"),
        "nitikube_network_routing_evaluation.json",
        "application/json",
    )

st.subheader("6 · Evidence boundary")
st.write(
    "Every traversed graph edge is an explicit data object. NitiKube does not automatically draw a route through a wall, column, slab, shaft or opening simply because two coordinates are near each other. The only unconstrained segment is the explicitly capped target-to-access-node connector. This removes the previous straight-line-across-the-building assumption while retaining a fail-closed evidence contract."
)
st.info(
    "Next integration step: use this graph result inside candidate feasibility and the whole-home factory so a service-aware kitchen/bathroom option is judged by routed network distance rather than Euclidean lower-bound distance."
)
