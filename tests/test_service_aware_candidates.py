import json

from nitikube.bedroom_planner import (
    BedSpec,
    WardrobeSpec,
    generate_bedroom_candidates,
)
from nitikube.kitchen_planner import (
    KitchenLayoutKind,
    KitchenRequirements,
    WorkCenterSpec,
    generate_kitchen_candidates,
)
from nitikube.room_layout import Rect
from nitikube.service_aware_candidates import (
    CandidateServiceRuleSet,
    candidate_service_rules_from_dict,
    candidate_service_rules_json,
    evaluate_bedroom_candidate_with_services,
    evaluate_candidate_services,
    evaluate_kitchen_candidate_with_services,
    load_candidate_service_rules_json,
    rank_service_aware_kitchens,
    service_aware_evaluation_json,
)
from nitikube.service_points import (
    ServiceKind,
    ServicePoint,
    ServiceRequirement,
    ServiceTarget,
)


def _kitchen_candidates(room):
    sink = WorkCenterSpec("sink", "Sink", 2.0, 2.5)
    hob = WorkCenterSpec("hob", "Hob", 2.0, 2.5)
    fridge = WorkCenterSpec("fridge", "Fridge", 2.0, 2.5)
    return generate_kitchen_candidates(
        room,
        counter_depth_ft=2.5,
        wall_margin_ft=0.0,
        sink=sink,
        hob=hob,
        fridge=fridge,
        include_kinds=(KitchenLayoutKind.ONE_WALL,),
    )


def test_candidate_service_rule_schema_roundtrip():
    payload = {
        "schema": "nitikube.candidate_service_rules",
        "allow_shared_points": False,
        "distance_mode": "plan",
        "requirements": [
            {
                "requirement_id": "sink-water",
                "target_id": "sink",
                "allowed_kinds": ["cold_water", "hot_water"],
                "max_route_ft": 4.0,
                "required": True,
            }
        ],
    }
    rules = candidate_service_rules_from_dict(payload)
    assert rules.requirements[0].allowed_kinds == (ServiceKind.COLD_WATER, ServiceKind.HOT_WATER)
    loaded = load_candidate_service_rules_json(candidate_service_rules_json(rules))
    assert loaded == rules


def test_missing_required_target_fails_this_candidate_without_throwing():
    rules = CandidateServiceRuleSet(
        requirements=(
            ServiceRequirement("desk-power", "desk", (ServiceKind.ELECTRICAL,), required=True),
        )
    )
    result = evaluate_candidate_services(
        (ServicePoint("e1", "bed1", ServiceKind.ELECTRICAL, 1, 1),),
        (ServiceTarget("bed", "Bed", "bed1", 2, 2),),
        rules,
    )
    assert not result.feasible
    assert result.assignments == ()
    assert "desk-power:target_absent_from_candidate" in result.failed


def test_missing_optional_target_is_warning_not_failure():
    rules = CandidateServiceRuleSet(
        requirements=(
            ServiceRequirement("desk-data", "desk", (ServiceKind.DATA,), required=False),
        )
    )
    result = evaluate_candidate_services((), (ServiceTarget("bed", "Bed", "bed1", 2, 2),), rules)
    assert result.feasible
    assert result.failed == ()
    assert "optional_target_absent_from_candidate" in result.warnings[0]


def test_kitchen_candidate_service_constraint_can_reject_otherwise_geometric_candidate():
    room = Rect(0, 0, 20, 16)
    candidates = _kitchen_candidates(room)
    top = next(candidate for candidate in candidates if candidate.name.endswith("top"))
    bottom = next(candidate for candidate in candidates if candidate.name.endswith("bottom"))
    top_sink = next(center for center in top.work_centers if center.spec.center_id == "sink").center
    points = (
        ServicePoint("cold-1", "k1", ServiceKind.COLD_WATER, top_sink[0], top_sink[1]),
    )
    rules = CandidateServiceRuleSet(
        requirements=(
            ServiceRequirement("sink-water", "sink", (ServiceKind.COLD_WATER,), max_route_ft=2.0),
        )
    )

    top_result = evaluate_kitchen_candidate_with_services(room, "k1", top, points, rules)
    bottom_result = evaluate_kitchen_candidate_with_services(room, "k1", bottom, points, rules)
    assert top_result.geometry.feasible
    assert top_result.services.feasible
    assert top_result.evaluation.overall_feasible
    assert bottom_result.geometry.feasible
    assert not bottom_result.services.feasible
    assert not bottom_result.evaluation.overall_feasible
    assert bottom_result.evaluation.geometry_score == bottom_result.geometry.geometry_score


def test_service_aware_kitchen_ranking_puts_overall_feasible_candidate_first():
    room = Rect(0, 0, 20, 16)
    candidates = _kitchen_candidates(room)
    top = next(candidate for candidate in candidates if candidate.name.endswith("top"))
    top_sink = next(center for center in top.work_centers if center.spec.center_id == "sink").center
    points = (ServicePoint("water", "k1", ServiceKind.COLD_WATER, *top_sink),)
    rules = CandidateServiceRuleSet(
        requirements=(ServiceRequirement("sink-water", "sink", (ServiceKind.COLD_WATER,), max_route_ft=1.0),)
    )
    ranked = rank_service_aware_kitchens(room, "k1", candidates, points, rules)
    assert ranked[0].evaluation.overall_feasible
    assert ranked[0].candidate.name.endswith("top")
    assert any(not item.evaluation.overall_feasible for item in ranked[1:])


def test_geometry_failure_cannot_be_rescued_by_perfect_service_assignment():
    room = Rect(0, 0, 20, 16)
    top = next(candidate for candidate in _kitchen_candidates(room) if candidate.name.endswith("top"))
    sink_xy = next(center for center in top.work_centers if center.spec.center_id == "sink").center
    points = (ServicePoint("water", "k1", ServiceKind.COLD_WATER, *sink_xy),)
    rules = CandidateServiceRuleSet(
        requirements=(ServiceRequirement("sink-water", "sink", (ServiceKind.COLD_WATER,)),)
    )
    geometry_fail = KitchenRequirements(min_counter_run_ft=100.0)
    result = evaluate_kitchen_candidate_with_services(
        room,
        "k1",
        top,
        points,
        rules,
        requirements=geometry_fail,
    )
    assert not result.geometry.feasible
    assert result.services.feasible
    assert not result.evaluation.overall_feasible


def test_bedroom_candidate_without_desk_fails_required_desk_service_rule():
    room = Rect(0, 0, 14, 14)
    wardrobe = WardrobeSpec(6, 2, 7)
    candidate = generate_bedroom_candidates(
        room,
        bed=BedSpec(5, 6.5),
        wardrobe=wardrobe,
        desk=None,
        wall_margin_ft=0,
    )[0]
    rules = CandidateServiceRuleSet(
        requirements=(ServiceRequirement("desk-power", "desk", (ServiceKind.ELECTRICAL,)),)
    )
    result = evaluate_bedroom_candidate_with_services(
        room,
        "bed1",
        candidate,
        wardrobe,
        (),
        rules,
    )
    assert result.geometry.feasible
    assert not result.services.feasible
    assert not result.evaluation.overall_feasible
    assert "target_absent_from_candidate" in result.evaluation.service_failed[0]


def test_service_aware_evaluation_export_preserves_separate_geometry_and_service_states():
    room = Rect(0, 0, 20, 16)
    top = next(candidate for candidate in _kitchen_candidates(room) if candidate.name.endswith("top"))
    sink_xy = next(center for center in top.work_centers if center.spec.center_id == "sink").center
    rules = CandidateServiceRuleSet(
        requirements=(ServiceRequirement("sink-water", "sink", (ServiceKind.COLD_WATER,)),)
    )
    result = evaluate_kitchen_candidate_with_services(
        room,
        "k1",
        top,
        (ServicePoint("water", "k1", ServiceKind.COLD_WATER, *sink_xy),),
        rules,
    )
    payload = json.loads(service_aware_evaluation_json(result.evaluation))
    assert payload["schema"] == "nitikube.service_aware_candidate_evaluation"
    assert payload["geometry_feasible"] is True
    assert payload["service_feasible"] is True
    assert payload["overall_feasible"] is True
    assert "straight-line lower-bound" in payload["model_boundary"]
