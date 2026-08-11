from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from enum import Enum
import csv
import io
import json
import math
from typing import Any, Iterable, Mapping, Sequence


class EvidenceState(str, Enum):
    VERIFIED = "verified"
    USER_PROVIDED = "user_provided"
    UNVERIFIED = "unverified"


@dataclass(frozen=True)
class EvidenceRef:
    state: EvidenceState
    source_url: str | None = None
    checked_at: str | None = None
    note: str = ""


@dataclass(frozen=True)
class LifecycleMaterialOption:
    option_id: str
    name: str
    currency: str
    area: float
    area_unit: str
    material_cost_per_area: float | None
    labour_cost_per_area: float | None
    initial_fixed_cost: float
    annual_maintenance_cost: float | None
    service_life_years: float | None
    replacement_cost_fraction: float
    disposal_cost_per_replacement: float
    waste_fraction: float
    performance_score: float | None = None
    features: tuple[str, ...] = ()
    evidence: tuple[tuple[str, EvidenceRef], ...] = ()

    def evidence_map(self) -> dict[str, EvidenceRef]:
        return dict(self.evidence)


@dataclass(frozen=True)
class LifecycleAssumptions:
    horizon_years: int
    discount_rate: float
    annual_cost_escalation_rate: float = 0.0
    include_residual_value: bool = True


@dataclass(frozen=True)
class CashFlow:
    year: int
    category: str
    amount: float
    present_value: float


@dataclass(frozen=True)
class LifecycleResult:
    option_id: str
    feasible: bool
    unknown_fields: tuple[str, ...]
    failed_constraints: tuple[str, ...]
    initial_installed_cost: float | None
    replacement_count: int
    residual_value_credit: float
    npv_cost: float | None
    equivalent_annual_cost: float | None
    npv_cost_per_area: float | None
    cashflows: tuple[CashFlow, ...]


@dataclass(frozen=True)
class SensitivityResult:
    option_id: str
    low_npv: float | None
    base_npv: float | None
    high_npv: float | None
    low_multiplier: float
    high_multiplier: float


@dataclass(frozen=True)
class ValueComparison:
    option_id: str
    name: str
    feasible: bool
    npv_cost: float | None
    equivalent_annual_cost: float | None
    performance_score: float | None
    npv_performance_cost: float | None
    pareto_efficient: bool


_REQUIRED_NUMERIC_FIELDS = (
    "material_cost_per_area",
    "labour_cost_per_area",
    "annual_maintenance_cost",
    "service_life_years",
)


def _parse_iso_timestamp(value: str, field: str) -> datetime:
    normalized = value.strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise ValueError(f"{field} must be ISO-8601") from exc
    if parsed.tzinfo is None:
        raise ValueError(f"{field} must include timezone")
    return parsed


def validate_evidence(ref: EvidenceRef) -> None:
    if ref.state == EvidenceState.VERIFIED:
        if not ref.source_url or not ref.source_url.startswith(("https://", "http://")):
            raise ValueError("verified evidence requires an http(s) source_url")
        if not ref.checked_at:
            raise ValueError("verified evidence requires checked_at")
        _parse_iso_timestamp(ref.checked_at, "checked_at")


def validate_option(option: LifecycleMaterialOption) -> None:
    if not option.option_id.strip() or not option.name.strip() or not option.currency.strip():
        raise ValueError("option_id, name and currency are required")
    if option.area <= 0:
        raise ValueError("area must be positive")
    if option.area_unit.strip().casefold() not in {"ft2", "ft²", "m2", "m²"}:
        raise ValueError("area_unit must be ft2 or m2")
    if option.initial_fixed_cost < 0 or option.disposal_cost_per_replacement < 0:
        raise ValueError("fixed/disposal costs cannot be negative")
    if option.replacement_cost_fraction < 0 or option.waste_fraction < 0:
        raise ValueError("replacement/waste fractions cannot be negative")
    for field in ("material_cost_per_area", "labour_cost_per_area", "annual_maintenance_cost"):
        value = getattr(option, field)
        if value is not None and (not math.isfinite(value) or value < 0):
            raise ValueError(f"{field} must be finite and non-negative when supplied")
    if option.service_life_years is not None and (
        not math.isfinite(option.service_life_years) or option.service_life_years <= 0
    ):
        raise ValueError("service_life_years must be finite and positive when supplied")
    if option.performance_score is not None and not 0 <= option.performance_score <= 100:
        raise ValueError("performance_score must be in [0,100]")
    for _field, ref in option.evidence:
        validate_evidence(ref)


def validate_assumptions(assumptions: LifecycleAssumptions) -> None:
    if assumptions.horizon_years < 1:
        raise ValueError("horizon_years must be >= 1")
    if assumptions.discount_rate <= -1:
        raise ValueError("discount_rate must be greater than -1")
    if assumptions.annual_cost_escalation_rate <= -1:
        raise ValueError("annual_cost_escalation_rate must be greater than -1")


def evidence_readiness(option: LifecycleMaterialOption, *, require_verified: bool = False) -> tuple[str, ...]:
    """Return numeric fields that are missing or lack the requested evidence state."""
    validate_option(option)
    refs = option.evidence_map()
    unknown: list[str] = []
    for field in _REQUIRED_NUMERIC_FIELDS:
        if getattr(option, field) is None:
            unknown.append(field)
            continue
        if require_verified:
            ref = refs.get(field)
            if ref is None or ref.state != EvidenceState.VERIFIED:
                unknown.append(f"{field}:verified_evidence")
    return tuple(unknown)


def initial_installed_cost(option: LifecycleMaterialOption) -> float:
    validate_option(option)
    if option.material_cost_per_area is None or option.labour_cost_per_area is None:
        raise ValueError("material and labour cost per area are required")
    area_cost = option.area * (
        option.material_cost_per_area * (1.0 + option.waste_fraction)
        + option.labour_cost_per_area
    )
    return area_cost + option.initial_fixed_cost


def _pv(amount: float, year: int, rate: float) -> float:
    return amount / ((1.0 + rate) ** year)


def _escalate(amount: float, year: int, escalation: float) -> float:
    return amount * ((1.0 + escalation) ** year)


def lifecycle_cost(
    option: LifecycleMaterialOption,
    assumptions: LifecycleAssumptions,
    *,
    require_verified_evidence: bool = False,
    required_features: Sequence[str] = (),
    excluded_features: Sequence[str] = (),
    cost_multiplier: float = 1.0,
) -> LifecycleResult:
    validate_option(option)
    validate_assumptions(assumptions)
    if cost_multiplier <= 0 or not math.isfinite(cost_multiplier):
        raise ValueError("cost_multiplier must be finite and positive")

    unknown = list(evidence_readiness(option, require_verified=require_verified_evidence))
    option_features = {feature.casefold() for feature in option.features}
    failed: list[str] = []
    for feature in required_features:
        if feature.casefold() not in option_features:
            failed.append(f"missing_feature:{feature}")
    for feature in excluded_features:
        if feature.casefold() in option_features:
            failed.append(f"excluded_feature:{feature}")
    if unknown:
        return LifecycleResult(option.option_id, False, tuple(unknown), tuple(failed), None, 0, 0.0, None, None, None, ())

    assert option.annual_maintenance_cost is not None
    assert option.service_life_years is not None
    base_initial = initial_installed_cost(option)
    initial = base_initial * cost_multiplier
    flows: list[CashFlow] = [CashFlow(0, "initial_installation", initial, initial)]

    # Maintenance is an end-of-year cash flow. Cost multiplier can represent a
    # sensitivity applied to all cost components without pretending to predict a probability distribution.
    for year in range(1, assumptions.horizon_years + 1):
        amount = _escalate(option.annual_maintenance_cost * cost_multiplier, year, assumptions.annual_cost_escalation_rate)
        if amount:
            flows.append(CashFlow(year, "maintenance", amount, _pv(amount, year, assumptions.discount_rate)))

    replacement_count = 0
    # Non-integer service life is supported; replacements occur at floor-multiple years
    # only when the replacement point is an integer analysis year. This keeps the
    # model explicit and annual rather than silently interpolating intra-year cash flows.
    service_life = option.service_life_years
    replacement_years: list[int] = []
    multiple = service_life
    while multiple < assumptions.horizon_years - 1e-9:
        rounded = int(round(multiple))
        if abs(multiple - rounded) > 1e-7:
            raise ValueError(
                "service_life_years must yield integer replacement years in the current annual model; use an integer service life"
            )
        replacement_years.append(rounded)
        multiple += service_life

    for year in replacement_years:
        replacement_count += 1
        replacement_base = base_initial * option.replacement_cost_fraction + option.disposal_cost_per_replacement
        amount = _escalate(replacement_base * cost_multiplier, year, assumptions.annual_cost_escalation_rate)
        flows.append(CashFlow(year, "replacement", amount, _pv(amount, year, assumptions.discount_rate)))

    residual_credit = 0.0
    if assumptions.include_residual_value:
        age_at_horizon = assumptions.horizon_years - (replacement_years[-1] if replacement_years else 0)
        remaining_fraction = max(0.0, min(1.0, (service_life - age_at_horizon) / service_life))
        if remaining_fraction > 0:
            replacement_value_at_horizon = base_initial * option.replacement_cost_fraction * cost_multiplier
            residual_credit = _escalate(
                replacement_value_at_horizon * remaining_fraction,
                assumptions.horizon_years,
                assumptions.annual_cost_escalation_rate,
            )
            flows.append(
                CashFlow(
                    assumptions.horizon_years,
                    "residual_value_credit",
                    -residual_credit,
                    _pv(-residual_credit, assumptions.horizon_years, assumptions.discount_rate),
                )
            )

    flows.sort(key=lambda item: (item.year, item.category))
    npv = sum(flow.present_value for flow in flows)
    n = assumptions.horizon_years
    rate = assumptions.discount_rate
    if abs(rate) <= 1e-12:
        eac = npv / n
    else:
        factor = rate * ((1 + rate) ** n) / (((1 + rate) ** n) - 1)
        eac = npv * factor
    return LifecycleResult(
        option.option_id,
        not failed,
        tuple(unknown),
        tuple(failed),
        initial,
        replacement_count,
        residual_credit,
        npv,
        eac,
        npv / option.area,
        tuple(flows),
    )


def sensitivity_band(
    option: LifecycleMaterialOption,
    assumptions: LifecycleAssumptions,
    *,
    low_multiplier: float,
    high_multiplier: float,
    require_verified_evidence: bool = False,
    required_features: Sequence[str] = (),
    excluded_features: Sequence[str] = (),
) -> SensitivityResult:
    if not 0 < low_multiplier <= 1:
        raise ValueError("low_multiplier must be in (0,1]")
    if high_multiplier < 1:
        raise ValueError("high_multiplier must be >= 1")
    kwargs = dict(
        require_verified_evidence=require_verified_evidence,
        required_features=required_features,
        excluded_features=excluded_features,
    )
    low = lifecycle_cost(option, assumptions, cost_multiplier=low_multiplier, **kwargs)
    base = lifecycle_cost(option, assumptions, cost_multiplier=1.0, **kwargs)
    high = lifecycle_cost(option, assumptions, cost_multiplier=high_multiplier, **kwargs)
    return SensitivityResult(
        option.option_id,
        low.npv_cost,
        base.npv_cost,
        high.npv_cost,
        low_multiplier,
        high_multiplier,
    )


def pareto_value_comparison(
    options: Sequence[LifecycleMaterialOption],
    results: Mapping[str, LifecycleResult],
) -> list[ValueComparison]:
    candidates = []
    for option in options:
        result = results.get(option.option_id)
        feasible = bool(result and result.feasible and result.npv_cost is not None)
        candidates.append((option, result, feasible))

    efficient_ids: set[str] = set()
    for option, result, feasible in candidates:
        if not feasible or result is None or result.npv_cost is None or option.performance_score is None:
            continue
        dominated = False
        for other, other_result, other_feasible in candidates:
            if other.option_id == option.option_id or not other_feasible or other_result is None or other_result.npv_cost is None or other.performance_score is None:
                continue
            no_more_cost = other_result.npv_cost <= result.npv_cost + 1e-9
            no_less_perf = other.performance_score >= option.performance_score - 1e-9
            strictly_better = other_result.npv_cost < result.npv_cost - 1e-9 or other.performance_score > option.performance_score + 1e-9
            if no_more_cost and no_less_perf and strictly_better:
                dominated = True
                break
        if not dominated:
            efficient_ids.add(option.option_id)

    rows: list[ValueComparison] = []
    for option, result, feasible in candidates:
        npv = result.npv_cost if result else None
        eac = result.equivalent_annual_cost if result else None
        ratio = None
        if feasible and npv is not None and option.performance_score is not None and npv > 0:
            ratio = option.performance_score / npv
        rows.append(
            ValueComparison(
                option.option_id,
                option.name,
                feasible,
                npv,
                eac,
                option.performance_score,
                ratio,
                option.option_id in efficient_ids,
            )
        )
    return sorted(
        rows,
        key=lambda item: (
            item.feasible,
            item.pareto_efficient,
            item.performance_score if item.performance_score is not None else -1,
            -(item.npv_cost if item.npv_cost is not None else math.inf),
        ),
        reverse=True,
    )


def _split_features(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, (list, tuple)):
        return tuple(str(item).strip() for item in value if str(item).strip())
    return tuple(part.strip() for part in str(value).replace(",", "|").split("|") if part.strip())


def _optional_float(value: Any) -> float | None:
    if value is None or str(value).strip() == "":
        return None
    return float(value)


def evidence_from_dict(data: Mapping[str, Any]) -> tuple[tuple[str, EvidenceRef], ...]:
    output = []
    for field, raw in data.items():
        if not isinstance(raw, Mapping):
            raise ValueError(f"evidence for {field} must be an object")
        state = EvidenceState(str(raw.get("state") or "unverified").casefold())
        ref = EvidenceRef(
            state=state,
            source_url=str(raw["source_url"]) if raw.get("source_url") else None,
            checked_at=str(raw["checked_at"]) if raw.get("checked_at") else None,
            note=str(raw.get("note") or ""),
        )
        validate_evidence(ref)
        output.append((str(field), ref))
    return tuple(output)


def option_from_dict(data: Mapping[str, Any]) -> LifecycleMaterialOption:
    option = LifecycleMaterialOption(
        option_id=str(data.get("option_id") or ""),
        name=str(data.get("name") or ""),
        currency=str(data.get("currency") or "INR"),
        area=float(data["area"]),
        area_unit=str(data.get("area_unit") or "ft2"),
        material_cost_per_area=_optional_float(data.get("material_cost_per_area")),
        labour_cost_per_area=_optional_float(data.get("labour_cost_per_area")),
        initial_fixed_cost=float(data.get("initial_fixed_cost") or 0.0),
        annual_maintenance_cost=_optional_float(data.get("annual_maintenance_cost")),
        service_life_years=_optional_float(data.get("service_life_years")),
        replacement_cost_fraction=float(data.get("replacement_cost_fraction") if data.get("replacement_cost_fraction") not in {None, ""} else 1.0),
        disposal_cost_per_replacement=float(data.get("disposal_cost_per_replacement") or 0.0),
        waste_fraction=float(data.get("waste_fraction") or 0.0),
        performance_score=_optional_float(data.get("performance_score")),
        features=_split_features(data.get("features")),
        evidence=evidence_from_dict(data.get("evidence") or {}),
    )
    validate_option(option)
    return option


def load_options_json(payload: str | bytes) -> list[LifecycleMaterialOption]:
    if isinstance(payload, bytes):
        payload = payload.decode("utf-8")
    data = json.loads(payload)
    rows = data.get("options") if isinstance(data, dict) else data
    if not isinstance(rows, list):
        raise ValueError("lifecycle JSON must be a list or {'options': [...]} object")
    options = [option_from_dict(row) for row in rows]
    ids = [option.option_id for option in options]
    if len(ids) != len(set(ids)):
        raise ValueError("option_id values must be unique")
    return options


def load_options_csv(payload: str | bytes) -> list[LifecycleMaterialOption]:
    """Load flat user-provided CSV. CSV rows are USER_PROVIDED, not VERIFIED."""
    if isinstance(payload, bytes):
        payload = payload.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(payload))
    options = []
    for row in reader:
        option = option_from_dict(row | {"evidence": {}})
        options.append(option)
    ids = [option.option_id for option in options]
    if len(ids) != len(set(ids)):
        raise ValueError("option_id values must be unique")
    return options


def lifecycle_rows(results: Sequence[LifecycleResult]) -> list[dict[str, Any]]:
    return [asdict(result) | {"cashflows": len(result.cashflows)} for result in results]


def cashflow_rows(result: LifecycleResult) -> list[dict[str, Any]]:
    return [asdict(flow) | {"option_id": result.option_id} for flow in result.cashflows]
