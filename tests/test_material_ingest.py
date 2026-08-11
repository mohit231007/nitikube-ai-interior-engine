import json

import pytest

from nitikube.material_db import validate_material
from nitikube.material_ingest import (
    DatasheetBundle,
    PropertyObservation,
    SourceDocument,
    canonicalize_property_name,
    convert_to_canonical,
    detect_property_conflicts,
    load_datasheet_json,
    material_record_from_bundle,
    normalize_bundle,
    resolve_observations,
)
from nitikube.material_suitability import (
    NumericRequirement,
    RequirementStatus,
    evaluate_material,
    requirement_evidence_state,
)
from nitikube.provenance import EvidenceState


def test_property_aliases_normalize_to_canonical_names():
    assert canonicalize_property_name("Thermal Conductivity") == "thermal_conductivity"
    assert canonicalize_property_name("specific heat capacity") == "specific_heat"
    assert canonicalize_property_name("VOC content") == "voc"
    assert canonicalize_property_name("water_absorption_percent") == "water_absorption"
    assert canonicalize_property_name("Custom Surface Rating") == "custom_surface_rating"


def test_supported_unit_conversions_are_deterministic():
    assert convert_to_canonical("density", 1.2, "g/cm³") == pytest.approx((1200.0, "kg/m³"))
    assert convert_to_canonical("specific_heat", 0.84, "kJ/(kg·K)") == pytest.approx((840.0, "J/(kg·K)"))
    assert convert_to_canonical("water_absorption", 0.05, "fraction") == pytest.approx((5.0, "%"))
    assert convert_to_canonical("voc", 300.0, "mg/L") == pytest.approx((0.3, "g/L"))
    assert convert_to_canonical("thickness", 0.5, "in") == pytest.approx((12.7, "mm"))
    assert convert_to_canonical("service_life", 18.0, "months") == pytest.approx((1.5, "year"))


def test_unknown_units_raise_instead_of_guessing():
    with pytest.raises(ValueError, match="unsupported unit"):
        convert_to_canonical("density", 1.2, "lb/ft3")


def test_json_bundle_inherits_source_provenance():
    payload = {
        "material_id": "board-1",
        "material_name": "Example Board",
        "category": "cabinetry",
        "sources": [
            {
                "document_id": "manufacturer-ds",
                "title": "Manufacturer datasheet",
                "source_url": "https://manufacturer.example/datasheet.pdf",
                "checked_at": "2026-08-11T12:00:00+00:00",
            }
        ],
        "observations": [
            {
                "property_name": "density",
                "value": 0.72,
                "unit": "g/cm3",
                "source_document_id": "manufacturer-ds",
                "state": "verified",
            }
        ],
    }
    bundle = load_datasheet_json(json.dumps(payload))
    normalized = normalize_bundle(bundle)
    assert len(normalized) == 1
    assert normalized[0].canonical_name == "density"
    assert normalized[0].canonical_value == pytest.approx(720.0)
    assert normalized[0].source_url == "https://manufacturer.example/datasheet.pdf"
    assert normalized[0].checked_at == "2026-08-11T12:00:00+00:00"

    record, conflicts = material_record_from_bundle(bundle)
    assert conflicts == []
    assert record.properties["density"].value == pytest.approx(720.0)
    assert validate_material(record).valid_for_verified_recommendation is True


def _conflicting_bundle() -> DatasheetBundle:
    return DatasheetBundle(
        material_id="tile-1",
        material_name="Example Tile",
        category="flooring",
        sources={
            "A": SourceDocument(
                document_id="A",
                title="Source A",
                source_url="https://a.example/ds",
                checked_at="2026-08-11T10:00:00+00:00",
            ),
            "B": SourceDocument(
                document_id="B",
                title="Source B",
                source_url="https://b.example/ds",
                checked_at="2026-08-11T10:00:00+00:00",
            ),
        },
        observations=[
            PropertyObservation(
                property_name="water absorption",
                value=0.5,
                unit="%",
                source_document_id="A",
                state=EvidenceState.VERIFIED,
            ),
            PropertyObservation(
                property_name="water_absorption",
                value=3.0,
                unit="%",
                source_document_id="B",
                state=EvidenceState.VERIFIED,
            ),
        ],
    )


def test_cross_source_conflicts_remain_visible_and_are_not_averaged():
    normalized = normalize_bundle(_conflicting_bundle())
    conflicts = detect_property_conflicts(normalized)
    assert len(conflicts) == 1
    assert conflicts[0].canonical_name == "water_absorption"
    assert conflicts[0].distinct_values == pytest.approx((0.5, 3.0))

    resolved, unresolved = resolve_observations(normalized)
    assert "water_absorption" not in resolved
    assert len(unresolved) == 1

    record, record_conflicts = material_record_from_bundle(_conflicting_bundle())
    assert "water_absorption" not in record.properties
    assert len(record_conflicts) == 1


def test_explicit_preferred_source_resolves_conflict_without_averaging():
    normalized = normalize_bundle(_conflicting_bundle())
    resolved, conflicts = resolve_observations(
        normalized,
        preferred_source_by_property={"water_absorption": "A"},
    )
    assert conflicts == []
    assert resolved["water_absorption"].canonical_value == pytest.approx(0.5)
    assert resolved["water_absorption"].source_document_id == "A"


def test_agreeing_sources_keep_best_evidence_record_without_averaging():
    bundle = DatasheetBundle(
        material_id="m1",
        material_name="Material",
        category="surface",
        sources={
            "verified": SourceDocument(
                document_id="verified",
                title="Verified source",
                source_url="https://example.com/ds",
                checked_at="2026-08-11T10:00:00+00:00",
            ),
            "user": SourceDocument(document_id="user", title="User source"),
        },
        observations=[
            PropertyObservation("thickness", 12.0, "mm", "user", EvidenceState.USER_PROVIDED),
            PropertyObservation("thickness", 12.1, "mm", "verified", EvidenceState.VERIFIED),
        ],
    )
    normalized = normalize_bundle(bundle)
    resolved, conflicts = resolve_observations(normalized, rel_tol=0.02)
    assert conflicts == []
    assert resolved["thickness"].source_document_id == "verified"
    assert resolved["thickness"].canonical_value == pytest.approx(12.1)


def test_verified_numeric_material_without_provenance_is_rejected():
    payload = {
        "material_id": "m1",
        "material_name": "Material",
        "category": "surface",
        "observations": [
            {
                "property_name": "density",
                "value": 800,
                "unit": "kg/m3",
                "source_document_id": "missing-meta",
                "state": "verified",
            }
        ],
    }
    bundle = load_datasheet_json(json.dumps(payload))
    record, conflicts = material_record_from_bundle(bundle)
    assert conflicts == []
    validation = validate_material(record)
    assert validation.valid_for_verified_recommendation is False
    assert any("requires source_url and checked_at" in error for error in validation.errors)


def test_material_suitability_pass_fail_and_unknown_are_explicit():
    payload = {
        "material_id": "tile",
        "material_name": "Tile",
        "category": "flooring",
        "sources": [
            {
                "document_id": "ds",
                "title": "Datasheet",
                "source_url": "https://example.com/tile",
                "checked_at": "2026-08-11T10:00:00+00:00",
            }
        ],
        "observations": [
            {
                "property_name": "water_absorption",
                "value": 0.4,
                "unit": "%",
                "source_document_id": "ds",
                "state": "verified",
            }
        ],
    }
    record, _ = material_record_from_bundle(load_datasheet_json(json.dumps(payload)))

    passes = evaluate_material(
        record,
        [NumericRequirement("water_absorption", "max", 0.5, unit="%")],
    )
    assert passes.feasible is True
    assert passes.results[0].status == RequirementStatus.PASS

    fails = evaluate_material(
        record,
        [NumericRequirement("water_absorption", "max", 0.2, unit="%")],
    )
    assert fails.feasible is False
    assert fails.results[0].status == RequirementStatus.FAIL

    unknown = evaluate_material(
        record,
        [NumericRequirement("voc", "max", 1.0, unit="g/L")],
    )
    assert unknown.feasible is False
    assert unknown.results[0].status == RequirementStatus.UNKNOWN


def test_requirement_threshold_provenance_is_not_overstated():
    user_req = NumericRequirement("density", "min", 600.0, unit="kg/m³")
    state, reason = requirement_evidence_state(user_req)
    assert state == EvidenceState.USER_PROVIDED
    assert "not a sourced standard" in reason

    sourced_req = NumericRequirement(
        "density",
        "min",
        600.0,
        unit="kg/m³",
        source_url="https://example.com/standard",
        checked_at="2026-08-11T10:00:00+00:00",
    )
    state, _ = requirement_evidence_state(sourced_req)
    assert state == EvidenceState.VERIFIED
