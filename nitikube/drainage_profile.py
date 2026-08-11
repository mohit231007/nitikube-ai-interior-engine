from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
import json
import math
from typing import Any, Mapping, Sequence

from .service_network import (
    NetworkServiceAssignment,
    ServiceNetwork,
    load_service_network_json,
)
from .service_points import ServiceTarget
from .service_routing_io import load_service_routing_brief


_EPS = 1e-9


class DrainageStatus(str, Enum):
    PASS = "pass"
    FAIL = "fail"
    UNKNOWN = "unknown"
    NOT_APPLICABLE = "not_applicable"


@dataclass(frozen=True)
class DrainageProfileRequirement:
    service_requirement_id: str
    min_slope_percent: float
    source_ref: str
    max_slope_percent: float | None = None
    require_monotonic_fall: bool = True
    evaluate_each_sloped_segment: bool = True
    note: str = ""


@dataclass(frozen=True)
class DrainageSegment:
    segment_id: str
    start_label: str
    end_label: str
    plan_run_ft: float
    start_z_ft: float
    end_z_ft: float
    fall_in: float
    slope_percent: float | None
    vertical: bool


@dataclass(frozen=True)
class DrainageProfileEvaluation:
    service_requirement_id: str
    target_id: str
    point_id: str
    status: DrainageStatus
    total_plan_run_ft: float | None
    total_fall_in: float | None
    average_slope_percent: float | None
    required_minimum_fall_in: float | None
    fall_margin_in: float | None
    segments: tuple[DrainageSegment, ...]
    failed: tuple[str, ...]
    unknown: tuple[str, ...]
    warnings: tuple[str, ...]
    source_ref: str
    model_note: str = (
        "Drainage profile uses explicit route-node elevations and plan runs. Slope thresholds are caller/source inputs, not bundled code values. "
        "The result does not size pipe diameter, calculate hydraulic capacity, trap/vent design, cleanouts or certify local code compliance."
    )


def _finite(value: float, label: str) -> float:
    value = float(value)
    if not math.isfinite(value):
        raise ValueError(f"{label} must be finite")
    return value


def validate_drainage_requirement(requirement: DrainageProfileRequirement) -> None:
    if not requirement.service_requirement_id.strip():
        raise ValueError("service_requirement_id is required")
    if not requirement.source_ref.strip():
        raise ValueError(f"{requirement.service_requirement_id}: source_ref is required")
    min_slope = _finite(requirement.min_slope_percent, "min_slope_percent")
    if min_slope < 0:
        raise ValueError("min_slope_percent cannot be negative")
    if requirement.max_slope_percent is not None:
        max_slope = _finite(requirement.max_slope_percent, "max_slope_percent")
        if max_slope < min_slope:
            raise ValueError("max_slope_percent cannot be below min_slope_percent")
    if not isinstance(requirement.require_monotonic_fall, bool):
        raise ValueError("require_monotonic_fall must be boolean")
    if not isinstance(requirement.evaluate_each_sloped_segment, bool):
        raise ValueError("evaluate_each_sloped_segment must be boolean")


def required_fall_inches(plan_run_ft: float, slope_percent: float) -> float:
    run = _finite(plan_run_ft, "plan_run_ft")
    slope = _finite(slope_percent, "slope_percent")
    if run < 0 or slope < 0:
        raise ValueError("plan run and slope cannot be negative")
    return run * 12.0 * slope / 100.0


def slope_percent_from_fall(plan_run_ft: float, fall_in: float) -> float | None:
    run = _finite(plan_run_ft, "plan_run_ft")
    fall = _finite(fall_in, "fall_in")
    if run < 0:
        raise ValueError("plan_run_ft cannot be negative")
    if run <= _EPS:
        return None
    return fall / (run * 12.0) * 100.0


def _plan_distance(a: tuple[float, float], b: tuple[float, float]) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


def _assignment_from_dict(data: Mapping[str, Any]) -> NetworkServiceAssignment:
    required = (
        "requirement_id",
        "target_id",
        "point_id",
        "kind",
        "target_access_node_id",
        "target_access_distance_ft",
        "network_distance_ft",
        "total_route_ft",
        "path_node_ids",
        "path_edge_ids",
    )
    missing = [
        key for key in required
        if key not in data or data.get(key) is None or data.get(key) == ""
    ]
    if missing:
        raise ValueError(f"missing network-assignment fields: {missing}")
    path_nodes = data["path_node_ids"]
    path_edges = data["path_edge_ids"]
    if not isinstance(path_nodes, list) or not isinstance(path_edges, list):
        raise ValueError("path_node_ids/path_edge_ids must be lists")
    return NetworkServiceAssignment(
        requirement_id=str(data["requirement_id"]),
        target_id=str(data["target_id"]),
        point_id=str(data["point_id"]),
        kind=str(data["kind"]),
        target_access_node_id=str(data["target_access_node_id"]),
        target_access_distance_ft=float(data["target_access_distance_ft"]),
        network_distance_ft=float(data["network_distance_ft"]),
        total_route_ft=float(data["total_route_ft"]),
        path_node_ids=tuple(str(item) for item in path_nodes),
        path_edge_ids=tuple(str(item) for item in path_edges),
    )


def load_network_routing_assignments(payload: str | bytes) -> tuple[NetworkServiceAssignment, ...]:
    text = payload.decode("utf-8") if isinstance(payload, bytes) else payload
    data = json.loads(text)
    if not isinstance(data, dict):
        raise ValueError("network routing evaluation must be a JSON object")
    if data.get("schema") != "nitikube.network_routing_evaluation":
        raise ValueError("expected nitikube.network_routing_evaluation")
    rows = data.get("assignments")
    if not isinstance(rows, list):
        raise ValueError("network routing evaluation assignments must be a list")
    assignments = tuple(_assignment_from_dict(row) for row in rows)
    ids = [item.requirement_id for item in assignments]
    if len(ids) != len(set(ids)):
        raise ValueError("network routing evaluation contains duplicate requirement assignments")
    return assignments


def drainage_requirement_from_dict(data: Mapping[str, Any]) -> DrainageProfileRequirement:
    required = ("service_requirement_id", "min_slope_percent", "source_ref")
    missing = [
        key for key in required
        if key not in data or data.get(key) is None or data.get(key) == ""
    ]
    if missing:
        raise ValueError(f"missing drainage-profile fields: {missing}")
    requirement = DrainageProfileRequirement(
        service_requirement_id=str(data["service_requirement_id"]),
        min_slope_percent=float(data["min_slope_percent"]),
        source_ref=str(data["source_ref"]),
        max_slope_percent=None if data.get("max_slope_percent") in {None, ""} else float(data["max_slope_percent"]),
        require_monotonic_fall=bool(data.get("require_monotonic_fall", True)),
        evaluate_each_sloped_segment=bool(data.get("evaluate_each_sloped_segment", True)),
        note=str(data.get("note") or ""),
    )
    validate_drainage_requirement(requirement)
    return requirement


def load_drainage_profile_brief(payload: str | bytes) -> tuple[DrainageProfileRequirement, ...]:
    text = payload.decode("utf-8") if isinstance(payload, bytes) else payload
    data = json.loads(text)
    if not isinstance(data, dict):
        raise ValueError("drainage profile brief must be a JSON object")
    if data.get("schema") not in {None, "nitikube.drainage_profile_brief"}:
        raise ValueError("unsupported drainage profile brief schema")
    rows = data.get("requirements")
    if not isinstance(rows, list):
        raise ValueError("drainage profile requirements must be a list")
    requirements = tuple(drainage_requirement_from_dict(row) for row in rows)
    ids = [item.service_requirement_id for item in requirements]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate service_requirement_id in drainage profile brief")
    return requirements


def drainage_profile_brief_template(*, indent: int = 2) -> str:
    return json.dumps(
        {
            "schema": "nitikube.drainage_profile_brief",
            "schema_version": "0.29",
            "requirements": [
                {
                    "service_requirement_id": "replace-with-drain-service-requirement-id",
                    "min_slope_percent": None,
                    "max_slope_percent": None,
                    "require_monotonic_fall": True,
                    "evaluate_each_sloped_segment": True,
                    "source_ref": None,
                    "note": "Populate slope thresholds only from a sourced standard, manufacturer requirement or qualified professional input.",
                }
            ],
        },
        indent=indent,
        ensure_ascii=False,
    )


def evaluate_drainage_profile(
    assignment: NetworkServiceAssignment,
    target: ServiceTarget,
    network: ServiceNetwork,
    requirement: DrainageProfileRequirement,
) -> DrainageProfileEvaluation:
    validate_drainage_requirement(requirement)
    if requirement.service_requirement_id != assignment.requirement_id:
        raise ValueError("drainage requirement ID does not match network assignment requirement_id")
    if assignment.target_id != target.target_id:
        raise ValueError("network assignment target_id does not match supplied target")
    if assignment.kind != "drain":
        return DrainageProfileEvaluation(
            assignment.requirement_id,
            assignment.target_id,
            assignment.point_id,
            DrainageStatus.NOT_APPLICABLE,
            None,
            None,
            None,
            None,
            None,
            (),
            (),
            (),
            (f"assignment service kind is {assignment.kind}, not drain",),
            requirement.source_ref,
        )

    node_map = {node.node_id: node for node in network.nodes}
    unknown: list[str] = []
    failed: list[str] = []
    warnings: list[str] = []

    if not assignment.path_node_ids:
        unknown.append("network assignment contains no path nodes")
    elif assignment.path_node_ids[0] != assignment.target_access_node_id:
        unknown.append("network assignment path does not start at target_access_node_id")
    if len(assignment.path_edge_ids) != max(0, len(assignment.path_node_ids) - 1):
        unknown.append("network assignment path edge/node cardinality is inconsistent")

    missing_nodes = [node_id for node_id in assignment.path_node_ids if node_id not in node_map]
    if missing_nodes:
        unknown.append("network assignment references missing nodes: " + ", ".join(missing_nodes))
    if target.z_ft is None:
        unknown.append("target elevation z_ft is missing")
    for node_id in assignment.path_node_ids:
        node = node_map.get(node_id)
        if node is not None and node.z_ft is None:
            unknown.append(f"route node {node_id} elevation z_ft is missing")

    if unknown:
        return DrainageProfileEvaluation(
            assignment.requirement_id,
            assignment.target_id,
            assignment.point_id,
            DrainageStatus.UNKNOWN,
            None,
            None,
            None,
            None,
            None,
            (),
            (),
            tuple(dict.fromkeys(unknown)),
            (),
            requirement.source_ref,
        )

    assert target.z_ft is not None
    segments: list[DrainageSegment] = []

    access = node_map[assignment.path_node_ids[0]]
    access_run = _plan_distance((target.x_ft, target.y_ft), (access.x_ft, access.y_ft))
    access_fall_in = (target.z_ft - float(access.z_ft)) * 12.0
    access_slope = slope_percent_from_fall(access_run, access_fall_in)
    segments.append(
        DrainageSegment(
            "target-access",
            target.target_id,
            access.node_id,
            access_run,
            target.z_ft,
            float(access.z_ft),
            access_fall_in,
            access_slope,
            access_run <= _EPS,
        )
    )

    for index, edge_id in enumerate(assignment.path_edge_ids):
        start = node_map[assignment.path_node_ids[index]]
        end = node_map[assignment.path_node_ids[index + 1]]
        run = _plan_distance((start.x_ft, start.y_ft), (end.x_ft, end.y_ft))
        fall_in = (float(start.z_ft) - float(end.z_ft)) * 12.0
        slope = slope_percent_from_fall(run, fall_in)
        segments.append(
            DrainageSegment(
                edge_id,
                start.node_id,
                end.node_id,
                run,
                float(start.z_ft),
                float(end.z_ft),
                fall_in,
                slope,
                run <= _EPS,
            )
        )

    total_run = sum(segment.plan_run_ft for segment in segments)
    total_fall = (target.z_ft - float(node_map[assignment.path_node_ids[-1]].z_ft)) * 12.0
    average_slope = slope_percent_from_fall(total_run, total_fall)
    required_fall = required_fall_inches(total_run, requirement.min_slope_percent)
    margin = total_fall - required_fall

    if requirement.require_monotonic_fall:
        for segment in segments:
            if segment.fall_in < -1e-7:
                failed.append(f"local_rise:{segment.segment_id}")

    if average_slope is None:
        if total_fall < -1e-7:
            failed.append("zero-plan-run route rises toward drain endpoint")
        elif abs(total_fall) <= 1e-7:
            warnings.append("route has zero plan run and zero fall; percentage slope is undefined")
        else:
            warnings.append("route is purely vertical; percentage slope is not applicable to the vertical drop")
    else:
        if average_slope + 1e-7 < requirement.min_slope_percent:
            failed.append("average_slope_below_minimum")
        if requirement.max_slope_percent is not None and average_slope - 1e-7 > requirement.max_slope_percent:
            failed.append("average_slope_above_maximum")

    if requirement.evaluate_each_sloped_segment:
        for segment in segments:
            if segment.slope_percent is None:
                if segment.vertical and segment.fall_in > 0:
                    warnings.append(f"vertical_drop:{segment.segment_id}:slope_percent_not_applied")
                continue
            if segment.slope_percent + 1e-7 < requirement.min_slope_percent:
                failed.append(f"segment_slope_below_minimum:{segment.segment_id}")
            if requirement.max_slope_percent is not None and segment.slope_percent - 1e-7 > requirement.max_slope_percent:
                failed.append(f"segment_slope_above_maximum:{segment.segment_id}")

    status = DrainageStatus.FAIL if failed else DrainageStatus.PASS
    return DrainageProfileEvaluation(
        assignment.requirement_id,
        assignment.target_id,
        assignment.point_id,
        status,
        total_run,
        total_fall,
        average_slope,
        required_fall,
        margin,
        tuple(segments),
        tuple(dict.fromkeys(failed)),
        (),
        tuple(dict.fromkeys(warnings)),
        requirement.source_ref,
    )


def evaluate_drainage_artifacts(
    service_network_payload: str | bytes,
    network_routing_evaluation_payload: str | bytes,
    service_routing_brief_payload: str | bytes,
    drainage_profile_brief_payload: str | bytes,
) -> tuple[DrainageProfileEvaluation, ...]:
    network = load_service_network_json(service_network_payload)
    assignments = load_network_routing_assignments(network_routing_evaluation_payload)
    targets, _service_requirements, _allow_shared, _distance_mode = load_service_routing_brief(service_routing_brief_payload)
    drainage_requirements = load_drainage_profile_brief(drainage_profile_brief_payload)

    assignment_map = {item.requirement_id: item for item in assignments}
    target_map = {item.target_id: item for item in targets}
    results: list[DrainageProfileEvaluation] = []
    for requirement in drainage_requirements:
        assignment = assignment_map.get(requirement.service_requirement_id)
        if assignment is None:
            results.append(
                DrainageProfileEvaluation(
                    requirement.service_requirement_id,
                    "",
                    "",
                    DrainageStatus.UNKNOWN,
                    None,
                    None,
                    None,
                    None,
                    None,
                    (),
                    (),
                    ("network routing evaluation has no assignment for this drainage service requirement",),
                    (),
                    requirement.source_ref,
                )
            )
            continue
        target = target_map.get(assignment.target_id)
        if target is None:
            results.append(
                DrainageProfileEvaluation(
                    requirement.service_requirement_id,
                    assignment.target_id,
                    assignment.point_id,
                    DrainageStatus.UNKNOWN,
                    None,
                    None,
                    None,
                    None,
                    None,
                    (),
                    (),
                    ("service routing brief does not contain the assigned target",),
                    (),
                    requirement.source_ref,
                )
            )
            continue
        results.append(evaluate_drainage_profile(assignment, target, network, requirement))
    return tuple(results)


def drainage_profile_evaluation_json(
    evaluations: Sequence[DrainageProfileEvaluation],
    *,
    indent: int = 2,
) -> str:
    return json.dumps(
        {
            "schema": "nitikube.drainage_profile_evaluation",
            "schema_version": "0.29",
            "results": [
                {
                    **asdict(item),
                    "status": item.status.value,
                }
                for item in evaluations
            ],
            "model_note": (
                "PASS/FAIL uses only the explicit drainage thresholds in the drainage profile brief. Missing elevations produce UNKNOWN. "
                "No bundled numeric plumbing standard is implied."
            ),
        },
        indent=indent,
        ensure_ascii=False,
    )
