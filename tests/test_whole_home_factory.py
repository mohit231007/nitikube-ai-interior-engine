import json

from nitikube.home_optimizer import load_room_options_json
from nitikube.verified_geometry import VerifiedOpening, VerifiedRoom, geometry_to_project_json, rectangle_room
from nitikube.whole_home_factory import (
    RoomRole,
    brief_template_from_geometry,
    build_whole_home_candidates,
    infer_room_role,
    room_options_json,
    verified_room_rect,
)


def _scores(value=70.0):
    return {
        "quality": value,
        "durability": value,
        "aesthetics": value,
        "comfort": value,
        "maintainability": value,
    }


def _bedroom_profile(*, with_cost=True, opening_depth=None):
    profile = {
        "role": "bedroom",
        "planner": {
            "bed": {"width_ft": 5.0, "length_ft": 6.5},
            "wardrobe": {"run_ft": 6.0, "depth_ft": 2.0, "height_ft": 7.0},
            "desk": None,
            "wall_margin_ft": 0.0,
        },
        "requirements": {
            "side_clearance_ft": 0.0,
            "foot_clearance_ft": 0.0,
            "wardrobe_front_clearance_ft": 0.0,
            "passage_width_ft": 0.0,
        },
        "decision_scores": _scores(),
        "geometry_score_blend": {"comfort": 0.5},
    }
    if with_cost:
        profile["cost_model"] = {
            "fixed_cost": 100000.0,
            "metric_rates": {"wardrobe_run_ft": 1000.0},
        }
    if opening_depth is not None:
        profile["opening_keepouts"] = {
            "inward_depth_ft": opening_depth,
            "side_padding_ft": 0.0,
            "kinds": ["door", "opening"],
        }
    return profile


def test_role_inference_is_deterministic_and_fail_closed():
    assert infer_room_role("Main Kitchen").role == RoomRole.KITCHEN
    assert infer_room_role("Master Bedroom").role == RoomRole.BEDROOM
    assert infer_room_role("Guest WC").role == RoomRole.BATHROOM
    assert infer_room_role("Living + Dining").role == RoomRole.DRAWING_DINING
    assert infer_room_role("Room 03").role is None
    assert infer_room_role("Kitchen Bedroom").role is None


def test_verified_room_rect_does_not_replace_polygon_with_bbox():
    rectangle = rectangle_room("r1", "Bedroom", 0, 0, 12, 10, 9)
    rect = verified_room_rect(rectangle)
    assert rect.width_ft == 12
    assert rect.depth_ft == 10

    l_shape = VerifiedRoom(
        room_id="r2",
        name="Bedroom",
        polygon_ft=((0, 0), (10, 0), (10, 4), (5, 4), (5, 10), (0, 10)),
        ceiling_height_ft=9,
        verified=True,
    )
    try:
        verified_room_rect(l_shape)
    except ValueError as exc:
        assert "rectangular" in str(exc)
    else:
        raise AssertionError("non-rectangular geometry must fail closed")


def test_template_preserves_unknowns_instead_of_inventing_dimensions_or_prices():
    room = rectangle_room("bed1", "Bedroom", 0, 0, 14, 14, 9)
    geometry = geometry_to_project_json("Template Demo", [room])
    template = json.loads(brief_template_from_geometry(geometry))
    assert template["rooms"]["bed1"]["role"] == "bedroom"
    assert template["rooms"]["bed1"]["planner"]["bed"]["width_ft"] is None
    assert template["rooms"]["bed1"]["cost_model"]["fixed_cost"] is None
    assert template["rooms"]["bed1"]["decision_scores"]["quality"] is None
    assert template["optimization"]["budget"] is None


def test_bedroom_factory_generates_optimizer_options_and_design_package():
    room = rectangle_room("bed1", "Bedroom", 0, 0, 14, 14, 9)
    geometry = geometry_to_project_json("Bedroom Demo", [room])
    brief = {
        "schema": "nitikube.whole_home_brief",
        "schema_version": "0.23",
        "required_room_ids": ["bed1"],
        "rooms": {"bed1": _bedroom_profile()},
        "optimization": {
            "budget": 200000.0,
            "reserve": 10000.0,
            "created_at": "2026-08-12T00:00:00+00:00",
        },
    }
    result = build_whole_home_candidates(geometry, brief)
    room_result = result.room_results[0]
    assert room_result.status == "optimizer_ready"
    assert len(room_result.candidates) == 12
    assert room_result.feasible_candidate_count > 0
    assert len(result.optimizer_options) == 12
    assert len({option.option_id for option in result.optimizer_options}) == 12
    assert all(option.option_id.startswith("bed1::bedroom::B-") for option in result.optimizer_options)
    assert all("explicit_geometry_blend" in option.score_source for option in result.optimizer_options)
    assert result.optimization is not None and result.optimization.feasible
    assert result.design_package is not None
    assert result.design_package["schema"] == "nitikube.design_package"
    assert result.design_package["required_room_ids"] == ["bed1"]

    payload = room_options_json(result.optimizer_options, project_name=result.project_name)
    loaded = load_room_options_json(payload)
    assert len(loaded) == len(result.optimizer_options)


def test_geometry_candidates_can_exist_without_becoming_optimizer_claims():
    room = rectangle_room("bed1", "Bedroom", 0, 0, 14, 14, 9)
    geometry = geometry_to_project_json("Geometry Only", [room])
    profile = _bedroom_profile(with_cost=False)
    brief = {
        "required_room_ids": ["bed1"],
        "rooms": {"bed1": profile},
        "optimization": {"budget": 200000.0},
    }
    result = build_whole_home_candidates(geometry, brief)
    assert result.room_results[0].status == "geometry_only"
    assert len(result.room_results[0].candidates) == 12
    assert result.optimizer_options == ()
    assert result.optimization is None
    assert result.design_package is None
    assert any("lack optimizer-ready options" in item for item in result.diagnostics)


def test_verified_door_is_not_silently_ignored_without_keepout_depth():
    room = rectangle_room("bed1", "Bedroom", 0, 0, 14, 14, 9)
    door = VerifiedOpening(
        opening_id="door-1",
        kind="door",
        start_ft=(6.0, 0.0),
        end_ft=(8.0, 0.0),
        room_a="bed1",
        verified=True,
    )
    geometry = geometry_to_project_json("Door Demo", [room], [door])
    brief = {
        "required_room_ids": ["bed1"],
        "rooms": {"bed1": _bedroom_profile()},
    }
    result = build_whole_home_candidates(geometry, brief)
    assert result.room_results[0].status == "blocked"
    assert "inward_depth_ft is missing" in result.room_results[0].errors[0]

    brief["rooms"]["bed1"] = _bedroom_profile(opening_depth=2.0)
    unblocked = build_whole_home_candidates(geometry, brief)
    assert unblocked.room_results[0].status == "optimizer_ready"


def test_two_rooms_get_globally_unique_option_ids_even_when_planner_layout_ids_repeat():
    room_a = rectangle_room("bed1", "Bedroom", 0, 0, 14, 14, 9)
    room_b = rectangle_room("bed2", "Guest Bedroom", 20, 0, 14, 14, 9)
    geometry = geometry_to_project_json("Two Bedroom Demo", [room_a, room_b])
    brief = {
        "required_room_ids": ["bed1", "bed2"],
        "rooms": {"bed1": _bedroom_profile(), "bed2": _bedroom_profile()},
    }
    result = build_whole_home_candidates(geometry, brief)
    ids = [option.option_id for option in result.optimizer_options]
    assert len(ids) == 24
    assert len(set(ids)) == 24
    assert any(value.startswith("bed1::") for value in ids)
    assert any(value.startswith("bed2::") for value in ids)


def test_kitchen_dispatch_generates_all_supported_layout_families():
    room = rectangle_room("k1", "Kitchen", 0, 0, 20, 16, 9)
    geometry = geometry_to_project_json("Kitchen Demo", [room])
    brief = {
        "required_room_ids": ["k1"],
        "rooms": {
            "k1": {
                "role": "kitchen",
                "planner": {
                    "counter_depth_ft": 2.5,
                    "wall_margin_ft": 0.0,
                    "sink": {"width_ft": 2.0, "depth_ft": 2.5},
                    "hob": {"width_ft": 2.0, "depth_ft": 2.5},
                    "fridge": {"width_ft": 2.0, "depth_ft": 2.5},
                    "include_kinds": ["one_wall", "galley", "l_shape", "u_shape"],
                },
                "requirements": {"passage_width_ft": 0.0},
                "decision_scores": _scores(75),
                "cost_model": {
                    "fixed_cost": 50000.0,
                    "metric_rates": {
                        "counter_run_ft": 1000.0,
                        "countertop_area_ft2": 500.0,
                    },
                },
            }
        },
    }
    result = build_whole_home_candidates(geometry, brief)
    room_result = result.room_results[0]
    assert len(room_result.candidates) == 14
    assert len(room_result.optimizer_options) == 14
    kinds = {feature for candidate in room_result.candidates for feature in candidate.features if feature.startswith("layout_kind:")}
    assert kinds == {
        "layout_kind:one_wall",
        "layout_kind:galley",
        "layout_kind:l_shape",
        "layout_kind:u_shape",
    }
