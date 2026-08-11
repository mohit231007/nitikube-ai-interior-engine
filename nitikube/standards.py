from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from enum import Enum
import csv
import io
import json
import math
from typing import Any, Iterable, Mapping, Sequence


class RuleOperator(str, Enum):
    MIN = "min"
    MAX = "max"
    RANGE = "range"
    EQUAL = "equal"


class RuleStatus(str, Enum):
    PASS = "pass"
    FAIL = "fail"
    UNKNOWN = "unknown"
    NOT_APPLICABLE = "not_applicable"


@dataclass(frozen=True)
class StandardSource:
    title: str
    authority: str
    jurisdiction: str
    document_version: str
    source_url: str
    checked_at: str
    effective_date: str | None = None
    locator: str | None = None
    source_type: str = "standard_or_guidance"


@dataclass(frozen=True)
class NumericRule:
    rule_id: str
    subject: str
    metric: str
    operator: RuleOperator
    value: float
    unit: str
    source: StandardSource
    upper_value: float | None = None
    room_types: tuple[str, ...] = ()
    applicability_tags: tuple[str, ...] = ()
    mandatory: bool = False
    summary: str = ""


@dataclass(frozen=True)
class RuleContext:
    room_type: str | None = None
    tags: tuple[str, ...] = ()
    jurisdiction: str | None = None


@dataclass(frozen=True)
class RuleEvaluation:
    rule_id: str
    status: RuleStatus
    actual_value: float | None
    actual_unit: str | None
    normalized_actual: float | None
    normalized_unit: str
    normalized_lower: float
    normalized_upper: float
    reason: str
    mandatory: bool


@dataclass(frozen=True)
class RuleConflict:
    metric: str
    rule_ids: tuple[str, ...]
    normalized_unit: str
    intervals: tuple[tuple[float, float], ...]
    reason: str


# Every supported unit belongs to exactly one dimension family and converts to
# the family's canonical unit. No conversion is guessed from free text.
_UNIT_TABLE: dict[str, tuple[str, str, float]] = {
    # length -> metres
    "mm": ("length", "m", 0.001),
    "millimeter": ("length", "m", 0.001),
    "millimetre": ("length", "m", 0.001),
    "cm": ("length", "m", 0.01),
    "m": ("length", "m", 1.0),
    "meter": ("length", "m", 1.0),
    "metre": ("length", "m", 1.0),
    "in": ("length", "m", 0.0254),
    "inch": ("length", "m", 0.0254),
    "ft": ("length", "m", 0.3048),
    "foot": ("length", "m", 0.3048),
    # area -> m2
    "mm2": ("area", "m2", 1e-6),
    "cm2": ("area", "m2", 1e-4),
    "m2": ("area", "m2", 1.0),
    "m²": ("area", "m2", 1.0),
    "in2": ("area", "m2", 0.00064516),
    "ft2": ("area", "m2", 0.09290304),
    "ft²": ("area", "m2", 0.09290304),
    # illuminance
    "lux": ("illuminance", "lux", 1.0),
    "lx": ("illuminance", "lux", 1.0),
    # airflow -> m3/h
    "m3/h": ("airflow", "m3/h", 1.0),
    "m³/h": ("airflow", "m3/h", 1.0),
    "cfm": ("airflow", "m3/h", 1.69901079552),
    # angle
    "deg": ("angle", "deg", 1.0),
    "degree": ("angle", "deg", 1.0),
    "°": ("angle", "deg", 1.0),
    # ratio / percent. Percent intentionally stays percent, not fraction.
    "%": ("percent", "%", 1.0),
    "percent": ("percent", "%", 1.0),
    # air changes per hour
    "ach": ("air_changes", "ach", 1.0),
    # temperature difference. Absolute temperature conversions are deliberately
    # not included because offset units require context-sensitive handling.
    "k": ("temperature_difference", "K", 1.0),
    # dimensionless
    "1": ("dimensionless", "1", 1.0),
    "ratio": ("dimensionless", "1", 1.0),
}


def normalize_unit(unit: str) -> str:
    return unit.strip().casefold().replace(" ", "")


def unit_info(unit: str) -> tuple[str, str, float]:
    key = normalize_unit(unit)
    if key not in _UNIT_TABLE:
        raise ValueError(f"unsupported unit: {unit!r}")
    return _UNIT_TABLE[key]


def convert_value(value: float, from_unit: str, to_unit: str) -> float:
    if not math.isfinite(value):
        raise ValueError("numeric value must be finite")
    from_family, from_canonical, from_factor = unit_info(from_unit)
    to_family, to_canonical, to_factor = unit_info(to_unit)
    if from_family != to_family or from_canonical != to_canonical:
        raise ValueError(f"incompatible units: {from_unit!r} -> {to_unit!r}")
    canonical = value * from_factor
    return canonical / to_factor


def _parse_iso_timestamp(value: str, field: str) -> datetime:
    if not value or not value.strip():
        raise ValueError(f"{field} is required")
    normalized = value.strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise ValueError(f"{field} must be ISO-8601") from exc
    if parsed.tzinfo is None:
        raise ValueError(f"{field} must include a timezone")
    return parsed


def validate_source(source: StandardSource) -> None:
    required = {
        "title": source.title,
        "authority": source.authority,
        "jurisdiction": source.jurisdiction,
        "document_version": source.document_version,
        "source_url": source.source_url,
        "checked_at": source.checked_at,
    }
    missing = [name for name, value in required.items() if not str(value).strip()]
    if missing:
        raise ValueError(f"standard source missing required fields: {missing}")
    if not source.source_url.startswith(("https://", "http://")):
        raise ValueError("standard source_url must be an http(s) URL")
    _parse_iso_timestamp(source.checked_at, "checked_at")


def validate_rule(rule: NumericRule) -> None:
    if not rule.rule_id.strip() or not rule.subject.strip() or not rule.metric.strip():
        raise ValueError("rule_id, subject and metric are required")
    validate_source(rule.source)
    unit_info(rule.unit)
    if not math.isfinite(rule.value):
        raise ValueError("rule value must be finite")
    if rule.operator == RuleOperator.RANGE:
        if rule.upper_value is None or not math.isfinite(rule.upper_value):
            raise ValueError("range rule requires finite upper_value")
        if rule.upper_value < rule.value:
            raise ValueError("range upper_value cannot be below lower value")
    elif rule.upper_value is not None:
        raise ValueError("upper_value is only valid for range rules")


def rule_interval(rule: NumericRule) -> tuple[float, float, str]:
    validate_rule(rule)
    _family, canonical_unit, factor = unit_info(rule.unit)
    value = rule.value * factor
    if rule.operator == RuleOperator.MIN:
        return value, math.inf, canonical_unit
    if rule.operator == RuleOperator.MAX:
        return -math.inf, value, canonical_unit
    if rule.operator == RuleOperator.EQUAL:
        return value, value, canonical_unit
    assert rule.upper_value is not None
    return value, rule.upper_value * factor, canonical_unit


def rule_applies(rule: NumericRule, context: RuleContext | None) -> bool:
    if context is None:
        return True
    if context.jurisdiction and rule.source.jurisdiction.casefold() not in {
        context.jurisdiction.casefold(),
        "global",
        "international",
    }:
        return False
    if rule.room_types:
        if context.room_type is None:
            return False
        if context.room_type.casefold() not in {room.casefold() for room in rule.room_types}:
            return False
    required_tags = {tag.casefold() for tag in rule.applicability_tags}
    actual_tags = {tag.casefold() for tag in context.tags}
    if required_tags and not required_tags.issubset(actual_tags):
        return False
    return True


def evaluate_rule(
    rule: NumericRule,
    actual_value: float | None,
    actual_unit: str | None,
    *,
    context: RuleContext | None = None,
    tolerance: float = 1e-9,
) -> RuleEvaluation:
    validate_rule(rule)
    lower, upper, canonical_unit = rule_interval(rule)
    if not rule_applies(rule, context):
        return RuleEvaluation(
            rule.rule_id,
            RuleStatus.NOT_APPLICABLE,
            actual_value,
            actual_unit,
            None,
            canonical_unit,
            lower,
            upper,
            "Rule applicability does not match the supplied context.",
            rule.mandatory,
        )
    if actual_value is None or actual_unit is None:
        return RuleEvaluation(
            rule.rule_id,
            RuleStatus.UNKNOWN,
            actual_value,
            actual_unit,
            None,
            canonical_unit,
            lower,
            upper,
            "Actual value/unit is missing; required evidence is unknown rather than assumed compliant.",
            rule.mandatory,
        )
    try:
        normalized_actual = convert_value(float(actual_value), actual_unit, canonical_unit)
    except (ValueError, TypeError) as exc:
        return RuleEvaluation(
            rule.rule_id,
            RuleStatus.UNKNOWN,
            actual_value,
            actual_unit,
            None,
            canonical_unit,
            lower,
            upper,
            f"Actual value cannot be compared to this rule: {exc}",
            rule.mandatory,
        )
    passed = normalized_actual >= lower - tolerance and normalized_actual <= upper + tolerance
    return RuleEvaluation(
        rule.rule_id,
        RuleStatus.PASS if passed else RuleStatus.FAIL,
        float(actual_value),
        actual_unit,
        normalized_actual,
        canonical_unit,
        lower,
        upper,
        "Actual value lies within the normalized allowed interval." if passed else "Actual value lies outside the normalized allowed interval.",
        rule.mandatory,
    )


def evaluate_rules(
    rules: Iterable[NumericRule],
    actuals: Mapping[str, tuple[float | None, str | None]],
    *,
    context: RuleContext | None = None,
) -> tuple[RuleEvaluation, ...]:
    return tuple(
        evaluate_rule(rule, *(actuals.get(rule.metric, (None, None))), context=context)
        for rule in rules
    )


def _applicability_signature(rule: NumericRule) -> tuple:
    return (
        rule.subject.casefold(),
        rule.metric.casefold(),
        rule.source.jurisdiction.casefold(),
        tuple(sorted(room.casefold() for room in rule.room_types)),
        tuple(sorted(tag.casefold() for tag in rule.applicability_tags)),
        rule.mandatory,
    )


def detect_conflicts(rules: Sequence[NumericRule]) -> tuple[RuleConflict, ...]:
    """Detect disjoint numeric intervals for rules with identical applicability.

    Different jurisdictions/room scopes are not called conflicts merely because
    their numbers differ. NitiKube surfaces rather than silently resolves true
    same-scope interval conflicts.
    """
    groups: dict[tuple, list[NumericRule]] = {}
    for rule in rules:
        validate_rule(rule)
        groups.setdefault(_applicability_signature(rule), []).append(rule)

    conflicts: list[RuleConflict] = []
    for signature, group in groups.items():
        if len(group) < 2:
            continue
        intervals = []
        canonical_unit = None
        compatible = True
        for rule in group:
            try:
                lower, upper, unit = rule_interval(rule)
            except ValueError:
                compatible = False
                break
            if canonical_unit is None:
                canonical_unit = unit
            elif unit != canonical_unit:
                compatible = False
                break
            intervals.append((lower, upper))
        if not compatible or canonical_unit is None:
            continue
        intersection_lower = max(lower for lower, _ in intervals)
        intersection_upper = min(upper for _, upper in intervals)
        if intersection_lower > intersection_upper + 1e-9:
            conflicts.append(
                RuleConflict(
                    metric=group[0].metric,
                    rule_ids=tuple(rule.rule_id for rule in group),
                    normalized_unit=canonical_unit,
                    intervals=tuple(intervals),
                    reason="Rules have identical applicability but disjoint allowed intervals; automatic compliance resolution is unsafe.",
                )
            )
    return tuple(conflicts)


def _split_list(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, (list, tuple)):
        return tuple(str(item).strip() for item in value if str(item).strip())
    text = str(value).strip()
    if not text:
        return ()
    return tuple(part.strip() for part in text.replace(",", "|").split("|") if part.strip())


def source_from_dict(data: Mapping[str, Any]) -> StandardSource:
    return StandardSource(
        title=str(data.get("title") or ""),
        authority=str(data.get("authority") or ""),
        jurisdiction=str(data.get("jurisdiction") or ""),
        document_version=str(data.get("document_version") or ""),
        source_url=str(data.get("source_url") or ""),
        checked_at=str(data.get("checked_at") or ""),
        effective_date=str(data["effective_date"]) if data.get("effective_date") not in {None, ""} else None,
        locator=str(data["locator"]) if data.get("locator") not in {None, ""} else None,
        source_type=str(data.get("source_type") or "standard_or_guidance"),
    )


def rule_from_dict(data: Mapping[str, Any]) -> NumericRule:
    source_data = data.get("source")
    if not isinstance(source_data, Mapping):
        source_data = {
            key: data.get(key)
            for key in (
                "title",
                "authority",
                "jurisdiction",
                "document_version",
                "source_url",
                "checked_at",
                "effective_date",
                "locator",
                "source_type",
            )
        }
    try:
        operator = RuleOperator(str(data.get("operator") or "").strip().casefold())
    except ValueError as exc:
        raise ValueError(f"unsupported rule operator: {data.get('operator')!r}") from exc
    upper = data.get("upper_value")
    rule = NumericRule(
        rule_id=str(data.get("rule_id") or ""),
        subject=str(data.get("subject") or ""),
        metric=str(data.get("metric") or ""),
        operator=operator,
        value=float(data["value"]),
        upper_value=None if upper in {None, ""} else float(upper),
        unit=str(data.get("unit") or ""),
        source=source_from_dict(source_data),
        room_types=_split_list(data.get("room_types")),
        applicability_tags=_split_list(data.get("applicability_tags")),
        mandatory=str(data.get("mandatory", "false")).strip().casefold() in {"true", "1", "yes", "y"} if not isinstance(data.get("mandatory"), bool) else bool(data.get("mandatory")),
        summary=str(data.get("summary") or ""),
    )
    validate_rule(rule)
    return rule


def load_rules_json(payload: str | bytes) -> list[NumericRule]:
    if isinstance(payload, bytes):
        payload = payload.decode("utf-8")
    data = json.loads(payload)
    rows = data.get("rules") if isinstance(data, dict) else data
    if not isinstance(rows, list):
        raise ValueError("standard rule JSON must be a list or {'rules': [...]} object")
    rules = [rule_from_dict(row) for row in rows]
    ids = [rule.rule_id for rule in rules]
    if len(ids) != len(set(ids)):
        raise ValueError("rule_id values must be unique")
    return rules


def load_rules_csv(payload: str | bytes) -> list[NumericRule]:
    if isinstance(payload, bytes):
        payload = payload.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(payload))
    if not reader.fieldnames:
        raise ValueError("standard-rule CSV requires a header")
    rules = [rule_from_dict(row) for row in reader]
    ids = [rule.rule_id for rule in rules]
    if len(ids) != len(set(ids)):
        raise ValueError("rule_id values must be unique")
    return rules


def rule_rows(rules: Sequence[NumericRule]) -> list[dict[str, Any]]:
    return [
        {
            "rule_id": rule.rule_id,
            "subject": rule.subject,
            "metric": rule.metric,
            "operator": rule.operator.value,
            "value": rule.value,
            "upper_value": rule.upper_value,
            "unit": rule.unit,
            "room_types": " | ".join(rule.room_types),
            "tags": " | ".join(rule.applicability_tags),
            "mandatory": rule.mandatory,
            "authority": rule.source.authority,
            "jurisdiction": rule.source.jurisdiction,
            "document_version": rule.source.document_version,
            "source_url": rule.source.source_url,
            "checked_at": rule.source.checked_at,
            "effective_date": rule.source.effective_date,
            "locator": rule.source.locator,
            "summary": rule.summary,
        }
        for rule in rules
    ]


def evaluation_rows(evaluations: Sequence[RuleEvaluation]) -> list[dict[str, Any]]:
    return [asdict(item) | {"status": item.status.value} for item in evaluations]
