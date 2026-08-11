from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
import json
import math
from typing import Any, Mapping, Sequence

from .service_network import NetworkServiceAssignment, ServiceNetwork, load_service_network_json


FT_TO_KM = 0.0003048
_EPS = 1e-12


class CircuitTopology(str, Enum):
    DC_TWO_WIRE = "dc_two_wire"
    SINGLE_PHASE_TWO_WIRE = "single_phase_two_wire"
    THREE_PHASE_BALANCED = "three_phase_balanced"


class ElectricalStatus(str, Enum):
    PASS = "pass"
    FAIL = "fail"
    CALCULATED = "calculated"
    UNKNOWN = "unknown"
    NOT_APPLICABLE = "not_applicable"


@dataclass(frozen=True)
class ElectricalRouteRequirement:
    service_requirement_id: str
    topology: CircuitTopology
    nominal_voltage_v: float
    current_a: float
    resistance_ohm_per_km: float
    conductor_source_ref: str
    reactance_ohm_per_km: float | None = None
    power_factor: float = 1.0
    parallel_conductors_per_phase: int = 1
    slack_fraction: float = 0.0
    resistance_reference_temp_c: float | None = None
    design_conductor_temp_c: float | None = None
    temperature_coefficient_per_c: float | None = None
    max_voltage_drop_percent: float | None = None
    voltage_drop_limit_source_ref: str | None = None
    operating_hours: float | None = None
    note: str = ""


@dataclass(frozen=True)
class ElectricalRouteEvaluation:
    service_requirement_id: str
    point_id: str
    topology: str
    status: ElectricalStatus
    routed_length_ft: float | None
    design_length_ft: float | None
    adjusted_resistance_ohm_per_km: float | None
    effective_resistance_ohm_per_km: float | None
    effective_reactance_ohm_per_km: float | None
    voltage_drop_v: float | None
    voltage_drop_percent: float | None
    receiving_voltage_v: float | None
    copper_loss_w: float | None
    energy_loss_kwh: float | None
    max_voltage_drop_percent: float | None
    margin_percent_points: float | None
    failed: tuple[str, ...]
    unknown: tuple[str, ...]
    warnings: tuple[str, ...]
    conductor_source_ref: str
    voltage_drop_limit_source_ref: str | None
    model_note: str = (
        "Voltage drop uses the routed geometric length and explicit conductor R/X evidence. AC calculation uses R·cosφ + X·sinφ. "
        "It does not size protective devices, verify ampacity/derating, fault current, earthing, short-circuit withstand or certify electrical code compliance."
    )


def _finite(value: float, label: str) -> float:
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{label} must be finite")
    return result


def validate_electrical_requirement(requirement: ElectricalRouteRequirement) -> None:
    if not requirement.service_requirement_id.strip():
        raise ValueError("service_requirement_id is required")
    if not requirement.conductor_source_ref.strip():
        raise ValueError(f"{requirement.service_requirement_id}: conductor_source_ref is required")
    if _finite(requirement.nominal_voltage_v, "nominal_voltage_v") <= 0:
        raise ValueError("nominal_voltage_v must be positive")
    if _finite(requirement.current_a, "current_a") < 0:
        raise ValueError("current_a cannot be negative")
    if _finite(requirement.resistance_ohm_per_km, "resistance_ohm_per_km") < 0:
        raise ValueError("resistance_ohm_per_km cannot be negative")
    if requirement.reactance_ohm_per_km is not None and _finite(requirement.reactance_ohm_per_km, "reactance_ohm_per_km") < 0:
        raise ValueError("reactance_ohm_per_km cannot be negative")
    pf = _finite(requirement.power_factor, "power_factor")
    if not 0 <= pf <= 1:
        raise ValueError("power_factor must be in [0,1]")
    if isinstance(requirement.parallel_conductors_per_phase, bool) or int(requirement.parallel_conductors_per_phase) != requirement.parallel_conductors_per_phase or requirement.parallel_conductors_per_phase < 1:
        raise ValueError("parallel_conductors_per_phase must be an integer >= 1")
    if _finite(requirement.slack_fraction, "slack_fraction") < 0:
        raise ValueError("slack_fraction cannot be negative")

    temp_values = (
        requirement.resistance_reference_temp_c,
        requirement.design_conductor_temp_c,
        requirement.temperature_coefficient_per_c,
    )
    if any(value is not None for value in temp_values) and not all(value is not None for value in temp_values):
        raise ValueError(
            "resistance_reference_temp_c, design_conductor_temp_c and temperature_coefficient_per_c must be supplied together"
        )
    if requirement.temperature_coefficient_per_c is not None:
        if _finite(requirement.temperature_coefficient_per_c, "temperature_coefficient_per_c") < 0:
            raise ValueError("temperature_coefficient_per_c cannot be negative")

    if requirement.max_voltage_drop_percent is not None:
        limit = _finite(requirement.max_voltage_drop_percent, "max_voltage_drop_percent")
        if limit < 0:
            raise ValueError("max_voltage_drop_percent cannot be negative")
        if not str(requirement.voltage_drop_limit_source_ref or "").strip():
            raise ValueError("voltage_drop_limit_source_ref is required when max_voltage_drop_percent is supplied")
    elif requirement.voltage_drop_limit_source_ref not in {None, ""}:
        raise ValueError("voltage_drop_limit_source_ref was supplied without max_voltage_drop_percent")

    if requirement.operating_hours is not None and _finite(requirement.operating_hours, "operating_hours") < 0:
        raise ValueError("operating_hours cannot be negative")


def adjusted_resistance_ohm_per_km(requirement: ElectricalRouteRequirement) -> float:
    validate_electrical_requirement(requirement)
    resistance = requirement.resistance_ohm_per_km
    if requirement.temperature_coefficient_per_c is None:
        return resistance
    assert requirement.resistance_reference_temp_c is not None
    assert requirement.design_conductor_temp_c is not None
    delta_t = requirement.design_conductor_temp_c - requirement.resistance_reference_temp_c
    adjusted = resistance * (1.0 + requirement.temperature_coefficient_per_c * delta_t)
    if adjusted < 0:
        raise ValueError("temperature adjustment produced negative resistance")
    return adjusted


def voltage_drop_factor(topology: CircuitTopology) -> float:
    if topology in {CircuitTopology.DC_TWO_WIRE, CircuitTopology.SINGLE_PHASE_TWO_WIRE}:
        return 2.0
    if topology == CircuitTopology.THREE_PHASE_BALANCED:
        return math.sqrt(3.0)
    raise ValueError(f"unsupported topology: {topology}")


def conductor_loss_factor(topology: CircuitTopology) -> float:
    if topology in {CircuitTopology.DC_TWO_WIRE, CircuitTopology.SINGLE_PHASE_TWO_WIRE}:
        return 2.0
    if topology == CircuitTopology.THREE_PHASE_BALANCED:
        return 3.0
    raise ValueError(f"unsupported topology: {topology}")


def evaluate_electrical_route(
    assignment: NetworkServiceAssignment,
    requirement: ElectricalRouteRequirement,
    *,
    network: ServiceNetwork | None = None,
) -> ElectricalRouteEvaluation:
    validate_electrical_requirement(requirement)
    if requirement.service_requirement_id != assignment.requirement_id:
        raise ValueError("electrical requirement ID does not match network assignment requirement_id")
    if assignment.kind != "electrical":
        return ElectricalRouteEvaluation(
            assignment.requirement_id,
            assignment.point_id,
            requirement.topology.value,
            ElectricalStatus.NOT_APPLICABLE,
            None, None, None, None, None, None, None, None, None, None,
            requirement.max_voltage_drop_percent,
            None,
            (), (),
            (f"assignment service kind is {assignment.kind}, not electrical",),
            requirement.conductor_source_ref,
            requirement.voltage_drop_limit_source_ref,
        )

    unknown: list[str] = []
    warnings: list[str] = []
    failed: list[str] = []

    if assignment.total_route_ft < 0 or not math.isfinite(assignment.total_route_ft):
        unknown.append("network assignment total_route_ft is invalid")
    if network is not None:
        edge_ids = {edge.edge_id for edge in network.edges}
        node_ids = {node.node_id for node in network.nodes}
        missing_edges = [edge_id for edge_id in assignment.path_edge_ids if edge_id not in edge_ids]
        missing_nodes = [node_id for node_id in assignment.path_node_ids if node_id not in node_ids]
        if missing_edges:
            unknown.append("network assignment references missing edges: " + ", ".join(missing_edges))
        if missing_nodes:
            unknown.append("network assignment references missing nodes: " + ", ".join(missing_nodes))

    if unknown:
        return ElectricalRouteEvaluation(
            assignment.requirement_id,
            assignment.point_id,
            requirement.topology.value,
            ElectricalStatus.UNKNOWN,
            None, None, None, None, None, None, None, None, None, None,
            requirement.max_voltage_drop_percent,
            None,
            (), tuple(dict.fromkeys(unknown)), (),
            requirement.conductor_source_ref,
            requirement.voltage_drop_limit_source_ref,
        )

    routed_length_ft = float(assignment.total_route_ft)
    design_length_ft = routed_length_ft * (1.0 + requirement.slack_fraction)
    length_km = design_length_ft * FT_TO_KM
    adjusted_r = adjusted_resistance_ohm_per_km(requirement)
    effective_r = adjusted_r / requirement.parallel_conductors_per_phase
    effective_x = None
    if requirement.reactance_ohm_per_km is not None:
        effective_x = requirement.reactance_ohm_per_km / requirement.parallel_conductors_per_phase

    if requirement.topology == CircuitTopology.DC_TWO_WIRE:
        impedance_component = effective_r
    else:
        if effective_x is None:
            effective_x_for_calc = 0.0
            warnings.append("AC reactance is unknown; voltage drop shown is a resistive-only calculation")
        else:
            effective_x_for_calc = effective_x
        cos_phi = requirement.power_factor
        sin_phi = math.sqrt(max(0.0, 1.0 - cos_phi * cos_phi))
        impedance_component = effective_r * cos_phi + effective_x_for_calc * sin_phi

    drop_v = voltage_drop_factor(requirement.topology) * requirement.current_a * length_km * impedance_component
    drop_pct = drop_v / requirement.nominal_voltage_v * 100.0
    receiving_v = requirement.nominal_voltage_v - drop_v

    conductor_line_r = effective_r * length_km
    copper_loss_w = conductor_loss_factor(requirement.topology) * requirement.current_a**2 * conductor_line_r
    energy_loss = None
    if requirement.operating_hours is not None:
        energy_loss = copper_loss_w * requirement.operating_hours / 1000.0

    limit = requirement.max_voltage_drop_percent
    margin = None
    status = ElectricalStatus.CALCULATED
    if limit is not None:
        margin = limit - drop_pct
        if requirement.topology != CircuitTopology.DC_TWO_WIRE and effective_x is None:
            status = ElectricalStatus.UNKNOWN
            warnings.append(
                "A voltage-drop limit was supplied, but full AC R/X evidence is incomplete; resistive-only result is not promoted to PASS/FAIL"
            )
        elif drop_pct <= limit + 1e-9:
            status = ElectricalStatus.PASS
        else:
            status = ElectricalStatus.FAIL
            failed.append("voltage_drop_above_explicit_limit")

    if receiving_v < 0:
        failed.append("calculated_voltage_drop_exceeds_nominal_voltage")
        status = ElectricalStatus.FAIL

    return ElectricalRouteEvaluation(
        assignment.requirement_id,
        assignment.point_id,
        requirement.topology.value,
        status,
        routed_length_ft,
        design_length_ft,
        adjusted_r,
        effective_r,
        effective_x,
        drop_v,
        drop_pct,
        receiving_v,
        copper_loss_w,
        energy_loss,
        limit,
        margin,
        tuple(dict.fromkeys(failed)),
        (),
        tuple(dict.fromkeys(warnings)),
        requirement.conductor_source_ref,
        requirement.voltage_drop_limit_source_ref,
    )


def electrical_requirement_from_dict(data: Mapping[str, Any]) -> ElectricalRouteRequirement:
    required = (
        "service_requirement_id",
        "topology",
        "nominal_voltage_v",
        "current_a",
        "resistance_ohm_per_km",
        "conductor_source_ref",
    )
    missing = [
        key for key in required
        if key not in data or data.get(key) is None or data.get(key) == ""
    ]
    if missing:
        raise ValueError(f"missing electrical-route fields: {missing}")

    def optional_float(key: str) -> float | None:
        value = data.get(key)
        return None if value in {None, ""} else float(value)

    requirement = ElectricalRouteRequirement(
        service_requirement_id=str(data["service_requirement_id"]),
        topology=CircuitTopology(str(data["topology"])),
        nominal_voltage_v=float(data["nominal_voltage_v"]),
        current_a=float(data["current_a"]),
        resistance_ohm_per_km=float(data["resistance_ohm_per_km"]),
        conductor_source_ref=str(data["conductor_source_ref"]),
        reactance_ohm_per_km=optional_float("reactance_ohm_per_km"),
        power_factor=float(data.get("power_factor", 1.0)),
        parallel_conductors_per_phase=int(data.get("parallel_conductors_per_phase", 1)),
        slack_fraction=float(data.get("slack_fraction", 0.0)),
        resistance_reference_temp_c=optional_float("resistance_reference_temp_c"),
        design_conductor_temp_c=optional_float("design_conductor_temp_c"),
        temperature_coefficient_per_c=optional_float("temperature_coefficient_per_c"),
        max_voltage_drop_percent=optional_float("max_voltage_drop_percent"),
        voltage_drop_limit_source_ref=None if data.get("voltage_drop_limit_source_ref") in {None, ""} else str(data["voltage_drop_limit_source_ref"]),
        operating_hours=optional_float("operating_hours"),
        note=str(data.get("note") or ""),
    )
    validate_electrical_requirement(requirement)
    return requirement


def load_electrical_route_brief(payload: str | bytes) -> tuple[ElectricalRouteRequirement, ...]:
    text = payload.decode("utf-8") if isinstance(payload, bytes) else payload
    data = json.loads(text)
    if not isinstance(data, dict):
        raise ValueError("electrical route brief must be a JSON object")
    if data.get("schema") not in {None, "nitikube.electrical_route_brief"}:
        raise ValueError("unsupported electrical route brief schema")
    rows = data.get("requirements")
    if not isinstance(rows, list):
        raise ValueError("electrical route requirements must be a list")
    requirements = tuple(electrical_requirement_from_dict(row) for row in rows)
    ids = [item.service_requirement_id for item in requirements]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate service_requirement_id in electrical route brief")
    return requirements


def electrical_route_brief_template(*, indent: int = 2) -> str:
    return json.dumps(
        {
            "schema": "nitikube.electrical_route_brief",
            "schema_version": "0.30",
            "requirements": [
                {
                    "service_requirement_id": "replace-with-electrical-service-requirement-id",
                    "topology": "single_phase_two_wire",
                    "nominal_voltage_v": None,
                    "current_a": None,
                    "resistance_ohm_per_km": None,
                    "reactance_ohm_per_km": None,
                    "power_factor": 1.0,
                    "parallel_conductors_per_phase": 1,
                    "slack_fraction": 0.0,
                    "resistance_reference_temp_c": None,
                    "design_conductor_temp_c": None,
                    "temperature_coefficient_per_c": None,
                    "conductor_source_ref": None,
                    "max_voltage_drop_percent": None,
                    "voltage_drop_limit_source_ref": None,
                    "operating_hours": None,
                    "note": "Populate conductor R/X and any voltage-drop limit from identified evidence. AC limit evaluation remains UNKNOWN when reactance evidence is absent.",
                }
            ],
        },
        indent=indent,
        ensure_ascii=False,
    )


def _assignment_from_dict(data: Mapping[str, Any]) -> NetworkServiceAssignment:
    list_fields = ("path_node_ids", "path_edge_ids")
    for field in list_fields:
        if not isinstance(data.get(field), list):
            raise ValueError(f"network assignment {field} must be a list")
    required = (
        "requirement_id", "target_id", "point_id", "kind", "target_access_node_id",
        "target_access_distance_ft", "network_distance_ft", "total_route_ft",
    )
    missing = [key for key in required if data.get(key) in {None, ""}]
    if missing:
        raise ValueError(f"missing network-assignment fields: {missing}")
    return NetworkServiceAssignment(
        requirement_id=str(data["requirement_id"]),
        target_id=str(data["target_id"]),
        point_id=str(data["point_id"]),
        kind=str(data["kind"]),
        target_access_node_id=str(data["target_access_node_id"]),
        target_access_distance_ft=float(data["target_access_distance_ft"]),
        network_distance_ft=float(data["network_distance_ft"]),
        total_route_ft=float(data["total_route_ft"]),
        path_node_ids=tuple(str(item) for item in data["path_node_ids"]),
        path_edge_ids=tuple(str(item) for item in data["path_edge_ids"]),
    )


def load_network_assignments(payload: str | bytes) -> tuple[NetworkServiceAssignment, ...]:
    text = payload.decode("utf-8") if isinstance(payload, bytes) else payload
    data = json.loads(text)
    if not isinstance(data, dict) or data.get("schema") != "nitikube.network_routing_evaluation":
        raise ValueError("expected nitikube.network_routing_evaluation")
    rows = data.get("assignments")
    if not isinstance(rows, list):
        raise ValueError("network routing assignments must be a list")
    assignments = tuple(_assignment_from_dict(row) for row in rows)
    ids = [item.requirement_id for item in assignments]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate requirement assignments in network routing evaluation")
    return assignments


def evaluate_electrical_artifacts(
    service_network_payload: str | bytes,
    network_routing_evaluation_payload: str | bytes,
    electrical_route_brief_payload: str | bytes,
) -> tuple[ElectricalRouteEvaluation, ...]:
    network = load_service_network_json(service_network_payload)
    assignments = load_network_assignments(network_routing_evaluation_payload)
    requirements = load_electrical_route_brief(electrical_route_brief_payload)
    assignment_map = {item.requirement_id: item for item in assignments}
    results: list[ElectricalRouteEvaluation] = []
    for requirement in requirements:
        assignment = assignment_map.get(requirement.service_requirement_id)
        if assignment is None:
            results.append(
                ElectricalRouteEvaluation(
                    requirement.service_requirement_id,
                    "",
                    requirement.topology.value,
                    ElectricalStatus.UNKNOWN,
                    None, None, None, None, None, None, None, None, None, None,
                    requirement.max_voltage_drop_percent,
                    None,
                    (),
                    ("network routing evaluation has no assignment for this electrical service requirement",),
                    (),
                    requirement.conductor_source_ref,
                    requirement.voltage_drop_limit_source_ref,
                )
            )
            continue
        results.append(evaluate_electrical_route(assignment, requirement, network=network))
    return tuple(results)


def electrical_route_evaluation_json(
    evaluations: Sequence[ElectricalRouteEvaluation],
    *,
    indent: int = 2,
) -> str:
    return json.dumps(
        {
            "schema": "nitikube.electrical_route_evaluation",
            "schema_version": "0.30",
            "results": [
                {
                    **asdict(item),
                    "status": item.status.value,
                }
                for item in evaluations
            ],
            "model_note": (
                "No conductor resistance/reactance, design current, voltage-drop limit or temperature assumption is bundled as a hidden default. "
                "PASS/FAIL is only produced when the required evidence for the selected model is supplied."
            ),
        },
        indent=indent,
        ensure_ascii=False,
    )
