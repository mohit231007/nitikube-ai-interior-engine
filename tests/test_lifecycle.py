import json

import pytest

from nitikube.lifecycle import (
    EvidenceRef,
    EvidenceState,
    LifecycleAssumptions,
    LifecycleMaterialOption,
    evidence_readiness,
    initial_installed_cost,
    lifecycle_cost,
    load_options_csv,
    load_options_json,
    pareto_value_comparison,
    sensitivity_band,
)


def option(option_id="a", **overrides):
    data = {
        "option_id": option_id,
        "name": option_id,
        "currency": "INR",
        "area": 100.0,
        "area_unit": "ft2",
        "material_cost_per_area": 100.0,
        "labour_cost_per_area": 50.0,
        "initial_fixed_cost": 1000.0,
        "annual_maintenance_cost": 500.0,
        "service_life_years": 10.0,
        "replacement_cost_fraction": 0.8,
        "disposal_cost_per_replacement": 500.0,
        "waste_fraction": 0.10,
        "performance_score": 80.0,
        "features": ("moisture-resistant",),
        "evidence": (),
    }
    data.update(overrides)
    return LifecycleMaterialOption(**data)


def verified_ref():
    return EvidenceRef(
        EvidenceState.VERIFIED,
        source_url="https://example.com/source",
        checked_at="2026-08-11T18:00:00+00:00",
    )


def test_initial_installed_cost_keeps_material_waste_separate_from_labour():
    # 100 ft² × (100 material × 1.1 + 50 labour) + 1000 = 17,000
    assert initial_installed_cost(option()) == pytest.approx(17_000)


def test_missing_required_lifecycle_fields_are_unknown_not_zero():
    o = option(material_cost_per_area=None, service_life_years=None)
    unknown = evidence_readiness(o)
    assert "material_cost_per_area" in unknown
    assert "service_life_years" in unknown
    result = lifecycle_cost(o, LifecycleAssumptions(20, 0.05))
    assert result.feasible is False
    assert result.npv_cost is None


def test_verified_evidence_requirement_is_field_specific():
    evidence = tuple((field, verified_ref()) for field in (
        "material_cost_per_area",
        "labour_cost_per_area",
        "annual_maintenance_cost",
        "service_life_years",
    ))
    assert evidence_readiness(option(evidence=evidence), require_verified=True) == ()
    missing = option(evidence=(("material_cost_per_area", verified_ref()),))
    unknown = evidence_readiness(missing, require_verified=True)
    assert "labour_cost_per_area:verified_evidence" in unknown
    assert "service_life_years:verified_evidence" in unknown


def test_lifecycle_cost_builds_initial_maintenance_replacement_and_residual_cashflows():
    assumptions = LifecycleAssumptions(horizon_years=25, discount_rate=0.0, annual_cost_escalation_rate=0.0, include_residual_value=True)
    result = lifecycle_cost(option(), assumptions)
    assert result.feasible
    assert result.initial_installed_cost == pytest.approx(17_000)
    assert result.replacement_count == 2  # years 10 and 20
    categories = [flow.category for flow in result.cashflows]
    assert categories.count("maintenance") == 25
    assert categories.count("replacement") == 2
    assert categories.count("residual_value_credit") == 1
    # Replacement base = 17,000 × .8 + 500 = 14,100 each.
    # At year 25, second replacement is 5 years old with 5/10 life left,
    # residual credit = 17,000 × .8 × .5 = 6,800.
    expected = 17_000 + 25 * 500 + 2 * 14_100 - 6_800
    assert result.npv_cost == pytest.approx(expected)
    assert result.residual_value_credit == pytest.approx(6_800)
    assert result.equivalent_annual_cost == pytest.approx(expected / 25)


def test_discounted_npv_is_lower_than_undiscounted_for_positive_future_costs():
    no_discount = lifecycle_cost(option(), LifecycleAssumptions(20, 0.0, include_residual_value=False))
    discounted = lifecycle_cost(option(), LifecycleAssumptions(20, 0.08, include_residual_value=False))
    assert discounted.npv_cost < no_discount.npv_cost


def test_cost_escalation_increases_future_cost_npv_all_else_equal():
    base = lifecycle_cost(option(), LifecycleAssumptions(20, 0.05, 0.0, False))
    escalated = lifecycle_cost(option(), LifecycleAssumptions(20, 0.05, 0.05, False))
    assert escalated.npv_cost > base.npv_cost


def test_non_integer_replacement_years_fail_closed_in_annual_model():
    with pytest.raises(ValueError, match="integer replacement years"):
        lifecycle_cost(option(service_life_years=7.5), LifecycleAssumptions(20, 0.05))


def test_feature_constraints_are_hard_failures():
    assumptions = LifecycleAssumptions(10, 0.05)
    missing = lifecycle_cost(option(), assumptions, required_features=("uv-resistant",))
    excluded = lifecycle_cost(option(), assumptions, excluded_features=("moisture-resistant",))
    assert not missing.feasible and "missing_feature:uv-resistant" in missing.failed_constraints
    assert not excluded.feasible and "excluded_feature:moisture-resistant" in excluded.failed_constraints


def test_sensitivity_band_uses_explicit_cost_multipliers_not_random_sampling():
    band = sensitivity_band(option(), LifecycleAssumptions(10, 0.05), low_multiplier=0.9, high_multiplier=1.2)
    assert band.low_npv < band.base_npv < band.high_npv
    assert band.low_multiplier == pytest.approx(0.9)
    assert band.high_multiplier == pytest.approx(1.2)


def test_pareto_value_comparison_marks_cost_performance_dominance():
    options = [
        option("a", performance_score=80),
        option("b", performance_score=90, material_cost_per_area=80),
        option("c", performance_score=70, material_cost_per_area=150),
    ]
    assumptions = LifecycleAssumptions(10, 0.05, include_residual_value=False)
    results = {o.option_id: lifecycle_cost(o, assumptions) for o in options}
    comparison = {row.option_id: row for row in pareto_value_comparison(options, results)}
    assert comparison["b"].pareto_efficient is True
    assert comparison["c"].pareto_efficient is False
    assert comparison["b"].npv_performance_cost is not None


def test_json_loader_preserves_verified_evidence_and_unique_ids():
    payload = {
        "options": [
            {
                "option_id": "tile-a",
                "name": "Tile A",
                "currency": "INR",
                "area": 100,
                "area_unit": "ft2",
                "material_cost_per_area": 100,
                "labour_cost_per_area": 50,
                "initial_fixed_cost": 0,
                "annual_maintenance_cost": 100,
                "service_life_years": 10,
                "replacement_cost_fraction": 1,
                "disposal_cost_per_replacement": 0,
                "waste_fraction": 0.1,
                "performance_score": 80,
                "features": ["easy-clean"],
                "evidence": {
                    "material_cost_per_area": {
                        "state": "verified",
                        "source_url": "https://example.com/price",
                        "checked_at": "2026-08-11T18:00:00+00:00"
                    }
                }
            }
        ]
    }
    loaded = load_options_json(json.dumps(payload))
    assert loaded[0].features == ("easy-clean",)
    assert loaded[0].evidence_map()["material_cost_per_area"].state == EvidenceState.VERIFIED
    payload["options"].append(payload["options"][0])
    with pytest.raises(ValueError, match="unique"):
        load_options_json(json.dumps(payload))


def test_csv_loader_is_user_provided_structure_not_verified_evidence():
    csv_payload = """option_id,name,currency,area,area_unit,material_cost_per_area,labour_cost_per_area,initial_fixed_cost,annual_maintenance_cost,service_life_years,replacement_cost_fraction,disposal_cost_per_replacement,waste_fraction,performance_score,features
x,Option X,INR,100,ft2,100,50,0,100,10,1,0,0.1,80,easy-clean|moisture-resistant
"""
    loaded = load_options_csv(csv_payload)
    assert len(loaded) == 1
    assert loaded[0].features == ("easy-clean", "moisture-resistant")
    assert loaded[0].evidence == ()
    assert "material_cost_per_area:verified_evidence" in evidence_readiness(loaded[0], require_verified=True)
