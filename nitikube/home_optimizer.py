from __future__ import annotations

from dataclasses import dataclass
import json
import math
from typing import Any, Iterable, Mapping, Sequence


@dataclass(frozen=True)
class ScoreWeights:
    quality: float = 0.25
    durability: float = 0.25
    aesthetics: float = 0.15
    comfort: float = 0.15
    maintainability: float = 0.20

    def normalized(self) -> tuple[float, float, float, float, float]:
        values = (self.quality, self.durability, self.aesthetics, self.comfort, self.maintainability)
        if any(value < 0 for value in values) or sum(values) <= 0:
            raise ValueError("score weights must be non-negative and sum to > 0")
        total = sum(values)
        return tuple(value / total for value in values)


@dataclass(frozen=True)
class RoomGeometryConstraint:
    room_id: str
    area_ft2: float
    width_ft: float | None = None
    height_ft: float | None = None


@dataclass(frozen=True)
class RoomPolicy:
    room_id: str
    max_cost: float | None = None
    min_quality: float | None = None
    min_durability: float | None = None
    min_comfort: float | None = None
    min_maintainability: float | None = None
    required_features: tuple[str, ...] = ()


@dataclass(frozen=True)
class RoomDesignOption:
    room_id: str
    option_id: str
    name: str
    cost: float
    quality: float
    durability: float
    aesthetics: float
    comfort: float
    maintainability: float
    min_area_ft2: float | None = None
    min_width_ft: float | None = None
    min_height_ft: float | None = None
    features: tuple[str, ...] = ()
    feasible: bool = True
    score_source: str = "user_or_model_input"
    notes: tuple[str, ...] = ()

    def metrics(self) -> tuple[float, float, float, float, float]:
        return (
            self.quality,
            self.durability,
            self.aesthetics,
            self.comfort,
            self.maintainability,
        )


@dataclass(frozen=True)
class OptionFeasibility:
    option_id: str
    feasible: bool
    failed: tuple[str, ...]
    unknown: tuple[str, ...]


@dataclass(frozen=True)
class SelectedRoomOption:
    room_id: str
    option_id: str
    option_name: str
    cost: float
    utility: float


@dataclass(frozen=True)
class HomeOptimizationResult:
    feasible: bool
    budget: float
    reserve: float
    spendable_budget: float
    selected_cost: float | None
    budget_remaining: float | None
    total_utility: float | None
    selected: tuple[SelectedRoomOption, ...]
    message: str
    states_considered: int


@dataclass(frozen=True)
class ScenarioResult:
    name: str
    budget_fraction: float
    optimization: HomeOptimizationResult


@dataclass(frozen=True)
class _State:
    cost: float
    utility: float
    choices: tuple[RoomDesignOption, ...]


def validate_option(option: RoomDesignOption) -> None:
    if not option.room_id.strip() or not option.option_id.strip() or not option.name.strip():
        raise ValueError("room_id, option_id and name are required")
    if option.cost < 0 or not math.isfinite(option.cost):
        raise ValueError(f"option {option.option_id}: cost must be finite and non-negative")
    for name, value in zip(
        ("quality", "durability", "aesthetics", "comfort", "maintainability"), option.metrics()
    ):
        if not math.isfinite(value) or not 0 <= value <= 100:
            raise ValueError(f"option {option.option_id}: {name} must be in [0,100]")
    for label, value in (
        ("min_area_ft2", option.min_area_ft2),
        ("min_width_ft", option.min_width_ft),
        ("min_height_ft", option.min_height_ft),
    ):
        if value is not None and (value <= 0 or not math.isfinite(value)):
            raise ValueError(f"option {option.option_id}: {label} must be positive when supplied")


def option_utility(option: RoomDesignOption, weights: ScoreWeights) -> float:
    validate_option(option)
    normalized = weights.normalized()
    return sum(metric * weight for metric, weight in zip(option.metrics(), normalized))


def evaluate_room_option(
    option: RoomDesignOption,
    *,
    geometry: RoomGeometryConstraint | None = None,
    policy: RoomPolicy | None = None,
) -> OptionFeasibility:
    validate_option(option)
    failed: list[str] = []
    unknown: list[str] = []

    if not option.feasible:
        failed.append("option_marked_infeasible")

    if geometry is not None:
        if geometry.room_id != option.room_id:
            failed.append("geometry_room_id_mismatch")
        if geometry.area_ft2 <= 0:
            failed.append("invalid_room_area")
        if option.min_area_ft2 is not None and geometry.area_ft2 < option.min_area_ft2:
            failed.append("min_area")
        if option.min_width_ft is not None:
            if geometry.width_ft is None:
                unknown.append("min_width")
            elif geometry.width_ft < option.min_width_ft:
                failed.append("min_width")
        if option.min_height_ft is not None:
            if geometry.height_ft is None:
                unknown.append("min_height")
            elif geometry.height_ft < option.min_height_ft:
                failed.append("min_height")
    elif any(value is not None for value in (option.min_area_ft2, option.min_width_ft, option.min_height_ft)):
        unknown.append("room_geometry")

    if policy is not None:
        if policy.room_id != option.room_id:
            failed.append("policy_room_id_mismatch")
        if policy.max_cost is not None and option.cost > policy.max_cost:
            failed.append("room_max_cost")
        thresholds = (
            ("min_quality", option.quality, policy.min_quality),
            ("min_durability", option.durability, policy.min_durability),
            ("min_comfort", option.comfort, policy.min_comfort),
            ("min_maintainability", option.maintainability, policy.min_maintainability),
        )
        for label, actual, threshold in thresholds:
            if threshold is not None and actual < threshold:
                failed.append(label)
        option_features = {feature.casefold() for feature in option.features}
        for feature in policy.required_features:
            if feature.casefold() not in option_features:
                failed.append(f"required_feature:{feature}")

    # Geometry-dependent unknowns prevent approval. The optimizer must not assume
    # an option fits when a required room dimension is missing.
    feasible = not failed and not unknown
    return OptionFeasibility(option.option_id, feasible, tuple(failed), tuple(unknown))


def _prune_states(states: Sequence[_State], *, cost_tolerance: float = 1e-9, utility_tolerance: float = 1e-9) -> list[_State]:
    """Keep the exact additive cost/utility Pareto frontier after each room.

    All states at this stage have selected one option for the same set of rooms,
    so a state that costs no less and has no higher utility can never become
    optimal after adding the remaining rooms.
    """
    if not states:
        return []
    ordered = sorted(states, key=lambda state: (state.cost, -state.utility))
    frontier: list[_State] = []
    best_utility = -math.inf
    for state in ordered:
        if state.utility > best_utility + utility_tolerance:
            frontier.append(state)
            best_utility = state.utility
        elif frontier and abs(state.utility - best_utility) <= utility_tolerance:
            # Same utility at higher/equal cost is dominated. At effectively the
            # same cost/utility, retaining one path is sufficient for additive optimization.
            continue
    return frontier


def optimize_home(
    options: Iterable[RoomDesignOption],
    *,
    budget: float,
    reserve: float = 0.0,
    weights: ScoreWeights | None = None,
    geometries: Mapping[str, RoomGeometryConstraint] | None = None,
    policies: Mapping[str, RoomPolicy] | None = None,
    locked_choices: Mapping[str, str] | None = None,
    required_room_ids: Sequence[str] | None = None,
) -> HomeOptimizationResult:
    if budget <= 0 or not math.isfinite(budget):
        raise ValueError("budget must be finite and positive")
    if reserve < 0 or not math.isfinite(reserve):
        raise ValueError("reserve must be finite and non-negative")
    if reserve >= budget:
        return HomeOptimizationResult(
            feasible=False,
            budget=budget,
            reserve=reserve,
            spendable_budget=max(0.0, budget - reserve),
            selected_cost=None,
            budget_remaining=None,
            total_utility=None,
            selected=(),
            message="Reserve consumes the entire budget; no design spend is available.",
            states_considered=0,
        )

    weights = weights or ScoreWeights()
    geometries = geometries or {}
    policies = policies or {}
    locked_choices = locked_choices or {}

    grouped: dict[str, list[RoomDesignOption]] = {}
    seen_option_ids: set[str] = set()
    for option in options:
        validate_option(option)
        if option.option_id in seen_option_ids:
            raise ValueError(f"duplicate option_id: {option.option_id}")
        seen_option_ids.add(option.option_id)
        grouped.setdefault(option.room_id, []).append(option)

    room_ids = list(required_room_ids) if required_room_ids is not None else sorted(grouped)
    if not room_ids:
        raise ValueError("at least one room is required")
    if len(room_ids) != len(set(room_ids)):
        raise ValueError("required_room_ids contains duplicates")

    spendable = budget - reserve
    feasible_by_room: dict[str, list[RoomDesignOption]] = {}
    diagnostics: list[str] = []
    for room_id in room_ids:
        candidates = grouped.get(room_id, [])
        if not candidates:
            diagnostics.append(f"room {room_id} has no candidate design options")
            continue
        lock = locked_choices.get(room_id)
        if lock is not None:
            candidates = [candidate for candidate in candidates if candidate.option_id == lock]
            if not candidates:
                diagnostics.append(f"room {room_id} locked option {lock!r} was not found")
                continue

        accepted = []
        for candidate in candidates:
            evaluation = evaluate_room_option(
                candidate,
                geometry=geometries.get(room_id),
                policy=policies.get(room_id),
            )
            if evaluation.feasible:
                accepted.append(candidate)
        if not accepted:
            diagnostics.append(f"room {room_id} has no option that passes its current geometry/policy constraints")
        feasible_by_room[room_id] = accepted

    if diagnostics:
        return HomeOptimizationResult(
            feasible=False,
            budget=budget,
            reserve=reserve,
            spendable_budget=spendable,
            selected_cost=None,
            budget_remaining=None,
            total_utility=None,
            selected=(),
            message="; ".join(diagnostics),
            states_considered=0,
        )

    states = [_State(0.0, 0.0, ())]
    states_considered = 1
    for room_id in room_ids:
        expanded: list[_State] = []
        for state in states:
            for option in feasible_by_room[room_id]:
                new_cost = state.cost + option.cost
                if new_cost <= spendable + 1e-9:
                    expanded.append(
                        _State(
                            cost=new_cost,
                            utility=state.utility + option_utility(option, weights),
                            choices=state.choices + (option,),
                        )
                    )
        states_considered += len(expanded)
        states = _prune_states(expanded)
        if not states:
            return HomeOptimizationResult(
                feasible=False,
                budget=budget,
                reserve=reserve,
                spendable_budget=spendable,
                selected_cost=None,
                budget_remaining=None,
                total_utility=None,
                selected=(),
                message=f"No combination remains within budget after adding room {room_id}.",
                states_considered=states_considered,
            )

    best = max(states, key=lambda state: (state.utility, -state.cost))
    selected = tuple(
        SelectedRoomOption(
            room_id=option.room_id,
            option_id=option.option_id,
            option_name=option.name,
            cost=option.cost,
            utility=round(option_utility(option, weights), 4),
        )
        for option in best.choices
    )
    return HomeOptimizationResult(
        feasible=True,
        budget=budget,
        reserve=reserve,
        spendable_budget=spendable,
        selected_cost=round(best.cost, 2),
        budget_remaining=round(budget - best.cost, 2),
        total_utility=round(best.utility, 4),
        selected=selected,
        message="Optimal additive-utility combination found under the supplied constraints.",
        states_considered=states_considered,
    )


def optimize_budget_scenarios(
    options: Iterable[RoomDesignOption],
    *,
    total_budget: float,
    scenario_fractions: Mapping[str, float],
    reserve_fraction: float,
    weights: ScoreWeights | None = None,
    geometries: Mapping[str, RoomGeometryConstraint] | None = None,
    policies: Mapping[str, RoomPolicy] | None = None,
    locked_choices: Mapping[str, str] | None = None,
    required_room_ids: Sequence[str] | None = None,
) -> tuple[ScenarioResult, ...]:
    if not 0 <= reserve_fraction < 1:
        raise ValueError("reserve_fraction must be in [0,1)")
    results = []
    option_list = list(options)
    for name, fraction in scenario_fractions.items():
        if not 0 < fraction <= 1:
            raise ValueError("scenario budget fractions must be in (0,1]")
        scenario_budget = total_budget * fraction
        reserve = scenario_budget * reserve_fraction
        result = optimize_home(
            option_list,
            budget=scenario_budget,
            reserve=reserve,
            weights=weights,
            geometries=geometries,
            policies=policies,
            locked_choices=locked_choices,
            required_room_ids=required_room_ids,
        )
        results.append(ScenarioResult(name=name, budget_fraction=fraction, optimization=result))
    return tuple(results)


def option_from_dict(data: dict[str, Any]) -> RoomDesignOption:
    required = ["room_id", "option_id", "name", "cost", "quality", "durability", "aesthetics", "comfort", "maintainability"]
    missing = [field for field in required if data.get(field) in {None, ""}]
    if missing:
        raise ValueError(f"missing design-option fields: {missing}")

    def optional_float(name: str) -> float | None:
        value = data.get(name)
        if value in {None, ""}:
            return None
        return float(value)

    option = RoomDesignOption(
        room_id=str(data["room_id"]),
        option_id=str(data["option_id"]),
        name=str(data["name"]),
        cost=float(data["cost"]),
        quality=float(data["quality"]),
        durability=float(data["durability"]),
        aesthetics=float(data["aesthetics"]),
        comfort=float(data["comfort"]),
        maintainability=float(data["maintainability"]),
        min_area_ft2=optional_float("min_area_ft2"),
        min_width_ft=optional_float("min_width_ft"),
        min_height_ft=optional_float("min_height_ft"),
        features=tuple(str(item) for item in data.get("features", [])),
        feasible=bool(data.get("feasible", True)),
        score_source=str(data.get("score_source") or "user_or_model_input"),
        notes=tuple(str(item) for item in data.get("notes", [])),
    )
    validate_option(option)
    return option


def load_room_options_json(payload: str | bytes) -> list[RoomDesignOption]:
    if isinstance(payload, bytes):
        payload = payload.decode("utf-8")
    data = json.loads(payload)
    rows = data.get("options") if isinstance(data, dict) else data
    if not isinstance(rows, list):
        raise ValueError("room option JSON must be a list or {'options': [...]} object")
    options = [option_from_dict(row) for row in rows]
    ids = [option.option_id for option in options]
    if len(ids) != len(set(ids)):
        raise ValueError("option_id values must be globally unique")
    return options


def result_rows(result: HomeOptimizationResult) -> list[dict[str, Any]]:
    return [
        {
            "room_id": item.room_id,
            "option_id": item.option_id,
            "option_name": item.option_name,
            "cost": item.cost,
            "utility": item.utility,
        }
        for item in result.selected
    ]
