import json

from nitikube.service_network import (
    NetworkEdge,
    NetworkNode,
    NetworkRoutingPolicy,
    ServiceNetwork,
    ServicePointAttachment,
    evaluate_network_routing,
    feasible_routes_for_requirement,
    load_service_network_json,
    network_routing_result_json,
    service_network_json,
    shortest_network_path,
    validate_service_network,
)
from nitikube.service_points import ServiceKind, ServicePoint, ServiceRequirement, ServiceTarget


def _network():
    return ServiceNetwork(
        nodes=(
            NetworkNode("a", 0.0, 0.0, room_id="k1"),
            NetworkNode("b", 2.0, 0.0, room_id="k1"),
            NetworkNode("c", 2.0, 3.0, room_id="k1"),
            NetworkNode("d", 5.0, 3.0, room_id="k1"),
        ),
        edges=(
            NetworkEdge("ab", "a", "b", (ServiceKind.COLD_WATER, ServiceKind.ELECTRICAL)),
            NetworkEdge("bc", "b", "c", (ServiceKind.COLD_WATER, ServiceKind.ELECTRICAL)),
            NetworkEdge("cd", "c", "d", (ServiceKind.COLD_WATER,)),
            NetworkEdge("ad-electric", "a", "d", (ServiceKind.ELECTRICAL,), explicit_length_ft=20.0),
        ),
        attachments=(ServicePointAttachment("water-1", "d"),),
    )


def test_shortest_path_follows_only_kind_compatible_verified_edges():
    path = shortest_network_path(_network(), "a", "d", kind=ServiceKind.COLD_WATER)
    assert path is not None
    assert path.edge_ids == ("ab", "bc", "cd")
    assert round(path.network_distance_ft, 6) == 8.0


def test_explicit_length_is_used_when_supplied():
    path = shortest_network_path(_network(), "a", "d", kind=ServiceKind.ELECTRICAL)
    assert path is not None
    assert path.edge_ids == ("ad-electric",)
    assert path.network_distance_ft == 20.0


def test_unverified_edge_fails_closed_by_default_but_can_be_enabled_explicitly():
    network = ServiceNetwork(
        nodes=(NetworkNode("a", 0, 0), NetworkNode("b", 1, 0)),
        edges=(NetworkEdge("ab", "a", "b", (ServiceKind.DRAIN,), verified=False),),
        attachments=(),
    )
    assert shortest_network_path(network, "a", "b", kind=ServiceKind.DRAIN) is None
    path = shortest_network_path(
        network,
        "a",
        "b",
        kind=ServiceKind.DRAIN,
        require_verified_network=False,
    )
    assert path is not None
    assert path.network_distance_ft == 1.0


def test_3d_path_skips_edges_when_height_evidence_is_missing():
    network = ServiceNetwork(
        nodes=(NetworkNode("a", 0, 0, z_ft=0), NetworkNode("b", 3, 4, z_ft=None)),
        edges=(NetworkEdge("ab", "a", "b", (ServiceKind.EXHAUST,)),),
        attachments=(),
    )
    assert shortest_network_path(network, "a", "b", kind=ServiceKind.EXHAUST, distance_mode="3d") is None
    assert shortest_network_path(network, "a", "b", kind=ServiceKind.EXHAUST, distance_mode="plan") is not None


def test_target_access_plus_network_distance_forms_total_route():
    network = _network()
    points = (ServicePoint("water-1", "k1", ServiceKind.COLD_WATER, 5.0, 3.0),)
    target = ServiceTarget("sink", "Sink", "k1", 0.5, 0.0)
    requirement = ServiceRequirement("sink-water", "sink", (ServiceKind.COLD_WATER,), max_route_ft=9.0)
    policy = NetworkRoutingPolicy(max_target_access_ft=1.0)
    routes = feasible_routes_for_requirement(points, target, requirement, network, policy)
    assert len(routes) == 1
    assert routes[0].target_access_node_id == "a"
    assert routes[0].target_access_distance_ft == 0.5
    assert routes[0].network_distance_ft == 8.0
    assert routes[0].total_route_ft == 8.5


def test_max_route_rejects_candidate_even_when_graph_path_exists():
    network = _network()
    points = (ServicePoint("water-1", "k1", ServiceKind.COLD_WATER, 5.0, 3.0),)
    target = ServiceTarget("sink", "Sink", "k1", 0.5, 0.0)
    requirement = ServiceRequirement("sink-water", "sink", (ServiceKind.COLD_WATER,), max_route_ft=8.0)
    routes = feasible_routes_for_requirement(
        points,
        target,
        requirement,
        network,
        NetworkRoutingPolicy(max_target_access_ft=1.0),
    )
    assert routes == ()


def test_same_room_access_prevents_candidate_from_jumping_to_adjacent_room_node():
    network = ServiceNetwork(
        nodes=(
            NetworkNode("k-access", 2.0, 0.0, room_id="k1"),
            NetworkNode("b-access", 0.1, 0.0, room_id="b1"),
            NetworkNode("source", 3.0, 0.0, room_id="k1"),
        ),
        edges=(
            NetworkEdge("k-route", "k-access", "source", (ServiceKind.COLD_WATER,)),
            NetworkEdge("b-route", "b-access", "source", (ServiceKind.COLD_WATER,)),
        ),
        attachments=(ServicePointAttachment("water", "source"),),
    )
    points = (ServicePoint("water", "k1", ServiceKind.COLD_WATER, 3, 0),)
    target = ServiceTarget("sink", "Sink", "k1", 0, 0)
    req = ServiceRequirement("r", "sink", (ServiceKind.COLD_WATER,))
    strict = feasible_routes_for_requirement(
        points,
        target,
        req,
        network,
        NetworkRoutingPolicy(max_target_access_ft=0.5, same_room_target_access=True),
    )
    assert strict == ()
    permissive = feasible_routes_for_requirement(
        points,
        target,
        req,
        network,
        NetworkRoutingPolicy(max_target_access_ft=0.5, same_room_target_access=False),
    )
    assert len(permissive) == 1
    assert permissive[0].target_access_node_id == "b-access"


def test_evaluator_fails_required_route_but_warns_for_optional_route():
    network = _network()
    points = (ServicePoint("water-1", "k1", ServiceKind.COLD_WATER, 5, 3),)
    target = ServiceTarget("sink", "Sink", "k1", 0.5, 0)
    required = ServiceRequirement("required", "sink", (ServiceKind.HOT_WATER,), required=True)
    optional = ServiceRequirement("optional", "sink", (ServiceKind.ELECTRICAL,), required=False)
    result = evaluate_network_routing(
        points,
        (target,),
        (required, optional),
        network,
        NetworkRoutingPolicy(max_target_access_ft=1.0),
    )
    assert not result.feasible
    assert any("required" in item for item in result.failed)
    assert any("optional" in item for item in result.warnings)


def test_exact_assignment_avoids_greedy_trap_when_points_cannot_be_shared():
    network = ServiceNetwork(
        nodes=(
            NetworkNode("t1", 0, 0, room_id="k1"),
            NetworkNode("t2", 0, 10, room_id="k1"),
            NetworkNode("p1", 1, 0, room_id="k1"),
            NetworkNode("p2", 10, 0, room_id="k1"),
        ),
        edges=(
            NetworkEdge("t1-p1", "t1", "p1", (ServiceKind.ELECTRICAL,), explicit_length_ft=1),
            NetworkEdge("t1-p2", "t1", "p2", (ServiceKind.ELECTRICAL,), explicit_length_ft=2),
            NetworkEdge("t2-p1", "t2", "p1", (ServiceKind.ELECTRICAL,), explicit_length_ft=1),
        ),
        attachments=(
            ServicePointAttachment("point-1", "p1"),
            ServicePointAttachment("point-2", "p2"),
        ),
    )
    points = (
        ServicePoint("point-1", "k1", ServiceKind.ELECTRICAL, 1, 0),
        ServicePoint("point-2", "k1", ServiceKind.ELECTRICAL, 10, 0),
    )
    targets = (
        ServiceTarget("target-1", "T1", "k1", 0, 0),
        ServiceTarget("target-2", "T2", "k1", 0, 10),
    )
    reqs = (
        ServiceRequirement("r1", "target-1", (ServiceKind.ELECTRICAL,)),
        ServiceRequirement("r2", "target-2", (ServiceKind.ELECTRICAL,)),
    )
    result = evaluate_network_routing(
        points,
        targets,
        reqs,
        network,
        NetworkRoutingPolicy(max_target_access_ft=0.01, allow_shared_points=False),
    )
    assert result.feasible
    by_req = {item.requirement_id: item.point_id for item in result.assignments}
    assert by_req == {"r1": "point-2", "r2": "point-1"}
    assert result.total_route_ft == 3.0


def test_network_json_roundtrip_and_result_export_preserve_evidence_fields():
    network = _network()
    payload = service_network_json(network)
    loaded = load_service_network_json(payload)
    assert loaded == network

    points = (ServicePoint("water-1", "k1", ServiceKind.COLD_WATER, 5, 3),)
    target = ServiceTarget("sink", "Sink", "k1", 0.5, 0)
    req = ServiceRequirement("sink-water", "sink", (ServiceKind.COLD_WATER,))
    result = evaluate_network_routing(
        points,
        (target,),
        (req,),
        loaded,
        NetworkRoutingPolicy(max_target_access_ft=1.0),
    )
    exported = json.loads(network_routing_result_json(result))
    assert exported["schema"] == "nitikube.network_routing_evaluation"
    assert exported["assignments"][0]["path_edge_ids"] == ["ab", "bc", "cd"]
    assert "verified network edges" in exported["model_note"]


def test_network_validation_rejects_unknown_edge_endpoint_and_duplicate_attachment():
    network = ServiceNetwork(
        nodes=(NetworkNode("a", 0, 0),),
        edges=(NetworkEdge("bad", "a", "missing", (ServiceKind.DATA,)),),
        attachments=(
            ServicePointAttachment("p", "a"),
            ServicePointAttachment("p", "a"),
        ),
    )
    errors = validate_service_network(network)
    assert any("unknown node" in item for item in errors)
    assert any("multiple network attachments" in item for item in errors)
