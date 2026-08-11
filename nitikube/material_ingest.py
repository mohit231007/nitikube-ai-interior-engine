from __future__ import annotations

from dataclasses import dataclass, field
import csv
from io import StringIO
import json
import math
import re
from typing import Any, Iterable, Sequence

from .material_db import MaterialProperty, MaterialRecord
from .provenance import EvidenceState


@dataclass(frozen=True)
class PropertySpec:
    canonical_name: str
    canonical_unit: str | None
    aliases: tuple[str, ...] = ()


PROPERTY_SPECS: dict[str, PropertySpec] = {
    "thermal_conductivity": PropertySpec(
        "thermal_conductivity", "W/(m·K)", ("thermal conductivity", "k_value", "k-value", "lambda")
    ),
    "density": PropertySpec("density", "kg/m³", ("bulk density", "mass density")),
    "specific_heat": PropertySpec(
        "specific_heat", "J/(kg·K)", ("specific heat", "specific heat capacity", "heat capacity")
    ),
    "water_absorption": PropertySpec(
        "water_absorption", "%", ("water absorption", "water absorption percent", "water_absorption_percent")
    ),
    "voc": PropertySpec("voc", "g/L", ("voc content", "volatile organic compounds", "volatile organic compound")),
    "thickness": PropertySpec("thickness", "mm", ("material thickness", "nominal thickness")),
    "service_life": PropertySpec("service_life", "year", ("service life", "design life", "expected life")),
    "slip_resistance": PropertySpec(
        "slip_resistance", None, ("slip resistance", "slip rating", "coefficient of friction", "cof")
    ),
    "fire_rating": PropertySpec("fire_rating", None, ("fire rating", "reaction to fire", "fire classification")),
    "uv_resistance": PropertySpec("uv_resistance", None, ("uv resistance", "ultraviolet resistance")),
    "chemical_resistance": PropertySpec(
        "chemical_resistance", None, ("chemical resistance", "chemical resistant")
    ),
    "abrasion_resistance": PropertySpec(
        "abrasion_resistance", None, ("abrasion resistance", "wear resistance", "abrasion class")
    ),
}


@dataclass(frozen=True)
class SourceDocument:
    document_id: str
    title: str
    manufacturer: str | None = None
    product_name: str | None = None
    source_url: str | None = None
    document_version: str | None = None
    checked_at: str | None = None
    notes: tuple[str, ...] = ()


@dataclass(frozen=True)
class PropertyObservation:
    property_name: str
    value: Any
    unit: str | None
    source_document_id: str
    state: EvidenceState = EvidenceState.UNVERIFIED
    source_url: str | None = None
    checked_at: str | None = None
    note: str | None = None


@dataclass(frozen=True)
class NormalizedObservation:
    canonical_name: str
    canonical_value: Any
    canonical_unit: str | None
    original_name: str
    original_value: Any
    original_unit: str | None
    source_document_id: str
    state: EvidenceState
    source_url: str | None
    checked_at: str | None
    note: str | None = None


@dataclass(frozen=True)
class PropertyConflict:
    canonical_name: str
    observations: tuple[NormalizedObservation, ...]
    distinct_values: tuple[Any, ...]
    reason: str


@dataclass
class DatasheetBundle:
    material_id: str
    material_name: str
    category: str
    aliases: list[str] = field(default_factory=list)
    sources: dict[str, SourceDocument] = field(default_factory=dict)
    observations: list[PropertyObservation] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


_ALIAS_INDEX: dict[str, str] = {}
for canonical, spec in PROPERTY_SPECS.items():
    names = (canonical, canonical.replace("_", " "), *spec.aliases)
    for name in names:
        key = re.sub(r"[^a-z0-9]+", " ", name.lower()).strip()
        _ALIAS_INDEX[key] = canonical


def canonicalize_property_name(name: str) -> str:
    key = re.sub(r"[^a-z0-9]+", " ", str(name).lower()).strip()
    if not key:
        raise ValueError("property name cannot be empty")
    return _ALIAS_INDEX.get(key, key.replace(" ", "_"))


def _normalize_unit(unit: str | None) -> str | None:
    if unit is None:
        return None
    value = str(unit).strip().lower()
    replacements = {
        "³": "3",
        "²": "2",
        "·": "*",
        "°": "",
        " ": "",
    }
    for old, new in replacements.items():
        value = value.replace(old, new)
    return value


def convert_to_canonical(property_name: str, value: Any, unit: str | None) -> tuple[Any, str | None]:
    """Convert a supported numeric observation to the property's canonical unit.

    Conversion rules are unit arithmetic only; this function does not invent or
    infer missing physical properties. Unknown units raise instead of guessing.
    Non-numeric classification properties are returned unchanged.
    """
    canonical = canonicalize_property_name(property_name)
    spec = PROPERTY_SPECS.get(canonical)
    if spec is None:
        return value, unit
    if spec.canonical_unit is None:
        return value, unit
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise ValueError(f"{canonical} requires a numeric value for unit normalization")
    if not math.isfinite(float(value)):
        raise ValueError(f"{canonical} value must be finite")

    u = _normalize_unit(unit)
    x = float(value)

    if canonical == "density":
        if u in {"kg/m3", "kg/m^3", "kgm-3", "kgm3"}:
            return x, spec.canonical_unit
        if u in {"g/cm3", "g/cm^3", "gcm-3", "gcm3"}:
            return x * 1000.0, spec.canonical_unit
    elif canonical == "thermal_conductivity":
        if u in {"w/(m*k)", "w/mk", "wm-1k-1", "w/m/k"}:
            return x, spec.canonical_unit
    elif canonical == "specific_heat":
        if u in {"j/(kg*k)", "j/kgk", "j/kg/k"}:
            return x, spec.canonical_unit
        if u in {"kj/(kg*k)", "kj/kgk", "kj/kg/k"}:
            return x * 1000.0, spec.canonical_unit
    elif canonical == "water_absorption":
        if u in {"%", "percent", "pct"}:
            return x, spec.canonical_unit
        if u in {"fraction", "ratio", "1"}:
            return x * 100.0, spec.canonical_unit
    elif canonical == "voc":
        if u in {"g/l", "gl-1"}:
            return x, spec.canonical_unit
        if u in {"mg/l", "mgl-1"}:
            return x / 1000.0, spec.canonical_unit
    elif canonical == "thickness":
        if u in {"mm", "millimeter", "millimetre", "millimeters", "millimetres"}:
            return x, spec.canonical_unit
        if u in {"cm", "centimeter", "centimetre", "centimeters", "centimetres"}:
            return x * 10.0, spec.canonical_unit
        if u in {"m", "meter", "metre", "meters", "metres"}:
            return x * 1000.0, spec.canonical_unit
        if u in {"in", "inch", "inches", '"'}:
            return x * 25.4, spec.canonical_unit
    elif canonical == "service_life":
        if u in {"year", "years", "yr", "yrs"}:
            return x, spec.canonical_unit
        if u in {"month", "months", "mo"}:
            return x / 12.0, spec.canonical_unit

    raise ValueError(
        f"unsupported unit {unit!r} for {canonical}; provide a supported unit or keep the observation unnormalized"
    )


def normalize_observation(observation: PropertyObservation) -> NormalizedObservation:
    canonical = canonicalize_property_name(observation.property_name)
    value, unit = convert_to_canonical(canonical, observation.value, observation.unit)
    return NormalizedObservation(
        canonical_name=canonical,
        canonical_value=value,
        canonical_unit=unit,
        original_name=observation.property_name,
        original_value=observation.value,
        original_unit=observation.unit,
        source_document_id=observation.source_document_id,
        state=observation.state,
        source_url=observation.source_url,
        checked_at=observation.checked_at,
        note=observation.note,
    )


def normalize_bundle(bundle: DatasheetBundle) -> list[NormalizedObservation]:
    normalized = []
    for observation in bundle.observations:
        source = bundle.sources.get(observation.source_document_id)
        source_url = observation.source_url or (source.source_url if source else None)
        checked_at = observation.checked_at or (source.checked_at if source else None)
        enriched = PropertyObservation(
            property_name=observation.property_name,
            value=observation.value,
            unit=observation.unit,
            source_document_id=observation.source_document_id,
            state=observation.state,
            source_url=source_url,
            checked_at=checked_at,
            note=observation.note,
        )
        normalized.append(normalize_observation(enriched))
    return normalized


def _values_equal(a: Any, b: Any, rel_tol: float, abs_tol: float) -> bool:
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return math.isclose(float(a), float(b), rel_tol=rel_tol, abs_tol=abs_tol)
    return str(a).strip().casefold() == str(b).strip().casefold()


def detect_property_conflicts(
    observations: Sequence[NormalizedObservation], *, rel_tol: float = 0.02, abs_tol: float = 1e-9
) -> list[PropertyConflict]:
    """Return source disagreements without averaging them away."""
    grouped: dict[str, list[NormalizedObservation]] = {}
    for observation in observations:
        grouped.setdefault(observation.canonical_name, []).append(observation)

    conflicts: list[PropertyConflict] = []
    for name, group in grouped.items():
        if len(group) < 2:
            continue
        distinct: list[Any] = []
        for observation in group:
            if not any(_values_equal(observation.canonical_value, existing, rel_tol, abs_tol) for existing in distinct):
                distinct.append(observation.canonical_value)
        if len(distinct) > 1:
            conflicts.append(
                PropertyConflict(
                    canonical_name=name,
                    observations=tuple(group),
                    distinct_values=tuple(distinct),
                    reason="sources disagree beyond configured tolerance; explicit resolution required",
                )
            )
    return conflicts


def resolve_observations(
    observations: Sequence[NormalizedObservation],
    *,
    preferred_source_by_property: dict[str, str] | None = None,
    rel_tol: float = 0.02,
    abs_tol: float = 1e-9,
) -> tuple[dict[str, NormalizedObservation], list[PropertyConflict]]:
    """Resolve non-conflicting observations; conflicts require an explicit preferred source.

    When multiple observations agree within tolerance, the highest evidence-state
    priority is retained. No numerical averaging is performed.
    """
    preferred_source_by_property = preferred_source_by_property or {}
    grouped: dict[str, list[NormalizedObservation]] = {}
    for observation in observations:
        grouped.setdefault(observation.canonical_name, []).append(observation)

    state_priority = {
        EvidenceState.VERIFIED: 4,
        EvidenceState.USER_PROVIDED: 3,
        EvidenceState.UNVERIFIED: 2,
        EvidenceState.SUBJECTIVE: 1,
    }
    resolved: dict[str, NormalizedObservation] = {}
    unresolved: list[PropertyConflict] = []

    for name, group in grouped.items():
        preferred = preferred_source_by_property.get(name)
        if preferred:
            matches = [obs for obs in group if obs.source_document_id == preferred]
            if not matches:
                raise ValueError(f"preferred source {preferred!r} not found for {name}")
            resolved[name] = max(matches, key=lambda obs: state_priority[obs.state])
            continue

        distinct: list[Any] = []
        for observation in group:
            if not any(_values_equal(observation.canonical_value, existing, rel_tol, abs_tol) for existing in distinct):
                distinct.append(observation.canonical_value)
        if len(distinct) > 1:
            unresolved.append(
                PropertyConflict(
                    canonical_name=name,
                    observations=tuple(group),
                    distinct_values=tuple(distinct),
                    reason="sources disagree beyond configured tolerance; choose a source explicitly",
                )
            )
            continue
        resolved[name] = max(group, key=lambda obs: state_priority[obs.state])

    return resolved, unresolved


def material_record_from_bundle(
    bundle: DatasheetBundle, *, preferred_source_by_property: dict[str, str] | None = None
) -> tuple[MaterialRecord, list[PropertyConflict]]:
    normalized = normalize_bundle(bundle)
    resolved, conflicts = resolve_observations(
        normalized, preferred_source_by_property=preferred_source_by_property
    )
    properties = {
        name: MaterialProperty(
            name=name,
            value=obs.canonical_value,
            unit=obs.canonical_unit,
            state=obs.state,
            source_url=obs.source_url,
            checked_at=obs.checked_at,
            note=f"source_document_id={obs.source_document_id}" + (f"; {obs.note}" if obs.note else ""),
        )
        for name, obs in resolved.items()
    }
    notes = list(bundle.notes)
    if conflicts:
        notes.append(
            "Unresolved source conflicts omitted from material properties: "
            + ", ".join(conflict.canonical_name for conflict in conflicts)
        )
    return (
        MaterialRecord(
            material_id=bundle.material_id,
            name=bundle.material_name,
            category=bundle.category,
            aliases=list(bundle.aliases),
            properties=properties,
            notes=notes,
        ),
        conflicts,
    )


def bundle_from_dict(data: dict[str, Any]) -> DatasheetBundle:
    required = ["material_id", "material_name", "category"]
    missing = [key for key in required if not str(data.get(key, "")).strip()]
    if missing:
        raise ValueError(f"missing required bundle fields: {missing}")

    sources: dict[str, SourceDocument] = {}
    for payload in data.get("sources", []):
        source = SourceDocument(
            document_id=str(payload["document_id"]),
            title=str(payload.get("title") or payload["document_id"]),
            manufacturer=payload.get("manufacturer"),
            product_name=payload.get("product_name"),
            source_url=payload.get("source_url"),
            document_version=payload.get("document_version"),
            checked_at=payload.get("checked_at"),
            notes=tuple(payload.get("notes", [])),
        )
        if source.document_id in sources:
            raise ValueError(f"duplicate source document_id: {source.document_id}")
        sources[source.document_id] = source

    observations: list[PropertyObservation] = []
    for payload in data.get("observations", []):
        state = EvidenceState(payload.get("state", EvidenceState.UNVERIFIED.value))
        source_id = str(payload.get("source_document_id", "")).strip()
        if not source_id:
            raise ValueError("every observation requires source_document_id")
        if sources and source_id not in sources:
            raise ValueError(f"observation references unknown source_document_id: {source_id}")
        observations.append(
            PropertyObservation(
                property_name=str(payload["property_name"]),
                value=payload.get("value"),
                unit=payload.get("unit"),
                source_document_id=source_id,
                state=state,
                source_url=payload.get("source_url"),
                checked_at=payload.get("checked_at"),
                note=payload.get("note"),
            )
        )

    return DatasheetBundle(
        material_id=str(data["material_id"]),
        material_name=str(data["material_name"]),
        category=str(data["category"]),
        aliases=list(data.get("aliases", [])),
        sources=sources,
        observations=observations,
        notes=list(data.get("notes", [])),
    )


def load_datasheet_json(payload: str | bytes) -> DatasheetBundle:
    if isinstance(payload, bytes):
        payload = payload.decode("utf-8")
    data = json.loads(payload)
    if not isinstance(data, dict):
        raise ValueError("datasheet bundle JSON must be an object")
    return bundle_from_dict(data)


def load_observations_csv(
    payload: str | bytes,
    *,
    material_id: str,
    material_name: str,
    category: str,
) -> DatasheetBundle:
    """Load a simple structured observation CSV without semantic guessing.

    Required columns: property_name, value, unit, source_document_id.
    Optional: state, source_url, checked_at, note.
    Values are parsed as floats when possible; otherwise preserved as text.
    """
    if isinstance(payload, bytes):
        payload = payload.decode("utf-8")
    reader = csv.DictReader(StringIO(payload))
    required = {"property_name", "value", "unit", "source_document_id"}
    if reader.fieldnames is None or not required.issubset(set(reader.fieldnames)):
        raise ValueError(f"CSV requires columns: {sorted(required)}")

    observations: list[PropertyObservation] = []
    source_docs: dict[str, SourceDocument] = {}
    for row in reader:
        raw_value = row.get("value", "")
        try:
            value: Any = float(raw_value)
        except (TypeError, ValueError):
            value = raw_value
        source_id = str(row.get("source_document_id", "")).strip()
        state = EvidenceState(row.get("state") or EvidenceState.UNVERIFIED.value)
        observations.append(
            PropertyObservation(
                property_name=str(row.get("property_name", "")),
                value=value,
                unit=row.get("unit") or None,
                source_document_id=source_id,
                state=state,
                source_url=row.get("source_url") or None,
                checked_at=row.get("checked_at") or None,
                note=row.get("note") or None,
            )
        )
        if source_id and source_id not in source_docs:
            source_docs[source_id] = SourceDocument(
                document_id=source_id,
                title=source_id,
                source_url=row.get("source_url") or None,
                checked_at=row.get("checked_at") or None,
            )

    return DatasheetBundle(
        material_id=material_id,
        material_name=material_name,
        category=category,
        sources=source_docs,
        observations=observations,
    )


def normalized_rows(observations: Iterable[NormalizedObservation]) -> list[dict[str, Any]]:
    return [
        {
            "property": obs.canonical_name,
            "value": obs.canonical_value,
            "unit": obs.canonical_unit,
            "source_document_id": obs.source_document_id,
            "state": obs.state.value,
            "source_url": obs.source_url,
            "checked_at": obs.checked_at,
            "original_name": obs.original_name,
            "original_value": obs.original_value,
            "original_unit": obs.original_unit,
        }
        for obs in observations
    ]
