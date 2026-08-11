from __future__ import annotations

from dataclasses import asdict, dataclass, replace
import json
import math
from typing import Any, Mapping, Sequence

from .bathroom_planner import FixtureSpec, ShowerSpec, generate_bathroom_candidates
from .bedroom_planner import BedSpec, DeskSpec, WardrobeSpec, generate_bedroom_candidates
from .home_optimizer import HomeOptimizationResult, RoomDesignOption, optimize_home, result_rows
from .kitchen_planner import KitchenLayoutKind, WorkCenterSpec, generate_kitchen_candidates
from .project_orchestrator import (
    MergedOptionBundle,
    OptionSource,
    artifact_ref,
    build_design_package,
    canonical_json_bytes,
    sha256_bytes,
)
from .room_layout import FurnitureSpec, generate_drawing_dining_candidates
from .service_aware_candidates import (
    CandidateServiceRuleSet,
    candidate_service_rules_from_dict,
    evaluate_candidate_services,
)
from .service_points import (
    ServicePoint,
    bathroom_service_targets,
    bedroom_service_targets,
    kitchen_service_targets,
    layout_service_targets,
    load_service_points_json,
)
from .verified_geometry import VerifiedOpening, VerifiedRoom, geometry_from_project_json
from .whole_home_factory import (
    FactoryCandidate,
    RoomFactoryResult,
    RoomRole,
    _optimizer_geometries,
    _opening_keepouts,
    _room_policies,
    _score_weights,
    build_whole_home_candidates,
    candidate_to_optimizer_option,
    factory_rows,
    room_options_json,
    verified_room_rect,
)


@dataclass(frozen=True)
class ServiceAwareRoomAudit:
    room_id: str
    room_name: str
    role: str | None
    service_status: str
    service_rule_count: int
    candidates_checked: int
    service_feasible_candidates: int
    overall_feasible_candidates: int
    notes: tuple[str, ...] = ()


@dataclass(frozen=True)
class ServiceAwareWholeHomeFactoryResult:
    project_name: str
    required_room_ids: tuple[str, ...]
    room_results: tuple[RoomFactoryResult, ...]
    room_service_audits: tuple[ServiceAwareRoomAudit, ...]
    optimizer_options: tuple[RoomDesignOption, ...]
    optimization: HomeOptimizationResult | None
    design_package: Mapping[str, Any] | None
    geometry_sha256: str
    service_points_sha256: str
    brief_sha256: str
    option_artifact_sha256: str | None
    diagnostics: tuple[str, ...]

    @property
    def optimizer_ready(self) -> bool:
        feasible_by_room = {
            room_id
            for room_id in self.required_room_ids
            if any(option.room_id == room_id and option.feasible for option in self.optimizer_options)
        }
        return bool(self.required_room_ids) and feasible_by_room == set(self.required_room_ids)


def _required_positive(data: Mapping[str, Any], key: str, context: str) -> float:
    value = data.get(key)
    if value in {None, ""}:
        raise ValueError(f"{context}.{key} is required")
    result = float(value)
    if not math.isfinite(result) or result <= 0:
        raise ValueError(f"{context}.{key} must be finite and positive")
    return result


def _nonnegative(data: Mapping[str, Any], key: str, context: str, default: float = 0.0) -> float:
    value = float(data.get(key, default) or 0.0)
    if not math.isfinite(value) or value < 0:
        raise ValueError(f"{context}.{key} must be finite and non-negative")
    return value


def _furniture(data: Mapping[str, Any], item_id: str, label: str, context: str) -> FurnitureSpec:
    return FurnitureSpec(
        item_id=item_id,
        label=label,
        width_ft=_required_positive(data, "width_ft", context),
        depth_ft=_required_positive(data, "depth_ft", context),
        clearance_ft=_nonnegative(data, "clearance_ft", context),
    )


def _work_center(data: Mapping[str, Any], center_id: str, label: str, context: str) -> WorkCenterSpec:
    return WorkCenterSpec(
        center_id=center_id,
        label=label,
        width_along_run_ft=_required_positive(data, "width_ft", context),
        depth_ft=_required_positive(data, "depth_ft", context),
    )


def _fixture(data: Mapping[str, Any], fixture_id: str, label: str, context: str) -> FixtureSpec:
    return FixtureSpec(
        fixture_id=fixture_id,
        label=label,
        width_ft=_required_positive(data, "width_ft", context),
        depth_ft=_required_positive(data, "depth_ft", context),
        front_clearance_ft=_nonnegative(data, "front_clearance_ft", context),
    )


def _raw_candidates(
    room: VerifiedRoom,
    role: str,
    profile: Mapping[str, Any],
) -> tuple[Any, ...]:
    rect = verified_room_rect(room)
    planner = profile.get("planner") or {}

    if role == RoomRole.KITCHEN.value:
        include_raw = planner.get("include_kinds")
        include = tuple(KitchenLayoutKind(str(item)) for item in include_raw) if include_raw else tuple(KitchenLayoutKind)
        return generate_kitchen_candidates(
            rect,
            counter_depth_ft=_required_positive(planner, "counter_depth_ft", "planner"),
            wall_margin_ft=_nonnegative(planner, "wall_margin_ft", "planner"),
            sink=_work_center(planner.get("sink") or {}, "sink", "Sink", "planner.sink"),
            hob=_work_center(planner.get("hob") or {}, "hob", "Hob", "planner.hob"),
            fridge=_work_center(planner.get("fridge") or {}, "fridge", "Fridge", "planner.fridge"),
            include_kinds=include,
        )

    if role == RoomRole.BEDROOM.value:
        bed_data = planner.get("bed") or {}
        wardrobe_data = planner.get("wardrobe") or {}
        desk_data = planner.get("desk")
        desk = None
        if desk_data:
            desk = DeskSpec(
                width_ft=_required_positive(desk_data, "width_ft", "planner.desk"),
                depth_ft=_required_positive(desk_data, "depth_ft", "planner.desk"),
            )
        return generate_bedroom_candidates(
            rect,
            bed=BedSpec(
                width_ft=_required_positive(bed_data, "width_ft", "planner.bed"),
                length_ft=_required_positive(bed_data, "length_ft", "planner.bed"),
            ),
            wardrobe=WardrobeSpec(
                run_ft=_required_positive(wardrobe_data, "run_ft", "planner.wardrobe"),
                depth_ft=_required_positive(wardrobe_data, "depth_ft", "planner.wardrobe"),
                height_ft=_required_positive(wardrobe_data, "height_ft", "planner.wardrobe"),
            ),
            desk=desk,
            wall_margin_ft=_nonnegative(planner, "wall_margin_ft", "planner"),
            side_clearance_ft=_nonnegative(profile.get("requirements") or {}, "side_clearance_ft", "requirements"),
            foot_clearance_ft=_nonnegative(profile.get("requirements") or {}, "foot_clearance_ft", "requirements"),
            wardrobe_front_clearance_ft=_nonnegative(
                profile.get("requirements") or {},
                "wardrobe_front_clearance_ft",
                "requirements",
            ),
        )

    if role == RoomRole.BATHROOM.value:
        shower_data = planner.get("shower") or {}
        return generate_bathroom_candidates(
            rect,
            shower=ShowerSpec(
                width_ft=_required_positive(shower_data, "width_ft", "planner.shower"),
                depth_ft=_required_positive(shower_data, "depth_ft", "planner.shower"),
            ),
            wc=_fixture(planner.get("wc") or {}, "wc", "WC", "planner.wc"),
            basin=_fixture(planner.get("basin") or {}, "basin", "Basin", "planner.basin"),
            wall_margin_ft=_nonnegative(planner, "wall_margin_ft", "planner"),
        )

    if role == RoomRole.DRAWING_DINING.value:
        return generate_drawing_dining_candidates(
            rect,
            sofa=_furniture(planner.get("sofa") or {}, "sofa", "Sofa", "planner.sofa"),
            tv_console=_furniture(
                planner.get("tv_console") or {},
                "tv_console",
                "TV console",
                "planner.tv_console",
            ),
            coffee_table=_furniture(
                planner.get("coffee_table") or {},
                "coffee_table",
                "Coffee table",
                "planner.coffee_table",
            ),
            dining_table=_furniture(
                planner.get("dining_table") or {},
                "dining_table",
                "Dining table",
                "planner.dining_table",
            ),
            living_fraction=_required_positive(planner, "living_fraction", "planner"),
            zone_gap_ft=_nonnegative(planner, "zone_gap_ft", "planner"),
            wall_margin_ft=_nonnegative(planner, "wall_margin_ft", "planner"),
        )

    raise ValueError(f"unsupported service-aware room role: {role}")


def _target_adapter(role: str, candidate: Any, room_id: str):
    if role == RoomRole.KITCHEN.value:
        return kitchen_service_targets(candidate, room_id)
    if role == RoomRole.BATHROOM.value:
        return bathroom_service_targets(candidate, room_id)
    if role == RoomRole.BEDROOM.value:
        return bedroom_service_targets(candidate, room_id)
    if role == RoomRole.DRAWING_DINING.value:
        return layout_service_targets(candidate, room_id)
    raise ValueError(f"unsupported service-aware room role: {role}")


def _parse_brief(payload: str | bytes | Mapping[str, Any]) -> tuple[dict[str, Any], str]:
    if isinstance(payload, Mapping):
        data = dict(payload)
        text = json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    else:
        text = payload.decode("utf-8") if isinstance(payload, bytes) else payload
        data = json.loads(text)
    if not isinstance(data, dict):
        raise ValueError("whole-home brief must be a JSON object")
    if data.get("schema") not in {None, "nitikube.whole_home_brief", "nitikube.service_aware_whole_home_brief"}:
        raise ValueError("unsupported service-aware whole-home brief schema")
    return data, text


def _service_rules_for_profile(profile: Mapping[str, Any]) -> CandidateServiceRuleSet | None:
    raw = profile.get("service_rules")
    if raw is None:
        return None
    if not isinstance(raw, Mapping):
        raise ValueError("room service_rules must be an object")
    return candidate_service_rules_from_dict(raw)


def _service_aware_candidate(
    base: FactoryCandidate,
    routing,
) -> FactoryCandidate:
    metrics = dict(base.metrics)
    if routing.total_route_ft is not None:
        metrics["service_total_route_ft"] = float(routing.total_route_ft)
    if routing.max_route_ft is not None:
        metrics["service_max_route_ft"] = float(routing.max_route_ft)
    failures = base.failed + tuple(f"service:{item}" for item in routing.failed)
    warnings = base.warnings + tuple(f"service:{item}" for item in routing.warnings)
    notes = base.notes + (
        "Service feasibility evaluated from actual candidate target coordinates against verified service-point evidence.",
        "Service route distances are straight-line lower bounds, not construction-ready routed lengths.",
    )
    features = tuple(dict.fromkeys(base.features + ("service_evaluated",)))
    return replace(
        base,
        feasible=base.feasible and routing.feasible,
        failed=failures,
        warnings=warnings,
        metrics=metrics,
        features=features,
        notes=notes,
    )


def _augment_package_hash(
    package: Mapping[str, Any],
    *,
    service_points_ref,
    brief_ref,
) -> dict[str, Any]:
    core = {key: value for key, value in package.items() if key != "package_id"}
    core["schema_version"] = "0.26"
    core["service_points_artifact"] = asdict(service_points_ref)
    core["service_aware_brief_artifact"] = asdict(brief_ref)
    core["service_feasibility_note"] = (
        "Selected options were filtered through candidate-specific verified service assignments before optimization. "
        "Service distances remain straight-line lower bounds and are not discipline-specific routed design."
    )
    return {**core, "package_id": sha256_bytes(canonical_json_bytes(core))}


def build_service_aware_whole_home_candidates(
    geometry_payload: str | bytes,
    brief_payload: str | bytes | Mapping[str, Any],
    service_points_payload: str | bytes,
    *,
    geometry_artifact_name: str = "nitikube_verified_geometry.json",
    service_points_artifact_name: str = "nitikube_service_points.json",
    brief_artifact_name: str = "nitikube_service_aware_whole_home_brief.json",
) -> ServiceAwareWholeHomeFactoryResult:
    geometry_text = geometry_payload.decode("utf-8") if isinstance(geometry_payload, bytes) else geometry_payload
    project_name, rooms, openings, _metadata = geometry_from_project_json(geometry_text)
    verified_rooms = [room for room in rooms if room.verified]
    if not verified_rooms:
        raise ValueError("verified geometry contains no verified rooms")

    brief, brief_text = _parse_brief(brief_payload)
    profiles = brief.get("rooms") or {}
    if not isinstance(profiles, Mapping):
        raise ValueError("brief.rooms must be an object keyed by room_id")

    service_points = load_service_points_json(service_points_payload, rooms=verified_rooms)
    service_text = service_points_payload.decode("utf-8") if isinstance(service_points_payload, bytes) else service_points_payload

    base_brief = dict(brief)
    base_brief.pop("optimization", None)
    base = build_whole_home_candidates(geometry_text, base_brief, geometry_artifact_name=geometry_artifact_name)

    room_lookup = {room.room_id: room for room in verified_rooms}
    new_room_results: list[RoomFactoryResult] = []
    service_audits: list[ServiceAwareRoomAudit] = []
    all_options: list[RoomDesignOption] = []
    diagnostics: list[str] = []

    for base_room in base.room_results:
        profile = profiles.get(base_room.room_id) or {}
        if base_room.status == "blocked" or base_room.role is None:
            new_room_results.append(base_room)
            service_audits.append(
                ServiceAwareRoomAudit(
                    base_room.room_id,
                    base_room.room_name,
                    base_room.role,
                    "not_evaluated_base_room_blocked",
                    0,
                    0,
                    0,
                    0,
                    base_room.errors,
                )
            )
            continue

        rules = _service_rules_for_profile(profile)
        if rules is None:
            # No service rule means this room retains v0.23 behavior. The audit is
            # explicit so absence is never misreported as a service PASS.
            rebuilt_options: list[RoomDesignOption] = []
            for candidate in base_room.candidates:
                option, _issues = candidate_to_optimizer_option(candidate, profile)
                if option is not None:
                    rebuilt_options.append(option)
            new_room = replace(base_room, optimizer_options=tuple(rebuilt_options))
            new_room_results.append(new_room)
            all_options.extend(rebuilt_options)
            service_audits.append(
                ServiceAwareRoomAudit(
                    base_room.room_id,
                    base_room.room_name,
                    base_room.role,
                    "not_configured",
                    0,
                    0,
                    0,
                    sum(candidate.feasible for candidate in base_room.candidates),
                    ("No service_rules block supplied for this room; service feasibility was not evaluated.",),
                )
            )
            continue

        try:
            raw_candidates = _raw_candidates(room_lookup[base_room.room_id], base_room.role, profile)
            raw_map = {candidate.layout_id: candidate for candidate in raw_candidates}
            base_ids = {candidate.layout_id for candidate in base_room.candidates}
            if set(raw_map) != base_ids:
                raise ValueError(
                    "service-aware candidate regeneration diverged from the v0.23 factory candidate IDs"
                )
            updated_candidates: list[FactoryCandidate] = []
            updated_options: list[RoomDesignOption] = []
            service_feasible = 0
            overall_feasible = 0
            for candidate in base_room.candidates:
                raw = raw_map[candidate.layout_id]
                targets = _target_adapter(base_room.role, raw, base_room.room_id)
                routing = evaluate_candidate_services(service_points, targets, rules)
                service_feasible += int(routing.feasible)
                updated = _service_aware_candidate(candidate, routing)
                overall_feasible += int(updated.feasible)
                updated_candidates.append(updated)
                option, _issues = candidate_to_optimizer_option(updated, profile)
                if option is not None:
                    updated_options.append(option)

            if not updated_candidates:
                status = "no_candidates_generated"
            elif updated_options:
                status = "optimizer_ready" if any(option.feasible for option in updated_options) else "service_blocked"
            else:
                status = "geometry_only"
            warnings = list(base_room.warnings)
            if rules.requirements == ():
                warnings.append("service_rules is configured with zero requirements; no service constraint was applied")
            new_room = replace(
                base_room,
                status=status,
                candidates=tuple(updated_candidates),
                optimizer_options=tuple(updated_options),
                warnings=tuple(warnings),
            )
            new_room_results.append(new_room)
            all_options.extend(updated_options)
            service_audits.append(
                ServiceAwareRoomAudit(
                    base_room.room_id,
                    base_room.room_name,
                    base_room.role,
                    "evaluated",
                    len(rules.requirements),
                    len(updated_candidates),
                    service_feasible,
                    overall_feasible,
                )
            )
        except Exception as exc:
            blocked = replace(
                base_room,
                status="blocked",
                candidates=(),
                optimizer_options=(),
                errors=base_room.errors + (f"service-aware factory: {exc}",),
            )
            new_room_results.append(blocked)
            service_audits.append(
                ServiceAwareRoomAudit(
                    base_room.room_id,
                    base_room.room_name,
                    base_room.role,
                    "blocked",
                    len(rules.requirements),
                    0,
                    0,
                    0,
                    (str(exc),),
                )
            )
            diagnostics.append(f"{base_room.room_id}: service-aware factory blocked: {exc}")

    options = tuple(all_options)
    option_ids = [option.option_id for option in options]
    if len(option_ids) != len(set(option_ids)):
        raise ValueError("service-aware factory produced duplicate globally unique option IDs")

    geometry_ref = artifact_ref(geometry_artifact_name, "verified_geometry", geometry_text)
    service_ref = artifact_ref(service_points_artifact_name, "service_points", service_text)
    brief_ref = artifact_ref(brief_artifact_name, "service_aware_whole_home_brief", brief_text)
    option_ref = None
    if options:
        option_ref = artifact_ref(
            "nitikube_service_aware_room_options.json",
            "room_design_options",
            room_options_json(options, project_name=project_name),
        )

    required_raw = brief.get("required_room_ids")
    required_room_ids = tuple(str(item) for item in (required_raw if required_raw is not None else base.required_room_ids))
    if not required_room_ids:
        raise ValueError("required_room_ids cannot be empty")

    viable_rooms = {
        room_id
        for room_id in required_room_ids
        if any(option.room_id == room_id and option.feasible for option in options)
    }
    missing_viable = sorted(set(required_room_ids) - viable_rooms)
    if missing_viable:
        diagnostics.append(
            "optimization not started because required rooms lack a feasible optimizer option after service-aware filtering: "
            + ", ".join(missing_viable)
        )

    optimization = None
    package = None
    optimization_data = brief.get("optimization")
    if optimization_data is not None and not isinstance(optimization_data, Mapping):
        raise ValueError("optimization must be an object when supplied")
    if optimization_data and not missing_viable:
        budget = _required_positive(optimization_data, "budget", "optimization")
        reserve = _nonnegative(optimization_data, "reserve", "optimization")
        weights = _score_weights(optimization_data.get("weights"))
        policies = _room_policies(optimization_data.get("policies"))
        locked_choices = {
            str(key): str(value)
            for key, value in (optimization_data.get("locked_choices") or {}).items()
        }
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
        if optimization.feasible:
            if option_ref is None:
                raise ValueError("feasible optimization has no option artifact")
            bundle = MergedOptionBundle(
                options=options,
                artifacts=(option_ref,),
                option_sources=tuple(
                    OptionSource(option.option_id, option_ref.name, option_ref.sha256)
                    for option in options
                ),
            )
            base_package = build_design_package(
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
            package = _augment_package_hash(
                base_package,
                service_points_ref=service_ref,
                brief_ref=brief_ref,
            )
        else:
            diagnostics.append("whole-home optimization ran but was infeasible: " + optimization.message)
    elif optimization_data is None:
        diagnostics.append("optimization was not requested; service-aware room candidates/options were generated only")

    return ServiceAwareWholeHomeFactoryResult(
        project_name=project_name,
        required_room_ids=required_room_ids,
        room_results=tuple(new_room_results),
        room_service_audits=tuple(service_audits),
        optimizer_options=options,
        optimization=optimization,
        design_package=package,
        geometry_sha256=geometry_ref.sha256,
        service_points_sha256=service_ref.sha256,
        brief_sha256=brief_ref.sha256,
        option_artifact_sha256=option_ref.sha256 if option_ref else None,
        diagnostics=tuple(diagnostics),
    )


def service_aware_factory_rows(result: ServiceAwareWholeHomeFactoryResult) -> list[dict[str, Any]]:
    base_by_room = {row["room_id"]: row for row in factory_rows(
        type("FactoryView", (), {"room_results": result.room_results})()
    )}
    service_by_room = {audit.room_id: audit for audit in result.room_service_audits}
    rows: list[dict[str, Any]] = []
    for room_id in result.required_room_ids:
        base = base_by_room.get(room_id, {})
        audit = service_by_room.get(room_id)
        rows.append(
            {
                **base,
                "service_status": audit.service_status if audit else "unknown",
                "service_rule_count": audit.service_rule_count if audit else 0,
                "service_candidates_checked": audit.candidates_checked if audit else 0,
                "service_feasible_candidates": audit.service_feasible_candidates if audit else 0,
                "overall_feasible_candidates": audit.overall_feasible_candidates if audit else 0,
                "service_notes": " | ".join(audit.notes) if audit else "",
            }
        )
    return rows


def service_aware_factory_audit_json(
    result: ServiceAwareWholeHomeFactoryResult,
    *,
    indent: int = 2,
) -> str:
    optimization = None
    if result.optimization is not None:
        optimization = {
            "feasible": result.optimization.feasible,
            "message": result.optimization.message,
            "budget": result.optimization.budget,
            "reserve": result.optimization.reserve,
            "selected_cost": result.optimization.selected_cost,
            "budget_remaining": result.optimization.budget_remaining,
            "total_utility": result.optimization.total_utility,
            "states_considered": result.optimization.states_considered,
            "selected": result_rows(result.optimization),
        }
    return json.dumps(
        {
            "schema": "nitikube.service_aware_whole_home_factory_audit",
            "schema_version": "0.26",
            "project_name": result.project_name,
            "required_room_ids": list(result.required_room_ids),
            "optimizer_ready": result.optimizer_ready,
            "artifacts": {
                "geometry_sha256": result.geometry_sha256,
                "service_points_sha256": result.service_points_sha256,
                "brief_sha256": result.brief_sha256,
                "option_artifact_sha256": result.option_artifact_sha256,
            },
            "rooms": service_aware_factory_rows(result),
            "optimization": optimization,
            "design_package_id": result.design_package.get("package_id") if result.design_package else None,
            "diagnostics": list(result.diagnostics),
        },
        indent=indent,
        ensure_ascii=False,
    )
