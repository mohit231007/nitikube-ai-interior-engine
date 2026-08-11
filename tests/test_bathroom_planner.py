import pytest

from nitikube.bathroom_planner import (
    BathroomRequirements,
    FixtureSpec,
    ShowerSpec,
    bathroom_quantities,
    bathroom_svg,
    drainage_fall_inches,
    evaluate_bathroom,
    fixture_front_zone,
    generate_bathroom_candidates,
    place_fixture,
    place_shower,
    rank_bathrooms,
    required_exhaust_cfm,
)
from nitikube.room_layout import KeepoutZone, Rect


def fixture_specs():
    return (
        FixtureSpec("wc", "WC", 2.0, 2.5, 2.0),
        FixtureSpec("basin", "Basin", 2.5, 1.5, 1.5),
    )


def test_shower_corner_placement():
    room = Rect(0, 0, 7, 9)
    shower = ShowerSpec(3, 3)
    assert place_shower(room, "top_left", shower).rect == Rect(0, 0, 3, 3)
    assert place_shower(room, "top_right", shower).rect == Rect(4, 0, 3, 3)
    assert place_shower(room, "bottom_left", shower).rect == Rect(0, 6, 3, 3)
    assert place_shower(room, "bottom_right", shower).rect == Rect(4, 6, 3, 3)


def test_fixture_wall_rotation_and_front_zone():
    room = Rect(0, 0, 7, 9)
    wc, _ = fixture_specs()
    top = place_fixture(room, "top", wc)
    left = place_fixture(room, "left", wc)
    assert top.rect == Rect(2.5, 0, 2, 2.5)
    assert left.rect == Rect(0, 3.5, 2.5, 2)
    assert fixture_front_zone(top) == Rect(2.5, 2.5, 2, 2.0)
    assert fixture_front_zone(left) == Rect(2.5, 3.5, 2.0, 2)


def test_generator_creates_all_corner_wall_combinations():
    room = Rect(0, 0, 7, 9)
    wc, basin = fixture_specs()
    candidates = generate_bathroom_candidates(room, shower=ShowerSpec(3, 3), wc=wc, basin=basin)
    assert len(candidates) == 48  # 4 shower corners × 4 WC walls × 3 different basin walls
    assert len({candidate.layout_id for candidate in candidates}) == 48


def test_fixture_collision_is_hard_failure():
    room = Rect(0, 0, 7, 9)
    wc, basin = fixture_specs()
    candidates = generate_bathroom_candidates(room, shower=ShowerSpec(3, 3), wc=wc, basin=basin)
    evaluations = [evaluate_bathroom(room, candidate) for candidate in candidates]
    assert any(any(failure.startswith("fixture_collision") for failure in e.failed) for e in evaluations)


def test_opening_keepout_rejects_fixture_or_shower():
    room = Rect(0, 0, 7, 9)
    wc, basin = fixture_specs()
    candidate = next(c for c in generate_bathroom_candidates(room, shower=ShowerSpec(3, 3), wc=wc, basin=basin) if c.shower.corner == "top_left")
    result = evaluate_bathroom(room, candidate, keepouts=[KeepoutZone("door", "Door", Rect(0, 0, 3, 3))])
    assert not result.feasible
    assert "keepout_collision:shower:door" in result.failed


def test_clearance_outside_room_is_detected():
    room = Rect(0, 0, 5, 6)
    wc = FixtureSpec("wc", "WC", 2, 2, 5)
    basin = FixtureSpec("basin", "Basin", 2, 1.5, 1)
    candidates = generate_bathroom_candidates(room, shower=ShowerSpec(2, 2), wc=wc, basin=basin)
    result = evaluate_bathroom(room, candidates[0], requirements=BathroomRequirements(require_fixture_front_clearance_inside_room=True))
    assert not result.feasible
    assert any(failure.startswith("clearance_outside_room") or failure.startswith("clearance_blocked") for failure in result.failed)


def test_requested_passage_can_make_small_bathroom_non_feasible():
    room = Rect(0, 0, 5, 6)
    wc, basin = fixture_specs()
    ranked = rank_bathrooms(
        room,
        generate_bathroom_candidates(room, shower=ShowerSpec(2.5, 2.5), wc=wc, basin=basin),
        requirements=BathroomRequirements(passage_width_ft=3.0, grid_step_ft=0.2, require_connected_passage=True),
    )
    assert ranked
    assert any(not evaluation.feasible for _, evaluation in ranked)


def test_exhaust_airflow_formula_is_room_volume_times_ach_over_sixty():
    assert required_exhaust_cfm(63, 9, 8) == pytest.approx(63 * 9 * 8 / 60)
    with pytest.raises(ValueError):
        required_exhaust_cfm(63, 9, 0)


def test_drainage_fall_math():
    # 1.5% slope over 4 ft = 48 in × .015 = .72 in fall.
    assert drainage_fall_inches(4, 1.5) == pytest.approx(0.72)
    with pytest.raises(ValueError):
        drainage_fall_inches(-1, 1)


def test_tile_waterproof_exhaust_and_drain_quantities_are_explicit():
    room = Rect(0, 0, 7, 9)
    wc, basin = fixture_specs()
    candidate = generate_bathroom_candidates(room, shower=ShowerSpec(3, 3), wc=wc, basin=basin)[0]
    q = bathroom_quantities(
        room,
        candidate,
        floor_waste_fraction=0.10,
        wall_tile_height_ft=7,
        wall_opening_deduction_ft2=14,
        waterproof_floor_fraction=1.0,
        shower_wet_wall_height_ft=7,
        ceiling_height_ft=9,
        air_changes_per_hour=8,
        drainage_run_ft=4,
        drainage_slope_percent=1.5,
    )
    assert q.floor_area_ft2 == pytest.approx(63)
    assert q.floor_purchase_area_ft2 == pytest.approx(69.3)
    assert q.gross_wall_tile_area_ft2 == pytest.approx(2 * (7 + 9) * 7)
    assert q.net_wall_tile_area_ft2 == pytest.approx(q.gross_wall_tile_area_ft2 - 14)
    assert q.wet_wall_waterproof_area_ft2 == pytest.approx((3 + 3) * 7)
    assert q.floor_waterproof_area_ft2 == pytest.approx(63)
    assert q.total_waterproof_area_ft2 == pytest.approx(105)
    assert q.required_exhaust_cfm == pytest.approx(75.6)
    assert q.drainage_fall_in == pytest.approx(0.72)


def test_quantity_dependencies_fail_closed_when_half_supplied():
    room = Rect(0, 0, 7, 9)
    wc, basin = fixture_specs()
    candidate = generate_bathroom_candidates(room, shower=ShowerSpec(3, 3), wc=wc, basin=basin)[0]
    with pytest.raises(ValueError, match="both ceiling_height_ft"):
        bathroom_quantities(room, candidate, floor_waste_fraction=0, wall_tile_height_ft=0, ceiling_height_ft=9)
    with pytest.raises(ValueError, match="both drainage_run_ft"):
        bathroom_quantities(room, candidate, floor_waste_fraction=0, wall_tile_height_ft=0, drainage_run_ft=4)


def test_ranking_keeps_feasible_candidates_first():
    room = Rect(0, 0, 7, 9)
    wc, basin = fixture_specs()
    ranked = rank_bathrooms(room, generate_bathroom_candidates(room, shower=ShowerSpec(3, 3), wc=wc, basin=basin))
    flags = [evaluation.feasible for _, evaluation in ranked]
    if False in flags:
        first_false = flags.index(False)
        assert all(flags[:first_false])


def test_svg_contains_fixtures_and_status():
    room = Rect(0, 0, 7, 9)
    wc, basin = fixture_specs()
    candidate = generate_bathroom_candidates(room, shower=ShowerSpec(3, 3), wc=wc, basin=basin)[0]
    evaluation = evaluate_bathroom(room, candidate)
    svg = bathroom_svg(room, candidate, evaluation)
    assert svg.startswith("<svg")
    assert "Shower" in svg and "WC" in svg and "Basin" in svg
    assert "Status:" in svg
