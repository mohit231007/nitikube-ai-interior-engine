import pytest

from nitikube.room_layout import (
    FurnitureSpec,
    KeepoutZone,
    LayoutCandidate,
    LayoutRequirements,
    OpeningSegment,
    PlacedFurniture,
    Rect,
    circulation_metrics,
    evaluate_layout,
    generate_drawing_dining_candidates,
    inflate_rect,
    layout_svg,
    opening_keepout,
    rank_layouts,
    rect_contains,
    rect_gap,
    rect_overlap,
)


def test_rectangle_primitives_are_deterministic():
    room = Rect(0, 0, 10, 20)
    item = Rect(1, 2, 3, 4)
    assert room.area_ft2 == pytest.approx(200)
    assert item.center == pytest.approx((2.5, 4.0))
    assert rect_contains(room, item)
    assert rect_contains(room, inflate_rect(item, 1.0))
    assert rect_overlap(Rect(0, 0, 2, 2), Rect(1, 1, 2, 2))
    assert not rect_overlap(Rect(0, 0, 2, 2), Rect(2, 0, 2, 2))
    assert rect_gap(Rect(0, 0, 2, 2), Rect(3, 0, 2, 2)) == pytest.approx(1.0)


def test_opening_keepout_is_projected_inward_from_each_wall():
    room = Rect(0, 0, 10, 20)
    top = OpeningSegment("D-top", (2, 0), (5, 0), "door")
    bottom = OpeningSegment("D-bottom", (2, 20), (5, 20), "door")
    left = OpeningSegment("D-left", (0, 5), (0, 8), "door")
    right = OpeningSegment("D-right", (10, 5), (10, 8), "door")

    assert opening_keepout(room, top, inward_depth_ft=3).rect == Rect(2, 0, 3, 3)
    assert opening_keepout(room, bottom, inward_depth_ft=3).rect == Rect(2, 17, 3, 3)
    assert opening_keepout(room, left, inward_depth_ft=3).rect == Rect(0, 5, 3, 3)
    assert opening_keepout(room, right, inward_depth_ft=3).rect == Rect(7, 5, 3, 3)


def test_non_wall_opening_is_rejected():
    room = Rect(0, 0, 10, 20)
    with pytest.raises(ValueError, match="not on a room boundary"):
        opening_keepout(room, OpeningSegment("D", (2, 5), (5, 5)), inward_depth_ft=3)


def test_layout_collision_and_keepout_are_hard_failures():
    room = Rect(0, 0, 10, 10)
    sofa = FurnitureSpec("sofa", "Sofa", 4, 2)
    table = FurnitureSpec("table", "Table", 3, 2)
    candidate = LayoutCandidate(
        "L1",
        "Collision",
        (
            PlacedFurniture(sofa, 1, 1, 0),
            PlacedFurniture(table, 3, 2, 0),
        ),
    )
    keepout = KeepoutZone("door", "Door", Rect(0, 0, 2, 3))
    evaluation = evaluate_layout(room, candidate, keepouts=[keepout])
    assert evaluation.feasible is False
    assert any(item.startswith("furniture_collision") for item in evaluation.failed)
    assert any(item.startswith("keepout_collision") for item in evaluation.failed)
    assert evaluation.geometry_score <= 49.99


def test_reserved_clearance_must_fit_inside_room_when_enabled():
    room = Rect(0, 0, 10, 10)
    spec = FurnitureSpec("cabinet", "Cabinet", 2, 2, clearance_ft=1)
    candidate = LayoutCandidate("L1", "Edge", (PlacedFurniture(spec, 0, 0, 0),))
    evaluation = evaluate_layout(room, candidate)
    assert evaluation.feasible is False
    assert "reserved_clearance_outside_room:cabinet" in evaluation.failed


def test_pair_gap_requirement_is_explicit():
    room = Rect(0, 0, 10, 10)
    a = FurnitureSpec("a", "A", 2, 2)
    b = FurnitureSpec("b", "B", 2, 2)
    candidate = LayoutCandidate("L1", "Gap", (PlacedFurniture(a, 1, 1), PlacedFurniture(b, 3.5, 1)))
    loose = evaluate_layout(room, candidate, requirements=LayoutRequirements(min_pair_gap_ft=0.25))
    strict = evaluate_layout(room, candidate, requirements=LayoutRequirements(min_pair_gap_ft=1.0))
    assert loose.feasible is True
    assert loose.minimum_pair_gap_ft == pytest.approx(0.5)
    assert strict.feasible is False
    assert any(item.startswith("pair_gap") for item in strict.failed)


def test_circulation_metrics_detect_fragmented_walkable_space():
    room = Rect(0, 0, 10, 10)
    # A full-height central barrier splits the room into two components.
    barrier = Rect(4.5, 0, 1.0, 10.0)
    largest, walkable = circulation_metrics(room, [barrier], passage_width_ft=0.0, grid_step_ft=0.5)
    assert 0.45 <= largest <= 0.55
    assert 0.85 <= walkable <= 0.95


def test_benchmark_generator_creates_eight_deterministic_variants_and_feasible_subset():
    room = Rect(0, 0, 10 + 7 / 12, 22 + 9 / 12)
    sofa = FurnitureSpec("sofa", "Sofa", 7, 3, 0.25)
    tv = FurnitureSpec("tv", "TV", 5, 1.25, 0.25)
    coffee = FurnitureSpec("coffee", "Coffee", 4, 2, 0.0)
    dining = FurnitureSpec("dining", "Dining", 6, 3, 2.0)
    candidates = generate_drawing_dining_candidates(
        room,
        sofa=sofa,
        tv_console=tv,
        coffee_table=coffee,
        dining_table=dining,
        living_fraction=0.58,
        zone_gap_ft=0.5,
        wall_margin_ft=0.25,
    )
    assert len(candidates) == 8
    assert len({candidate.layout_id for candidate in candidates}) == 8

    ranked = rank_layouts(
        room,
        candidates,
        requirements=LayoutRequirements(
            wall_margin_ft=0.25,
            min_pair_gap_ft=0.0,
            passage_width_ft=0.0,
        ),
    )
    assert any(evaluation.feasible for _, evaluation in ranked)
    assert ranked[0][1].feasible is True


def test_door_keepout_can_reject_otherwise_valid_generated_layout():
    room = Rect(0, 0, 10, 20)
    sofa = FurnitureSpec("sofa", "Sofa", 7, 3)
    tv = FurnitureSpec("tv", "TV", 5, 1)
    coffee = FurnitureSpec("coffee", "Coffee", 3, 2)
    dining = FurnitureSpec("dining", "Dining", 5, 3)
    candidates = generate_drawing_dining_candidates(
        room,
        sofa=sofa,
        tv_console=tv,
        coffee_table=coffee,
        dining_table=dining,
        wall_margin_ft=0.0,
    )
    # Entire room as a keepout guarantees every placement is rejected.
    keepout = KeepoutZone("construction", "Construction keepout", room)
    ranked = rank_layouts(room, candidates, keepouts=[keepout])
    assert all(not evaluation.feasible for _, evaluation in ranked)
    assert all(any(failure.startswith("keepout_collision") for failure in evaluation.failed) for _, evaluation in ranked)


def test_layout_svg_contains_zones_furniture_and_status():
    room = Rect(0, 0, 10, 20)
    sofa = FurnitureSpec("sofa", "Sofa & Lounge", 4, 2)
    candidate = LayoutCandidate(
        "L1",
        "Test <Layout>",
        (PlacedFurniture(sofa, 1, 1),),
        zones=(("Living", Rect(0, 0, 10, 10)),),
    )
    evaluation = evaluate_layout(room, candidate)
    svg = layout_svg(room, candidate, evaluation)
    assert svg.startswith("<svg")
    assert "Test &lt;Layout&gt;" in svg
    assert "Sofa &amp; Lounge" in svg
    assert "FEASIBLE" in svg
    assert "Living" in svg
