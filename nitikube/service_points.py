from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
import json
import math
from typing import Any, Iterable, Mapping, Sequence

from .bathroom_planner import BathroomCandidate
from .bedroom_planner import BedroomCandidate
from .kitchen_planner import KitchenCandidate
from .room_layout import LayoutCandidate
from .verified_geometry import VerifiedRoom, geometry_from_project_json


class ServiceKind(str, Enum):
    COLD_WATER = "cold_water"
    HOT_WATER = "hot_water"
    DRAIN = "drain"
    ELECTRICAL = "electrical"
    GAS = "gas"
    EXHAUST = "exhaust"
    DATA = "data"
    HVAC_CONDENSATE = "hvac_condensate"
    OTHER = "other"


@dataclass(frozen=True)
class ServicePoint:
    point_id: str
    room_id: str
    kind: ServiceKind
    x_ft: float
    y_ft: float
    z_ft: float | None = None
    verified: bool = True
    source: str = "manual_survey"
    note: str = ""


@dataclass(frozen=True)
class ServiceTarget:
    target_id: str
    label: str
    room_id: str
    x_ft: float
    y_ft: float
    z_ft: float | None = None


@dataclass(frozen=True)
class ServiceRequirement:
    requirement_id: str
    target_id: str
    allowed_kinds: tuple[ServiceKind, ...]
    max_route_ft: float | None = None
    required: bool = True


@dataclass(frozen=True)
class ServiceAssignment:
    requirement_id: str
    target_id: str
    point_id: str
    kind: str
    distance_ft: float


@dataclass(frozen=True)
class ServiceRoutingResult:
    feasible: bool
    assignments: tuple[ServiceAssignment, ...]
    failed: tuple[str, ...]
    warnings: tuple[str, ...]
    total_route_ft: float | None
    max_route_ft: float | None
    distance_mode: str
    allow_shared_points: bool


_EPS = 1e-9


def _finite(value: float, label: str) -> float:
    value = float(value)
    if not math.isfinite(value):
        raise ValueError(f"{label} must be finite")
    return value


def validate_service_point(point: ServicePoint) -> None:
    if not point.point_id.strip() or not point.room_id.strip():
        raise ValueError("service point_id and room_id are required")
    if not isinstance(point.kind, ServiceKind):
        raise ValueError("service point kind must be a ServiceKind")
    _finite(point.x_ft, "x_ft")
    _finite(point.y_ft, "y_ft")
    if point.z_ft is not None:
        _finite(point.z_ft, "z_ft")
    if not point.source.strip():
        raise ValueError("service point source is required")


def validate_service_target(target: ServiceTarget) -> None:
    if not target.target_id.strip() or not target.label.strip() or not target.room_id.strip():
        raise ValueError("target_id, label and room_id are required")
    _finite(target.x_ft, "target x_ft")
    _finite(target.y_ft, "target y_ft")
    if target.z_ft is not None:
        _finite(target.z_ft, "target z_ft")


def validate_requirement(requirement: ServiceRequirement) -> None:
    if not requirement.requirement_id.strip() or not requirement.target_id.strip():
        raise ValueError("requirement_id and target_id are required")
    if not requirement.allowed_kinds:
        raise ValueError(f"{requirement.requirement_id}: at least one allowed service kind is required")
    if requirement.max_route_ft is not None:
        value = _finite(requirement.max_route_ft, "max_route_ft")
        if value < 0:
            raise ValueError("max_route_ft cannot be negative")


def _point_on_segment(point: tuple[float, float], a: tuple[float, float], b: tuple[float, float], tolerance: float = 1e-7) -> bool:
    px, py = point
    ax, ay = a
    bx, by = b
    cross = (bx - ax) * (py - ay) - (by - ay) * (px - ax)
    if abs(cross) > tolerance:
        return False
    return (
        min(ax, bx) - tolerance <= px <= max(ax, bx) + tolerance
        and min(ay, by) - tolerance <= py <= max(ay, by) + tolerance
    )


def point_in_room(point: tuple[float, float], room: VerifiedRoom, *, include_boundary: bool = True) -> bool:
    """Deterministic point-in-polygon test for verified simple room polygons."""
    x, y = point
    vertices = room.polygon_ft
    if include_boundary:
        for index, a in enumerate(vertices):
            b = vertices[(index + 1) % len(vertices)]
            if _point_on_segment(point, a, b):
                return True
    inside = False
    j = len(vertices) - 1
    for i in range(len(vertices)):
        xi, yi = vertices[i]
        xj, yj = vertices[j]
        intersects = ((yi > y) != (yj > y)) and (
            x < (xj - xi) * (y - yi) / ((yj - yi) or _EPS) + xi
        )
        if intersects:
            inside = not inside
        j = i
    return inside


def validate_service_points(
    points: Sequence[ServicePoint],
    rooms: Sequence[VerifiedRoom] | None = None,
    *,
    verified_rooms_only: bool = True,
) -> list[str]:
    errors: list[str] = []
    seen: set[str] = set()
    room_map = {
        room.room_id: room
        for room in (rooms or ())
        if room.verified or not verified_rooms_only
    }
    for point in points:
        if point.point_id in seen:
            errors.append(f"duplicate service point_id: {point.point_id}")
        seen.add(point.point_id)
        try:
            validate_service_point(point)
        except ValueError as exc:
            errors.append(str(exc))
            continue
        if rooms is not None:
            room = room_map.get(point.room_id)
            if room is None:
                errors.append(f"service point {point.point_id} references unknown/unverified room {point.room_id}")
            elif not point_in_room((point.x_ft, point.y_ft), room):
                errors.append(f"service point {point.point_id} lies outside verified room {point.room_id}")
    return errors


def service_point_from_dict(data: Mapping[str, Any]) -> ServicePoint:
    required = ("point_id", "room_id", "kind", "x_ft", "y_ft")
    missing = [field for field in required if data.get(field) in {None, ""}]
    if missing:
        raise ValueError(f"missing service-point fields: {missing}")
    point = ServicePoint(
        point_id=str(data["point_id"]),
        room_id=str(data["room_id"]),
        kind=ServiceKind(str(data["kind"])),
        x_ft=float(data["x_ft"]),
        y_ft=float(data["y_ft"]),
        z_ft=None if data.get("z_ft") in {None, ""} else float(data["z_ft"]),
        verified=bool(data.get("verified", True)),
        source=str(data.get("source") or "manual_survey"),
        note=str(data.get("note") or ""),
    )
    validate_service_point(point)
    return point


def load_service_points_json(
    payload: str | bytes,
    *,
    rooms: Sequence[VerifiedRoom] | None = None,
) -> tuple[ServicePoint, ...]:
    text = payload.decode("utf-8") if isinstance(payload, bytes) else payload
    data = json.loads(text)
    if isinstance(data, dict):
        if data.get("schema") not in {None, "nitikube.service_points"}:
            raise ValueError("unsupported service-point schema")
        rows = data.get("points")
    else:
        rows = data
    if not isinstance(rows, list):
        raise ValueError("service-point JSON must be a list or {'points': [...]} object")
    points = tuple(service_point_from_dict(row) for row in rows)
    errors = validate_service_points(points, rooms)
    if errors:
        raise ValueError("invalid service points: " + "; ".join(errors))
    return points


def service_points_json(points: Sequence[ServicePoint], *, indent: int = 2) -> str:
    return json.dumps(
        {
            "schema": "nitikube.service_points",
            "schema_version": "0.24",
            "points": [
                {
                    **asdict(point),
                    "kind": point.kind.value,
                }
                for point in points
            ],
        },
        indent=indent,
        ensure_ascii=False,
    )


def service_points_template_from_geometry(geometry_payload: str | bytes, *, indent: int = 2) -> str:
    text = geometry_payload.decode("utf-8") if isinstance(geometry_payload, bytes) else geometry_payload
    project_name, rooms, _openings, _metadata = geometry_from_project_json(text)
    payload = {
        "schema": "nitikube.service_points",
        "schema_version": "0.24",
        "project_name_note": project_name,
        "verified_rooms": [
            {"room_id": room.room_id, "room_name": room.name, "area_ft2": room.area_ft2}
            for room in rooms
            if room.verified
        ],
        "points": [],
        "template_note": (
            "Add only surveyed/verified service coordinates. No plumbing/electrical/gas/exhaust point is invented from room type. "
            "Coordinates use the same floor-plan feet coordinate system as nitikube.verified_geometry."
        ),
    }
    return json.dumps(payload, indent=indent, ensure_ascii=False)


def target_from_dict(data: Mapping[str, Any]) -> ServiceTarget:
    required = ("target_id", "label", "room_id", "x_ft", "y_ft")
    missing = [field for field in required if data.get(field) in {None, ""}]
    if missing:
        raise ValueError(f"missing service-target fields: {missing}")
    target = ServiceTarget(
        target_id=str(data["target_id"]),
        label=str(data["label"]),
        room_id=str(data["room_id"]),
        x_ft=float(data["x_ft"]),
        y_ft=float(data["y_ft"]),
        z_ft=None if data.get("z_ft") in {None, ""} else float(data["z_ft"]),
    )
    validate_service_target(target)
    return target


def requirement_from_dict(data: Mapping[str, Any]) -> ServiceRequirement:
    if data.get("allowed_kinds") in {None, ""}:
        raise ValueError("allowed_kinds is required")
    allowed_raw = data["allowed_kinds"]
    if not isinstance(allowed_raw, list):
        raise ValueError("allowed_kinds must be a list")
    requirement = ServiceRequirement(
        requirement_id=str(data.get("requirement_id") or ""),
        target_id=str(data.get("target_id") or ""),
        allowed_kinds=tuple(ServiceKind(str(item)) for item in allowed_raw),
        max_route_ft=None if data.get("max_route_ft") in {None, ""} else float(data["max_route_ft"]),
        required=bool(data.get("required", True)),
    )
    validate_requirement(requirement)
    return requirement


def load_service_routing_brief(payload: str | bytes) -> tuple[tuple[ServiceTarget, ...], tuple[ServiceRequirement, ...], bool, str]:
    text = payload.decode("utf-8") if isinstance(payload, bytes) else payload
    data = json.loads(text)
    if not isinstance(data, dict):
        raise ValueError("service routing brief must be a JSON object")
    if data.get("schema") not in {None, "nitikube.service_routing_brief"}:
        raise ValueError("unsupported service routing brief schema")
    targets = tuple(target_from_dict(row) for row in data.get("targets", []))
    requirements = tuple(requirement_from_dict(row) for row in data.get("requirements", []))
    allow_shared = bool(data.get("allow_shared_points", False))
    distance_mode = str(data.get("distance_mode") or "plan")
    if distance_mode not in {"plan", "3d"}:
        raise ValueError("distance_mode must be 'plan' or '3d'")
    target_ids = [target.target_id for target in targets]
    if len(target_ids) != len(set(target_ids)):
        raise ValueError("service target_id values must be unique")
    requirement_ids = [item.requirement_id for item in requirements]
    if len(requirement_ids) != len(set(requirement_ids)):
        raise ValueError("service requirement_id values must be unique")
    known_targets = set(target_ids)
    missing_targets = sorted({item.target_id for item in requirements} - known_targets)
    if missing_targets:
        raise ValueError("service requirements reference unknown target IDs: " + ", ".join(missing_targets))
    return targets, requirements, allow_shared, distance_mode


def routing_brief_template(*, indent: int = 2) -> str:
    payload = {
        "schema": "nitikube.service_routing_brief",
        "schema_version": "0.24",
        "distance_mode": "plan",
        "allow_shared_points": False,
        "targets": [
            {
                "target_id": "example-target",
                "label": "Replace with actual planner target",
                "room_id": None,
                "x_ft": None,
                "y_ft": None,
                "z_ft": None,
            }
        ],
        "requirements": [
            {
                "requirement_id": "example-requirement",
                "target_id": "example-target",
                "allowed_kinds": ["electrical"],
                "max_route_ft": None,
                "required": True,
            }
        ],
        "template_note": (
            "Straight-line distance is a routing lower bound, not a pipe/cable path, pressure-drop calculation, voltage-drop calculation, "
            "vent sizing or code-compliance certificate. Populate targets/limits explicitly."
        ),
    }
    return json.dumps(payload, indent=indent, ensure_ascii=False)


def _distance(target: ServiceTarget, point: ServicePoint, mode: str) -> float | None:
    if mode == "plan":
        return math.hypot(target.x_ft - point.x_ft, target.y_ft - point.y_ft)
    if mode == "3d":
        if target.z_ft is None or point.z_ft is None:
            return None
        return math.sqrt(
            (target.x_ft - point.x_ft) ** 2
            + (target.y_ft - point.y_ft) ** 2
            + (target.z_ft - point.z_ft) ** 2
        )
    raise ValueError("unsupported distance mode")


def _candidate_links(
    requirement: ServiceRequirement,
    target: ServiceTarget,
    points: Sequence[ServicePoint],
    mode: str,
) -> tuple[list[tuple[ServicePoint, float]], bool]:
    allowed = set(requirement.allowed_kinds)
    candidates: list[tuple[ServicePoint, float]] = []
    unknown_height = False
    for point in points:
        if not point.verified or point.room_id != target.room_id or point.kind not in allowed:
            continue
        distance = _distance(target, point, mode)
        if distance is None:
            unknown_height = True
            continue
        if requirement.max_route_ft is not None and distance > requirement.max_route_ft + 1e-9:
            continue
        candidates.append((point, distance))
    candidates.sort(key=lambda item: (item[1], item[0].point_id))
    return candidates, unknown_height


def _assign_unique(
    requirements: Sequence[ServiceRequirement],
    candidate_map: Mapping[str, Sequence[tuple[ServicePoint, float]]],
) -> tuple[dict[str, tuple[ServicePoint, float]] | None, float | None]:
    ordered = sorted(requirements, key=lambda item: (len(candidate_map[item.requirement_id]), item.requirement_id))
    best_assignment: dict[str, tuple[ServicePoint, float]] | None = None
    best_total = math.inf

    def search(index: int, used: set[str], total: float, chosen: dict[str, tuple[ServicePoint, float]]) -> None:
        nonlocal best_assignment, best_total
        if total >= best_total - 1e-12:
            return
        if index == len(ordered):
            best_assignment = dict(chosen)
            best_total = total
            return
        requirement = ordered[index]
        for point, distance in candidate_map[requirement.requirement_id]:
            if point.point_id in used:
                continue
            used.add(point.point_id)
            chosen[requirement.requirement_id] = (point, distance)
            search(index + 1, used, total + distance, chosen)
            chosen.pop(requirement.requirement_id, None)
            used.remove(point.point_id)

    search(0, set(), 0.0, {})
    if best_assignment is None:
        return None, None
    return best_assignment, best_total


def evaluate_service_routing(
    points: Sequence[ServicePoint],
    targets: Sequence[ServiceTarget],
    requirements: Sequence[ServiceRequirement],
    *,
    allow_shared_points: bool = False,
    distance_mode: str = "plan",
) -> ServiceRoutingResult:
    if distance_mode not in {"plan", "3d"}:
        raise ValueError("distance_mode must be 'plan' or '3d'")
    for point in points:
        validate_service_point(point)
    target_map: dict[str, ServiceTarget] = {}
    for target in targets:
        validate_service_target(target)
        if target.target_id in target_map:
            raise ValueError(f"duplicate target_id: {target.target_id}")
        target_map[target.target_id] = target
    seen_requirements: set[str] = set()
    for requirement in requirements:
        validate_requirement(requirement)
        if requirement.requirement_id in seen_requirements:
            raise ValueError(f"duplicate requirement_id: {requirement.requirement_id}")
        seen_requirements.add(requirement.requirement_id)
        if requirement.target_id not in target_map:
            raise ValueError(f"requirement {requirement.requirement_id} references unknown target {requirement.target_id}")

    candidate_map: dict[str, list[tuple[ServicePoint, float]]] = {}
    failed: list[str] = []
    warnings: list[str] = []
    required_with_candidates: list[ServiceRequirement] = []
    optional_with_candidates: list[ServiceRequirement] = []

    for requirement in requirements:
        target = target_map[requirement.target_id]
        candidates, unknown_height = _candidate_links(requirement, target, points, distance_mode)
        candidate_map[requirement.requirement_id] = candidates
        if not candidates:
            if distance_mode == "3d" and unknown_height:
                reason = f"{requirement.requirement_id}:3d_height_unknown"
            else:
                reason = f"{requirement.requirement_id}:no_matching_service_within_constraints"
            if requirement.required:
                failed.append(reason)
            else:
                warnings.append(reason)
        elif requirement.required:
            required_with_candidates.append(requirement)
        else:
            optional_with_candidates.append(requirement)

    assignments: dict[str, tuple[ServicePoint, float]] = {}
    if not failed:
        if allow_shared_points:
            for requirement in required_with_candidates:
                assignments[requirement.requirement_id] = candidate_map[requirement.requirement_id][0]
            for requirement in optional_with_candidates:
                assignments[requirement.requirement_id] = candidate_map[requirement.requirement_id][0]
        else:
            unique, _total = _assign_unique(required_with_candidates, candidate_map)
            if unique is None:
                failed.append("required_service_points_cannot_be_assigned_uniquely")
            else:
                assignments.update(unique)
                used = {point.point_id for point, _distance_ft in assignments.values()}
                for requirement in optional_with_candidates:
                    match = next(
                        (
                            item
                            for item in candidate_map[requirement.requirement_id]
                            if item[0].point_id not in used
                        ),
                        None,
                    )
                    if match is None:
                        warnings.append(f"{requirement.requirement_id}:optional_unique_service_unavailable")
                    else:
                        assignments[requirement.requirement_id] = match
                        used.add(match[0].point_id)

    rows: list[ServiceAssignment] = []
    for requirement in requirements:
        match = assignments.get(requirement.requirement_id)
        if match is None:
            continue
        point, distance = match
        rows.append(
            ServiceAssignment(
                requirement_id=requirement.requirement_id,
                target_id=requirement.target_id,
                point_id=point.point_id,
                kind=point.kind.value,
                distance_ft=round(distance, 4),
            )
        )
    distances = [item.distance_ft for item in rows]
    return ServiceRoutingResult(
        feasible=not failed,
        assignments=tuple(rows),
        failed=tuple(failed),
        warnings=tuple(warnings),
        total_route_ft=round(sum(distances), 4) if distances else (0.0 if not failed else None),
        max_route_ft=round(max(distances), 4) if distances else (0.0 if not failed else None),
        distance_mode=distance_mode,
        allow_shared_points=allow_shared_points,
    )


def kitchen_service_targets(candidate: KitchenCandidate, room_id: str) -> tuple[ServiceTarget, ...]:
    targets: list[ServiceTarget] = []
    for center in candidate.work_centers:
        x, y = center.center
        targets.append(ServiceTarget(center.spec.center_id, center.spec.label, room_id, x, y))
    return tuple(targets)


def bathroom_service_targets(candidate: BathroomCandidate, room_id: str) -> tuple[ServiceTarget, ...]:
    sx, sy = candidate.shower.rect.center
    wx, wy = candidate.wc.rect.center
    bx, by = candidate.basin.rect.center
    return (
        ServiceTarget("shower", "Shower", room_id, sx, sy),
        ServiceTarget(candidate.wc.spec.fixture_id, candidate.wc.spec.label, room_id, wx, wy),
        ServiceTarget(candidate.basin.spec.fixture_id, candidate.basin.spec.label, room_id, bx, by),
    )


def bedroom_service_targets(candidate: BedroomCandidate, room_id: str) -> tuple[ServiceTarget, ...]:
    targets = [
        ServiceTarget(candidate.bed.item_id, candidate.bed.label, room_id, *candidate.bed.rect.center),
        ServiceTarget(candidate.wardrobe.item_id, candidate.wardrobe.label, room_id, *candidate.wardrobe.rect.center),
    ]
    if candidate.desk is not None:
        targets.append(ServiceTarget(candidate.desk.item_id, candidate.desk.label, room_id, *candidate.desk.rect.center))
    return tuple(targets)


def layout_service_targets(candidate: LayoutCandidate, room_id: str) -> tuple[ServiceTarget, ...]:
    return tuple(
        ServiceTarget(placement.spec.item_id, placement.spec.label, room_id, *placement.rect.center)
        for placement in candidate.placements
    )


def assignment_rows(result: ServiceRoutingResult) -> list[dict[str, Any]]:
    return [asdict(item) for item in result.assignments]


def service_point_rows(points: Sequence[ServicePoint]) -> list[dict[str, Any]]:
    return [
        {
            "point_id": point.point_id,
            "room_id": point.room_id,
            "kind": point.kind.value,
            "x_ft": point.x_ft,
            "y_ft": point.y_ft,
            "z_ft": point.z_ft,
            "verified": point.verified,
            "source": point.source,
            "note": point.note,
        }
        for point in points
    ]


def routing_result_json(result: ServiceRoutingResult, *, indent: int = 2) -> str:
    return json.dumps(
        {
            "schema": "nitikube.service_routing_evaluation",
            "schema_version": "0.24",
            "feasible": result.feasible,
            "distance_mode": result.distance_mode,
            "allow_shared_points": result.allow_shared_points,
            "total_route_ft": result.total_route_ft,
            "max_route_ft": result.max_route_ft,
            "assignments": assignment_rows(result),
            "failed": list(result.failed),
            "warnings": list(result.warnings),
            "model_boundary": (
                "Distances are straight-line lower bounds between verified service points and targets. "
                "They are not routed pipe/cable/duct lengths and do not certify pressure drop, drainage hydraulics, voltage drop, ventilation, gas safety or code compliance."
            ),
        },
        indent=indent,
        ensure_ascii=False,
    )
