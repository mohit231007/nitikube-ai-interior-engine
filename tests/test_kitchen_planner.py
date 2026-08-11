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


def test_counter_runs_follow_each_wall_and_stay_inside_room():
    room = Rect(0, 0, 10, 12)
    top = counter_run_for_wall(room, "top", counter_depth_ft=2)
    bottom = counter_run_for_wall(room, "bottom", counter_depth_ft=2)
    left = counter_run_for_wall(room, "left", counter_depth_ft=2)
    right = counter_run_for_wall(room, "right", counter_depth_ft=2)
    assert top.rect == Rect(0, 0, 10, 2)
    assert bottom.rect == Rect(0, 10, 10, 2)
    assert left.rect == Rect(0, 0, 2, 12)
    assert right.rect == Rect(8, 0, 2, 12)
    assert top.length_ft == pytest.approx(10)
    assert left.length_ft == pytest.approx(12)


def test_work_center_is_placed_inside_run():
    room = Rect(0, 0, 10, 12)
    run = counter_run_for_wall(room, "top", counter_depth_ft=2)
    sink, _, _ = specs()
    placed = place_work_center(run, sink, 0.5)
    assert placed.rect.width_ft == pytest.approx(3)
    assert placed.rect.depth_ft == pytest.approx(2)
    assert placed.rect.x_ft == pytest.approx(3.5)
    assert placed.center == pytest.approx((5.0, 1.0))


def test_too_wide_module_is_rejected_not_clipped():
    room = Rect(0, 0, 4, 8)
    run = counter_run_for_wall(room, "top", counter_depth_ft=2)
    huge = WorkCenterSpec("sink", "Sink", 5, 2)
    with pytest.raises(ValueError, match="wider than counter run"):
        place_work_center(run, huge, 0.5)


def test_work_triangle_uses_actual_module_centers():
    room = Rect(0, 0, 10, 12)
    sink, hob, fridge = specs()
    runs = [
        counter_run_for_wall(room, "top", counter_depth_ft=2, run_id="top"),
        counter_run_for_wall(room, "left", counter_depth_ft=2, run_id="left"),
        counter_run_for_wall(room, "right", counter_depth_ft=2, run_id="right"),
    ]
    centers = [
        place_work_center(runs[0], sink, 0.5),
        place_work_center(runs[1], hob, 0.5),
        place_work_center(runs[2], fridge, 0.5),
    ]
    triangle = work_triangle(centers)
    assert triangle is not None
    assert triangle.perimeter_ft == pytest.approx(sum(triangle.legs))
    assert triangle.area_ft2 > 0


def test_generator_explores_all_four_kitchen_families():
    room = Rect(0, 0, 10, 12)
    sink, hob, fridge = specs()
    candidates = generate_kitchen_candidates(
        room,
        counter_depth_ft=2,
        wall_margin_ft=0,
        sink=sink,
        hob=hob,
        fridge=fridge,
    )
    # 4 one-wall + 2 galley + 4 L + 4 U
    assert len(candidates) == 14
    kinds = {candidate.kind for candidate in candidates}
    assert kinds == {
        KitchenLayoutKind.ONE_WALL,
        KitchenLayoutKind.GALLEY,
        KitchenLayoutKind.L_SHAPE,
        KitchenLayoutKind.U_SHAPE,
    }
    assert len({candidate.layout_id for candidate in candidates}) == 14


def test_opening_keepout_rejects_counter_run_on_that_wall():
    room = Rect(0, 0, 10, 12)
    sink, hob, fridge = specs()
    candidates = generate_kitchen_candidates(
        room,
        counter_depth_ft=2,
        wall_margin_ft=0,
        sink=sink,
        hob=hob,
        fridge=fridge,
        include_kinds=(KitchenLayoutKind.ONE_WALL,),
    )
    top = next(candidate for candidate in candidates if candidate.name.endswith("top"))
    keepout = KeepoutZone("door", "Door", Rect(3, 0, 3, 3))
    evaluation = evaluate_kitchen(room, top, keepouts=[keepout])
    assert evaluation.feasible is False
    assert any(item.startswith("counter_keepout_collision") for item in evaluation.failed)


def test_work_triangle_thresholds_are_explicit_hard_constraints():
    room = Rect(0, 0, 10, 12)
    sink, hob, fridge = specs()
    candidate = generate_kitchen_candidates(
        room,
        counter_depth_ft=2,
        wall_margin_ft=0,
        sink=sink,
        hob=hob,
        fridge=fridge,
        include_kinds=(KitchenLayoutKind.ONE_WALL,),
    )[0]
    triangle = work_triangle(candidate.work_centers)
    assert triangle is not None
    loose = KitchenRequirements(work_triangle_total_max_ft=triangle.perimeter_ft + 0.1)
    strict = KitchenRequirements(work_triangle_total_max_ft=max(0.1, triangle.perimeter_ft - 0.1))
    assert evaluate_kitchen(room, candidate, requirements=loose).feasible is True
    strict_eval = evaluate_kitchen(room, candidate, requirements=strict)
    assert strict_eval.feasible is False
    assert "work_triangle_total_above_max" in strict_eval.failed


def test_requested_passage_width_can_reject_too_narrow_galley():
    room = Rect(0, 0, 6, 12)
    sink, hob, fridge = specs()
    candidates = generate_kitchen_candidates(
        room,
        counter_depth_ft=2,
        wall_margin_ft=0,
        sink=sink,
        hob=hob,
        fridge=fridge,
        include_kinds=(KitchenLayoutKind.GALLEY,),
    )
    left_right = next(candidate for candidate in candidates if "left + right" in candidate.name)
    evaluation = evaluate_kitchen(
        room,
        left_right,
        requirements=KitchenRequirements(
            passage_width_ft=3.0,
            grid_step_ft=0.25,
            require_connected_passage=True,
        ),
    )
    # 2 ft counters on each side leave 2 ft physical gap. Inflating by 1.5 ft
    # closes the central path, so a requested 3 ft passage cannot be represented.
    assert evaluation.feasible is False
    assert "passage_not_connected_at_requested_width" in evaluation.failed


def test_countertop_union_area_does_not_double_count_l_corners():
    room = Rect(0, 0, 10, 12)
    sink, hob, fridge = specs()
    candidate = generate_kitchen_candidates(
        room,
        counter_depth_ft=2,
        wall_margin_ft=0,
        sink=sink,
        hob=hob,
        fridge=fridge,
        include_kinds=(KitchenLayoutKind.L_SHAPE,),
    )[0]
    evaluation = evaluate_kitchen(room, candidate)
    raw_sum = sum(run.rect.area_ft2 for run in candidate.counter_runs)
    assert evaluation.countertop_union_area_ft2 < raw_sum
    assert evaluation.countertop_union_area_ft2 == pytest.approx(raw_sum - 4.0)


def test_quantity_summary_uses_union_area_and_explicit_waste():
    room = Rect(0, 0, 10, 12)
    sink, hob, fridge = specs()
    candidate = generate_kitchen_candidates(
        room,
        counter_depth_ft=2,
        wall_margin_ft=0,
        sink=sink,
        hob=hob,
        fridge=fridge,
        include_kinds=(KitchenLayoutKind.L_SHAPE,),
    )[0]
    evaluation = evaluate_kitchen(room, candidate)
    summary = kitchen_quantity_summary(
        candidate,
        evaluation,
        base_cabinet_height_ft=2.75,
        wall_cabinet_height_ft=2.5,
        wall_cabinet_run_fraction=0.5,
        countertop_waste_fraction=0.1,
    )
    assert summary["base_cabinet_front_area_ft2"] == pytest.approx(evaluation.gross_counter_run_ft * 2.75)
    assert summary["wall_cabinet_run_ft"] == pytest.approx(evaluation.gross_counter_run_ft * 0.5)
    assert summary["countertop_purchase_area_ft2"] == pytest.approx(evaluation.countertop_union_area_ft2 * 1.1)


def test_ranking_keeps_feasibility_ahead_of_geometry_score():
    room = Rect(0, 0, 10, 12)
    sink, hob, fridge = specs()
    candidates = generate_kitchen_candidates(
        room,
        counter_depth_ft=2,
        wall_margin_ft=0,
        sink=sink,
        hob=hob,
        fridge=fridge,
    )
    ranked = rank_kitchens(room, candidates, requirements=KitchenRequirements())
    assert ranked
    feasible_flags = [evaluation.feasible for _, evaluation in ranked]
    if False in feasible_flags:
        first_false = feasible_flags.index(False)
        assert all(feasible_flags[:first_false])


def test_svg_contains_work_centers_and_triangle():
    room = Rect(0, 0, 10, 12)
    sink, hob, fridge = specs()
    candidate = generate_kitchen_candidates(
        room,
        counter_depth_ft=2,
        wall_margin_ft=0,
        sink=sink,
        hob=hob,
        fridge=fridge,
        include_kinds=(KitchenLayoutKind.U_SHAPE,),
    )[0]
    evaluation = evaluate_kitchen(room, candidate)
    svg = kitchen_svg(room, candidate, evaluation)
    assert svg.startswith("<svg")
    assert "Sink" in svg
    assert "Hob" in svg
    assert "Fridge" in svg
    assert "polyline" in svg
