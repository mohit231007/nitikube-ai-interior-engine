import json
import math

import pytest

from nitikube.electrical_route import (
    CircuitTopology,
    ElectricalRouteRequirement,
    ElectricalStatus,
    adjusted_resistance_ohm_per_km,
    electrical_route_brief_template,
    electrical_route_evaluation_json,
    evaluate_electrical_artifacts,
    evaluate_electrical_route,
    load_electrical_route_brief,
)
from nitikube.service_network import (
    NetworkEdge,
    NetworkNode,
    NetworkRoutingPolicy,
    NetworkServiceAssignment,
    ServiceNetwork,
    ServicePointAttachment,
    evaluate_network_routing,
    network_routing_result_json,
    service_network_json,
)
from nitikube.service_points import ServiceKind, ServicePoint, ServiceRequirement, ServiceTarget


def _assignment(length_ft=100.0, kind="electrical"):
    return NetworkServiceAssignment(
        "hob-power",
        "hob",
        "panel-feed",
        kind,
        "access",
        0.0,
        length_ft,
        length_ft,
        ("access", "panel"),
        ("cable-route",),
    )


def _requirement(**overrides):
    data = dict(
        service_requirement_id="hob-power",
        topology=CircuitTopology.DC_TWO_WIRE,
        nominal_voltage_v=120.0,
        current_a=10.0,
        resistance_ohm_per_km=10.0,
        conductor_source_ref="manufacturer:cable-datasheet-v1",
        reactance_ohm_per_km=None,
        power_factor=1.0,
        parallel_conductors_per_phase=1,
        slack_fraction=0.0,
        max_voltage_drop_percent=None,
        voltage_drop_limit_source_ref=None,
    )
    data.update(overrides)
    return ElectricalRouteRequirement(**data)


def test_dc_two_wire_voltage_drop_and_copper_loss_math():
    result = evaluate_electrical_route(_assignment(100.0), _requirement())
    # 100 ft = 0.03048 km; Vdrop=2*I*L*R
    assert result.status == ElectricalStatus.CALCULATED
    assert result.voltage_drop_v == pytest.approx(6.096)
    assert result.voltage_drop_percent == pytest.approx(5.08)
    assert result.receiving_voltage_v == pytest.approx(113.904)
    # P_loss = two conductors * I² * R_line
    assert result.copper_loss_w == pytest.approx(60.96)


def test_single_phase_ac_uses_r_cos_phi_plus_x_sin_phi():
    req = _requirement(
        topology=CircuitTopology.SINGLE_PHASE_TWO_WIRE,
        nominal_voltage_v=230.0,
        resistance_ohm_per_km=1.0,
        reactance_ohm_per_km=0.1,
        power_factor=0.8,
    )
    # 100 m route.
    result = evaluate_electrical_route(_assignment(100.0 / 0.3048), req)
    expected = 2.0 * 10.0 * 0.1 * (1.0 * 0.8 + 0.1 * 0.6)
    assert result.voltage_drop_v == pytest.approx(expected)
    assert result.status == ElectricalStatus.CALCULATED


def test_three_phase_uses_sqrt3_drop_factor_and_three_conductor_loss():
    req = _requirement(
        topology=CircuitTopology.THREE_PHASE_BALANCED,
        nominal_voltage_v=400.0,
        resistance_ohm_per_km=1.0,
        reactance_ohm_per_km=0.0,
        power_factor=1.0,
    )
    result = evaluate_electrical_route(_assignment(100.0 / 0.3048), req)
    assert result.voltage_drop_v == pytest.approx(math.sqrt(3) * 10.0 * 0.1)
    assert result.copper_loss_w == pytest.approx(3 * 10.0**2 * 0.1)


def test_temperature_adjustment_parallel_conductors_and_slack_are_explicit():
    req = _requirement(
        resistance_ohm_per_km=1.0,
        resistance_reference_temp_c=20.0,
        design_conductor_temp_c=70.0,
        temperature_coefficient_per_c=0.004,
        parallel_conductors_per_phase=2,
        slack_fraction=0.10,
    )
    assert adjusted_resistance_ohm_per_km(req) == pytest.approx(1.2)
    result = evaluate_electrical_route(_assignment(100.0), req)
    assert result.design_length_ft == pytest.approx(110.0)
    assert result.effective_resistance_ohm_per_km == pytest.approx(0.6)


def test_explicit_voltage_drop_limit_generates_pass_or_fail_only_with_source():
    passing = evaluate_electrical_route(
        _assignment(10.0),
        _requirement(
            max_voltage_drop_percent=3.0,
            voltage_drop_limit_source_ref="project-standard:VD-01",
        ),
    )
    assert passing.status == ElectricalStatus.PASS
    assert passing.margin_percent_points > 0

    failing = evaluate_electrical_route(
        _assignment(100.0),
        _requirement(
            max_voltage_drop_percent=3.0,
            voltage_drop_limit_source_ref="project-standard:VD-01",
        ),
    )
    assert failing.status == ElectricalStatus.FAIL
    assert "voltage_drop_above_explicit_limit" in failing.failed


def test_ac_limit_stays_unknown_when_reactance_evidence_is_missing():
    req = _requirement(
        topology=CircuitTopology.SINGLE_PHASE_TWO_WIRE,
        nominal_voltage_v=230.0,
        resistance_ohm_per_km=1.0,
        reactance_ohm_per_km=None,
        power_factor=0.8,
        max_voltage_drop_percent=3.0,
        voltage_drop_limit_source_ref="project-standard:VD-01",
    )
    result = evaluate_electrical_route(_assignment(50.0), req)
    assert result.status == ElectricalStatus.UNKNOWN
    assert result.voltage_drop_v is not None
    assert any("reactance" in item.lower() for item in result.warnings)


def test_unsourced_limit_and_partial_temperature_model_are_rejected():
    with pytest.raises(ValueError, match="voltage_drop_limit_source_ref"):
        load_electrical_route_brief(
            json.dumps(
                {
                    "schema": "nitikube.electrical_route_brief",
                    "requirements": [
                        {
                            "service_requirement_id": "hob-power",
                            "topology": "dc_two_wire",
                            "nominal_voltage_v": 120,
                            "current_a": 10,
                            "resistance_ohm_per_km": 10,
                            "conductor_source_ref": "datasheet",
                            "max_voltage_drop_percent": 3,
                        }
                    ],
                }
            )
        )

    with pytest.raises(ValueError, match="must be supplied together"):
        evaluate_electrical_route(
            _assignment(),
            _requirement(resistance_reference_temp_c=20.0),
        )


def test_non_electrical_assignment_is_not_applicable():
    result = evaluate_electrical_route(_assignment(kind="drain"), _requirement())
    assert result.status == ElectricalStatus.NOT_APPLICABLE


def test_missing_referenced_network_edge_produces_unknown():
    network = ServiceNetwork(
        nodes=(NetworkNode("access", 0, 0), NetworkNode("panel", 10, 0)),
        edges=(),
        attachments=(),
    )
    result = evaluate_electrical_route(_assignment(), _requirement(), network=network)
    assert result.status == ElectricalStatus.UNKNOWN
    assert any("missing edges" in item for item in result.unknown)


def test_operating_hours_turns_copper_loss_into_energy_loss():
    result = evaluate_electrical_route(
        _assignment(100.0),
        _requirement(operating_hours=1000.0),
    )
    assert result.energy_loss_kwh == pytest.approx(result.copper_loss_w)


def test_artifact_pipeline_uses_verified_network_assignment_and_preserves_sources():
    network = ServiceNetwork(
        nodes=(
            NetworkNode("access", 0, 0, room_id="k1"),
            NetworkNode("panel", 100, 0, room_id="k1", can_accept_targets=False),
        ),
        edges=(
            NetworkEdge(
                "cable-route",
                "access",
                "panel",
                (ServiceKind.ELECTRICAL,),
                explicit_length_ft=100.0,
            ),
        ),
        attachments=(ServicePointAttachment("panel-feed", "panel"),),
    )
    point = ServicePoint("panel-feed", "k1", ServiceKind.ELECTRICAL, 100, 0)
    target = ServiceTarget("hob", "Hob", "k1", 0, 0)
    service_req = ServiceRequirement("hob-power", "hob", (ServiceKind.ELECTRICAL,))
    routing = evaluate_network_routing(
        (point,),
        (target,),
        (service_req,),
        network,
        NetworkRoutingPolicy(max_target_access_ft=0.01),
    )
    assert routing.feasible
    brief = json.dumps(
        {
            "schema": "nitikube.electrical_route_brief",
            "requirements": [
                {
                    "service_requirement_id": "hob-power",
                    "topology": "dc_two_wire",
                    "nominal_voltage_v": 120.0,
                    "current_a": 10.0,
                    "resistance_ohm_per_km": 10.0,
                    "conductor_source_ref": "manufacturer:cable-datasheet-v1",
                    "max_voltage_drop_percent": 6.0,
                    "voltage_drop_limit_source_ref": "project-standard:VD-01",
                }
            ],
        }
    )
    evaluations = evaluate_electrical_artifacts(
        service_network_json(network),
        network_routing_result_json(routing),
        brief,
    )
    assert evaluations[0].status == ElectricalStatus.PASS
    exported = json.loads(electrical_route_evaluation_json(evaluations))
    assert exported["schema"] == "nitikube.electrical_route_evaluation"
    assert exported["results"][0]["conductor_source_ref"] == "manufacturer:cable-datasheet-v1"
    assert exported["results"][0]["voltage_drop_limit_source_ref"] == "project-standard:VD-01"


def test_template_does_not_invent_voltage_current_resistance_or_limits():
    row = json.loads(electrical_route_brief_template())["requirements"][0]
    assert row["nominal_voltage_v"] is None
    assert row["current_a"] is None
    assert row["resistance_ohm_per_km"] is None
    assert row["conductor_source_ref"] is None
    assert row["max_voltage_drop_percent"] is None
    assert row["voltage_drop_limit_source_ref"] is None
