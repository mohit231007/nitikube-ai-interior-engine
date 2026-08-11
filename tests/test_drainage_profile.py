import json

import pytest

from nitikube.drainage_profile import (
    DrainageProfileRequirement,
    DrainageStatus,
    drainage_profile_brief_template,
    drainage_profile_evaluation_json,
    evaluate_drainage_artifacts,
    evaluate_drainage_profile,
    load_drainage_profile_brief,
    required_fall_inches,
    slope_percent_from_fall,
)
from nitikube.service_network import (
    NetworkEdge,
    NetworkNode,
    NetworkRoutingPolicy,
    ServiceNetwork,
    ServicePointAttachment,
    evaluate_network_routing,
    network_routing_result_json,
    service_network_json,
)
from nitikube.service_points import ServiceKind, ServicePoint, ServiceRequirement, ServiceTarget


def _profile_network(*, middle_z=2.98, end_z=2.90):
    return ServiceNetwork(
        nodes=(
            NetworkNode("access", 0.0, 1.0, z_ft=middle_z, room_id="b1"),
            NetworkNode("drain", 0.0, 5.0, z_ft=end_z, room_id="b1", can_accept_targets=False),
        ),
        edges=(
            NetworkEdge(
                "drain-run",
                "access",
                "drain",
                (ServiceKind.DRAIN,),
                route_class="drain_route",
            ),
        ),
        attachments=(ServicePointAttachment("drain-point", "drain"),),
    )


def _assignment_and_target(network=None):
    network = network or _profile_network()
    point = ServicePoint("drain-point", "b1", ServiceKind.DRAIN, 0.0, 5.0, z_ft=2.90)
    target = ServiceTarget("basin", "Basin waste", "b1", 0.0, 0.0, z_ft=3.0)
    requirement = ServiceRequirement("basin-drain", "basin", (ServiceKind.DRAIN,), max_route_ft=20.0)
    result = evaluate_network_routing(
        (point,),
        (target,),
        (requirement,),
        network,
        NetworkRoutingPolicy(max_target_access_ft=1.1, distance_mode="3d"),
    )
    assert result.feasible
    return result.assignments[0], target


def _slope_requirement(min_slope=1.0, max_slope=None):
    return DrainageProfileRequirement(
        "basin-drain",
        min_slope,
        source_ref="qualified_professional_input:fixture-brief-v1",
        max_slope_percent=max_slope,
    )


def test_required_fall_and_slope_math_are_inverses():
    assert required_fall_inches(10.0, 2.0) == pytest.approx(2.4)
    assert slope_percent_from_fall(10.0, 2.4) == pytest.approx(2.0)
    assert slope_percent_from_fall(0.0, 12.0) is None


def test_route_profile_passes_when_average_and_each_segment_clear_explicit_minimum():
    network = _profile_network()
    assignment, target = _assignment_and_target(network)
    evaluation = evaluate_drainage_profile(assignment, target, network, _slope_requirement(1.0))
    assert evaluation.status == DrainageStatus.PASS
    assert evaluation.total_plan_run_ft == pytest.approx(5.0)
    assert evaluation.total_fall_in == pytest.approx(1.2)
    assert evaluation.average_slope_percent == pytest.approx(2.0)
    assert evaluation.required_minimum_fall_in == pytest.approx(0.6)
    assert evaluation.fall_margin_in == pytest.approx(0.6)
    assert len(evaluation.segments) == 2
    assert all(segment.slope_percent == pytest.approx(2.0) for segment in evaluation.segments)


def test_average_can_pass_while_local_rise_forces_failure():
    # Target 3.0 -> access 3.02 is an initial rise; endpoint 2.80 creates a large
    # later drop, so average fall is positive but gravity-path monotonicity fails.
    network = _profile_network(middle_z=3.02, end_z=2.80)
    assignment, target = _assignment_and_target(network)
    evaluation = evaluate_drainage_profile(assignment, target, network, _slope_requirement(1.0))
    assert evaluation.average_slope_percent is not None and evaluation.average_slope_percent > 1.0
    assert evaluation.status == DrainageStatus.FAIL
    assert "local_rise:target-access" in evaluation.failed
    assert "segment_slope_below_minimum:target-access" in evaluation.failed


def test_maximum_slope_is_checked_only_when_explicitly_supplied():
    network = _profile_network()
    assignment, target = _assignment_and_target(network)
    unrestricted = evaluate_drainage_profile(assignment, target, network, _slope_requirement(1.0))
    assert unrestricted.status == DrainageStatus.PASS
    restricted = evaluate_drainage_profile(assignment, target, network, _slope_requirement(1.0, 1.5))
    assert restricted.status == DrainageStatus.FAIL
    assert "average_slope_above_maximum" in restricted.failed


def test_missing_route_elevation_produces_unknown_not_pass():
    network = ServiceNetwork(
        nodes=(
            NetworkNode("access", 0, 1, z_ft=None, room_id="b1"),
            NetworkNode("drain", 0, 5, z_ft=2.9, room_id="b1", can_accept_targets=False),
        ),
        edges=(NetworkEdge("run", "access", "drain", (ServiceKind.DRAIN,)),),
        attachments=(ServicePointAttachment("drain-point", "drain"),),
    )
    # Build the assignment manually because 3D network routing correctly refuses
    # a geometry-derived edge with missing Z; the profile evaluator must still
    # preserve UNKNOWN if it receives such an incomplete external assignment.
    from nitikube.service_network import NetworkServiceAssignment

    assignment = NetworkServiceAssignment(
        "basin-drain",
        "basin",
        "drain-point",
        "drain",
        "access",
        1.0,
        4.0,
        5.0,
        ("access", "drain"),
        ("run",),
    )
    target = ServiceTarget("basin", "Basin", "b1", 0, 0, z_ft=3.0)
    evaluation = evaluate_drainage_profile(assignment, target, network, _slope_requirement())
    assert evaluation.status == DrainageStatus.UNKNOWN
    assert any("access" in item and "z_ft" in item for item in evaluation.unknown)


def test_non_drain_assignment_is_not_applicable_not_failure():
    from nitikube.service_network import NetworkServiceAssignment

    assignment = NetworkServiceAssignment(
        "basin-drain",
        "basin",
        "socket",
        "electrical",
        "access",
        1.0,
        0.0,
        1.0,
        ("access",),
        (),
    )
    target = ServiceTarget("basin", "Basin", "b1", 0, 0, z_ft=3.0)
    network = ServiceNetwork((NetworkNode("access", 0, 1, z_ft=2.9, room_id="b1"),), (), ())
    evaluation = evaluate_drainage_profile(assignment, target, network, _slope_requirement())
    assert evaluation.status == DrainageStatus.NOT_APPLICABLE


def test_vertical_drop_is_allowed_but_slope_percent_is_not_misreported():
    from nitikube.service_network import NetworkServiceAssignment

    network = ServiceNetwork(
        (NetworkNode("access", 0, 0, z_ft=2.5, room_id="b1"),),
        (),
        (),
    )
    assignment = NetworkServiceAssignment(
        "basin-drain",
        "basin",
        "drain-point",
        "drain",
        "access",
        0.0,
        0.0,
        0.0,
        ("access",),
        (),
    )
    target = ServiceTarget("basin", "Basin", "b1", 0, 0, z_ft=3.0)
    evaluation = evaluate_drainage_profile(assignment, target, network, _slope_requirement())
    assert evaluation.status == DrainageStatus.PASS
    assert evaluation.average_slope_percent is None
    assert any("purely vertical" in item for item in evaluation.warnings)


def test_unsourced_numeric_slope_requirement_is_rejected():
    with pytest.raises(ValueError, match="source_ref"):
        load_drainage_profile_brief(
            json.dumps(
                {
                    "schema": "nitikube.drainage_profile_brief",
                    "requirements": [
                        {
                            "service_requirement_id": "basin-drain",
                            "min_slope_percent": 1.0,
                            "source_ref": "",
                        }
                    ],
                }
            )
        )


def test_artifact_pipeline_preserves_source_and_pass_fail_math():
    network = _profile_network()
    point = ServicePoint("drain-point", "b1", ServiceKind.DRAIN, 0.0, 5.0, z_ft=2.90)
    target = ServiceTarget("basin", "Basin waste", "b1", 0.0, 0.0, z_ft=3.0)
    service_requirement = ServiceRequirement("basin-drain", "basin", (ServiceKind.DRAIN,), max_route_ft=20.0)
    routing = evaluate_network_routing(
        (point,),
        (target,),
        (service_requirement,),
        network,
        NetworkRoutingPolicy(max_target_access_ft=1.1, distance_mode="3d"),
    )
    routing_brief = json.dumps(
        {
            "schema": "nitikube.service_routing_brief",
            "distance_mode": "3d",
            "targets": [
                {
                    "target_id": "basin",
                    "label": "Basin waste",
                    "room_id": "b1",
                    "x_ft": 0.0,
                    "y_ft": 0.0,
                    "z_ft": 3.0,
                }
            ],
            "requirements": [
                {
                    "requirement_id": "basin-drain",
                    "target_id": "basin",
                    "allowed_kinds": ["drain"],
                    "max_route_ft": 20.0,
                    "required": True,
                }
            ],
        }
    )
    drainage_brief = json.dumps(
        {
            "schema": "nitikube.drainage_profile_brief",
            "requirements": [
                {
                    "service_requirement_id": "basin-drain",
                    "min_slope_percent": 1.0,
                    "source_ref": "professional:plumbing-note-17",
                }
            ],
        }
    )
    evaluations = evaluate_drainage_artifacts(
        service_network_json(network),
        network_routing_result_json(routing),
        routing_brief,
        drainage_brief,
    )
    assert len(evaluations) == 1
    assert evaluations[0].status == DrainageStatus.PASS
    exported = json.loads(drainage_profile_evaluation_json(evaluations))
    assert exported["schema"] == "nitikube.drainage_profile_evaluation"
    assert exported["results"][0]["source_ref"] == "professional:plumbing-note-17"
    assert exported["results"][0]["segments"][0]["slope_percent"] == pytest.approx(2.0)


def test_template_leaves_numeric_threshold_and_source_empty():
    template = json.loads(drainage_profile_brief_template())
    row = template["requirements"][0]
    assert row["min_slope_percent"] is None
    assert row["source_ref"] is None
