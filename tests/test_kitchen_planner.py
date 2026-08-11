import pytest

from nitikube.kitchen_planner import (
    KitchenLayoutKind,
    KitchenRequirements,
    WorkCenterSpec,
    counter_run_for_wall,
    evaluate_kitchen,
    generate_kitchen_candidates,
    kitchen_quantity_summary,
    kitchen_svg,
    place_work_center,
    rank_kitchens,
    work_triangle,
)
from nitikube.room_layout import KeepoutZone, Rect


def specs():
    return (
        WorkCenterSpec("sink", "Sink", 3.0, 2.0),
        WorkCenterSpec("hob", "Hob", 2.5, 2.0),
        WorkCenterSpec("fridge", "Fridge", 3.0, 2.0),
    )


def test_counter_runs_follow_walls():
    room = Rect(0, 0, 10, 12)
    assert counter_run_for_wall(room, "top", counter_depth_ft=2).rect == Rect(0, 0, 10, 2)
    assert counter_run_for_wall(room, "bottom", counter_depth_ft=2).rect == Rect(0, 10, 10, 2)
    assert counter_run_for_wall(room, "left", counter_depth_ft=2).rect == Rect(0, 0, 2, 12)
    assert counter_run_for_wall(room, "right", counter_depth_ft=2).rect == Rect(8, 0, 2, 12)


def test_work_center_fit_and_fail_closed_oversize():
    room = Rect(0, 0, 10, 12)
    run = counter_run_for_wall(room, "top", counter_depth_ft=2)
    sink, _, _ = specs()
    placed = place_work_center(run, sink, 0.5)
    assert placed.center == pytest.approx((5.0, 1.0))
    with pytest.raises(ValueError, match="wider than counter run"):
        place_work_center(run, WorkCenterSpec("x", "Too wide", 11, 2), 0.5)


def test_generator_builds_fourteen_family_orientations():
    room = Rect(0, 0, 10, 12)
    sink, hob, fridge = specs()
    candidates = generate_kitchen_candidates(room, counter_depth_ft=2, wall_margin_ft=0, sink=sink, hob=hob, fridge=fridge)
    assert len(candidates) == 14
    assert len({candidate.layout_id for candidate in candidates}) == 14
    assert {candidate.kind for candidate in candidates} == set(KitchenLayoutKind)


def test_work_triangle_uses_actual_centres():
    room = Rect(0, 0, 10, 12)
    sink, hob, fridge = specs()
    candidate = generate_kitchen_candidates(
        room, counter_depth_ft=2, wall_margin_ft=0, sink=sink, hob=hob, fridge=fridge,
        include_kinds=(KitchenLayoutKind.U_SHAPE,),
    )[0]
    triangle = work_triangle(candidate.work_centers)
    assert triangle is not None
    assert triangle.perimeter_ft == pytest.approx(sum(triangle.legs))
    assert triangle.area_ft2 > 0


def test_opening_keepout_rejects_counter_on_occupied_wall():
    room = Rect(0, 0, 10, 12)
    sink, hob, fridge = specs()
    top = next(c for c in generate_kitchen_candidates(
        room, counter_depth_ft=2, wall_margin_ft=0, sink=sink, hob=hob, fridge=fridge,
        include_kinds=(KitchenLayoutKind.ONE_WALL,),
    ) if c.name.endswith("top"))
    result = evaluate_kitchen(room, top, keepouts=[KeepoutZone("door", "Door", Rect(3, 0, 3, 3))])
    assert not result.feasible
    assert any(item.startswith("counter_keepout_collision") for item in result.failed)


def test_work_triangle_thresholds_are_explicit_hard_constraints():
    room = Rect(0, 0, 10, 12)
    sink, hob, fridge = specs()
    candidate = generate_kitchen_candidates(
        room, counter_depth_ft=2, wall_margin_ft=0, sink=sink, hob=hob, fridge=fridge,
        include_kinds=(KitchenLayoutKind.ONE_WALL,),
    )[0]
    triangle = work_triangle(candidate.work_centers)
    assert triangle is not None
    assert evaluate_kitchen(room, candidate, requirements=KitchenRequirements(work_triangle_total_max_ft=triangle.perimeter_ft + 0.1)).feasible
    strict = evaluate_kitchen(room, candidate, requirements=KitchenRequirements(work_triangle_total_max_ft=triangle.perimeter_ft - 0.1))
    assert not strict.feasible
    assert "work_triangle_total_above_max" in strict.failed


def test_requested_passage_can_reject_narrow_galley():
    room = Rect(0, 0, 6, 12)
    sink, hob, fridge = specs()
    candidate = next(c for c in generate_kitchen_candidates(
        room, counter_depth_ft=2, wall_margin_ft=0, sink=sink, hob=hob, fridge=fridge,
        include_kinds=(KitchenLayoutKind.GALLEY,),
    ) if "left + right" in c.name)
    result = evaluate_kitchen(room, candidate, requirements=KitchenRequirements(
        passage_width_ft=3.0, grid_step_ft=0.25, require_connected_passage=True,
    ))
    assert not result.feasible
    assert "passage_not_connected_at_requested_width" in result.failed


def test_l_corner_countertop_union_does_not_double_count():
    room = Rect(0, 0, 10, 12)
    sink, hob, fridge = specs()
    candidate = generate_kitchen_candidates(
        room, counter_depth_ft=2, wall_margin_ft=0, sink=sink, hob=hob, fridge=fridge,
        include_kinds=(KitchenLayoutKind.L_SHAPE,),
    )[0]
    result = evaluate_kitchen(room, candidate)
    raw = sum(run.rect.area_ft2 for run in candidate.counter_runs)
    assert result.countertop_union_area_ft2 == pytest.approx(raw - 4.0)


def test_quantity_summary_uses_union_area_and_explicit_waste():
    room = Rect(0, 0, 10, 12)
    sink, hob, fridge = specs()
    candidate = generate_kitchen_candidates(
        room, counter_depth_ft=2, wall_margin_ft=0, sink=sink, hob=hob, fridge=fridge,
        include_kinds=(KitchenLayoutKind.L_SHAPE,),
    )[0]
    result = evaluate_kitchen(room, candidate)
    q = kitchen_quantity_summary(
        candidate, result, base_cabinet_height_ft=2.75, wall_cabinet_height_ft=2.5,
        wall_cabinet_run_fraction=0.5, countertop_waste_fraction=0.1,
    )
    assert q["base_cabinet_front_area_ft2"] == pytest.approx(result.gross_counter_run_ft * 2.75)
    assert q["countertop_purchase_area_ft2"] == pytest.approx(result.countertop_union_area_ft2 * 1.1)


def test_ranking_keeps_feasible_candidates_first():
    room = Rect(0, 0, 10, 12)
    sink, hob, fridge = specs()
    ranked = rank_kitchens(room, generate_kitchen_candidates(
        room, counter_depth_ft=2, wall_margin_ft=0, sink=sink, hob=hob, fridge=fridge,
    ))
    flags = [evaluation.feasible for _, evaluation in ranked]
    if False in flags:
        first_false = flags.index(False)
        assert all(flags[:first_false])


def test_svg_contains_work_centres_and_triangle():
    room = Rect(0, 0, 10, 12)
    sink, hob, fridge = specs()
    candidate = generate_kitchen_candidates(
        room, counter_depth_ft=2, wall_margin_ft=0, sink=sink, hob=hob, fridge=fridge,
        include_kinds=(KitchenLayoutKind.U_SHAPE,),
    )[0]
    result = evaluate_kitchen(room, candidate)
    svg = kitchen_svg(room, candidate, result)
    assert svg.startswith("<svg")
    assert all(label in svg for label in ("Sink", "Hob", "Fridge", "polyline"))
