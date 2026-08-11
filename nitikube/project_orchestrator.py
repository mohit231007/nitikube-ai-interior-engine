from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import json
from typing import Any, Iterable, Mapping, Sequence

from .home_optimizer import HomeOptimizationResult, RoomDesignOption, ScoreWeights, load_room_options_json, result_rows
from .verified_geometry import geometry_from_project_json


@dataclass(frozen=True)
class ArtifactRef:
    name: str
    kind: str
    sha256: str
    bytes_size: int


@dataclass(frozen=True)
class OptionSource:
    option_id: str
    artifact_name: str
    artifact_sha256: str


@dataclass(frozen=True)
class RoomCoverage:
    room_id: str
    room_name: str
    option_count: int
    status: str


@dataclass(frozen=True)
class MergedOptionBundle:
    options: tuple[RoomDesignOption, ...]
    artifacts: tuple[ArtifactRef, ...]
    option_sources: tuple[OptionSource, ...]


def sha256_bytes(payload: str | bytes) -> str:
    if isinstance(payload, str):
        payload = payload.encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def artifact_ref(name: str, kind: str, payload: str | bytes) -> ArtifactRef:
    if not name.strip() or not kind.strip():
        raise ValueError("artifact name and kind are required")
    raw = payload.encode("utf-8") if isinstance(payload, str) else payload
    return ArtifactRef(name=name, kind=kind, sha256=sha256_bytes(raw), bytes_size=len(raw))


def merge_option_payloads(named_payloads: Iterable[tuple[str, str | bytes]]) -> MergedOptionBundle:
    options: list[RoomDesignOption] = []
    artifacts: list[ArtifactRef] = []
    sources: list[OptionSource] = []
    seen_ids: set[str] = set()
    for name, payload in named_payloads:
        ref = artifact_ref(name, "room_design_options", payload)
        parsed = load_room_options_json(payload)
        artifacts.append(ref)
        for option in parsed:
            if option.option_id in seen_ids:
                raise ValueError(f"duplicate option_id across option artifacts: {option.option_id}")
            seen_ids.add(option.option_id)
            options.append(option)
            sources.append(OptionSource(option.option_id, ref.name, ref.sha256))
    if not options:
        raise ValueError("at least one room option artifact with one option is required")
    return MergedOptionBundle(tuple(options), tuple(artifacts), tuple(sources))


def verified_geometry_inventory(payload: str | bytes) -> tuple[ArtifactRef, str, tuple[tuple[str, str], ...]]:
    text = payload.decode("utf-8") if isinstance(payload, bytes) else payload
    project_name, rooms, _openings, _metadata = geometry_from_project_json(text)
    verified_rooms = tuple((room.room_id, room.name) for room in rooms if room.verified)
    if not verified_rooms:
        raise ValueError("verified geometry contains no verified rooms")
    return artifact_ref("nitikube_verified_geometry.json", "verified_geometry", text), project_name, verified_rooms


def validate_option_room_links(options: Sequence[RoomDesignOption], verified_room_ids: Sequence[str]) -> None:
    verified = set(verified_room_ids)
    unknown = sorted({option.room_id for option in options if option.room_id not in verified})
    if unknown:
        raise ValueError(
            "room option artifacts reference room_id values absent from verified geometry: " + ", ".join(unknown)
        )


def room_coverage(
    verified_rooms: Sequence[tuple[str, str]],
    options: Sequence[RoomDesignOption],
) -> tuple[RoomCoverage, ...]:
    counts: dict[str, int] = {}
    for option in options:
        counts[option.room_id] = counts.get(option.room_id, 0) + 1
    return tuple(
        RoomCoverage(
            room_id=room_id,
            room_name=room_name,
            option_count=counts.get(room_id, 0),
            status="covered" if counts.get(room_id, 0) > 0 else "missing_options",
        )
        for room_id, room_name in verified_rooms
    )


def canonical_json_bytes(data: Any) -> bytes:
    return json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _weights_dict(weights: ScoreWeights) -> dict[str, float]:
    return {
        "quality": weights.quality,
        "durability": weights.durability,
        "aesthetics": weights.aesthetics,
        "comfort": weights.comfort,
        "maintainability": weights.maintainability,
    }


def build_design_package(
    *,
    project_name: str,
    geometry_artifact: ArtifactRef,
    option_bundle: MergedOptionBundle,
    optimization: HomeOptimizationResult,
    weights: ScoreWeights,
    required_room_ids: Sequence[str],
    locked_choices: Mapping[str, str] | None = None,
    professional_verification_flags: Sequence[str] = (),
    created_at: str | None = None,
) -> dict[str, Any]:
    if not optimization.feasible:
        raise ValueError("cannot create an approved design package from an infeasible optimization result")
    if not required_room_ids:
        raise ValueError("required_room_ids cannot be empty")
    selected_ids = {item.option_id for item in optimization.selected}
    source_lookup = {source.option_id: source for source in option_bundle.option_sources}
    missing_source = selected_ids - set(source_lookup)
    if missing_source:
        raise ValueError(f"selected options are missing option-artifact provenance: {sorted(missing_source)}")
    timestamp = created_at or datetime.now(timezone.utc).replace(microsecond=0).isoformat()

    selected_with_source = []
    for row in result_rows(optimization):
        source = source_lookup[row["option_id"]]
        selected_with_source.append({
            **row,
            "source_artifact": source.artifact_name,
            "source_sha256": source.artifact_sha256,
        })

    core = {
        "schema": "nitikube.design_package",
        "schema_version": "0.17",
        "project_name": project_name,
        "created_at": timestamp,
        "geometry_artifact": asdict(geometry_artifact),
        "option_artifacts": [asdict(ref) for ref in option_bundle.artifacts],
        "required_room_ids": list(required_room_ids),
        "locked_choices": dict(locked_choices or {}),
        "budget": optimization.budget,
        "reserve": optimization.reserve,
        "spendable_budget": optimization.spendable_budget,
        "selected_cost": optimization.selected_cost,
        "budget_remaining": optimization.budget_remaining,
        "total_utility": optimization.total_utility,
        "weights": _weights_dict(weights),
        "selected_options": selected_with_source,
        "professional_verification_flags": list(professional_verification_flags),
        "reproducibility_note": (
            "package_id hashes this manifest and its input artifact hashes; it does not prove the truth of source data. "
            "Source/evidence validity remains governed by each NitiKube evidence contract."
        ),
    }
    package_id = sha256_bytes(canonical_json_bytes(core))
    return {**core, "package_id": package_id}


def verify_design_package_hash(package: Mapping[str, Any]) -> bool:
    if "package_id" not in package:
        return False
    claimed = str(package["package_id"])
    core = {key: value for key, value in package.items() if key != "package_id"}
    return sha256_bytes(canonical_json_bytes(core)) == claimed


def coverage_rows(coverage: Sequence[RoomCoverage]) -> list[dict[str, Any]]:
    return [asdict(item) for item in coverage]


def artifact_rows(geometry: ArtifactRef, bundle: MergedOptionBundle) -> list[dict[str, Any]]:
    return [asdict(geometry)] + [asdict(ref) for ref in bundle.artifacts]
