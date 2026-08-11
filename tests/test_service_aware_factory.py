import json

from nitikube.project_orchestrator import verify_design_package_hash
from nitikube.service_aware_factory import (
    build_service_aware_whole_home_candidates,
    service_aware_factory_audit_json,
)
from nitikube.service_points import ServiceKind, ServicePoint, service_points_json
from nitikube.verified_geometry import geometry_to_project_json, rectangle_room


def _scores(value=75.0):
    return {
        "quality": value,
        "durability": value,
        "aesthetics": value,
        "comfort": value,
        "maintainability": value,
    }


def _kitchen_profile(max_route_ft=2.0, with_service_rules=True):
    profile = {
        "role": "kitchen",
        "planner": {
            "counter_depth_ft": 2.5,
            "wall_margin_ft": 0.0,
            "sink": {"width_ft": 2.0, "depth_ft": 2.5},
            "hob": {"width_ft": 2.0, "depth_ft": 2.5},
            "fridge": {"width_ft": 2.0, "depth_ft": 2.5},
            "include_kinds": ["one_wall"],
        },
        "requirements": {"passage_width_ft": 0.0},
        "decision_scores": _scores(),
        "cost_model": {
            "fixed_cost": 100000.0,
            "metric_rates": {
                "counter_run_ft": 1000.0,
                "countertop_area_ft2": 500.0,
            },
        },
    }
    if with_service_rules:
        profile["service_rules"] = {
            "schema": "nitikube.candidate_service_rules",
            "distance_mode": "plan",
            "allow_shared_points": False,
            "requirements": [
                {
                    "requirement_id": "sink-water",
                    "target_id": "sink",
                    "allowed_kinds": ["cold_water"],
                    "max_route_ft": max_route_ft,
                    "required": True,
                }
            ],
        }
    return profile


def _geometry():
    room = rectangle_room("k1", "Kitchen", 0, 0, 20, 16, 9)
    return geometry_to_project_json("Service Aware Home", [room])


def _service_points_at_top_sink():
    # One-wall top counter depth=2.5. Sink is centered on the top run, so its
    # deterministic target centre is (10, 1.25) for the 20×16 room.
    return service_points_json(
        (
            ServicePoint(
                "cold-top",
                "k1",
                ServiceKind.COLD_WATER,
                10.0,
                1.25,
                verified=True,
                source="site_survey",
            ),
        )
    )


def test_service_aware_factory_filters_options_before_optimization_and_hashes_service_evidence():
    brief = {
        "schema": "nitikube.service_aware_whole_home_brief",
        "schema_version": "0.26",
        "required_room_ids": ["k1"],
        "rooms": {"k1": _kitchen_profile(max_route_ft=2.0)},
        "professional_verification_flags": ["Confirm final plumbing route with qualified professional"],
        "optimization": {
            "budget": 250000.0,
            "reserve": 10000.0,
            "created_at": "2026-08-12T00:00:00+00:00",
        },
    }
    result = build_service_aware_whole_home_candidates(
        _geometry(),
        brief,
        _service_points_at_top_sink(),
    )
    assert result.optimizer_ready
    assert len(result.room_results) == 1
    room_result = result.room_results[0]
    assert len(room_result.candidates) == 4
    assert 0 < sum(candidate.feasible for candidate in room_result.candidates) < 4
    assert any("service:" in failure for candidate in room_result.candidates for failure in candidate.failed)
    assert result.optimization is not None and result.optimization.feasible
    assert result.design_package is not None
    assert result.design_package["schema"] == "nitikube.design_package"
    assert result.design_package["schema_version"] == "0.26"
    assert result.design_package["service_points_artifact"]["kind"] == "service_points"
    assert result.design_package["service_aware_brief_artifact"]["kind"] == "service_aware_whole_home_brief"
    assert verify_design_package_hash(result.design_package)
    selected_id = result.optimization.selected[0].option_id
    selected_option = next(option for option in result.optimizer_options if option.option_id == selected_id)
    assert selected_option.feasible


def test_service_constraints_can_block_every_candidate_and_prevent_optimization():
    brief = {
        "schema": "nitikube.service_aware_whole_home_brief",
        "required_room_ids": ["k1"],
        "rooms": {"k1": _kitchen_profile(max_route_ft=0.01)},
        "optimization": {"budget": 250000.0},
    }
    # Service point is valid and in-room but no candidate sink target lies within 0.01 ft.
    points = service_points_json(
        (ServicePoint("cold-corner", "k1", ServiceKind.COLD_WATER, 0.0, 0.0),)
    )
    result = build_service_aware_whole_home_candidates(_geometry(), brief, points)
    assert not result.optimizer_ready
    assert result.optimization is None
    assert result.design_package is None
    assert result.room_results[0].status == "service_blocked"
    assert all(not candidate.feasible for candidate in result.room_results[0].candidates)
    assert any("lack a feasible optimizer option" in item for item in result.diagnostics)


def test_room_without_service_rules_is_explicitly_not_evaluated_not_fake_pass():
    brief = {
        "required_room_ids": ["k1"],
        "rooms": {"k1": _kitchen_profile(with_service_rules=False)},
    }
    result = build_service_aware_whole_home_candidates(
        _geometry(),
        brief,
        _service_points_at_top_sink(),
    )
    audit = result.room_service_audits[0]
    assert audit.service_status == "not_configured"
    assert audit.service_rule_count == 0
    assert audit.candidates_checked == 0
    assert "not evaluated" in audit.notes[0]
    assert result.optimizer_options


def test_service_metrics_are_added_only_after_service_evaluation():
    brief = {
        "required_room_ids": ["k1"],
        "rooms": {"k1": _kitchen_profile(max_route_ft=100.0)},
    }
    result = build_service_aware_whole_home_candidates(
        _geometry(),
        brief,
        _service_points_at_top_sink(),
    )
    candidates = result.room_results[0].candidates
    assert candidates
    assert all("service_total_route_ft" in candidate.metrics for candidate in candidates)
    assert all("service_evaluated" in candidate.features for candidate in candidates)
    assert all(any("straight-line lower bounds" in note for note in candidate.notes) for candidate in candidates)


def test_factory_audit_exposes_service_evidence_hashes_and_room_counts():
    brief = {
        "required_room_ids": ["k1"],
        "rooms": {"k1": _kitchen_profile(max_route_ft=2.0)},
    }
    result = build_service_aware_whole_home_candidates(
        _geometry(),
        brief,
        _service_points_at_top_sink(),
    )
    payload = json.loads(service_aware_factory_audit_json(result))
    assert payload["schema"] == "nitikube.service_aware_whole_home_factory_audit"
    assert len(payload["artifacts"]["geometry_sha256"]) == 64
    assert len(payload["artifacts"]["service_points_sha256"]) == 64
    assert len(payload["artifacts"]["brief_sha256"]) == 64
    assert payload["rooms"][0]["service_status"] == "evaluated"
    assert payload["rooms"][0]["service_candidates_checked"] == 4
