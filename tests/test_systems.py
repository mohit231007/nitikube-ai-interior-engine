from nitikube.budget import allocate_budget, build_scenarios, weighted_option_score
from nitikube.climate import condensation_risk, dew_point_c, layer_r_value, u_value
from nitikube.confidence import ConfidenceInputs, confidence_label, confidence_score


def test_budget_allocation_sums_to_budget():
    allocation = allocate_budget(1_200_000)
    assert round(sum(allocation.values()), 2) == 1_200_000


def test_scenarios_are_within_budget():
    for scenario in build_scenarios(1_200_000):
        assert scenario.reserve + sum(scenario.allocations.values()) <= 1_200_000 + 0.01


def test_over_budget_option_is_infeasible():
    score = weighted_option_score(
        quality=90,
        durability=90,
        aesthetics=90,
        comfort=90,
        maintainability=90,
        cost=110,
        budget=100,
    )
    assert score == float("-inf")


def test_dew_point_and_condensation():
    dp = dew_point_c(24, 60)
    assert 15 < dp < 16.5
    risk, _ = condensation_risk(14, 24, 60)
    assert risk is True


def test_simple_u_value():
    r = layer_r_value(0.1, 0.72)
    u = u_value([r])
    assert 3.0 < u < 3.3


def test_confidence_score():
    score = confidence_score(ConfidenceInputs(95, 95, 85, 80))
    assert score == 90.0
    assert confidence_label(score) == "High"
