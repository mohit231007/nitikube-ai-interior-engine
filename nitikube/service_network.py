from __future__ import annotations

from dataclasses import asdict, dataclass
import heapq
import json
import math
from typing import Any, Mapping, Sequence

from .service_points import (
    ServiceKind,
    ServicePoint,
    ServiceRequirement,
    ServiceTarget,
    point_in_room,
    validate_requirement,
    validate_service_point,
    validate_service_target,
)
from .verified_geometry import VerifiedRoom


_EPS = 1e-9


@dataclass(frozen=True)
class NetworkNode:
    node_id: str
    x_ft: float
    y_ft: float
    z_ft: float | None = None
    room_id: str | None = None
    route_class: str = "verified_route_node"
    can_accept_targets: bool = True
    verified: bool = True
    source: str = "manual_survey"
    note: str = ""


@dataclass(frozen=True)
class NetworkEdge:
    edge_id: str
    start_node_id: str
    end_node_id: str
    allowed_kinds: tuple[ServiceKind, ...]
    bidirectional: bool = True
    explicit_length_ft: float | None = None
    route_class: str = "wall_channel"
    verified: bool = True
    source: str = "manual_survey"
    note: str = ""


@dataclass(frozen=True)
class ServicePointAttachment:
    point_id: str
    node_id: str
    verified: bool = True
    source: str = "manual_survey"
    note: str = ""


@dataclass(frozen=True)
class ServiceNetwork:
    nodes: tuple[NetworkNode, ...]
    edges: tuple[NetworkEdge, ...]
    attachments: tuple[ServicePointAttachment, ...]


@dataclass(frozen=True)
class NetworkRoutingPolicy:
    max_target_access_ft: float
    distance_mode: str = "plan"
    allow_shared_points: bool = False
    require_verified_network: bool = True
    same_room_target_access: bool = True


@dataclass(frozen=True)
class NetworkPath:
    start_node_id: str
    end_node_id: str
    node_ids: tuple[str, ...]
    edge_ids: tuple[str, ...]
    network_distance_ft: float


@dataclass(frozen=True)
class NetworkServiceAssignment:
    requirement_id: str
    target_id: str
    point_id: str
    kind: str
    target_access_node_id: str
    target_access_distance_ft: float
    network_distance_ft: float
    total_route_ft: float
    path_node_ids: tuple[str, ...]
    path_edge_ids: tuple[str, ...]


@dataclass(frozen=True)
class NetworkRoutingResult:
    feasible: bool
    assignments: tuple[NetworkServiceAssignment, ...]
    failed: tuple[str, ...]
    warnings: tuple[str, ...]
    total_route_ft: float | None
    max_route_ft: float | None
    distance_mode: str
    allow_shared_points: bool
    model_note: str = (
        "Routes follow only explicitly verified network edges plus a short target-to-access-node connector. "
        "They are not hydraulic, electrical, gas, ventilation or code-compliance calculations."
    )


def _finite(value: float, label: str) -> float:
    value = float(value)
    if not math.isfinite(value):
        raise ValueError(f"{label} must be finite")
    return value


def _coord_distance(
    a: tuple[float, float, float | None],
    b: tuple[float, float, float | None],
    *,
    mode: str,
) -> float | None:
    if mode == "plan":
        return math.hypot(a[0] - b[0], a[1] - b[1])
    if mode != "3d":
        raise ValueError("distance_mode must be 'plan' or '3d'")
    if a[2] is None or b[2] is None:
        return None
    return math.dist((a[0], a[1], a[2]), (b[0], b[1], b[2]))


def validate_network_node(node: NetworkNode) -> None:
    if not node.node_id.strip():
        raise ValueError("network node_id is required")
    _finite(node.x_ft, "node x_ft")
    _finite(node.y_ft, "node y_ft")
    if node.z_ft is not None:
        _finite(node.z_ft, "node z_ft")
    if not node.route_class.strip():
        raise ValueError(f"{node.node_id}: route_class is required")
    if not node.source.strip():
        raise ValueError(f"{node.node_id}: source is required")


def validate_network_edge(edge: NetworkEdge) -> None:
    if not edge.edge_id.strip() or not edge.start_node_id.strip() or not edge.end_node_id.strip():
        raise ValueError("network edge_id/start_node_id/end_node_id are required")
    if edge.start_node_id == edge.end_node_id:
        raise ValueError(f"{edge.edge_id}: self-loop edges are not supported")
    if not edge.allowed_kinds:
        raise ValueError(f"{edge.edge_id}: allowed_kinds cannot be empty")
    if any(not isinstance(kind, ServiceKind) for kind in edge.allowed_kinds):
        raise ValueError(f"{edge.edge_id}: allowed_kinds must contain ServiceKind values")
    if edge.explicit_length_ft is not None:
        value = _finite(edge.explicit_length_ft, "explicit_length_ft")
        if value <= 0:
            raise ValueError(f"{edge.edge_id}: explicit_length_ft must be positive")
    if not edge.route_class.strip() or not edge.source.strip():
        raise ValueError(f"{edge.edge_id}: route_class and source are required")


def validate_attachment(attachment: ServicePointAttachment) -> None:
    if not attachment.point_id.strip() or not attachment.node_id.strip():
        raise ValueError("service point attachment point_id/node_id are required")
    if not attachment.source.strip():
        raise ValueError("service point attachment source is required")


def validate_service_network(
    network: ServiceNetwork,
    *,
    rooms: Sequence[VerifiedRoom] | None = None,
    service_points: Sequence[ServicePoint] | None = None,
) -> list[str]:
    errors: list[str] = []
    node_map: dict[str, NetworkNode] = {}
    edge_ids: set[str] = set()
    attachment_points: set[str] = set()

    verified_rooms = {room.room_id: room for room in (rooms or ()) if room.verified}
    point_ids = {point.point_id for point in (service_points or ())}

    for node in network.nodes:
        try:
            validate_network_node(node)
        except ValueError as exc:
            errors.append(str(exc))
            continue
        if node.node_id in node_map:
            errors.append(f"duplicate network node_id: {node.node_id}")
        node_map[node.node_id] = node
        if rooms is not None and node.room_id is not None:
            room = verified_rooms.get(node.room_id)
            if room is None:
                errors.append(f"network node {node.node_id} references unknown/unverified room {node.room_id}")
            elif not point_in_room((node.x_ft, node.y_ft), room):
                errors.append(f"network node {node.node_id} lies outside verified room {node.room_id}")

    for edge in network.edges:
        try:
            validate_network_edge(edge)
        except ValueError as exc:
            errors.append(str(exc))
            continue
        if edge.edge_id in edge_ids:
            errors.append(f"duplicate network edge_id: {edge.edge_id}")
        edge_ids.add(edge.edge_id)
        if edge.start_node_id not in node_map or edge.end_node_id not in node_map:
            errors.append(f"network edge {edge.edge_id} references an unknown node")

    for attachment in network.attachments:
        try:
            validate_attachment(attachment)
        except ValueError as exc:
            errors.append(str(exc))
            continue
        if attachment.point_id in attachment_points:
            errors.append(f"service point {attachment.point_id} has multiple network attachments")
        attachment_points.add(attachment.point_id)
        if attachment.node_id not in node_map:
            errors.append(f"attachment for {attachment.point_id} references unknown node {attachment.node_id}")
        if service_points is not None and attachment.point_id not in point_ids:
            errors.append(f"attachment references unknown service point {attachment.point_id}")

    return errors


def _node_from_dict(data: Mapping[str, Any]) -> NetworkNode:
    required = ("node_id", "x_ft", "y_ft")
    missing = [key for key in required if data.get(key) in {None, ""}]
    if missing:
        raise ValueError(f"missing network-node fields: {missing}")
    node = NetworkNode(
        node_id=str(data["node_id"]),
        x_ft=float(data["x_ft"]),
        y_ft=float(data["y_ft"]),
        z_ft=None if data.get("z_ft") in {None, ""} else float(data["z_ft"]),
        room_id=None if data.get("room_id") in {None, ""} else str(data["room_id"]),
        route_class=str(data.get("route_class") or "verified_route_node"),
        can_accept_targets=bool(data.get("can_accept_targets", True)),
        verified=bool(data.get("verified", True)),
        source=str(data.get("source") or "manual_survey"),
        note=str(data.get("note") or ""),
    )
    validate_network_node(node)
    return node


def _edge_from_dict(data: Mapping[str, Any]) -> NetworkEdge:
    required = ("edge_id", "start_node_id", "end_node_id", "allowed_kinds")
    missing = [
        key
        for key in required
        if key not in data or data.get(key) is None or data.get(key) == ""
    ]
    if missing:
        raise ValueError(f"missing network-edge fields: {missing}")
    raw_kinds = data["allowed_kinds"]
    if not isinstance(raw_kinds, list):
        raise ValueError("network edge allowed_kinds must be a list")
    edge = NetworkEdge(
        edge_id=str(data["edge_id"]),
        start_node_id=str(data["start_node_id"]),
        end_node_id=str(data["end_node_id"]),
        allowed_kinds=tuple(ServiceKind(str(kind)) for kind in raw_kinds),
        bidirectional=bool(data.get("bidirectional", True)),
        explicit_length_ft=None if data.get("explicit_length_ft") in {None, ""} else float(data["explicit_length_ft"]),
        route_class=str(data.get("route_class") or "wall_channel"),
        verified=bool(data.get("verified", True)),
        source=str(data.get("source") or "manual_survey"),
        note=str(data.get("note") or ""),
    )
    validate_network_edge(edge)
    return edge


def _attachment_from_dict(data: Mapping[str, Any]) -> ServicePointAttachment:
    attachment = ServicePointAttachment(
        point_id=str(data.get("point_id") or ""),
        node_id=str(data.get("node_id") or ""),
        verified=bool(data.get("verified", True)),
        source=str(data.get("source") or "manual_survey"),
        note=str(data.get("note") or ""),
    )
    validate_attachment(attachment)
    return attachment


def load_service_network_json(
    payload: str | bytes,
    *,
    rooms: Sequence[VerifiedRoom] | None = None,
    service_points: Sequence[ServicePoint] | None = None,
) -> ServiceNetwork:
    text = payload.decode("utf-8") if isinstance(payload, bytes) else payload
    data = json.loads(text)
    if not isinstance(data, dict):
        raise ValueError("service network JSON must be an object")
    if data.get("schema") not in {None, "nitikube.service_network"}:
        raise ValueError("unsupported service network schema")
    network = ServiceNetwork(
        nodes=tuple(_node_from_dict(row) for row in data.get("nodes", [])),
        edges=tuple(_edge_from_dict(row) for row in data.get("edges", [])),
        attachments=tuple(_attachment_from_dict(row) for row in data.get("attachments", [])),
    )
    errors = validate_service_network(network, rooms=rooms, service_points=service_points)
    if errors:
        raise ValueError("invalid service network: " + "; ".join(errors))
    return network


def service_network_json(network: ServiceNetwork, *, indent: int = 2) -> str:
    return json.dumps(
        {
            "schema": "nitikube.service_network",
            "schema_version": "0.27",
            "nodes": [asdict(node) for node in network.nodes],
            "edges": [
                {
                    **asdict(edge),
                    "allowed_kinds": [kind.value for kind in edge.allowed_kinds],
                }
                for edge in network.edges
            ],
            "attachments": [asdict(item) for item in network.attachments],
            "model_note": (
                "Edges represent explicit surveyed/verified feasible routing corridors such as wall channels, shafts, risers or sleeves. "
                "Do not draw an edge through a wall/column/void unless that path is actually verified as usable."
            ),
        },
        indent=indent,
        ensure_ascii=False,
    )


def service_network_template(*, indent: int = 2) -> str:
    return json.dumps(
        {
            "schema": "nitikube.service_network",
            "schema_version": "0.27",
            "nodes": [],
            "edges": [],
            "attachments": [],
            "template_note": (
                "Populate only surveyed/verified route nodes and edges. Attach each verified service point to exactly one network node. "
                "Use room_id for room-local access nodes and omit room_id for shared shafts/risers if appropriate."
            ),
        },
        indent=indent,
        ensure_ascii=False,
    )


def _edge_length(edge: NetworkEdge, nodes: Mapping[str, NetworkNode], *, distance_mode: str) -> float | None:
    if edge.explicit_length_ft is not None:
        return edge.explicit_length_ft
    start = nodes[edge.start_node_id]
    end = nodes[edge.end_node_id]
    return _coord_distance(
        (start.x_ft, start.y_ft, start.z_ft),
        (end.x_ft, end.y_ft, end.z_ft),
        mode=distance_mode,
    )


def shortest_network_path(
    network: ServiceNetwork,
    start_node_id: str,
    end_node_id: str,
    *,
    kind: ServiceKind,
    distance_mode: str = "plan",
    require_verified_network: bool = True,
) -> NetworkPath | None:
    node_map = {node.node_id: node for node in network.nodes}
    if start_node_id not in node_map or end_node_id not in node_map:
        raise ValueError("start/end node must exist in the network")
    if distance_mode not in {"plan", "3d"}:
        raise ValueError("distance_mode must be 'plan' or '3d'")
    if require_verified_network and (
        not node_map[start_node_id].verified or not node_map[end_node_id].verified
    ):
        return None
    if start_node_id == end_node_id:
        return NetworkPath(start_node_id, end_node_id, (start_node_id,), (), 0.0)

    adjacency: dict[str, list[tuple[str, str, float]]] = {node_id: [] for node_id in node_map}
    for edge in network.edges:
        if kind not in edge.allowed_kinds:
            continue
        if require_verified_network and not edge.verified:
            continue
        if require_verified_network and (
            not node_map[edge.start_node_id].verified or not node_map[edge.end_node_id].verified
        ):
            continue
        length = _edge_length(edge, node_map, distance_mode=distance_mode)
        if length is None:
            continue
        adjacency[edge.start_node_id].append((edge.end_node_id, edge.edge_id, length))
        if edge.bidirectional:
            adjacency[edge.end_node_id].append((edge.start_node_id, edge.edge_id, length))

    queue: list[tuple[float, str, tuple[str, ...], tuple[str, ...]]] = [(0.0, start_node_id, (start_node_id,), ())]
    best: dict[str, float] = {start_node_id: 0.0}
    while queue:
        distance, node_id, path_nodes, path_edges = heapq.heappop(queue)
        if distance > best.get(node_id, math.inf) + _EPS:
            continue
        if node_id == end_node_id:
            return NetworkPath(start_node_id, end_node_id, path_nodes, path_edges, distance)
        for next_id, edge_id, length in adjacency.get(node_id, ()):
            new_distance = distance + length
            if new_distance + _EPS < best.get(next_id, math.inf):
                best[next_id] = new_distance
                heapq.heappush(
                    queue,
                    (new_distance, next_id, path_nodes + (next_id,), path_edges + (edge_id,)),
                )
    return None


def _target_access_candidates(
    target: ServiceTarget,
    network: ServiceNetwork,
    policy: NetworkRoutingPolicy,
) -> list[tuple[NetworkNode, float]]:
    validate_service_target(target)
    if policy.max_target_access_ft < 0 or not math.isfinite(policy.max_target_access_ft):
        raise ValueError("max_target_access_ft must be finite and non-negative")
    candidates: list[tuple[NetworkNode, float]] = []
    for node in network.nodes:
        if not node.can_accept_targets:
            continue
        if policy.require_verified_network and not node.verified:
            continue
        if policy.same_room_target_access and node.room_id != target.room_id:
            continue
        distance = _coord_distance(
            (target.x_ft, target.y_ft, target.z_ft),
            (node.x_ft, node.y_ft, node.z_ft),
            mode=policy.distance_mode,
        )
        if distance is not None and distance <= policy.max_target_access_ft + _EPS:
            candidates.append((node, distance))
    return sorted(candidates, key=lambda item: (item[1], item[0].node_id))


def _attachment_map(network: ServiceNetwork, *, require_verified: bool) -> dict[str, ServicePointAttachment]:
    return {
        item.point_id: item
        for item in network.attachments
        if item.verified or not require_verified
    }


def feasible_routes_for_requirement(
    service_points: Sequence[ServicePoint],
    target: ServiceTarget,
    requirement: ServiceRequirement,
    network: ServiceNetwork,
    policy: NetworkRoutingPolicy,
) -> tuple[NetworkServiceAssignment, ...]:
    validate_service_target(target)
    validate_requirement(requirement)
    if requirement.target_id != target.target_id:
        raise ValueError("requirement target_id does not match supplied target")
    attachments = _attachment_map(network, require_verified=policy.require_verified_network)
    access_nodes = _target_access_candidates(target, network, policy)
    if not access_nodes:
        return ()

    node_map = {node.node_id: node for node in network.nodes}
    routes: list[NetworkServiceAssignment] = []
    for point in service_points:
        validate_service_point(point)
        if policy.require_verified_network and not point.verified:
            continue
        if point.kind not in requirement.allowed_kinds:
            continue
        attachment = attachments.get(point.point_id)
        if attachment is None or attachment.node_id not in node_map:
            continue
        best_for_point: NetworkServiceAssignment | None = None
        for access_node, access_distance in access_nodes:
            path = shortest_network_path(
                network,
                access_node.node_id,
                attachment.node_id,
                kind=point.kind,
                distance_mode=policy.distance_mode,
                require_verified_network=policy.require_verified_network,
            )
            if path is None:
                continue
            total = access_distance + path.network_distance_ft
            if requirement.max_route_ft is not None and total > requirement.max_route_ft + _EPS:
                continue
            assignment = NetworkServiceAssignment(
                requirement_id=requirement.requirement_id,
                target_id=target.target_id,
                point_id=point.point_id,
                kind=point.kind.value,
                target_access_node_id=access_node.node_id,
                target_access_distance_ft=access_distance,
                network_distance_ft=path.network_distance_ft,
                total_route_ft=total,
                path_node_ids=path.node_ids,
                path_edge_ids=path.edge_ids,
            )
            if best_for_point is None or (
                assignment.total_route_ft,
                assignment.target_access_node_id,
                assignment.point_id,
            ) < (
                best_for_point.total_route_ft,
                best_for_point.target_access_node_id,
                best_for_point.point_id,
            ):
                best_for_point = assignment
        if best_for_point is not None:
            routes.append(best_for_point)
    return tuple(sorted(routes, key=lambda item: (item.total_route_ft, item.point_id)))


def evaluate_network_routing(
    service_points: Sequence[ServicePoint],
    targets: Sequence[ServiceTarget],
    requirements: Sequence[ServiceRequirement],
    network: ServiceNetwork,
    policy: NetworkRoutingPolicy,
) -> NetworkRoutingResult:
    if policy.distance_mode not in {"plan", "3d"}:
        raise ValueError("distance_mode must be 'plan' or '3d'")
    if policy.max_target_access_ft < 0 or not math.isfinite(policy.max_target_access_ft):
        raise ValueError("max_target_access_ft must be finite and non-negative")
    network_errors = validate_service_network(network, service_points=service_points)
    if network_errors:
        raise ValueError("invalid service network: " + "; ".join(network_errors))

    target_map: dict[str, ServiceTarget] = {}
    for target in targets:
        validate_service_target(target)
        if target.target_id in target_map:
            raise ValueError(f"duplicate service target_id: {target.target_id}")
        target_map[target.target_id] = target

    requirement_ids: set[str] = set()
    required_routes: list[tuple[ServiceRequirement, tuple[NetworkServiceAssignment, ...]]] = []
    optional_assignments: list[NetworkServiceAssignment] = []
    failed: list[str] = []
    warnings: list[str] = []

    for requirement in requirements:
        validate_requirement(requirement)
        if requirement.requirement_id in requirement_ids:
            raise ValueError(f"duplicate requirement_id: {requirement.requirement_id}")
        requirement_ids.add(requirement.requirement_id)
        target = target_map.get(requirement.target_id)
        if target is None:
            message = f"requirement {requirement.requirement_id} references missing target {requirement.target_id}"
            (failed if requirement.required else warnings).append(message)
            continue
        routes = feasible_routes_for_requirement(service_points, target, requirement, network, policy)
        if not routes:
            message = f"no verified network route for requirement {requirement.requirement_id}"
            (failed if requirement.required else warnings).append(message)
            continue
        if requirement.required:
            required_routes.append((requirement, routes))
        else:
            optional_assignments.append(routes[0])

    if failed:
        return NetworkRoutingResult(
            False,
            (),
            tuple(failed),
            tuple(warnings),
            None,
            None,
            policy.distance_mode,
            policy.allow_shared_points,
        )

    best_required: tuple[NetworkServiceAssignment, ...] | None = None
    best_distance = math.inf

    def search(index: int, used_points: set[str], chosen: tuple[NetworkServiceAssignment, ...], total: float) -> None:
        nonlocal best_required, best_distance
        if total >= best_distance - _EPS:
            return
        if index == len(required_routes):
            best_required = chosen
            best_distance = total
            return
        _requirement, routes = required_routes[index]
        for route in routes:
            if not policy.allow_shared_points and route.point_id in used_points:
                continue
            next_used = used_points if policy.allow_shared_points else used_points | {route.point_id}
            search(index + 1, next_used, chosen + (route,), total + route.total_route_ft)

    search(0, set(), (), 0.0)
    if best_required is None and required_routes:
        return NetworkRoutingResult(
            False,
            (),
            ("required network routes exist individually but cannot be assigned under service-point sharing constraints",),
            tuple(warnings),
            None,
            None,
            policy.distance_mode,
            policy.allow_shared_points,
        )

    assignments = list(best_required or ())
    used = {item.point_id for item in assignments}
    for item in optional_assignments:
        if policy.allow_shared_points or item.point_id not in used:
            assignments.append(item)
            used.add(item.point_id)
        else:
            warnings.append(f"optional requirement {item.requirement_id} skipped because its best service point is already used")

    assignments.sort(key=lambda item: item.requirement_id)
    total_route = sum(item.total_route_ft for item in assignments) if assignments else 0.0
    max_route = max((item.total_route_ft for item in assignments), default=0.0)
    return NetworkRoutingResult(
        True,
        tuple(assignments),
        (),
        tuple(warnings),
        total_route,
        max_route,
        policy.distance_mode,
        policy.allow_shared_points,
    )


def network_routing_result_json(result: NetworkRoutingResult, *, indent: int = 2) -> str:
    return json.dumps(
        {
            "schema": "nitikube.network_routing_evaluation",
            "schema_version": "0.27",
            "feasible": result.feasible,
            "assignments": [asdict(item) for item in result.assignments],
            "failed": list(result.failed),
            "warnings": list(result.warnings),
            "total_route_ft": result.total_route_ft,
            "max_route_ft": result.max_route_ft,
            "distance_mode": result.distance_mode,
            "allow_shared_points": result.allow_shared_points,
            "model_note": result.model_note,
        },
        indent=indent,
        ensure_ascii=False,
    )
