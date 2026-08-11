from __future__ import annotations

from dataclasses import dataclass, field
import json
from pathlib import Path
from typing import Any, Iterable

from .provenance import EvidenceRecord, EvidenceState, validate_numeric_evidence


@dataclass(frozen=True)
class MaterialProperty:
    name: str
    value: Any
    unit: str | None = None
    state: EvidenceState = EvidenceState.UNVERIFIED
    source_url: str | None = None
    checked_at: str | None = None
    note: str | None = None

    def as_evidence(self) -> EvidenceRecord:
        return EvidenceRecord(
            name=self.name,
            value=self.value,
            unit=self.unit,
            state=self.state,
            source_url=self.source_url,
            checked_at=self.checked_at,
            note=self.note,
        )


@dataclass
class MaterialRecord:
    material_id: str
    name: str
    category: str
    aliases: list[str] = field(default_factory=list)
    properties: dict[str, MaterialProperty] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class MaterialValidation:
    valid_for_verified_recommendation: bool
    errors: tuple[str, ...]
    warnings: tuple[str, ...]


def validate_material(record: MaterialRecord) -> MaterialValidation:
    errors: list[str] = []
    warnings: list[str] = []
    if not record.material_id.strip():
        errors.append("material_id is required")
    if not record.name.strip():
        errors.append("material name is required")
    if not record.category.strip():
        errors.append("material category is required")
    if not record.properties:
        warnings.append("material has no properties yet")

    for key, prop in record.properties.items():
        if key != prop.name:
            warnings.append(f"property key '{key}' differs from property name '{prop.name}'")
        ok, reason = validate_numeric_evidence(prop.as_evidence())
        if not ok and prop.state == EvidenceState.VERIFIED:
            errors.append(f"{record.material_id}.{key}: {reason}")
        elif prop.state == EvidenceState.UNVERIFIED:
            warnings.append(f"{record.material_id}.{key}: unverified and must not drive a verified recommendation")

    return MaterialValidation(not errors, tuple(errors), tuple(warnings))


def numeric_property(record: MaterialRecord, property_name: str, *, verified_only: bool = True) -> float | None:
    prop = record.properties.get(property_name)
    if prop is None or not isinstance(prop.value, (int, float)):
        return None
    if verified_only:
        ok, _ = validate_numeric_evidence(prop.as_evidence())
        if not ok or prop.state not in {EvidenceState.VERIFIED, EvidenceState.USER_PROVIDED}:
            return None
    return float(prop.value)


def material_from_dict(data: dict[str, Any]) -> MaterialRecord:
    properties: dict[str, MaterialProperty] = {}
    for key, payload in data.get("properties", {}).items():
        state = EvidenceState(payload.get("state", EvidenceState.UNVERIFIED.value))
        properties[key] = MaterialProperty(
            name=key,
            value=payload.get("value"),
            unit=payload.get("unit"),
            state=state,
            source_url=payload.get("source_url"),
            checked_at=payload.get("checked_at"),
            note=payload.get("note"),
        )
    return MaterialRecord(
        material_id=data["material_id"],
        name=data["name"],
        category=data["category"],
        aliases=list(data.get("aliases", [])),
        properties=properties,
        notes=list(data.get("notes", [])),
    )


def load_materials(path: str | Path) -> list[MaterialRecord]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    records = payload.get("materials", payload) if isinstance(payload, dict) else payload
    if not isinstance(records, list):
        raise ValueError("materials JSON must contain a list or {'materials': [...]} object")
    return [material_from_dict(item) for item in records]


def verified_materials(records: Iterable[MaterialRecord]) -> list[MaterialRecord]:
    return [record for record in records if validate_material(record).valid_for_verified_recommendation]
