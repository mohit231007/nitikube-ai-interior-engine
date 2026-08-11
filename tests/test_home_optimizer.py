import itertools

import pytest

from nitikube.home_optimizer import (
    RoomDesignOption,
    RoomGeometryConstraint,
    RoomPolicy,
    ScoreWeights,
    evaluate_room_option,
    load_room_options_json,
    option_utility,
    optimize_budget_scenarios,
    optimize_home,
)


def option(room, option_id, cost, score, **kwargs):
    return RoomDesignOption(
        room_id=room,
        option_id=option_id,
        name=option_id,
        cost=cost,
        quality=score,
        durability=score,
        aesthetics=score,
        comfort=score,
        maintainability=score,
        **kwargs,
    )


def test_weighted_utility_is_explicit_and_normalized():
    candidate = RoomDesignOption(
        room_id="R1",
        option_id="o1",
        name="Option",
        cost=100,
        quality=100,
        durability=80,
        aesthetics=60,
        comfort=40,
        maintainability=20,
    )
    weights = ScoreWeights(quality=2, durability=1, aesthetics=1, comfort=0, maintainability=0)
    assert option_utility(candidate, weights) == pytest.approx((100 * 2 + 80 + 60) / 4)


def test_geometry_constraints_are_hard_not_soft_scores():
    candidate = option("R1", "large", 100, 100, min_area_ft2=200, min_width_ft=12)
    geometry = RoomGeometryConstraint("R1", area_ft2=150, width_ft=10, height_ft=15)
    evaluation = evaluate_room_option(candidate, geometry=geometry)
    assert evaluation.feasible is False
    assert "min_area" in evaluation.failed
    assert "min_width" in evaluation.failed


def test_missing_required_geometry_is_unknown_and_not_approved():
    candidate = option("R1", "wide", 100, 90, min_width_ft=12)
    evaluation = evaluate_room_option(candidate, geometry=None)
    assert evaluation.feasible is False
    assert "room_geometry" in evaluation.unknown


def test_room_policy_enforces_minimums_features_and_room_cap():
    candidate = RoomDesignOption(
        room_id="R1",
        option_id="o1",
        name="Option",
        cost=500,
        quality=80,
        durability=70,
        aesthetics=90,
        comfort=75,
        maintainability=65,
        features=("low-maintenance", "child-safe"),
    )
    policy = RoomPolicy(
        room_id="R1",
        max_cost=450,
        min_durability=75,
        required_features=("child-safe", "moisture-safe"),
    )
    evaluation = evaluate_room_option(candidate, policy=policy)
    assert evaluation.feasible is False
    assert "room_max_cost" in evaluation.failed
    assert "min_durability" in evaluation.failed
    assert "required_feature:moisture-safe" in evaluation.failed
    assert "required_feature:child-safe" not in evaluation.failed


def test_cross_room_budget_forces_global_tradeoff():
    options = [
        option("living", "living-premium", 700, 100),
        option("living", "living-value", 400, 75),
        option("bed", "bed-premium", 700, 100),
        option("bed", "bed-value", 400, 75),
    ]
    result = optimize_home(options, budget=1100, required_room_ids=["living", "bed"])
    assert result.feasible is True
    assert result.selected_cost == pytest.approx(1100)
    selected = {item.option_id for item in result.selected}
    assert len(selected & {"living-premium", "bed-premium"}) == 1
    assert len(selected & {"living-value", "bed-value"}) == 1


def test_optimizer_matches_bruteforce_for_small_additive_problem():
    options = [
        option("A", "A1", 100, 40),
        option("A", "A2", 180, 85),
        option("A", "A3", 250, 100),
        option("B", "B1", 90, 35),
        option("B", "B2", 150, 70),
        option("B", "B3", 230, 98),
        option("C", "C1", 80, 50),
        option("C", "C2", 160, 90),
    ]
    budget = 500
    result = optimize_home(options, budget=budget, required_room_ids=["A", "B", "C"])
    assert result.feasible

    groups = [[o for o in options if o.room_id == room] for room in ["A", "B", "C"]]
    brute = []
    for combo in itertools.product(*groups):
        cost = sum(item.cost for item in combo)
        if cost <= budget:
            utility = sum(option_utility(item, ScoreWeights()) for item in combo)
            brute.append((utility, -cost, {item.option_id for item in combo}))
    expected = max(brute)
    assert result.total_utility == pytest.approx(expected[0])
    assert {item.option_id for item in result.selected} == expected[2]


def test_locked_choice_is_respected():
    options = [
        option("A", "A-best", 100, 100),
        option("A", "A-locked", 100, 50),
        option("B", "B1", 100, 80),
    ]
    result = optimize_home(
        options,
        budget=300,
        locked_choices={"A": "A-locked"},
        required_room_ids=["A", "B"],
    )
    assert result.feasible
    assert {item.option_id for item in result.selected} == {"A-locked", "B1"}


def test_invalid_lock_returns_explainable_infeasible_result():
    options = [option("A", "A1", 100, 80)]
    result = optimize_home(options, budget=500, locked_choices={"A": "missing"}, required_room_ids=["A"])
    assert result.feasible is False
    assert "locked option" in result.message


def test_reserve_is_protected_from_design_spend():
    options = [option("A", "A1", 900, 100), option("A", "A2", 800, 80)]
    result = optimize_home(options, budget=1000, reserve=150, required_room_ids=["A"])
    assert result.feasible
    assert result.selected[0].option_id == "A2"
    assert result.spendable_budget == pytest.approx(850)
    # Budget remaining includes the protected reserve plus any unspent design budget.
    assert result.budget_remaining == pytest.approx(200)


def test_no_feasible_combination_under_budget_is_explicit():
    options = [option("A", "A1", 600, 100), option("B", "B1", 600, 100)]
    result = optimize_home(options, budget=1000, required_room_ids=["A", "B"])
    assert result.feasible is False
    assert "No combination remains within budget" in result.message


def test_scenario_frontier_uses_user_supplied_budget_fractions():
    options = [
        option("A", "A1", 300, 60),
        option("A", "A2", 450, 90),
        option("B", "B1", 300, 60),
        option("B", "B2", 450, 90),
    ]
    scenarios = optimize_budget_scenarios(
        options,
        total_budget=1000,
        scenario_fractions={"Value": 0.7, "Full": 1.0},
        reserve_fraction=0.0,
        required_room_ids=["A", "B"],
    )
    by_name = {scenario.name: scenario.optimization for scenario in scenarios}
    assert by_name["Value"].selected_cost == pytest.approx(600)
    assert by_name["Full"].selected_cost == pytest.approx(900)
    assert by_name["Full"].total_utility > by_name["Value"].total_utility


def test_json_loader_rejects_duplicate_option_ids():
    payload = {
        "options": [
            {
                "room_id": "A",
                "option_id": "dup",
                "name": "One",
                "cost": 100,
                "quality": 50,
                "durability": 50,
                "aesthetics": 50,
                "comfort": 50,
                "maintainability": 50,
            },
            {
                "room_id": "B",
                "option_id": "dup",
                "name": "Two",
                "cost": 100,
                "quality": 50,
                "durability": 50,
                "aesthetics": 50,
                "comfort": 50,
                "maintainability": 50,
            },
        ]
    }
    import json

    with pytest.raises(ValueError, match="globally unique"):
        load_room_options_json(json.dumps(payload))
