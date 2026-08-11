from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Sequence

from .material_db import MaterialRecord, numeric_property
from .provenance import EvidenceState, validate_numeric_evidence


class RequirementStatus(str, Enum):
    PASS = "pass"
    FAIL = "fail"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class NumericRequirement:
    property_name: str
    comparator: str
    threshold: float
    unit: str | None = None
    label: str | None = None
    source_url: str | None = None
    checked_at: str | None = None
    required: bool = True


@dataclass(frozen=True)
class RequirementResult:
    property_name: str
    status: RequirementStatus
    actual_value: float | None
    actual_unit: str | None
    threshold: float
    comparator: str
    reason: str
    evidence_state: EvidenceState | None
    source_url: str | None


@dataclass(frozen=True)
class MaterialSuitability:
    material_id: str
    feasible: bool
    passed: int
    failed: int
    unknown: int
    results: tuple[RequirementResult, ...]


def _compare(actual: float, comparator: str, threshold: float) -> bool:
    if comparator == "min":
        return actual >= threshold
    if comparator == "max":
        return actual <= threshold
    if comparator == "eq":
        return actual == threshold
    if comparator == "gt":
        return actual > threshold
    if comparator == "lt":
        return actual < threshold
    raise ValueError("comparator must be one of: min, max, eq, gt, lt")


def evaluate_material(
    material: MaterialRecord,
    requirements: Sequence[NumericRequirement],
    *,
    verified_only: bool = True,
) -> MaterialSuitability:
    """Evaluate user/sourced numeric constraints without turning unknowns into passes.

    NitiKube deliberately does not ship hidden threshold values here. The caller
    must provide thresholds from a user requirement, manufacturer specification,
    regulation, design brief or another provenance-carrying source.
    """
    results: list[RequirementResult] = []
    for requirement in requirements:
        prop = material.properties.get(requirement.property_name)
        if prop is None:
            results.append(
                RequirementResult(
                    property_name=requirement.property_name,
                    status=RequirementStatus.UNKNOWN,
                    actual_value=None,
                    actual_unit=None,
                    threshold=float(requirement.threshold),
                    comparator=requirement.comparator,
                    reason="required material property is missing",
                    evidence_state=None,
                    source_url=None,
                )
            )
            continue

        actual = numeric_property(material, requirement.property_name, verified_only=verified_only)
        if actual is None:
            results.append(
                RequirementResult(
                    property_name=requirement.property_name,
                    status=RequirementStatus.UNKNOWN,
                    actual_value=None,
                    actual_unit=prop.unit,
                    threshold=float(requirement.threshold),
                    comparator=requirement.comparator,
                    reason="property exists but is not usable under the current evidence policy",
                    evidence_state=prop.state,
                    source_url=prop.source_url,
                )
            )
            continue

        if requirement.unit and prop.unit and requirement.unit != prop.unit:
            results.append(
                RequirementResult(
                    property_name=requirement.property_name,
                    status=RequirementStatus.UNKNOWN,
                    actual_value=actual,
                    actual_unit=prop.unit,
                    threshold=float(requirement.threshold),
                    comparator=requirement.comparator,
                    reason=f"unit mismatch: material={prop.unit}, requirement={requirement.unit}; normalize before comparison",
                    evidence_state=prop.state,
                    source_url=prop.source_url,
                )
            )
            continue

        passes = _compare(actual, requirement.comparator, float(requirement.threshold))
        results.append(
            RequirementResult(
                property_name=requirement.property_name,
                status=RequirementStatus.PASS if passes else RequirementStatus.FAIL,
                actual_value=actual,
                actual_unit=prop.unit,
                threshold=float(requirement.threshold),
                comparator=requirement.comparator,
                reason="constraint satisfied" if passes else "constraint violated",
                evidence_state=prop.state,
                source_url=prop.source_url,
            )
        )

    failed_required = sum(
        1
        for requirement, result in zip(requirements, results)
        if requirement.required and result.status == RequirementStatus.FAIL
    )
    unknown_required = sum(
        1
        for requirement, result in zip(requirements, results)
        if requirement.required and result.status == RequirementStatus.UNKNOWN
    )
    return MaterialSuitability(
        material_id=material.material_id,
        feasible=failed_required == 0 and unknown_required == 0,
        passed=sum(r.status == RequirementStatus.PASS for r in results),
        failed=sum(r.status == RequirementStatus.FAIL for r in results),
        unknown=sum(r.status == RequirementStatus.UNKNOWN for r in results),
        results=tuple(results),
    )


def requirement_evidence_state(requirement: NumericRequirement) -> tuple[EvidenceState, str]:
    """Describe whether a threshold itself is sourced.

    A threshold with URL + checked timestamp is treated as verified evidence;
    otherwise it is explicitly user-provided. This prevents NitiKube from
    presenting an arbitrary threshold as a sourced standard.
    """
    if requirement.source_url and requirement.checked_at:
        return EvidenceState.VERIFIED, "threshold carries source and checked timestamp"
    return EvidenceState.USER_PROVIDED, "threshold is a user/design-brief input, not a sourced standard"


def suitability_rows(result: MaterialSuitability) -> list[dict]:
    return [
        {
            "property": item.property_name,
            "status": item.status.value,
            "actual": item.actual_value,
            "unit": item.actual_unit,
            "comparator": item.comparator,
            "threshold": item.threshold,
            "evidence_state": item.evidence_state.value if item.evidence_state else None,
            "source_url": item.source_url,
            "reason": item.reason,
        }
        for item in result.results
    ]
