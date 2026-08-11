import json

from nitikube.kitchen_planner import WorkCenterSpec, generate_kitchen_candidates
from nitikube.room_layout import Rect
from nitikube.service_points import (
    ServiceKind,
    ServicePoint,
    ServiceRequirement,
    ServiceTarget,
    evaluate_service_routing,
    kitchen_service_targets,
    load_service_points_json,
    load_service_routing_brief,
    point_in_room,
    service_points_json,
)
from nitikube.verified_geometry import VerifiedRoom, rectangle_room


def test_point_in_room_supports_boundary_and_concave_verified_polygon():
    room = VerifiedRoom(
        room_id="r1",
        name="L room",
        polygon_ft=((0, 0), (10, 0), (10, 4), (5, 4), (5, 10), (0, 10)),
        ceiling_height_ft=9,
        verified=True,
    )
    assert point_in_room((1, 1), room)
    assert point_in_room((0, 5), room)
    assert point_in_room((4, 8), room)
    assert not point_in_room((8, 8), room)


def test_service_point_json_roundtrip_and_room_validation():
    room = rectangle_room("k1", "Kitchen", 0, 0, 12, 10, 9)
    points = (
        ServicePoint("e1", "k1", ServiceKind.ELECTRICAL, 1.0, 1.0, source="site_survey"),
        ServicePoint("w1", "k1", ServiceKind.COLD_WATER, 2.0, 1.0, source="site_survey"),
    )
    payload = service_points_json(points)
    loaded = load_service_points_json(payload, rooms=[room])
    assert loaded == points

    bad = json.loads(payload)
    bad["points"][0]["x_ft"] = 99
    try:
        load_service_points_json(json.dumps(bad), rooms=[room])
    except ValueError as exc:
        assert "outside verified room" in str(exc)
    else:
        raise AssertionError("outside service point must fail validation")


def test_shared_points_can_be_allowed_explicitly():
    point = ServicePoint("e1", "r1", ServiceKind.ELECTRICAL, 0, 0)
    targets = (
        ServiceTarget("a", "A", "r1", 1, 0),
        ServiceTarget("b", "B", "r1", 2, 0),
    )
    requirements = (
        ServiceRequirement("ra", "a", (ServiceKind.ELECTRICAL,)),
        ServiceRequirement("rb", "b", (ServiceKind.ELECTRICAL,)),
    )
    blocked = evaluate_service_routing((point,), targets, requirements, allow_shared_points=False)
    assert not blocked.feasible
    assert "required_service_points_cannot_be_assigned_uniquely" in blocked.failed

    shared = evaluate_service_routing((point,), targets, requirements, allow_shared_points=True)
    assert shared.feasible
    assert len(shared.assignments) == 2
    assert {row.point_id for row in shared.assignments} == {"e1"}


def test_unique_assignment_uses_exact_minimum_total_distance_not_greedy_reuse():
    points = (
        ServicePoint("p1", "r1", ServiceKind.ELECTRICAL, 0, 0),
        ServicePoint("p2", "r1", ServiceKind.ELECTRICAL, 10, 0),
    )
    targets = (
        ServiceTarget("a", "A", "r1", 4, 0),
        ServiceTarget("b", "B", "r1", 1, 0),
    )
    requirements = (
        ServiceRequirement("ra", "a", (ServiceKind.ELECTRICAL,)),
        ServiceRequirement("rb", "b", (ServiceKind.ELECTRICAL,)),
    )
    result = evaluate_service_routing(points, targets, requirements, allow_shared_points=False)
    assert result.feasible
    mapping = {row.requirement_id: row.point_id for row in result.assignments}
    assert mapping == {"ra": "p2", "rb": "p1"}
    assert result.total_route_ft == 7.0


def test_max_route_and_3d_unknown_fail_closed_for_required_service():
    points = (ServicePoint("d1", "r1", ServiceKind.DRAIN, 0, 0, z_ft=None),)
    target = (ServiceTarget("sink", "Sink", "r1", 5, 0, z_ft=3),)
    requirement = (ServiceRequirement("sink-drain", "sink", (ServiceKind.DRAIN,), max_route_ft=4),)
    too_far = evaluate_service_routing(points, target, requirement, distance_mode="plan")
    assert not too_far.feasible
    assert "no_matching_service_within_constraints" in too_far.failed[0]

    no_limit = (ServiceRequirement("sink-drain", "sink", (ServiceKind.DRAIN,)),)
    unknown_3d = evaluate_service_routing(points, target, no_limit, distance_mode="3d")
    assert not unknown_3d.feasible
    assert "3d_height_unknown" in unknown_3d.failed[0]


def test_optional_missing_service_is_warning_not_failure():
    target = (ServiceTarget("desk", "Desk", "r1", 1, 1),)
    requirement = (
        ServiceRequirement("desk-data", "desk", (ServiceKind.DATA,), required=False),
    )
    result = evaluate_service_routing((), target, requirement)
    assert result.feasible
    assert result.failed == ()
    assert result.warnings
    assert result.total_route_ft == 0.0


def test_routing_brief_loader_accepts_service_kind_lists():
    brief = {
        "schema": "nitikube.service_routing_brief",
        "distance_mode": "plan",
        "allow_shared_points": False,
        "targets": [
            {"target_id": "sink", "label": "Sink", "room_id": "k1", "x_ft": 5, "y_ft": 5}
        ],
        "requirements": [
            {
                "requirement_id": "sink-water",
                "target_id": "sink",
                "allowed_kinds": ["cold_water", "hot_water"],
                "max_route_ft": 6,
                "required": True,
            }
        ],
    }
    targets, requirements, allow_shared, mode = load_service_routing_brief(json.dumps(brief))
    assert targets[0].target_id == "sink"
    assert requirements[0].allowed_kinds == (ServiceKind.COLD_WATER, ServiceKind.HOT_WATER)
    assert not allow_shared
    assert mode == "plan"


def test_kitchen_candidate_adapter_uses_actual_work_center_centres():
    room = Rect(0, 0, 18, 14)
    sink = WorkCenterSpec("sink", "Sink", 2, 2.5)
    hob = WorkCenterSpec("hob", "Hob", 2, 2.5)
    fridge = WorkCenterSpec("fridge", "Fridge", 2, 2.5)
    candidate = generate_kitchen_candidates(
        room,
        counter_depth_ft=2.5,
        wall_margin_ft=0,
        sink=sink,
        hob=hob,
        fridge=fridge,
    )[0]
    targets = kitchen_service_targets(candidate, "k1")
    assert {target.target_id for target in targets} == {"sink", "hob", "fridge"}
    centers = {center.spec.center_id: center.center for center in candidate.work_centers}
    assert {(target.target_id, (target.x_ft, target.y_ft)) for target in targets} == set(centers.items())
