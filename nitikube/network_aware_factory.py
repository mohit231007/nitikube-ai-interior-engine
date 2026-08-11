from __future__ import annotations

from dataclasses import asdict, dataclass, replace
import json
import math
from typing import Any, Mapping, Sequence

from .home_optimizer import HomeOptimizationResult, RoomDesignOption, optimize_home, result_rows
from .project_orchestrator import (
    MergedOptionBundle,
    OptionSource,
    artifact_ref,
    build_design_package,
    canonical_json_bytes,
    sha256_bytes,
)
from .service_aware_candidates import CandidateServiceRuleSet
from .service_aware_factory import (
    ServiceAwareRoomAudit,
    _parse_brief,
    _raw_candidates,
    _service_rules_for_profile,
    _target_adapter,
)
from .service_network import (
    NetworkRoutingPolicy,
    NetworkRoutingResult,
    ServiceNetwork,
    evaluate_network_routing,
    load_service_network_json,
)
from .service_points import ServicePoint, ServiceRequirement, ServiceTarget, load_service_points_json
from .verified_geometry import geometry_from_project_json
from .whole_home_factory import (
    FactoryCandidate,
    RoomFactoryResult,
    _optimizer_geometries,
    _room_policies,
    _score_weights,
    build_whole_home_candidates,
    candidate_to_optimizer_option,
    factory_rows,
    room_options_json,
)


@dataclass(frozen=True)
class NetworkAwareWholeHomeFactoryResult:
    project_name: str
    required_room_ids: tuple[str, ...]
    room_results: tuple[RoomFactoryResult, ...]
    room_service_audits: tuple[ServiceAwareRoomAudit, ...]
    optimizer_options: tuple[RoomDesignOption, ...]
    optimization: HomeOptimizationResult | None
    design_package: Mapping[str, Any] | None
    geometry_sha256: str
    service_points_sha256: str
    service_network_sha256: str
    brief_sha256: str
    option_artifact_sha256: str | None
    diagnostics: tuple[str, ...]

    @property
    def optimizer_ready(self) -> bool:
        viable = {
            room_id
            for room_id in self.required_room_ids
            if any(option.room_id == room_id and option.feasible for option in self.optimizer_options)
        }
        return bool(self.required_room_ids) and viable == set(self.required_room_ids)


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


def _network_policy(
    brief: Mapping[str, Any],
    profile: Mapping[str, Any],
    rules: CandidateServiceRuleSet,
) -> NetworkRoutingPolicy:
    global_data = brief.get("network_routing") or {}
    room_data = profile.get("network_routing") or {}
    if not isinstance(global_data, Mapping) or not isinstance(room_data, Mapping):
        raise ValueError("network_routing must be an object at project/room scope")

    merged = dict(global_data)
    merged.update(room_data)
    max_access = _nonnegative(merged, "max_target_access_ft", "network_routing", default=-1.0)
    if max_access < 0:
        raise ValueError("network_routing.max_target_access_ft is required for rooms with service_rules")
    require_verified = merged.get("require_verified_network", True)
    same_room = merged.get("same_room_target_access", True)
    if not isinstance(require_verified, bool) or not isinstance(same_room, bool):
        raise ValueError("network routing boolean policy fields must be boolean")
    return NetworkRoutingPolicy(
        max_target_access_ft=max_access,
        distance_mode=rules.distance_mode,
        allow_shared_points=rules.allow_shared_points,
        require_verified_network=require_verified,
        same_room_target_access=same_room,
    )


def _evaluate_candidate_network_services(
    points: Sequence[ServicePoint],
    targets: Sequence[ServiceTarget],
    rules: CandidateServiceRuleSet,
    network: ServiceNetwork,
    policy: NetworkRoutingPolicy,
) -> NetworkRoutingResult:
    target_ids = {target.target_id for target in targets}
    applicable: list[ServiceRequirement] = []
    pre_failed: list[str] = []
    pre_warnings: list[str] = []
    for requirement in rules.requirements:
        if requirement.target_id in target_ids:
            applicable.append(requirement)
        elif requirement.required:
            pre_failed.append(f"{requirement.requirement_id}:target_absent_from_candidate")
        else:
            pre_warnings.append(f"{requirement.requirement_id}:optional_target_absent_from_candidate")

    if applicable:
        base = evaluate_network_routing(points, targets, applicable, network, policy)
    else:
        base = NetworkRoutingResult(
            feasible=True,
            assignments=(),
            failed=(),
            warnings=(),
            total_route_ft=0.0,
            max_route_ft=0.0,
            distance_mode=policy.distance_mode,
            allow_shared_points=policy.allow_shared_points,
        )

    failed = tuple(pre_failed) + tuple(base.failed)
    warnings = tuple(pre_warnings) + tuple(base.warnings)
    return NetworkRoutingResult(
        feasible=not failed,
        assignments=base.assignments,
        failed=failed,
        warnings=warnings,
        total_route_ft=base.total_route_ft,
        max_route_ft=base.max_route_ft,
        distance_mode=base.distance_mode,
        allow_shared_points=base.allow_shared_points,
        model_note=base.model_note,
    )


def _network_aware_candidate(base: FactoryCandidate, routing: NetworkRoutingResult) -> FactoryCandidate:
    metrics = dict(base.metrics)
    if routing.total_route_ft is not None:
        metrics["service_network_total_route_ft"] = float(routing.total_route_ft)
    if routing.max_route_ft is not None:
        metrics["service_network_max_route_ft"] = float(routing.max_route_ft)
    failures = base.failed + tuple(f"service_network:{item}" for item in routing.failed)
    warnings = base.warnings + tuple(f"service_network:{item}" for item in routing.warnings)
    notes = base.notes + (
        "Service feasibility evaluated against candidate target coordinates using the verified routing graph.",
        "Route length = bounded target-access connector + compatible verified network edges; this is not discipline-specific MEP engineering.",
    )
    features = tuple(dict.fromkeys(base.features + ("service_network_evaluated",)))
    return replace(
        base,
        feasible=base.feasible and routing.feasible,
        failed=failures,
        warnings=warnings,
        metrics=metrics,
        features=features,
        notes=notes,
    )


def _augment_package(
    package: Mapping[str, Any],
    *,
    service_points_ref,
    service_network_ref,
    brief_ref,
    project_network_policy: Mapping[str, Any],
) -> dict[str, Any]:
    core = {key: value for key, value in package.items() if key != "package_id"}
    core["schema_version"] = "0.28"
    core["service_points_artifact"] = asdict(service_points_ref)
    core["service_network_artifact"] = asdict(service_network_ref)
    core["network_aware_brief_artifact"] = asdict(brief_ref)
    core["network_routing_policy"] = dict(project_network_policy)
    core["service_feasibility_note"] = (
        "Selected options were filtered through candidate-specific routes constrained to explicit verified service-network edges before optimization. "
        "The route model is geometric and does not replace plumbing/electrical/gas/ventilation engineering."
    )
    return {**core, "package_id": sha256_bytes(canonical_json_bytes(core))}


def build_network_aware_whole_home_candidates(
    geometry_payload: str | bytes,
    brief_payload: str | bytes | Mapping[str, Any],
    service_points_payload: str | bytes,
    service_network_payload: str | bytes,
    *,
    geometry_artifact_name: str = "nitikube_verified_geometry.json",
    service_points_artifact_name: str = "nitikube_service_points.json",
    service_network_artifact_name: str = "nitikube_service_network.json",
    brief_artifact_name: str = "nitikube_network_aware_whole_home_brief.json",
) -> NetworkAwareWholeHomeFactoryResult:
    geometry_text = geometry_payload.decode("utf-8") if isinstance(geometry_payload, bytes) else geometry_payload
    project_name, rooms, openings, _metadata = geometry_from_project_json(geometry_text)
    verified_rooms = [room for room in rooms if room.verified]
    if not verified_rooms:
        raise ValueError("verified geometry contains no verified rooms")

    brief, brief_text = _parse_brief(brief_payload)
    profiles = brief.get("rooms") or {}
    if not isinstance(profiles, Mapping):
        raise ValueError("brief.rooms must be an object keyed by room_id")
    project_network_policy = brief.get("network_routing") or {}
    if not isinstance(project_network_policy, Mapping):
        raise ValueError("network_routing must be an object")

    service_points = load_service_points_json(service_points_payload, rooms=verified_rooms)
    service_text = service_points_payload.decode("utf-8") if isinstance(service_points_payload, bytes) else service_points_payload
    network = load_service_network_json(
        service_network_payload,
        rooms=verified_rooms,
        service_points=service_points,
    )
    network_text = service_network_payload.decode("utf-8") if isinstance(service_network_payload, bytes) else service_network_payload

    # v0.23 factory intentionally accepts its own schema. Keep the v0.28 brief
    # unchanged for provenance while dispatching a schema-adapted copy internally.
    base_brief = dict(brief)
    base_brief["schema"] = "nitikube.whole_home_brief"
    base_brief.pop("optimization", None)
    base_brief.pop("network_routing", None)
    base = build_whole_home_candidates(
        geometry_text,
        base_brief,
        geometry_artifact_name=geometry_artifact_name,
    )

    room_lookup = {room.room_id: room for room in verified_rooms}
    room_results: list[RoomFactoryResult] = []
    audits: list[ServiceAwareRoomAudit] = []
    all_options: list[RoomDesignOption] = []
    diagnostics: list[str] = []

    for base_room in base.room_results:
        profile = profiles.get(base_room.room_id) or {}
        if base_room.status == "blocked" or base_room.role is None:
            room_results.append(base_room)
            audits.append(
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
            rebuilt: list[RoomDesignOption] = []
            for candidate in base_room.candidates:
                option, _issues = candidate_to_optimizer_option(candidate, profile)
                if option is not None:
                    rebuilt.append(option)
            new_room = replace(base_room, optimizer_options=tuple(rebuilt))
            room_results.append(new_room)
            all_options.extend(rebuilt)
            audits.append(
                ServiceAwareRoomAudit(
                    base_room.room_id,
                    base_room.room_name,
                    base_room.role,
                    "not_configured",
                    0,
                    0,
                    0,
                    sum(candidate.feasible for candidate in base_room.candidates),
                    ("No service_rules block supplied; verified network routing was not evaluated for this room.",),
                )
            )
            continue

        try:
            policy = _network_policy(brief, profile, rules)
            raw_candidates = _raw_candidates(room_lookup[base_room.room_id], base_room.role, profile)
            raw_map = {candidate.layout_id: candidate for candidate in raw_candidates}
            base_ids = {candidate.layout_id for candidate in base_room.candidates}
            if set(raw_map) != base_ids:
                raise ValueError("network-aware candidate regeneration diverged from base factory candidate IDs")

            updated_candidates: list[FactoryCandidate] = []
            updated_options: list[RoomDesignOption] = []
            service_feasible = 0
            overall_feasible = 0
            for candidate in base_room.candidates:
                raw = raw_map[candidate.layout_id]
                targets = _target_adapter(base_room.role, raw, base_room.room_id)
                routing = _evaluate_candidate_network_services(
                    service_points,
                    targets,
                    rules,
                    network,
                    policy,
                )
                service_feasible += int(routing.feasible)
                updated = _network_aware_candidate(candidate, routing)
                overall_feasible += int(updated.feasible)
                updated_candidates.append(updated)
                option, _issues = candidate_to_optimizer_option(updated, profile)
                if option is not None:
                    updated_options.append(option)

            if not updated_candidates:
                status = "no_candidates_generated"
            elif updated_options:
                status = "optimizer_ready" if any(option.feasible for option in updated_options) else "service_network_blocked"
            else:
                status = "geometry_only"
            new_room = replace(
                base_room,
                status=status,
                candidates=tuple(updated_candidates),
                optimizer_options=tuple(updated_options),
            )
            room_results.append(new_room)
            all_options.extend(updated_options)
            audits.append(
                ServiceAwareRoomAudit(
                    base_room.room_id,
                    base_room.room_name,
                    base_room.role,
                    "network_evaluated",
                    len(rules.requirements),
                    len(updated_candidates),
                    service_feasible,
                    overall_feasible,
                    (
                        f"max_target_access_ft={policy.max_target_access_ft}",
                        f"same_room_target_access={policy.same_room_target_access}",
                        f"require_verified_network={policy.require_verified_network}",
                    ),
                )
            )
        except Exception as exc:
            blocked = replace(
                base_room,
                status="blocked",
                candidates=(),
                optimizer_options=(),
                errors=base_room.errors + (f"network-aware factory: {exc}",),
            )
            room_results.append(blocked)
            audits.append(
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
            diagnostics.append(f"{base_room.room_id}: network-aware factory blocked: {exc}")

    options = tuple(all_options)
    option_ids = [option.option_id for option in options]
    if len(option_ids) != len(set(option_ids)):
        raise ValueError("network-aware factory produced duplicate globally unique option IDs")

    geometry_ref = artifact_ref(geometry_artifact_name, "verified_geometry", geometry_text)
    service_ref = artifact_ref(service_points_artifact_name, "service_points", service_text)
    network_ref = artifact_ref(service_network_artifact_name, "service_network", network_text)
    brief_ref = artifact_ref(brief_artifact_name, "network_aware_whole_home_brief", brief_text)
    option_ref = None
    if options:
        option_ref = artifact_ref(
            "nitikube_network_aware_room_options.json",
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
            "optimization not started because required rooms lack a feasible optimizer option after verified-network filtering: "
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
            package = _augment_package(
                base_package,
                service_points_ref=service_ref,
                service_network_ref=network_ref,
                brief_ref=brief_ref,
                project_network_policy=project_network_policy,
            )
        else:
            diagnostics.append("whole-home optimization ran but was infeasible: " + optimization.message)
    elif optimization_data is None:
        diagnostics.append("optimization was not requested; network-aware room candidates/options were generated only")

    return NetworkAwareWholeHomeFactoryResult(
        project_name=project_name,
        required_room_ids=required_room_ids,
        room_results=tuple(room_results),
        room_service_audits=tuple(audits),
        optimizer_options=options,
        optimization=optimization,
        design_package=package,
        geometry_sha256=geometry_ref.sha256,
        service_points_sha256=service_ref.sha256,
        service_network_sha256=network_ref.sha256,
        brief_sha256=brief_ref.sha256,
        option_artifact_sha256=option_ref.sha256 if option_ref else None,
        diagnostics=tuple(diagnostics),
    )


def network_aware_factory_rows(result: NetworkAwareWholeHomeFactoryResult) -> list[dict[str, Any]]:
    base_by_room = {
        row["room_id"]: row
        for row in factory_rows(type("FactoryView", (), {"room_results": result.room_results})())
    }
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


def network_aware_factory_audit_json(
    result: NetworkAwareWholeHomeFactoryResult,
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
            "schema": "nitikube.network_aware_whole_home_factory_audit",
            "schema_version": "0.28",
            "project_name": result.project_name,
            "required_room_ids": list(result.required_room_ids),
            "optimizer_ready": result.optimizer_ready,
            "artifacts": {
                "geometry_sha256": result.geometry_sha256,
                "service_points_sha256": result.service_points_sha256,
                "service_network_sha256": result.service_network_sha256,
                "brief_sha256": result.brief_sha256,
                "option_artifact_sha256": result.option_artifact_sha256,
            },
            "rooms": network_aware_factory_rows(result),
            "optimization": optimization,
            "design_package_id": result.design_package.get("package_id") if result.design_package else None,
            "diagnostics": list(result.diagnostics),
        },
        indent=indent,
        ensure_ascii=False,
    )
