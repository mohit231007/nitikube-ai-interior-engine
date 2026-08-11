from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
import json
import math
import re
from typing import Any, Mapping, Sequence

from .bathroom_planner import (
    BathroomRequirements,
    FixtureSpec,
    ShowerSpec,
    generate_bathroom_candidates,
    rank_bathrooms,
)
from .bedroom_planner import (
    BedSpec,
    BedroomRequirements,
    DeskSpec,
    WardrobeSpec,
    generate_bedroom_candidates,
    rank_bedrooms,
)
from .home_optimizer import (
    HomeOptimizationResult,
    RoomDesignOption,
    RoomGeometryConstraint,
    RoomPolicy,
    ScoreWeights,
    optimize_home,
    result_rows,
)
from .kitchen_planner import (
    KitchenLayoutKind,
    KitchenRequirements,
    WorkCenterSpec,
    generate_kitchen_candidates,
    rank_kitchens,
)
from .project_orchestrator import (
    MergedOptionBundle,
    OptionSource,
    artifact_ref,
    build_design_package,
)
from .room_layout import (
    FurnitureSpec,
    KeepoutZone,
    LayoutRequirements,
    OpeningSegment,
    Rect,
    generate_drawing_dining_candidates,
    opening_keepout,
    rank_layouts,
)
from .verified_geometry import (
    VerifiedOpening,
    VerifiedRoom,
    geometry_from_project_json,
    opening_boundary_rooms,
)


SCORE_FIELDS = ("quality", "durability", "aesthetics", "comfort", "maintainability")


class RoomRole(str, Enum):
    DRAWING_DINING = "drawing_dining"
    KITCHEN = "kitchen"
    BEDROOM = "bedroom"
    BATHROOM = "bathroom"


@dataclass(frozen=True)
class RoleInference:
    role: RoomRole | None
    source: str
    matched_term: str | None = None


@dataclass(frozen=True)
class FactoryCandidate:
    room_id: str
    room_name: str
    role: str
    layout_id: str
    name: str
    feasible: bool
    geometry_score: float
    failed: tuple[str, ...]
    warnings: tuple[str, ...]
    metrics: Mapping[str, float]
    features: tuple[str, ...]
    notes: tuple[str, ...] = ()


@dataclass(frozen=True)
class RoomFactoryResult:
    room_id: str
    room_name: str
    role: str | None
    role_source: str
    status: str
    candidates: tuple[FactoryCandidate, ...]
    optimizer_options: tuple[RoomDesignOption, ...]
    errors: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()

    @property
    def feasible_candidate_count(self) -> int:
        return sum(candidate.feasible for candidate in self.candidates)


@dataclass(frozen=True)
class WholeHomeFactoryResult:
    project_name: str
    required_room_ids: tuple[str, ...]
    room_results: tuple[RoomFactoryResult, ...]
    optimizer_options: tuple[RoomDesignOption, ...]
    optimization: HomeOptimizationResult | None
    design_package: Mapping[str, Any] | None
    geometry_sha256: str
    option_artifact_sha256: str | None
    diagnostics: tuple[str, ...]

    @property
    def optimizer_ready(self) -> bool:
        covered = {option.room_id for option in self.optimizer_options}
        return bool(self.required_room_ids) and all(room_id in covered for room_id in self.required_room_ids)


_ROLE_PATTERNS: tuple[tuple[RoomRole, tuple[str, ...]], ...] = (
    (RoomRole.KITCHEN, ("kitchen", "pantry kitchen")),
    (RoomRole.BATHROOM, ("bathroom", "bath", "toilet", "washroom", "wc")),
    (RoomRole.BEDROOM, ("bedroom", "bed room", "master bedroom", "guest bedroom")),
    (RoomRole.DRAWING_DINING, ("drawing", "living", "lounge", "dining", "drawing dining", "living dining")),
)


def _norm_name(value: str) -> str:
    return " ".join(re.sub(r"[^a-z0-9]+", " ", value.casefold()).split())


def infer_room_role(room_name: str) -> RoleInference:
    """Infer only from explicit room-name terms; ambiguous/anonymous rooms remain unknown.

    This is deterministic convenience logic, not an ML classifier. The caller can
    always override the inferred role in the design brief.
    """
    name = _norm_name(room_name)
    if not name:
        return RoleInference(None, "unknown")
    tokens = set(name.split())
    matches: list[tuple[RoomRole, str]] = []
    for role, terms in _ROLE_PATTERNS:
        for term in terms:
            normalized = _norm_name(term)
            if " " in normalized:
                if normalized in name:
                    matches.append((role, term))
            elif normalized in tokens:
                matches.append((role, term))
    roles = {role for role, _ in matches}
    if len(roles) == 1:
        role = next(iter(roles))
        term = next(term for candidate_role, term in matches if candidate_role == role)
        return RoleInference(role, "room_name_keyword", term)
    if len(roles) > 1:
        return RoleInference(None, "ambiguous_room_name")
    return RoleInference(None, "unknown")


def _unique_values(values: Sequence[float], tolerance: float = 1e-7) -> list[float]:
    result: list[float] = []
    for value in sorted(float(item) for item in values):
        if not result or abs(value - result[-1]) > tolerance:
            result.append(value)
    return result


def verified_room_rect(room: VerifiedRoom, *, tolerance: float = 1e-7) -> Rect:
    """Return the exact axis-aligned rectangle represented by a verified room.

    No bounding-box substitution is allowed. Non-rectangular polygons fail closed.
    """
    if not room.verified:
        raise ValueError(f"room {room.room_id} is not verified")
    points = room.polygon_ft
    if len(points) != 4:
        raise ValueError("current candidate factory supports only exact four-corner rectangular rooms")
    xs = _unique_values([point[0] for point in points], tolerance)
    ys = _unique_values([point[1] for point in points], tolerance)
    if len(xs) != 2 or len(ys) != 2:
        raise ValueError("room polygon is not an axis-aligned rectangle")
    expected = {(xs[0], ys[0]), (xs[1], ys[0]), (xs[1], ys[1]), (xs[0], ys[1])}
    for point in points:
        if not any(math.dist(point, corner) <= tolerance for corner in expected):
            raise ValueError("room polygon is not an exact axis-aligned rectangle")
    rect = Rect(xs[0], ys[0], xs[1] - xs[0], ys[1] - ys[0])
    if abs(rect.area_ft2 - room.area_ft2) > max(tolerance, tolerance * rect.area_ft2):
        raise ValueError("room polygon area does not equal its rectangle area")
    return rect


def _required_float(data: Mapping[str, Any], key: str, context: str, *, allow_zero: bool = False) -> float:
    if key not in data or data[key] is None or data[key] == "":
        raise ValueError(f"{context}.{key} is required")
    value = float(data[key])
    if not math.isfinite(value) or (value < 0 if allow_zero else value <= 0):
        comparator = "non-negative" if allow_zero else "positive"
        raise ValueError(f"{context}.{key} must be finite and {comparator}")
    return value


def _optional_float(data: Mapping[str, Any], key: str, default: float | None = None) -> float | None:
    value = data.get(key, default)
    if value is None or value == "":
        return None
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{key} must be finite")
    return result


def _bool(data: Mapping[str, Any], key: str, default: bool) -> bool:
    value = data.get(key, default)
    if isinstance(value, bool):
        return value
    raise ValueError(f"{key} must be boolean")


def _furniture_spec(data: Mapping[str, Any], context: str, item_id: str, label: str) -> FurnitureSpec:
    return FurnitureSpec(
        item_id=item_id,
        label=label,
        width_ft=_required_float(data, "width_ft", context),
        depth_ft=_required_float(data, "depth_ft", context),
        clearance_ft=float(data.get("clearance_ft", 0.0) or 0.0),
    )


def _work_center(data: Mapping[str, Any], context: str, center_id: str, label: str) -> WorkCenterSpec:
    return WorkCenterSpec(
        center_id=center_id,
        label=label,
        width_along_run_ft=_required_float(data, "width_ft", context),
        depth_ft=_required_float(data, "depth_ft", context),
    )


def _fixture(data: Mapping[str, Any], context: str, fixture_id: str, label: str) -> FixtureSpec:
    return FixtureSpec(
        fixture_id=fixture_id,
        label=label,
        width_ft=_required_float(data, "width_ft", context),
        depth_ft=_required_float(data, "depth_ft", context),
        front_clearance_ft=float(data.get("front_clearance_ft", 0.0) or 0.0),
    )


def _room_openings(room: VerifiedRoom, openings: Sequence[VerifiedOpening]) -> tuple[VerifiedOpening, ...]:
    result: list[VerifiedOpening] = []
    for opening in openings:
        if not opening.verified:
            continue
        declared = {value for value in (opening.room_a, opening.room_b) if value}
        if room.room_id in declared:
            result.append(opening)
            continue
        if room.room_id in opening_boundary_rooms(opening, [room]):
            result.append(opening)
    return tuple(result)


def _opening_keepouts(
    room: VerifiedRoom,
    rect: Rect,
    openings: Sequence[VerifiedOpening],
    room_profile: Mapping[str, Any],
    top_level: Mapping[str, Any],
) -> tuple[tuple[KeepoutZone, ...], tuple[str, ...]]:
    settings = dict(top_level.get("opening_keepouts") or {})
    settings.update(room_profile.get("opening_keepouts") or {})
    kinds = tuple(str(item).casefold() for item in settings.get("kinds", ("door", "opening")))
    relevant = [opening for opening in _room_openings(room, openings) if opening.kind.casefold() in kinds]
    if not relevant:
        return (), ()
    depth = settings.get("inward_depth_ft")
    if depth in {None, ""}:
        raise ValueError(
            "verified door/opening geometry exists but opening_keepouts.inward_depth_ft is missing; "
            "the factory will not silently ignore access geometry"
        )
    depth_ft = float(depth)
    side_padding_ft = float(settings.get("side_padding_ft", 0.0) or 0.0)
    if depth_ft <= 0 or side_padding_ft < 0:
        raise ValueError("opening keepout depth must be positive and side padding non-negative")
    keepouts: list[KeepoutZone] = []
    warnings: list[str] = []
    for opening in relevant:
        try:
            keepouts.append(
                opening_keepout(
                    rect,
                    OpeningSegment(opening.opening_id, opening.start_ft, opening.end_ft, opening.kind),
                    inward_depth_ft=depth_ft,
                    side_padding_ft=side_padding_ft,
                )
            )
        except ValueError as exc:
            raise ValueError(f"opening {opening.opening_id} cannot become a room keepout: {exc}") from exc
    ignored_windows = [opening.opening_id for opening in _room_openings(room, openings) if opening.kind.casefold() == "window" and "window" not in kinds]
    if ignored_windows:
        warnings.append(
            "verified windows are not floor-level keepouts in this brief because window sill/head geometry is not authoritative: "
            + ", ".join(ignored_windows)
        )
    return tuple(keepouts), tuple(warnings)


def _candidate(
    room: VerifiedRoom,
    role: RoomRole,
    layout_id: str,
    name: str,
    feasible: bool,
    geometry_score: float,
    failed: Sequence[str],
    warnings: Sequence[str],
    metrics: Mapping[str, float | None],
    features: Sequence[str],
    notes: Sequence[str] = (),
) -> FactoryCandidate:
    clean_metrics = {
        key: float(value)
        for key, value in metrics.items()
        if value is not None and math.isfinite(float(value))
    }
    return FactoryCandidate(
        room_id=room.room_id,
        room_name=room.name,
        role=role.value,
        layout_id=layout_id,
        name=name,
        feasible=bool(feasible),
        geometry_score=float(geometry_score),
        failed=tuple(str(item) for item in failed),
        warnings=tuple(str(item) for item in warnings),
        metrics=clean_metrics,
        features=tuple(str(item) for item in features),
        notes=tuple(str(item) for item in notes),
    )


def _drawing_dining(
    room: VerifiedRoom,
    rect: Rect,
    profile: Mapping[str, Any],
    keepouts: Sequence[KeepoutZone],
) -> tuple[FactoryCandidate, ...]:
    planner = profile.get("planner") or {}
    requirements_data = profile.get("requirements") or {}
    sofa = _furniture_spec(planner.get("sofa") or {}, "planner.sofa", "sofa", "Sofa")
    tv = _furniture_spec(planner.get("tv_console") or {}, "planner.tv_console", "tv_console", "TV console")
    coffee = _furniture_spec(planner.get("coffee_table") or {}, "planner.coffee_table", "coffee_table", "Coffee table")
    dining = _furniture_spec(planner.get("dining_table") or {}, "planner.dining_table", "dining_table", "Dining table")
    living_fraction = _required_float(planner, "living_fraction", "planner")
    zone_gap = _required_float(planner, "zone_gap_ft", "planner", allow_zero=True)
    wall_margin = _required_float(planner, "wall_margin_ft", "planner", allow_zero=True)
    candidates = generate_drawing_dining_candidates(
        rect,
        sofa=sofa,
        tv_console=tv,
        coffee_table=coffee,
        dining_table=dining,
        living_fraction=living_fraction,
        zone_gap_ft=zone_gap,
        wall_margin_ft=wall_margin,
    )
    requirements = LayoutRequirements(
        wall_margin_ft=float(requirements_data.get("wall_margin_ft", 0.0) or 0.0),
        min_pair_gap_ft=float(requirements_data.get("min_pair_gap_ft", 0.0) or 0.0),
        passage_width_ft=float(requirements_data.get("passage_width_ft", 0.0) or 0.0),
        grid_step_ft=float(requirements_data.get("grid_step_ft", 0.25) or 0.25),
        require_reserved_clearance_inside_room=_bool(requirements_data, "require_reserved_clearance_inside_room", True),
    )
    ranked = rank_layouts(rect, candidates, keepouts=keepouts, requirements=requirements)
    result: list[FactoryCandidate] = []
    for candidate, evaluation in ranked:
        result.append(
            _candidate(
                room,
                RoomRole.DRAWING_DINING,
                candidate.layout_id,
                candidate.name,
                evaluation.feasible,
                evaluation.geometry_score,
                evaluation.failed,
                evaluation.warnings,
                {
                    "furniture_area_ft2": evaluation.furniture_area_ft2,
                    "reserved_area_ft2": evaluation.reserved_area_ft2,
                    "open_area_ratio": evaluation.open_area_ratio,
                    "minimum_pair_gap_ft": evaluation.minimum_pair_gap_ft,
                    "circulation_connectivity": evaluation.circulation_largest_component_ratio,
                    "circulation_walkable_ratio": evaluation.circulation_walkable_ratio,
                    "geometry_score": evaluation.geometry_score,
                },
                ("role:drawing_dining", "planner:drawing_dining", f"layout:{candidate.layout_id}"),
                candidate.notes,
            )
        )
    return tuple(result)


def _kitchen(
    room: VerifiedRoom,
    rect: Rect,
    profile: Mapping[str, Any],
    keepouts: Sequence[KeepoutZone],
) -> tuple[FactoryCandidate, ...]:
    planner = profile.get("planner") or {}
    requirements_data = profile.get("requirements") or {}
    sink = _work_center(planner.get("sink") or {}, "planner.sink", "sink", "Sink")
    hob = _work_center(planner.get("hob") or {}, "planner.hob", "hob", "Hob")
    fridge = _work_center(planner.get("fridge") or {}, "planner.fridge", "fridge", "Fridge")
    include_raw = planner.get("include_kinds")
    include = tuple(KitchenLayoutKind(str(item)) for item in include_raw) if include_raw else tuple(KitchenLayoutKind)
    candidates = generate_kitchen_candidates(
        rect,
        counter_depth_ft=_required_float(planner, "counter_depth_ft", "planner"),
        wall_margin_ft=_required_float(planner, "wall_margin_ft", "planner", allow_zero=True),
        sink=sink,
        hob=hob,
        fridge=fridge,
        include_kinds=include,
    )
    requirements = KitchenRequirements(
        min_counter_run_ft=float(requirements_data.get("min_counter_run_ft", 0.0) or 0.0),
        passage_width_ft=float(requirements_data.get("passage_width_ft", 0.0) or 0.0),
        grid_step_ft=float(requirements_data.get("grid_step_ft", 0.25) or 0.25),
        require_connected_passage=_bool(requirements_data, "require_connected_passage", True),
        work_triangle_leg_min_ft=_optional_float(requirements_data, "work_triangle_leg_min_ft"),
        work_triangle_leg_max_ft=_optional_float(requirements_data, "work_triangle_leg_max_ft"),
        work_triangle_total_min_ft=_optional_float(requirements_data, "work_triangle_total_min_ft"),
        work_triangle_total_max_ft=_optional_float(requirements_data, "work_triangle_total_max_ft"),
    )
    ranked = rank_kitchens(rect, candidates, keepouts=keepouts, requirements=requirements)
    result: list[FactoryCandidate] = []
    for candidate, evaluation in ranked:
        triangle = evaluation.work_triangle
        result.append(
            _candidate(
                room,
                RoomRole.KITCHEN,
                candidate.layout_id,
                candidate.name,
                evaluation.feasible,
                evaluation.geometry_score,
                evaluation.failed,
                evaluation.warnings,
                {
                    "counter_run_ft": evaluation.gross_counter_run_ft,
                    "countertop_area_ft2": evaluation.countertop_union_area_ft2,
                    "work_triangle_perimeter_ft": triangle.perimeter_ft if triangle else None,
                    "work_triangle_area_ft2": triangle.area_ft2 if triangle else None,
                    "circulation_connectivity": evaluation.circulation_connectivity,
                    "circulation_walkable_ratio": evaluation.circulation_walkable_ratio,
                    "geometry_score": evaluation.geometry_score,
                },
                ("role:kitchen", "planner:kitchen", f"layout_kind:{candidate.kind.value}", f"layout:{candidate.layout_id}"),
                candidate.notes,
            )
        )
    return tuple(result)


def _bedroom(
    room: VerifiedRoom,
    rect: Rect,
    profile: Mapping[str, Any],
    keepouts: Sequence[KeepoutZone],
) -> tuple[FactoryCandidate, ...]:
    planner = profile.get("planner") or {}
    requirements_data = profile.get("requirements") or {}
    bed_data = planner.get("bed") or {}
    wardrobe_data = planner.get("wardrobe") or {}
    bed = BedSpec(
        width_ft=_required_float(bed_data, "width_ft", "planner.bed"),
        length_ft=_required_float(bed_data, "length_ft", "planner.bed"),
    )
    wardrobe = WardrobeSpec(
        run_ft=_required_float(wardrobe_data, "run_ft", "planner.wardrobe"),
        depth_ft=_required_float(wardrobe_data, "depth_ft", "planner.wardrobe"),
        height_ft=_required_float(wardrobe_data, "height_ft", "planner.wardrobe"),
    )
    desk_data = planner.get("desk")
    desk = None
    if desk_data:
        desk = DeskSpec(
            width_ft=_required_float(desk_data, "width_ft", "planner.desk"),
            depth_ft=_required_float(desk_data, "depth_ft", "planner.desk"),
        )
    requirements = BedroomRequirements(
        side_clearance_ft=float(requirements_data.get("side_clearance_ft", 0.0) or 0.0),
        foot_clearance_ft=float(requirements_data.get("foot_clearance_ft", 0.0) or 0.0),
        wardrobe_front_clearance_ft=float(requirements_data.get("wardrobe_front_clearance_ft", 0.0) or 0.0),
        passage_width_ft=float(requirements_data.get("passage_width_ft", 0.0) or 0.0),
        grid_step_ft=float(requirements_data.get("grid_step_ft", 0.25) or 0.25),
        require_connected_passage=_bool(requirements_data, "require_connected_passage", True),
    )
    candidates = generate_bedroom_candidates(
        rect,
        bed=bed,
        wardrobe=wardrobe,
        desk=desk,
        wall_margin_ft=_required_float(planner, "wall_margin_ft", "planner", allow_zero=True),
        side_clearance_ft=requirements.side_clearance_ft,
        foot_clearance_ft=requirements.foot_clearance_ft,
        wardrobe_front_clearance_ft=requirements.wardrobe_front_clearance_ft,
    )
    ranked = rank_bedrooms(rect, candidates, wardrobe, keepouts=keepouts, requirements=requirements)
    result: list[FactoryCandidate] = []
    for candidate, evaluation in ranked:
        result.append(
            _candidate(
                room,
                RoomRole.BEDROOM,
                candidate.layout_id,
                candidate.name,
                evaluation.feasible,
                evaluation.geometry_score,
                evaluation.failed,
                evaluation.warnings,
                {
                    "furniture_area_ft2": evaluation.furniture_area_ft2,
                    "open_area_ratio": evaluation.open_area_ratio,
                    "bed_to_wardrobe_center_ft": evaluation.bed_to_wardrobe_center_ft,
                    "circulation_connectivity": evaluation.circulation_connectivity,
                    "circulation_walkable_ratio": evaluation.circulation_walkable_ratio,
                    "wardrobe_run_ft": evaluation.wardrobe_run_ft,
                    "wardrobe_front_area_ft2": evaluation.wardrobe_front_area_ft2,
                    "wardrobe_volume_ft3": evaluation.wardrobe_internal_volume_ft3,
                    "geometry_score": evaluation.geometry_score,
                },
                ("role:bedroom", "planner:bedroom", f"layout:{candidate.layout_id}"),
                candidate.notes,
            )
        )
    return tuple(result)


def _bathroom(
    room: VerifiedRoom,
    rect: Rect,
    profile: Mapping[str, Any],
    keepouts: Sequence[KeepoutZone],
) -> tuple[FactoryCandidate, ...]:
    planner = profile.get("planner") or {}
    requirements_data = profile.get("requirements") or {}
    shower_data = planner.get("shower") or {}
    shower = ShowerSpec(
        width_ft=_required_float(shower_data, "width_ft", "planner.shower"),
        depth_ft=_required_float(shower_data, "depth_ft", "planner.shower"),
    )
    wc = _fixture(planner.get("wc") or {}, "planner.wc", "wc", "WC")
    basin = _fixture(planner.get("basin") or {}, "planner.basin", "basin", "Basin")
    requirements = BathroomRequirements(
        passage_width_ft=float(requirements_data.get("passage_width_ft", 0.0) or 0.0),
        grid_step_ft=float(requirements_data.get("grid_step_ft", 0.20) or 0.20),
        require_connected_passage=_bool(requirements_data, "require_connected_passage", True),
        require_fixture_front_clearance_inside_room=_bool(
            requirements_data, "require_fixture_front_clearance_inside_room", True
        ),
    )
    candidates = generate_bathroom_candidates(
        rect,
        shower=shower,
        wc=wc,
        basin=basin,
        wall_margin_ft=_required_float(planner, "wall_margin_ft", "planner", allow_zero=True),
    )
    ranked = rank_bathrooms(rect, candidates, keepouts=keepouts, requirements=requirements)
    result: list[FactoryCandidate] = []
    for candidate, evaluation in ranked:
        result.append(
            _candidate(
                room,
                RoomRole.BATHROOM,
                candidate.layout_id,
                candidate.name,
                evaluation.feasible,
                evaluation.geometry_score,
                evaluation.failed,
                evaluation.warnings,
                {
                    "occupied_area_ft2": evaluation.occupied_area_ft2,
                    "open_area_ratio": evaluation.open_area_ratio,
                    "circulation_connectivity": evaluation.circulation_connectivity,
                    "circulation_walkable_ratio": evaluation.circulation_walkable_ratio,
                    "geometry_score": evaluation.geometry_score,
                    "room_floor_area_ft2": rect.area_ft2,
                },
                ("role:bathroom", "planner:bathroom", f"layout:{candidate.layout_id}"),
            )
        )
    return tuple(result)


def _cost_from_model(model: Mapping[str, Any] | None, metrics: Mapping[str, float]) -> tuple[float | None, str | None]:
    if not model:
        return None, "cost_model_missing"
    if "fixed_cost" not in model or model.get("fixed_cost") in {None, ""}:
        return None, "cost_model.fixed_cost_missing"
    fixed_cost = float(model["fixed_cost"])
    if fixed_cost < 0 or not math.isfinite(fixed_cost):
        raise ValueError("cost_model.fixed_cost must be finite and non-negative")
    total = fixed_cost
    rates = model.get("metric_rates") or {}
    if not isinstance(rates, Mapping):
        raise ValueError("cost_model.metric_rates must be an object")
    for metric, rate_raw in rates.items():
        if metric not in metrics:
            raise ValueError(f"cost_model references unavailable metric {metric!r}")
        rate = float(rate_raw)
        if rate < 0 or not math.isfinite(rate):
            raise ValueError(f"cost_model rate for {metric} must be finite and non-negative")
        total += metrics[metric] * rate
    return round(total, 2), None


def _scores_from_profile(
    scores: Mapping[str, Any] | None,
    geometry_score: float,
    mapping: Mapping[str, Any] | None,
) -> tuple[dict[str, float] | None, str | None, str]:
    if not scores:
        return None, "decision_scores_missing", "none"
    result: dict[str, float] = {}
    for field in SCORE_FIELDS:
        if field not in scores or scores[field] in {None, ""}:
            return None, f"decision_scores.{field}_missing", "none"
        value = float(scores[field])
        if not math.isfinite(value) or not 0 <= value <= 100:
            raise ValueError(f"decision_scores.{field} must be in [0,100]")
        result[field] = value
    mapping = mapping or {}
    used: list[str] = []
    for field, blend_raw in mapping.items():
        if field not in SCORE_FIELDS:
            raise ValueError(f"geometry_score_blend target {field!r} is not a decision score")
        blend = float(blend_raw)
        if not 0 <= blend <= 1:
            raise ValueError("geometry_score_blend values must be in [0,1]")
        result[field] = (1.0 - blend) * result[field] + blend * geometry_score
        used.append(f"{field}:{blend:g}")
    source = "explicit_brief_scores"
    if used:
        source += "+explicit_geometry_blend[" + ",".join(used) + "]"
    return result, None, source


def candidate_to_optimizer_option(
    candidate: FactoryCandidate,
    room_profile: Mapping[str, Any],
) -> tuple[RoomDesignOption | None, tuple[str, ...]]:
    cost, cost_issue = _cost_from_model(room_profile.get("cost_model"), candidate.metrics)
    scores, score_issue, score_source = _scores_from_profile(
        room_profile.get("decision_scores"),
        candidate.geometry_score,
        room_profile.get("geometry_score_blend"),
    )
    issues = tuple(issue for issue in (cost_issue, score_issue) if issue)
    if cost is None or scores is None:
        return None, issues
    option_id = f"{candidate.room_id}::{candidate.role}::{candidate.layout_id}"
    option = RoomDesignOption(
        room_id=candidate.room_id,
        option_id=option_id,
        name=candidate.name,
        cost=cost,
        quality=scores["quality"],
        durability=scores["durability"],
        aesthetics=scores["aesthetics"],
        comfort=scores["comfort"],
        maintainability=scores["maintainability"],
        features=candidate.features,
        feasible=candidate.feasible,
        score_source=score_source,
        notes=(
            f"deterministic_geometry_score={candidate.geometry_score:.2f}",
            "Cost comes only from the explicit fixed-cost/metric-rate model in the design brief.",
            "Geometry score is not a decision score unless geometry_score_blend explicitly maps it.",
        ) + candidate.notes,
    )
    return option, issues


def _resolve_role(room: VerifiedRoom, profile: Mapping[str, Any]) -> RoleInference:
    explicit = profile.get("role")
    if explicit not in {None, ""}:
        try:
            return RoleInference(RoomRole(str(explicit)), "explicit_brief")
        except ValueError as exc:
            raise ValueError(f"unsupported explicit role {explicit!r}") from exc
    return infer_room_role(room.name)


def _room_factory(
    room: VerifiedRoom,
    openings: Sequence[VerifiedOpening],
    profile: Mapping[str, Any],
    top_level: Mapping[str, Any],
) -> RoomFactoryResult:
    inference = _resolve_role(room, profile)
    if inference.role is None:
        return RoomFactoryResult(
            room.room_id,
            room.name,
            None,
            inference.source,
            "unknown_role",
            (),
            (),
            ("room role could not be resolved; set rooms.<room_id>.role explicitly",),
        )
    try:
        rect = verified_room_rect(room)
        keepouts, keepout_warnings = _opening_keepouts(room, rect, openings, profile, top_level)
        if inference.role == RoomRole.DRAWING_DINING:
            candidates = _drawing_dining(room, rect, profile, keepouts)
        elif inference.role == RoomRole.KITCHEN:
            candidates = _kitchen(room, rect, profile, keepouts)
        elif inference.role == RoomRole.BEDROOM:
            candidates = _bedroom(room, rect, profile, keepouts)
        elif inference.role == RoomRole.BATHROOM:
            candidates = _bathroom(room, rect, profile, keepouts)
        else:  # pragma: no cover - enum guards this path
            raise ValueError(f"unsupported role {inference.role}")
        optimizer_options: list[RoomDesignOption] = []
        readiness_issues: set[str] = set()
        for candidate in candidates:
            option, issues = candidate_to_optimizer_option(candidate, profile)
            readiness_issues.update(issues)
            if option is not None:
                optimizer_options.append(option)
        if not candidates:
            status = "no_candidates_generated"
        elif optimizer_options:
            status = "optimizer_ready"
        else:
            status = "geometry_only"
        warnings = list(keepout_warnings)
        if readiness_issues:
            warnings.append(
                "optimizer options were not produced until explicit cost/scores are complete: "
                + ", ".join(sorted(readiness_issues))
            )
        return RoomFactoryResult(
            room.room_id,
            room.name,
            inference.role.value,
            inference.source,
            status,
            candidates,
            tuple(optimizer_options),
            (),
            tuple(warnings),
        )
    except (ValueError, TypeError, KeyError) as exc:
        return RoomFactoryResult(
            room.room_id,
            room.name,
            inference.role.value,
            inference.source,
            "blocked",
            (),
            (),
            (str(exc),),
        )


def _score_weights(data: Mapping[str, Any] | None) -> ScoreWeights:
    if not data:
        return ScoreWeights()
    kwargs = {field: float(data[field]) for field in SCORE_FIELDS if field in data}
    return ScoreWeights(**kwargs)


def _room_policies(data: Mapping[str, Any] | None) -> dict[str, RoomPolicy]:
    result: dict[str, RoomPolicy] = {}
    for room_id, row in (data or {}).items():
        row = row or {}
        result[str(room_id)] = RoomPolicy(
            room_id=str(room_id),
            max_cost=_optional_float(row, "max_cost"),
            min_quality=_optional_float(row, "min_quality"),
            min_durability=_optional_float(row, "min_durability"),
            min_comfort=_optional_float(row, "min_comfort"),
            min_maintainability=_optional_float(row, "min_maintainability"),
            required_features=tuple(str(item) for item in row.get("required_features", [])),
        )
    return result


def _optimizer_geometries(rooms: Sequence[VerifiedRoom]) -> dict[str, RoomGeometryConstraint]:
    result: dict[str, RoomGeometryConstraint] = {}
    for room in rooms:
        if not room.verified:
            continue
        try:
            rect = verified_room_rect(room)
        except ValueError:
            result[room.room_id] = RoomGeometryConstraint(room.room_id, room.area_ft2, None, None)
        else:
            result[room.room_id] = RoomGeometryConstraint(room.room_id, room.area_ft2, rect.width_ft, rect.depth_ft)
    return result


def room_options_payload(
    options: Sequence[RoomDesignOption],
    *,
    project_name: str,
) -> dict[str, Any]:
    return {
        "schema": "nitikube.room_design_options",
        "schema_version": "0.23",
        "project_name": project_name,
        "generated_by": "nitikube.whole_home_candidate_factory",
        "options": [asdict(option) for option in options],
    }


def room_options_json(options: Sequence[RoomDesignOption], *, project_name: str, indent: int = 2) -> str:
    return json.dumps(room_options_payload(options, project_name=project_name), indent=indent, ensure_ascii=False)


def factory_rows(result: WholeHomeFactoryResult) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for room_result in result.room_results:
        rows.append(
            {
                "room_id": room_result.room_id,
                "room_name": room_result.room_name,
                "role": room_result.role,
                "role_source": room_result.role_source,
                "status": room_result.status,
                "candidate_count": len(room_result.candidates),
                "feasible_candidate_count": room_result.feasible_candidate_count,
                "optimizer_option_count": len(room_result.optimizer_options),
                "errors": " | ".join(room_result.errors),
                "warnings": " | ".join(room_result.warnings),
            }
        )
    return rows


def candidate_rows(result: WholeHomeFactoryResult) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for room_result in result.room_results:
        for candidate in room_result.candidates:
            rows.append(
                {
                    "room_id": candidate.room_id,
                    "room_name": candidate.room_name,
                    "role": candidate.role,
                    "layout_id": candidate.layout_id,
                    "name": candidate.name,
                    "feasible": candidate.feasible,
                    "geometry_score": candidate.geometry_score,
                    "failed": ", ".join(candidate.failed),
                    "warnings": ", ".join(candidate.warnings),
                    **{f"metric:{key}": value for key, value in candidate.metrics.items()},
                }
            )
    return rows


def factory_audit_payload(result: WholeHomeFactoryResult) -> dict[str, Any]:
    optimization = None
    if result.optimization is not None:
        optimization = {
            "feasible": result.optimization.feasible,
            "budget": result.optimization.budget,
            "reserve": result.optimization.reserve,
            "spendable_budget": result.optimization.spendable_budget,
            "selected_cost": result.optimization.selected_cost,
            "budget_remaining": result.optimization.budget_remaining,
            "total_utility": result.optimization.total_utility,
            "message": result.optimization.message,
            "states_considered": result.optimization.states_considered,
            "selected": result_rows(result.optimization),
        }
    return {
        "schema": "nitikube.whole_home_factory_audit",
        "schema_version": "0.23",
        "project_name": result.project_name,
        "required_room_ids": list(result.required_room_ids),
        "optimizer_ready": result.optimizer_ready,
        "geometry_sha256": result.geometry_sha256,
        "option_artifact_sha256": result.option_artifact_sha256,
        "rooms": factory_rows(result),
        "candidates": candidate_rows(result),
        "optimization": optimization,
        "design_package_id": result.design_package.get("package_id") if result.design_package else None,
        "diagnostics": list(result.diagnostics),
    }


def factory_audit_json(result: WholeHomeFactoryResult, indent: int = 2) -> str:
    return json.dumps(factory_audit_payload(result), indent=indent, ensure_ascii=False)


def build_whole_home_candidates(
    geometry_payload: str | bytes,
    brief_payload: str | bytes | Mapping[str, Any],
    *,
    geometry_artifact_name: str = "nitikube_verified_geometry.json",
) -> WholeHomeFactoryResult:
    geometry_text = geometry_payload.decode("utf-8") if isinstance(geometry_payload, bytes) else geometry_payload
    project_name, rooms, openings, _metadata = geometry_from_project_json(geometry_text)
    verified_rooms = [room for room in rooms if room.verified]
    if not verified_rooms:
        raise ValueError("verified geometry contains no verified rooms")

    if isinstance(brief_payload, Mapping):
        brief = dict(brief_payload)
    else:
        text = brief_payload.decode("utf-8") if isinstance(brief_payload, bytes) else brief_payload
        brief = json.loads(text)
    if not isinstance(brief, dict):
        raise ValueError("whole-home brief must be a JSON object")
    if brief.get("schema") not in {None, "nitikube.whole_home_brief"}:
        raise ValueError("unsupported whole-home brief schema")

    room_profiles = brief.get("rooms") or {}
    if not isinstance(room_profiles, Mapping):
        raise ValueError("brief.rooms must be an object keyed by room_id")
    known_room_ids = {room.room_id for room in verified_rooms}
    unknown_profile_rooms = sorted(set(room_profiles) - known_room_ids)
    if unknown_profile_rooms:
        raise ValueError("brief contains room IDs absent from verified geometry: " + ", ".join(unknown_profile_rooms))

    required_raw = brief.get("required_room_ids")
    required_room_ids = tuple(str(item) for item in (required_raw if required_raw is not None else sorted(known_room_ids)))
    if not required_room_ids or len(required_room_ids) != len(set(required_room_ids)):
        raise ValueError("required_room_ids must be a non-empty unique list")
    unknown_required = sorted(set(required_room_ids) - known_room_ids)
    if unknown_required:
        raise ValueError("required_room_ids absent from verified geometry: " + ", ".join(unknown_required))

    room_results = tuple(
        _room_factory(room, openings, room_profiles.get(room.room_id) or {}, brief)
        for room in verified_rooms
        if room.room_id in required_room_ids
    )
    options = tuple(option for room_result in room_results for option in room_result.optimizer_options)
    ids = [option.option_id for option in options]
    if len(ids) != len(set(ids)):
        raise ValueError("factory produced duplicate globally unique option IDs")

    geometry_ref = artifact_ref(geometry_artifact_name, "verified_geometry", geometry_text)
    diagnostics: list[str] = []
    optimization: HomeOptimizationResult | None = None
    design_package: Mapping[str, Any] | None = None
    option_ref = None

    covered = {option.room_id for option in options}
    missing_optimizer_rooms = [room_id for room_id in required_room_ids if room_id not in covered]
    if missing_optimizer_rooms:
        diagnostics.append(
            "optimization not started because required rooms lack optimizer-ready options: "
            + ", ".join(missing_optimizer_rooms)
        )

    optimization_data = brief.get("optimization")
    if optimization_data is not None and not isinstance(optimization_data, Mapping):
        raise ValueError("optimization must be an object when supplied")
    if optimization_data and not missing_optimizer_rooms:
        budget = _required_float(optimization_data, "budget", "optimization")
        reserve = float(optimization_data.get("reserve", 0.0) or 0.0)
        if reserve < 0:
            raise ValueError("optimization.reserve cannot be negative")
        weights = _score_weights(optimization_data.get("weights"))
        policies = _room_policies(optimization_data.get("policies"))
        locked_choices = {str(k): str(v) for k, v in (optimization_data.get("locked_choices") or {}).items()}
        optimization = optimize_home(
            options,
            budget=budget,
            reserve=reserve,
            weights=weights,
            geometries=_optimizer_geometries(verified_rooms),
            policies=policies,
            locked_choices=locked_choices,
            required_room_ids=required_room_ids,
        )
        options_json = room_options_json(options, project_name=project_name)
        option_ref = artifact_ref("nitikube_factory_room_options.json", "room_design_options", options_json)
        if optimization.feasible:
            bundle = MergedOptionBundle(
                options=options,
                artifacts=(option_ref,),
                option_sources=tuple(
                    OptionSource(option.option_id, option_ref.name, option_ref.sha256) for option in options
                ),
            )
            design_package = build_design_package(
                project_name=project_name,
                geometry_artifact=geometry_ref,
                option_bundle=bundle,
                optimization=optimization,
                weights=weights,
                required_room_ids=required_room_ids,
                locked_choices=locked_choices,
                professional_verification_flags=tuple(
                    str(item) for item in brief.get("professional_verification_flags", [])
                ),
                created_at=optimization_data.get("created_at"),
            )
        else:
            diagnostics.append("whole-home optimization ran but was infeasible: " + optimization.message)
    elif optimization_data is None:
        diagnostics.append("optimization was not requested; geometry candidates/options were generated only")

    if option_ref is None and options:
        option_ref = artifact_ref(
            "nitikube_factory_room_options.json",
            "room_design_options",
            room_options_json(options, project_name=project_name),
        )

    for room_result in room_results:
        diagnostics.extend(f"{room_result.room_id}: {error}" for error in room_result.errors)

    return WholeHomeFactoryResult(
        project_name=project_name,
        required_room_ids=required_room_ids,
        room_results=room_results,
        optimizer_options=options,
        optimization=optimization,
        design_package=design_package,
        geometry_sha256=geometry_ref.sha256,
        option_artifact_sha256=option_ref.sha256 if option_ref else None,
        diagnostics=tuple(diagnostics),
    )


def _role_template(role: RoomRole | None) -> dict[str, Any]:
    common = {
        "role": role.value if role else None,
        "opening_keepouts": {"inward_depth_ft": None, "side_padding_ft": 0.0, "kinds": ["door", "opening"]},
        "decision_scores": {field: None for field in SCORE_FIELDS},
        "geometry_score_blend": {},
        "cost_model": {"fixed_cost": None, "metric_rates": {}},
    }
    if role == RoomRole.KITCHEN:
        common.update({
            "planner": {
                "counter_depth_ft": None,
                "wall_margin_ft": None,
                "sink": {"width_ft": None, "depth_ft": None},
                "hob": {"width_ft": None, "depth_ft": None},
                "fridge": {"width_ft": None, "depth_ft": None},
                "include_kinds": [kind.value for kind in KitchenLayoutKind],
            },
            "requirements": {
                "min_counter_run_ft": 0.0,
                "passage_width_ft": 0.0,
                "work_triangle_leg_min_ft": None,
                "work_triangle_leg_max_ft": None,
                "work_triangle_total_min_ft": None,
                "work_triangle_total_max_ft": None,
            },
        })
    elif role == RoomRole.BEDROOM:
        common.update({
            "planner": {
                "bed": {"width_ft": None, "length_ft": None},
                "wardrobe": {"run_ft": None, "depth_ft": None, "height_ft": None},
                "desk": None,
                "wall_margin_ft": None,
            },
            "requirements": {
                "side_clearance_ft": 0.0,
                "foot_clearance_ft": 0.0,
                "wardrobe_front_clearance_ft": 0.0,
                "passage_width_ft": 0.0,
            },
        })
    elif role == RoomRole.BATHROOM:
        common.update({
            "planner": {
                "shower": {"width_ft": None, "depth_ft": None},
                "wc": {"width_ft": None, "depth_ft": None, "front_clearance_ft": 0.0},
                "basin": {"width_ft": None, "depth_ft": None, "front_clearance_ft": 0.0},
                "wall_margin_ft": None,
            },
            "requirements": {"passage_width_ft": 0.0},
        })
    elif role == RoomRole.DRAWING_DINING:
        common.update({
            "planner": {
                "sofa": {"width_ft": None, "depth_ft": None, "clearance_ft": 0.0},
                "tv_console": {"width_ft": None, "depth_ft": None, "clearance_ft": 0.0},
                "coffee_table": {"width_ft": None, "depth_ft": None, "clearance_ft": 0.0},
                "dining_table": {"width_ft": None, "depth_ft": None, "clearance_ft": 0.0},
                "living_fraction": None,
                "zone_gap_ft": None,
                "wall_margin_ft": None,
            },
            "requirements": {"wall_margin_ft": 0.0, "min_pair_gap_ft": 0.0, "passage_width_ft": 0.0},
        })
    else:
        common.update({"planner": {}, "requirements": {}})
    return common


def brief_template_from_geometry(geometry_payload: str | bytes, *, indent: int = 2) -> str:
    text = geometry_payload.decode("utf-8") if isinstance(geometry_payload, bytes) else geometry_payload
    project_name, rooms, _openings, _metadata = geometry_from_project_json(text)
    verified = [room for room in rooms if room.verified]
    payload = {
        "schema": "nitikube.whole_home_brief",
        "schema_version": "0.23",
        "project_name_note": project_name,
        "required_room_ids": [room.room_id for room in verified],
        "professional_verification_flags": [],
        "rooms": {
            room.room_id: _role_template(infer_room_role(room.name).role)
            for room in verified
        },
        "optimization": {
            "budget": None,
            "reserve": 0.0,
            "weights": {
                "quality": 0.25,
                "durability": 0.25,
                "aesthetics": 0.15,
                "comfort": 0.15,
                "maintainability": 0.20,
            },
            "policies": {},
            "locked_choices": {},
        },
        "template_note": (
            "Null planner dimensions, decision scores, cost values and budget are intentionally not invented. "
            "Populate them from the homeowner brief, verified product data or sourced professional guidance before optimization."
        ),
    }
    return json.dumps(payload, indent=indent, ensure_ascii=False)
