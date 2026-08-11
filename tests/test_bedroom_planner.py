import pytest

from nitikube.bedroom_planner import (
    BedSpec,
    BedroomRequirements,
    DeskSpec,
    WardrobeSpec,
    bed_clearance_zones,
    bed_placement,
    bedroom_svg,
    evaluate_bedroom,
    generate_bedroom_candidates,
    rank_bedrooms,
    wardrobe_front_zone,
    wardrobe_placement,
)
from nitikube.room_layout import KeepoutZone, Rect


def test_wall_placements_rotate_geometry_correctly():
    room = Rect(0, 0, 12, 14)
    bed = BedSpec(6, 6.5)
    top = bed_placement(room, "top", bed)
    left = bed_placement(room, "left", bed)
    assert top.rect == Rect(3, 0, 6, 6.5)
    assert left.rect == Rect(0, 4, 6.5, 6)

    wardrobe = WardrobeSpec(6, 2, 8)
    bottom = wardrobe_placement(room, "bottom", wardrobe)
    right = wardrobe_placement(room, "right", wardrobe)
    assert bottom.rect == Rect(3, 12, 6, 2)
    assert right.rect == Rect(10, 4, 2, 6)


def test_oversize_bed_or_wardrobe_fails_closed():
    room = Rect(0, 0, 8, 10)
    with pytest.raises(ValueError, match="does not fit"):
        bed_placement(room, "top", BedSpec(9, 6))
    with pytest.raises(ValueError, match="does not fit"):
        wardrobe_placement(room, "left", WardrobeSpec(11, 2, 8))


def test_bed_clearance_zones_are_directional_not_behind_headboard():
    room = Rect(0, 0, 12, 14)
    top = bed_placement(room, "top", BedSpec(6, 6.5))
    zones = bed_clearance_zones(room, top, side_clearance_ft=2, foot_clearance_ft=2.5)
    assert len(zones) == 3
    # No zone extends behind the top-wall headboard into negative y.
    assert all(zone.y_ft >= 0 for zone in zones)
    assert any(zone.y_ft == pytest.approx(6.5) and zone.depth_ft == pytest.approx(2.5) for zone in zones)


def test_wardrobe_front_zone_extends_into_room():
    room = Rect(0, 0, 12, 14)
    wardrobe = wardrobe_placement(room, "right", WardrobeSpec(6, 2, 8))
    zone = wardrobe_front_zone(room, wardrobe, clearance_ft=3)
    assert zone == Rect(7, 4, 3, 6)


def test_generator_produces_expected_wall_variants_with_and_without_desk():
    room = Rect(0, 0, 12, 14)
    bed, wardrobe = BedSpec(6, 6.5), WardrobeSpec(6, 2, 8)
    no_desk = generate_bedroom_candidates(room, bed=bed, wardrobe=wardrobe)
    assert len(no_desk) == 12  # 4 bed walls × 3 different wardrobe walls
    with_desk = generate_bedroom_candidates(room, bed=bed, wardrobe=wardrobe, desk=DeskSpec(4, 2))
    assert len(with_desk) == 24  # 2 remaining desk walls per bed/wardrobe pair
    assert len({candidate.layout_id for candidate in with_desk}) == 24


def test_physical_furniture_collision_is_hard_failure():
    room = Rect(0, 0, 8, 9)
    bed, wardrobe = BedSpec(6, 6.5), WardrobeSpec(6, 2, 8)
    candidates = generate_bedroom_candidates(room, bed=bed, wardrobe=wardrobe)
    assert candidates
    evaluations = [evaluate_bedroom(room, candidate, wardrobe) for candidate in candidates]
    assert any(any(failure.startswith("furniture_collision") for failure in e.failed) for e in evaluations)


def test_bed_and_wardrobe_clearance_can_reject_otherwise_physical_fit():
    room = Rect(0, 0, 12, 14)
    bed, wardrobe = BedSpec(6, 6.5), WardrobeSpec(6, 2, 8)
    candidate = next(c for c in generate_bedroom_candidates(room, bed=bed, wardrobe=wardrobe) if c.bed.wall == "top" and c.wardrobe.wall == "bottom")
    physical = evaluate_bedroom(room, candidate, wardrobe, requirements=BedroomRequirements())
    assert physical.feasible
    strict = evaluate_bedroom(room, candidate, wardrobe, requirements=BedroomRequirements(
        side_clearance_ft=3.5,
        foot_clearance_ft=4,
        wardrobe_front_clearance_ft=4,
    ))
    assert not strict.feasible
    assert any("clearance" in failure for failure in strict.failed)


def test_opening_keepout_collision_is_hard_failure():
    room = Rect(0, 0, 12, 14)
    bed, wardrobe = BedSpec(6, 6.5), WardrobeSpec(6, 2, 8)
    candidate = next(c for c in generate_bedroom_candidates(room, bed=bed, wardrobe=wardrobe) if c.bed.wall == "top")
    keepout = KeepoutZone("door", "Door", Rect(4, 0, 4, 3))
    result = evaluate_bedroom(room, candidate, wardrobe, keepouts=[keepout])
    assert not result.feasible
    assert "keepout_collision:bed:door" in result.failed


def test_wardrobe_storage_quantities_are_geometric():
    room = Rect(0, 0, 12, 14)
    bed, wardrobe = BedSpec(6, 6.5), WardrobeSpec(6, 2, 8)
    candidate = generate_bedroom_candidates(room, bed=bed, wardrobe=wardrobe)[0]
    result = evaluate_bedroom(room, candidate, wardrobe)
    assert result.wardrobe_run_ft == pytest.approx(6)
    assert result.wardrobe_front_area_ft2 == pytest.approx(48)
    assert result.wardrobe_internal_volume_ft3 == pytest.approx(96)


def test_requested_passage_width_can_make_layout_non_feasible():
    room = Rect(0, 0, 8, 10)
    bed, wardrobe = BedSpec(6, 6.5), WardrobeSpec(6, 2, 8)
    candidates = generate_bedroom_candidates(room, bed=bed, wardrobe=wardrobe)
    ranked = rank_bedrooms(room, candidates, wardrobe, requirements=BedroomRequirements(
        passage_width_ft=4.0,
        grid_step_ft=0.25,
        require_connected_passage=True,
    ))
    assert ranked
    assert any(not evaluation.feasible for _, evaluation in ranked)


def test_ranking_places_feasible_layouts_before_failed_layouts():
    room = Rect(0, 0, 12, 14)
    bed, wardrobe = BedSpec(6, 6.5), WardrobeSpec(6, 2, 8)
    ranked = rank_bedrooms(room, generate_bedroom_candidates(room, bed=bed, wardrobe=wardrobe), wardrobe)
    flags = [evaluation.feasible for _, evaluation in ranked]
    if False in flags:
        first_false = flags.index(False)
        assert all(flags[:first_false])


def test_svg_contains_core_furniture_and_status():
    room = Rect(0, 0, 12, 14)
    bed, wardrobe = BedSpec(6, 6.5), WardrobeSpec(6, 2, 8)
    candidate = generate_bedroom_candidates(room, bed=bed, wardrobe=wardrobe, desk=DeskSpec(4, 2))[0]
    result = evaluate_bedroom(room, candidate, wardrobe)
    svg = bedroom_svg(room, candidate, result)
    assert svg.startswith("<svg")
    assert "Bed" in svg and "Wardrobe" in svg and "Desk" in svg
    assert "Status:" in svg
