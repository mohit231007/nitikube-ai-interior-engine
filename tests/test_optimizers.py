from nitikube.constraints import ScopeCategory, guard_scope
from nitikube.lighting_optimizer import optimise_lighting_layouts
from nitikube.optimizer import DesignOption, pareto_front, weighted_rank


def test_lighting_optimizer_finds_current_room_candidates():
    candidates = optimise_lighting_layouts(
        length_ft=22.75,
        width_ft=10 + 7/12,
        ceiling_height_ft=9,
        evaluation_plane_height_ft=2.5,
        beam_angle_deg=36,
        lumen_options=[350, 400, 450, 500, 550, 600],
        min_lux=130,
        max_lux=200,
        max_spacing_to_beam=1.35,
        min_fixtures=8,
        max_fixtures=24,
    )
    assert candidates
    assert all(130 <= x.maintained_lux <= 200 for x in candidates)
    assert all(x.worst_spacing_to_beam <= 1.35 for x in candidates)


def test_weighted_rank_respects_budget():
    options = [
        DesignOption("A", 100, 80, 80, 80, 80, 80),
        DesignOption("B", 200, 95, 95, 95, 95, 95),
    ]
    ranked = weighted_rank(options, budget=150)
    assert [o.name for o, _ in ranked] == ["A"]


def test_pareto_front_removes_dominated_option():
    a = DesignOption("A", 100, 90, 90, 90, 90, 90)
    b = DesignOption("B", 120, 80, 80, 80, 80, 80)
    front = pareto_front([a, b])
    assert [x.name for x in front] == ["A"]


def test_structural_scope_requires_professional_verification():
    guard = guard_scope(ScopeCategory.LOAD_BEARING_OR_STRUCTURAL)
    assert guard.professional_verification_required is True


def test_cosmetic_scope_does_not_require_structural_verification_flag():
    guard = guard_scope(ScopeCategory.COSMETIC)
    assert guard.professional_verification_required is False
