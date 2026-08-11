from __future__ import annotations

import json
from typing import Any, Mapping

from .service_points import ServiceKind, ServiceRequirement, ServiceTarget, target_from_dict, validate_requirement


def requirement_from_dict(data: Mapping[str, Any]) -> ServiceRequirement:
    allowed_raw = data.get("allowed_kinds")
    if allowed_raw is None or allowed_raw == "":
        raise ValueError("allowed_kinds is required")
    if not isinstance(allowed_raw, list):
        raise ValueError("allowed_kinds must be a list")
    requirement = ServiceRequirement(
        requirement_id=str(data.get("requirement_id") or ""),
        target_id=str(data.get("target_id") or ""),
        allowed_kinds=tuple(ServiceKind(str(item)) for item in allowed_raw),
        max_route_ft=None if data.get("max_route_ft") in {None, ""} else float(data["max_route_ft"]),
        required=bool(data.get("required", True)),
    )
    validate_requirement(requirement)
    return requirement


def load_service_routing_brief(
    payload: str | bytes,
) -> tuple[tuple[ServiceTarget, ...], tuple[ServiceRequirement, ...], bool, str]:
    text = payload.decode("utf-8") if isinstance(payload, bytes) else payload
    data = json.loads(text)
    if not isinstance(data, dict):
        raise ValueError("service routing brief must be a JSON object")
    if data.get("schema") not in {None, "nitikube.service_routing_brief"}:
        raise ValueError("unsupported service routing brief schema")
    targets = tuple(target_from_dict(row) for row in data.get("targets", []))
    requirements = tuple(requirement_from_dict(row) for row in data.get("requirements", []))
    allow_shared = bool(data.get("allow_shared_points", False))
    distance_mode = str(data.get("distance_mode") or "plan")
    if distance_mode not in {"plan", "3d"}:
        raise ValueError("distance_mode must be 'plan' or '3d'")
    target_ids = [target.target_id for target in targets]
    if len(target_ids) != len(set(target_ids)):
        raise ValueError("service target_id values must be unique")
    requirement_ids = [item.requirement_id for item in requirements]
    if len(requirement_ids) != len(set(requirement_ids)):
        raise ValueError("service requirement_id values must be unique")
    known_targets = set(target_ids)
    missing_targets = sorted({item.target_id for item in requirements} - known_targets)
    if missing_targets:
        raise ValueError("service requirements reference unknown target IDs: " + ", ".join(missing_targets))
    return targets, requirements, allow_shared, distance_mode
