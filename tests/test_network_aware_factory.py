import json

from nitikube.network_aware_factory import (
    build_network_aware_whole_home_candidates,
    network_aware_factory_audit_json,
)
from nitikube.project_orchestrator import verify_design_package_hash
from nitikube.service_network import (
    NetworkEdge,
    NetworkNode,
    ServiceNetwork,
    ServicePointAttachment,
    service_network_json,
)
from nitikube.service_points import ServiceKind, ServicePoint, service_points_json
from nitikube.verified_geometry import geometry_to_project_json, rectangle_room


def _scores(value=78.0):
    return {
        "quality": value,
        "durability": value,
        "aesthetics": value,
        "comfort": value,
        "maintainability": value,
    }


def _kitchen_profile(max_route_ft=4.1, with_service_rules=True, max_access_ft=None):
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
    if max_access_ft is not None:
        profile["network_routing"] = {"max_target_access_ft": max_access_ft}
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
    return geometry_to_project_json("Network Aware Home", [room])


def _service_points():
    return service_points_json(
        (
            ServicePoint(
                "cold-source",
                "k1",
                ServiceKind.COLD_WATER,
                14.0,
                1.25,
                verified=True,
                source="site_survey",
            ),
        )
    )


def _network():
    # The top one-wall sink target is (10, 1.25). It can enter the network at
    # top-access and must then traverse the explicit 4 ft verified wall channel.
    network = ServiceNetwork(
        nodes=(
            NetworkNode(
                "top-access",
                10.0,
                1.25,
                room_id="k1",
                route_class="wall_access",
                source="site_survey",
            ),
            NetworkNode(
                "cold-source-node",
                14.0,
                1.25,
                room_id="k1",
                route_class="service_point_node",
                can_accept_targets=False,
                source="site_survey",
            ),
        ),
        edges=(
            NetworkEdge(
                "top-wall-channel",
                "top-access",
                "cold-source-node",
                (ServiceKind.COLD_WATER,),
                explicit_length_ft=4.0,
                route_class="wall_channel",
                source="site_survey",
            ),
        ),
        attachments=(
            ServicePointAttachment(
                "cold-source",
                "cold-source-node",
                source="site_survey",
            ),
        ),
    )
    return service_network_json(network)


def _brief(*, max_route_ft=4.1, max_access_ft=0.1, with_service_rules=True, optimize=True):
    brief = {
        "schema": "nitikube.service_aware_whole_home_brief",
        "schema_version": "0.28",
        "required_room_ids": ["k1"],
        "network_routing": {
            "max_target_access_ft": max_access_ft,
            "require_verified_network": True,
            "same_room_target_access": True,
        },
        "rooms": {
            "k1": _kitchen_profile(
                max_route_ft=max_route_ft,
                with_service_rules=with_service_rules,
            )
        },
        "professional_verification_flags": [
            "Confirm final plumbing route and pipe sizing with a qualified professional"
        ],
    }
    if optimize:
        brief["optimization"] = {
            "budget": 250000.0,
            "reserve": 10000.0,
            "created_at": "2026-08-12T00:00:00+00:00",
        }
    return brief


def test_verified_network_filters_candidates_before_optimization_and_hashes_network():
    result = build_network_aware_whole_home_candidates(
        _geometry(),
        _brief(),
        _service_points(),
        _network(),
    )
    assert result.optimizer_ready
    room_result = result.room_results[0]
    assert len(room_result.candidates) == 4
    assert sum(candidate.feasible for candidate in room_result.candidates) == 1
    passing = next(candidate for candidate in room_result.candidates if candidate.feasible)
    assert passing.layout_id == "K-01"
    assert passing.metrics["service_network_total_route_ft"] == 4.0
    assert "service_network_evaluated" in passing.features
    assert result.optimization is not None and result.optimization.feasible
    assert result.design_package is not None
    assert result.design_package["schema_version"] == "0.28"
    assert result.design_package["service_network_artifact"]["kind"] == "service_network"
    assert result.design_package["service_points_artifact"]["kind"] == "service_points"
    assert result.design_package["network_aware_brief_artifact"]["kind"] == "network_aware_whole_home_brief"
    assert verify_design_package_hash(result.design_package)


def test_network_route_limit_can_block_every_candidate_and_prevent_optimization():
    result = build_network_aware_whole_home_candidates(
        _geometry(),
        _brief(max_route_ft=3.9),
        _service_points(),
        _network(),
    )
    assert not result.optimizer_ready
    assert result.optimization is None
    assert result.design_package is None
    assert result.room_results[0].status == "service_network_blocked"
    assert all(not candidate.feasible for candidate in result.room_results[0].candidates)
    assert any("verified-network filtering" in item for item in result.diagnostics)


def test_network_access_limit_is_a_hard_gate_not_a_ranking_penalty():
    # Move the allowed connector below the exact distance required by all but the
    # top candidate. With zero allowance, only exact access-node coincidence passes.
    result = build_network_aware_whole_home_candidates(
        _geometry(),
        _brief(max_access_ft=0.0, optimize=False),
        _service_points(),
        _network(),
    )
    assert sum(candidate.feasible for candidate in result.room_results[0].candidates) == 1
    assert all(
        ("service_network_total_route_ft" in candidate.metrics) == candidate.feasible
        or "service_network_total_route_ft" in candidate.metrics
        for candidate in result.room_results[0].candidates
    )


def test_room_without_service_rules_remains_explicitly_not_configured():
    result = build_network_aware_whole_home_candidates(
        _geometry(),
        _brief(with_service_rules=False, optimize=False),
        _service_points(),
        _network(),
    )
    audit = result.room_service_audits[0]
    assert audit.service_status == "not_configured"
    assert audit.candidates_checked == 0
    assert "not evaluated" in audit.notes[0]
    assert result.optimizer_options
    assert all("service_network_evaluated" not in candidate.features for candidate in result.room_results[0].candidates)


def test_missing_network_access_policy_blocks_configured_service_room_fail_closed():
    brief = _brief(optimize=False)
    brief.pop("network_routing")
    result = build_network_aware_whole_home_candidates(
        _geometry(),
        brief,
        _service_points(),
        _network(),
    )
    assert result.room_results[0].status == "blocked"
    assert result.room_service_audits[0].service_status == "blocked"
    assert not result.optimizer_ready


def test_room_level_network_policy_overrides_project_policy():
    brief = _brief(max_access_ft=0.0, optimize=False)
    brief["rooms"]["k1"]["network_routing"] = {"max_target_access_ft": 1.0}
    result = build_network_aware_whole_home_candidates(
        _geometry(),
        brief,
        _service_points(),
        _network(),
    )
    audit = result.room_service_audits[0]
    assert audit.service_status == "network_evaluated"
    assert "max_target_access_ft=1.0" in audit.notes


def test_audit_exposes_four_artifact_hashes_and_network_room_state():
    result = build_network_aware_whole_home_candidates(
        _geometry(),
        _brief(optimize=False),
        _service_points(),
        _network(),
    )
    payload = json.loads(network_aware_factory_audit_json(result))
    assert payload["schema"] == "nitikube.network_aware_whole_home_factory_audit"
    for key in (
        "geometry_sha256",
        "service_points_sha256",
        "service_network_sha256",
        "brief_sha256",
    ):
        assert len(payload["artifacts"][key]) == 64
    assert payload["rooms"][0]["service_status"] == "network_evaluated"
    assert payload["rooms"][0]["service_candidates_checked"] == 4
