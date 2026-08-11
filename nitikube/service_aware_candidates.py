from __future__ import annotations

from dataclasses import asdict, dataclass
import json
import math
from typing import Any, Iterable, Mapping, Sequence

from .bathroom_planner import (
    BathroomCandidate,
    BathroomEvaluation,
    BathroomRequirements,
    evaluate_bathroom,
)
from .bedroom_planner import (
    BedroomCandidate,
    BedroomEvaluation,
    BedroomRequirements,
    WardrobeSpec,
    evaluate_bedroom,
)
from .kitchen_planner import (
    KitchenCandidate,
    KitchenEvaluation,
    KitchenRequirements,
    evaluate_kitchen,
)
from .room_layout import (
    KeepoutZone,
    LayoutCandidate,
    LayoutEvaluation,
    LayoutRequirements,
    Rect,
    evaluate_layout,
)
from .service_points import (
    ServiceAssignment,
    ServicePoint,
    ServiceRequirement,
    ServiceRoutingResult,
    ServiceTarget,
    bathroom_service_targets,
    bedroom_service_targets,
    evaluate_service_routing,
    kitchen_service_targets,
    layout_service_targets,
)
from .service_routing_io import requirement_from_dict


@dataclass(frozen=True)
class CandidateServiceRuleSet:
    requirements: tuple[ServiceRequirement, ...]
    allow_shared_points: bool = False
    distance_mode: str = "plan"


@dataclass(frozen=True)
class ServiceAwareCandidateEvaluation:
    candidate_id: str
    candidate_name: str
    geometry_feasible: bool
    service_feasible: bool
    overall_feasible: bool
    geometry_score: float
    service_total_route_ft: float | None
    service_max_route_ft: float | None
    geometry_failed: tuple[str, ...]
    service_failed: tuple[str, ...]
    geometry_warnings: tuple[str, ...]
    service_warnings: tuple[str, ...]
    service_assignments: tuple[ServiceAssignment, ...]


@dataclass(frozen=True)
class ServiceAwareKitchenResult:
    candidate: KitchenCandidate
    geometry: KitchenEvaluation
    services: ServiceRoutingResult
    evaluation: ServiceAwareCandidateEvaluation


@dataclass(frozen=True)
class ServiceAwareBedroomResult:
    candidate: BedroomCandidate
    geometry: BedroomEvaluation
    services: ServiceRoutingResult
    evaluation: ServiceAwareCandidateEvaluation


@dataclass(frozen=True)
class ServiceAwareBathroomResult:
    candidate: BathroomCandidate
    geometry: BathroomEvaluation
    services: ServiceRoutingResult
    evaluation: ServiceAwareCandidateEvaluation


@dataclass(frozen=True)
class ServiceAwareLayoutResult:
    candidate: LayoutCandidate
    geometry: LayoutEvaluation
    services: ServiceRoutingResult
    evaluation: ServiceAwareCandidateEvaluation


def _requirement_ids(requirements: Sequence[ServiceRequirement]) -> None:
    seen: set[str] = set()
    for requirement in requirements:
        if requirement.requirement_id in seen:
            raise ValueError(f"duplicate service requirement_id: {requirement.requirement_id}")
        seen.add(requirement.requirement_id)


def candidate_service_rules_from_dict(data: Mapping[str, Any]) -> CandidateServiceRuleSet:
    if data.get("schema") not in {None, "nitikube.candidate_service_rules"}:
        raise ValueError("unsupported candidate-service-rule schema")
    rows = data.get("requirements", [])
    if not isinstance(rows, list):
        raise ValueError("candidate service requirements must be a list")
    requirements = tuple(requirement_from_dict(row) for row in rows)
    _requirement_ids(requirements)
    allow_shared = data.get("allow_shared_points", False)
    if not isinstance(allow_shared, bool):
        raise ValueError("allow_shared_points must be boolean")
    distance_mode = str(data.get("distance_mode") or "plan")
    if distance_mode not in {"plan", "3d"}:
        raise ValueError("distance_mode must be 'plan' or '3d'")
    return CandidateServiceRuleSet(requirements, allow_shared, distance_mode)


def load_candidate_service_rules_json(payload: str | bytes) -> CandidateServiceRuleSet:
    text = payload.decode("utf-8") if isinstance(payload, bytes) else payload
    data = json.loads(text)
    if not isinstance(data, dict):
        raise ValueError("candidate service rule JSON must be an object")
    return candidate_service_rules_from_dict(data)


def candidate_service_rules_json(rules: CandidateServiceRuleSet, *, indent: int = 2) -> str:
    return json.dumps(
        {
            "schema": "nitikube.candidate_service_rules",
            "schema_version": "0.25",
            "allow_shared_points": rules.allow_shared_points,
            "distance_mode": rules.distance_mode,
            "requirements": [
                {
                    "requirement_id": requirement.requirement_id,
                    "target_id": requirement.target_id,
                    "allowed_kinds": [kind.value for kind in requirement.allowed_kinds],
                    "max_route_ft": requirement.max_route_ft,
                    "required": requirement.required,
                }
                for requirement in rules.requirements
            ],
        },
        indent=indent,
        ensure_ascii=False,
    )


def candidate_service_rules_template(*, indent: int = 2) -> str:
    payload = {
        "schema": "nitikube.candidate_service_rules",
        "schema_version": "0.25",
        "allow_shared_points": False,
        "distance_mode": "plan",
        "requirements": [
            {
                "requirement_id": "example-required-service",
                "target_id": "replace-with-planner-target-id",
                "allowed_kinds": ["electrical"],
                "max_route_ft": None,
                "required": True,
            }
        ],
        "target_id_examples": {
            "kitchen": ["sink", "hob", "fridge"],
            "bathroom": ["shower", "wc", "basin"],
            "bedroom": ["bed", "wardrobe", "desk (only when candidate has desk)"],
            "drawing_dining": ["planner furniture item_id values"],
        },
        "template_note": (
            "Rules describe service evidence required by candidate targets. They do not invent which service a product needs; "
            "derive allowed kinds / limits from verified product data, the homeowner brief or sourced professional requirements."
        ),
    }
    return json.dumps(payload, indent=indent, ensure_ascii=False)


def evaluate_candidate_services(
    points: Sequence[ServicePoint],
    targets: Sequence[ServiceTarget],
    rules: CandidateServiceRuleSet,
) -> ServiceRoutingResult:
    """Evaluate service rules against one candidate's actual target coordinates.

    Rules referencing a target absent from this particular candidate are handled
    explicitly: required => failure, optional => warning. Existing targets are
    still evaluated so the audit retains all achievable assignments.
    """
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
        base = evaluate_service_routing(
            points,
            targets,
            applicable,
            allow_shared_points=rules.allow_shared_points,
            distance_mode=rules.distance_mode,
        )
    else:
        base = ServiceRoutingResult(
            feasible=True,
            assignments=(),
            failed=(),
            warnings=(),
            total_route_ft=0.0,
            max_route_ft=0.0,
            distance_mode=rules.distance_mode,
            allow_shared_points=rules.allow_shared_points,
        )

    failed = tuple(pre_failed) + tuple(base.failed)
    warnings = tuple(pre_warnings) + tuple(base.warnings)
    return ServiceRoutingResult(
        feasible=not failed,
        assignments=base.assignments,
        failed=failed,
        warnings=warnings,
        total_route_ft=base.total_route_ft,
        max_route_ft=base.max_route_ft,
        distance_mode=base.distance_mode,
        allow_shared_points=base.allow_shared_points,
    )


def _combined(
    *,
    candidate_id: str,
    candidate_name: str,
    geometry_feasible: bool,
    geometry_score: float,
    geometry_failed: Sequence[str],
    geometry_warnings: Sequence[str],
    services: ServiceRoutingResult,
) -> ServiceAwareCandidateEvaluation:
    return ServiceAwareCandidateEvaluation(
        candidate_id=candidate_id,
        candidate_name=candidate_name,
        geometry_feasible=geometry_feasible,
        service_feasible=services.feasible,
        overall_feasible=geometry_feasible and services.feasible,
        geometry_score=float(geometry_score),
        service_total_route_ft=services.total_route_ft,
        service_max_route_ft=services.max_route_ft,
        geometry_failed=tuple(geometry_failed),
        service_failed=tuple(services.failed),
        geometry_warnings=tuple(geometry_warnings),
        service_warnings=tuple(services.warnings),
        service_assignments=tuple(services.assignments),
    )


def evaluate_kitchen_candidate_with_services(
    room: Rect,
    room_id: str,
    candidate: KitchenCandidate,
    service_points: Sequence[ServicePoint],
    service_rules: CandidateServiceRuleSet,
    *,
    keepouts: Sequence[KeepoutZone] = (),
    requirements: KitchenRequirements | None = None,
) -> ServiceAwareKitchenResult:
    geometry = evaluate_kitchen(room, candidate, keepouts=keepouts, requirements=requirements)
    services = evaluate_candidate_services(
        service_points,
        kitchen_service_targets(candidate, room_id),
        service_rules,
    )
    combined = _combined(
        candidate_id=candidate.layout_id,
        candidate_name=candidate.name,
        geometry_feasible=geometry.feasible,
        geometry_score=geometry.geometry_score,
        geometry_failed=geometry.failed,
        geometry_warnings=geometry.warnings,
        services=services,
    )
    return ServiceAwareKitchenResult(candidate, geometry, services, combined)


def evaluate_bathroom_candidate_with_services(
    room: Rect,
    room_id: str,
    candidate: BathroomCandidate,
    service_points: Sequence[ServicePoint],
    service_rules: CandidateServiceRuleSet,
    *,
    keepouts: Sequence[KeepoutZone] = (),
    requirements: BathroomRequirements | None = None,
) -> ServiceAwareBathroomResult:
    geometry = evaluate_bathroom(room, candidate, keepouts=keepouts, requirements=requirements)
    services = evaluate_candidate_services(
        service_points,
        bathroom_service_targets(candidate, room_id),
        service_rules,
    )
    combined = _combined(
        candidate_id=candidate.layout_id,
        candidate_name=candidate.name,
        geometry_feasible=geometry.feasible,
        geometry_score=geometry.geometry_score,
        geometry_failed=geometry.failed,
        geometry_warnings=geometry.warnings,
        services=services,
    )
    return ServiceAwareBathroomResult(candidate, geometry, services, combined)


def evaluate_bedroom_candidate_with_services(
    room: Rect,
    room_id: str,
    candidate: BedroomCandidate,
    wardrobe_spec: WardrobeSpec,
    service_points: Sequence[ServicePoint],
    service_rules: CandidateServiceRuleSet,
    *,
    keepouts: Sequence[KeepoutZone] = (),
    requirements: BedroomRequirements | None = None,
) -> ServiceAwareBedroomResult:
    geometry = evaluate_bedroom(
        room,
        candidate,
        wardrobe_spec,
        keepouts=keepouts,
        requirements=requirements,
    )
    services = evaluate_candidate_services(
        service_points,
        bedroom_service_targets(candidate, room_id),
        service_rules,
    )
    combined = _combined(
        candidate_id=candidate.layout_id,
        candidate_name=candidate.name,
        geometry_feasible=geometry.feasible,
        geometry_score=geometry.geometry_score,
        geometry_failed=geometry.failed,
        geometry_warnings=geometry.warnings,
        services=services,
    )
    return ServiceAwareBedroomResult(candidate, geometry, services, combined)


def evaluate_layout_candidate_with_services(
    room: Rect,
    room_id: str,
    candidate: LayoutCandidate,
    service_points: Sequence[ServicePoint],
    service_rules: CandidateServiceRuleSet,
    *,
    keepouts: Sequence[KeepoutZone] = (),
    requirements: LayoutRequirements | None = None,
) -> ServiceAwareLayoutResult:
    geometry = evaluate_layout(room, candidate, keepouts=keepouts, requirements=requirements)
    services = evaluate_candidate_services(
        service_points,
        layout_service_targets(candidate, room_id),
        service_rules,
    )
    combined = _combined(
        candidate_id=candidate.layout_id,
        candidate_name=candidate.name,
        geometry_feasible=geometry.feasible,
        geometry_score=geometry.geometry_score,
        geometry_failed=geometry.failed,
        geometry_warnings=geometry.warnings,
        services=services,
    )
    return ServiceAwareLayoutResult(candidate, geometry, services, combined)


def _route_sort_value(value: float | None) -> float:
    if value is None or not math.isfinite(value):
        return math.inf
    return value


def _rank_key(evaluation: ServiceAwareCandidateEvaluation) -> tuple[int, float, float, str]:
    # Service routing is a hard feasibility layer. It never rewrites geometry_score.
    # Among equally feasible candidates, geometry quality remains primary and the
    # shorter straight-line service lower-bound is only a transparent tie-breaker.
    return (
        0 if evaluation.overall_feasible else 1,
        -evaluation.geometry_score,
        _route_sort_value(evaluation.service_total_route_ft),
        evaluation.candidate_id,
    )


def rank_service_aware_kitchens(
    room: Rect,
    room_id: str,
    candidates: Iterable[KitchenCandidate],
    service_points: Sequence[ServicePoint],
    service_rules: CandidateServiceRuleSet,
    *,
    keepouts: Sequence[KeepoutZone] = (),
    requirements: KitchenRequirements | None = None,
) -> list[ServiceAwareKitchenResult]:
    results = [
        evaluate_kitchen_candidate_with_services(
            room,
            room_id,
            candidate,
            service_points,
            service_rules,
            keepouts=keepouts,
            requirements=requirements,
        )
        for candidate in candidates
    ]
    return sorted(results, key=lambda item: _rank_key(item.evaluation))


def rank_service_aware_bathrooms(
    room: Rect,
    room_id: str,
    candidates: Iterable[BathroomCandidate],
    service_points: Sequence[ServicePoint],
    service_rules: CandidateServiceRuleSet,
    *,
    keepouts: Sequence[KeepoutZone] = (),
    requirements: BathroomRequirements | None = None,
) -> list[ServiceAwareBathroomResult]:
    results = [
        evaluate_bathroom_candidate_with_services(
            room,
            room_id,
            candidate,
            service_points,
            service_rules,
            keepouts=keepouts,
            requirements=requirements,
        )
        for candidate in candidates
    ]
    return sorted(results, key=lambda item: _rank_key(item.evaluation))


def rank_service_aware_bedrooms(
    room: Rect,
    room_id: str,
    candidates: Iterable[BedroomCandidate],
    wardrobe_spec: WardrobeSpec,
    service_points: Sequence[ServicePoint],
    service_rules: CandidateServiceRuleSet,
    *,
    keepouts: Sequence[KeepoutZone] = (),
    requirements: BedroomRequirements | None = None,
) -> list[ServiceAwareBedroomResult]:
    results = [
        evaluate_bedroom_candidate_with_services(
            room,
            room_id,
            candidate,
            wardrobe_spec,
            service_points,
            service_rules,
            keepouts=keepouts,
            requirements=requirements,
        )
        for candidate in candidates
    ]
    return sorted(results, key=lambda item: _rank_key(item.evaluation))


def rank_service_aware_layouts(
    room: Rect,
    room_id: str,
    candidates: Iterable[LayoutCandidate],
    service_points: Sequence[ServicePoint],
    service_rules: CandidateServiceRuleSet,
    *,
    keepouts: Sequence[KeepoutZone] = (),
    requirements: LayoutRequirements | None = None,
) -> list[ServiceAwareLayoutResult]:
    results = [
        evaluate_layout_candidate_with_services(
            room,
            room_id,
            candidate,
            service_points,
            service_rules,
            keepouts=keepouts,
            requirements=requirements,
        )
        for candidate in candidates
    ]
    return sorted(results, key=lambda item: _rank_key(item.evaluation))


def service_aware_rows(results: Sequence[Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for result in results:
        evaluation: ServiceAwareCandidateEvaluation = result.evaluation
        rows.append(
            {
                "candidate_id": evaluation.candidate_id,
                "candidate_name": evaluation.candidate_name,
                "geometry_feasible": evaluation.geometry_feasible,
                "service_feasible": evaluation.service_feasible,
                "overall_feasible": evaluation.overall_feasible,
                "geometry_score": evaluation.geometry_score,
                "service_total_route_ft": evaluation.service_total_route_ft,
                "service_max_route_ft": evaluation.service_max_route_ft,
                "geometry_failed": " | ".join(evaluation.geometry_failed),
                "service_failed": " | ".join(evaluation.service_failed),
                "geometry_warnings": " | ".join(evaluation.geometry_warnings),
                "service_warnings": " | ".join(evaluation.service_warnings),
                "service_assignment_count": len(evaluation.service_assignments),
            }
        )
    return rows


def service_aware_evaluation_json(
    evaluation: ServiceAwareCandidateEvaluation,
    *,
    indent: int = 2,
) -> str:
    return json.dumps(
        {
            "schema": "nitikube.service_aware_candidate_evaluation",
            "schema_version": "0.25",
            **asdict(evaluation),
            "model_boundary": (
                "Overall feasibility is geometry feasibility AND service-assignment feasibility. "
                "Service routing uses the v0.24 straight-line lower-bound model and does not certify discipline-specific routed design or code compliance."
            ),
        },
        indent=indent,
        ensure_ascii=False,
    )
