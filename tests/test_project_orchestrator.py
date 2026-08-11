import copy
import json

import pytest

from nitikube.home_optimizer import RoomDesignOption, ScoreWeights, optimize_home
from nitikube.project_orchestrator import (
    ArtifactRef,
    MergedOptionBundle,
    OptionSource,
    artifact_ref,
    build_design_package,
    merge_option_payloads,
    room_coverage,
    sha256_bytes,
    validate_option_room_links,
    verify_design_package_hash,
)


def option_payload(room_id: str, option_id: str, *, cost: float = 100.0, score: float = 80.0) -> bytes:
    return json.dumps(
        {
            "options": [
                {
                    "room_id": room_id,
                    "option_id": option_id,
                    "name": option_id,
                    "cost": cost,
                    "quality": score,
                    "durability": score,
                    "aesthetics": score,
                    "comfort": score,
                    "maintainability": score,
                    "features": ["geometry-checked"],
                    "feasible": True,
                    "score_source": "test_fixture",
                    "notes": [],
                }
            ]
        },
        sort_keys=True,
    ).encode("utf-8")


def test_sha256_and_artifact_ref_are_deterministic():
    payload = b"nitikube"
    digest = sha256_bytes(payload)
    assert digest == sha256_bytes("nitikube")
    assert len(digest) == 64
    ref = artifact_ref("a.json", "room_design_options", payload)
    assert ref.sha256 == digest
    assert ref.bytes_size == len(payload)


def test_merge_option_payloads_tracks_source_hash_per_option():
    a = option_payload("R1", "R1-a")
    b = option_payload("R2", "R2-a")
    bundle = merge_option_payloads([("living.json", a), ("bedroom.json", b)])
    assert {option.option_id for option in bundle.options} == {"R1-a", "R2-a"}
    assert len(bundle.artifacts) == 2
    source = {item.option_id: item for item in bundle.option_sources}
    assert source["R1-a"].artifact_name == "living.json"
    assert source["R1-a"].artifact_sha256 == sha256_bytes(a)
    assert source["R2-a"].artifact_sha256 == sha256_bytes(b)


def test_duplicate_option_ids_across_artifacts_fail_closed():
    with pytest.raises(ValueError, match="duplicate option_id"):
        merge_option_payloads(
            [
                ("a.json", option_payload("R1", "same")),
                ("b.json", option_payload("R2", "same")),
            ]
        )


def test_room_link_validation_rejects_orphan_room_ids():
    bundle = merge_option_payloads([("a.json", option_payload("R1", "R1-a"))])
    validate_option_room_links(bundle.options, ["R1", "R2"])
    with pytest.raises(ValueError, match="absent from verified geometry"):
        validate_option_room_links(bundle.options, ["R2"])


def test_room_coverage_distinguishes_covered_and_missing_rooms():
    bundle = merge_option_payloads([("a.json", option_payload("R1", "R1-a"))])
    coverage = room_coverage((("R1", "Living"), ("R2", "Bedroom")), bundle.options)
    by_room = {row.room_id: row for row in coverage}
    assert by_room["R1"].status == "covered"
    assert by_room["R1"].option_count == 1
    assert by_room["R2"].status == "missing_options"
    assert by_room["R2"].option_count == 0


def test_build_design_package_carries_selected_option_provenance_and_self_hash():
    payload_a = option_payload("R1", "R1-a", cost=300, score=85)
    payload_b = option_payload("R2", "R2-a", cost=250, score=75)
    bundle = merge_option_payloads([("living.json", payload_a), ("bedroom.json", payload_b)])
    weights = ScoreWeights()
    optimization = optimize_home(
        bundle.options,
        budget=1000,
        reserve=100,
        weights=weights,
        required_room_ids=["R1", "R2"],
    )
    geometry = ArtifactRef("geometry.json", "verified_geometry", "a" * 64, 1234)
    package = build_design_package(
        project_name="Test Home",
        geometry_artifact=geometry,
        option_bundle=bundle,
        optimization=optimization,
        weights=weights,
        required_room_ids=["R1", "R2"],
        locked_choices={"R1": "R1-a"},
        professional_verification_flags=("structural wall change",),
        created_at="2026-08-11T18:00:00+00:00",
    )
    assert package["schema"] == "nitikube.design_package"
    assert package["schema_version"] == "0.17"
    assert package["project_name"] == "Test Home"
    assert package["geometry_artifact"]["sha256"] == "a" * 64
    assert package["locked_choices"] == {"R1": "R1-a"}
    assert package["professional_verification_flags"] == ["structural wall change"]
    assert len(package["selected_options"]) == 2
    for selected in package["selected_options"]:
        assert selected["source_artifact"] in {"living.json", "bedroom.json"}
        assert len(selected["source_sha256"]) == 64
    assert len(package["package_id"]) == 64
    assert verify_design_package_hash(package) is True


def test_package_hash_detects_manifest_tampering():
    bundle = merge_option_payloads([("a.json", option_payload("R1", "R1-a"))])
    weights = ScoreWeights()
    optimization = optimize_home(bundle.options, budget=500, weights=weights, required_room_ids=["R1"])
    package = build_design_package(
        project_name="Test",
        geometry_artifact=ArtifactRef("g.json", "verified_geometry", "b" * 64, 10),
        option_bundle=bundle,
        optimization=optimization,
        weights=weights,
        required_room_ids=["R1"],
        created_at="2026-08-11T18:00:00+00:00",
    )
    tampered = copy.deepcopy(package)
    tampered["selected_cost"] = 1
    assert verify_design_package_hash(tampered) is False
    assert verify_design_package_hash(package) is True


def test_infeasible_optimization_cannot_be_promoted_to_design_package():
    options = [
        RoomDesignOption("R1", "R1-a", "A", 600, 80, 80, 80, 80, 80),
        RoomDesignOption("R2", "R2-a", "B", 600, 80, 80, 80, 80, 80),
    ]
    optimization = optimize_home(options, budget=1000, required_room_ids=["R1", "R2"])
    assert optimization.feasible is False
    bundle = MergedOptionBundle(
        options=tuple(options),
        artifacts=(ArtifactRef("options.json", "room_design_options", "c" * 64, 1),),
        option_sources=(
            OptionSource("R1-a", "options.json", "c" * 64),
            OptionSource("R2-a", "options.json", "c" * 64),
        ),
    )
    with pytest.raises(ValueError, match="infeasible optimization"):
        build_design_package(
            project_name="Test",
            geometry_artifact=ArtifactRef("g.json", "verified_geometry", "d" * 64, 1),
            option_bundle=bundle,
            optimization=optimization,
            weights=ScoreWeights(),
            required_room_ids=["R1", "R2"],
            created_at="2026-08-11T18:00:00+00:00",
        )


def test_selected_option_missing_source_provenance_is_rejected():
    options = (RoomDesignOption("R1", "R1-a", "A", 100, 80, 80, 80, 80, 80),)
    optimization = optimize_home(options, budget=500, required_room_ids=["R1"])
    bundle = MergedOptionBundle(
        options=options,
        artifacts=(ArtifactRef("options.json", "room_design_options", "e" * 64, 1),),
        option_sources=(),
    )
    with pytest.raises(ValueError, match="missing option-artifact provenance"):
        build_design_package(
            project_name="Test",
            geometry_artifact=ArtifactRef("g.json", "verified_geometry", "f" * 64, 1),
            option_bundle=bundle,
            optimization=optimization,
            weights=ScoreWeights(),
            required_room_ids=["R1"],
            created_at="2026-08-11T18:00:00+00:00",
        )


def test_fixed_timestamp_makes_manifest_reproducible_for_identical_inputs():
    payload = option_payload("R1", "R1-a", cost=100, score=80)
    bundle = merge_option_payloads([("room.json", payload)])
    weights = ScoreWeights()
    optimization = optimize_home(bundle.options, budget=500, weights=weights, required_room_ids=["R1"])
    kwargs = dict(
        project_name="Reproducible",
        geometry_artifact=ArtifactRef("g.json", "verified_geometry", "1" * 64, 50),
        option_bundle=bundle,
        optimization=optimization,
        weights=weights,
        required_room_ids=["R1"],
        created_at="2026-08-11T18:00:00+00:00",
    )
    first = build_design_package(**kwargs)
    second = build_design_package(**kwargs)
    assert first == second
    assert first["package_id"] == second["package_id"]
