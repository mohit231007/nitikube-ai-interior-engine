import copy
import json

import pytest

from nitikube.final_report import audit_json, audit_report_inputs, render_final_report
from nitikube.home_optimizer import ScoreWeights, optimize_home
from nitikube.project_orchestrator import ArtifactRef, build_design_package, merge_option_payloads


def design_package(*, project_name="Test Home", flags=()):
    payload = json.dumps(
        {
            "options": [
                {
                    "room_id": "R1",
                    "option_id": "R1-a",
                    "name": "Living option",
                    "cost": 100000,
                    "quality": 80,
                    "durability": 80,
                    "aesthetics": 80,
                    "comfort": 80,
                    "maintainability": 80,
                    "features": ["geometry-checked"],
                    "feasible": True,
                    "score_source": "test",
                    "notes": [],
                }
            ]
        }
    ).encode("utf-8")
    bundle = merge_option_payloads([("living.json", payload)])
    weights = ScoreWeights()
    optimization = optimize_home(bundle.options, budget=200000, reserve=10000, weights=weights, required_room_ids=["R1"])
    return build_design_package(
        project_name=project_name,
        geometry_artifact=ArtifactRef("geometry.json", "verified_geometry", "a" * 64, 100),
        option_bundle=bundle,
        optimization=optimization,
        weights=weights,
        required_room_ids=["R1"],
        professional_verification_flags=flags,
        created_at="2026-08-11T18:00:00+00:00",
    )


def standards_attachment(status="pass", mandatory=False):
    return {
        "schema": "nitikube.rule_evaluation",
        "schema_version": "0.18",
        "context": {"room_type": "living", "tags": ["residential"], "jurisdiction": "India"},
        "results": [
            {
                "rule_id": "RULE-1",
                "status": status,
                "actual_value": 100,
                "actual_unit": "lux",
                "normalized_actual": 100,
                "normalized_unit": "lux",
                "normalized_lower": 50,
                "normalized_upper": 150,
                "reason": "test",
                "mandatory": mandatory,
            }
        ],
    }


def lifecycle_attachment(feasible=True):
    return {
        "schema": "nitikube.lifecycle_comparison",
        "schema_version": "0.19",
        "assumptions": {},
        "results": [
            {
                "option_id": "mat-a",
                "feasible": feasible,
                "unknown_fields": [] if feasible else ["service_life_years"],
                "failed_constraints": [],
                "initial_installed_cost": 10000 if feasible else None,
                "replacement_count": 1 if feasible else 0,
                "residual_value_credit": 0,
                "npv_cost": 15000 if feasible else None,
                "equivalent_annual_cost": 1000 if feasible else None,
                "npv_cost_per_area": 150 if feasible else None,
            }
        ],
        "pareto": [],
        "sensitivity": [],
    }


def test_audit_reports_hash_rooms_flags_and_attachment_states():
    package = design_package(flags=("electrical verification",))
    audit = audit_report_inputs(
        package,
        standards_evaluation=standards_attachment(status="unknown", mandatory=True),
        lifecycle_comparison=lifecycle_attachment(feasible=False),
    )
    assert audit.package_hash_valid is True
    assert audit.selected_room_count == 1
    assert audit.required_room_count == 1
    assert audit.professional_verification_flag_count == 1
    assert audit.standard_unknown_count == 1
    assert audit.mandatory_standard_unresolved_count == 1
    assert audit.lifecycle_nonfeasible_count == 1
    assert any("professional verification" in warning for warning in audit.warnings)
    assert any("mandatory standards" in warning for warning in audit.warnings)


def test_missing_optional_attachments_are_warnings_not_fabricated_results():
    audit = audit_report_inputs(design_package())
    assert audit.standard_pass_count == 0
    assert audit.lifecycle_feasible_count == 0
    assert any("no standards" in warning for warning in audit.warnings)
    assert any("no lifecycle" in warning for warning in audit.warnings)


def test_invalid_package_hash_blocks_report_by_default():
    package = design_package()
    package["selected_cost"] = 1
    with pytest.raises(ValueError, match="hash is invalid"):
        render_final_report(package)


def test_invalid_package_hash_can_only_render_with_explicit_override_and_is_visible():
    package = design_package()
    package["selected_cost"] = 1
    artifact = render_final_report(package, allow_invalid_package_hash=True)
    assert artifact.audit.package_hash_valid is False
    assert "FAIL / OVERRIDDEN" in artifact.html
    assert any("hash verification failed" in warning for warning in artifact.audit.warnings)


def test_report_contains_selected_option_source_hash_and_professional_flags():
    artifact = render_final_report(
        design_package(flags=("structural engineer required",)),
        standards_evaluation=standards_attachment(),
        lifecycle_comparison=lifecycle_attachment(),
    )
    assert "living.json" in artifact.html
    assert "structural engineer required" in artifact.html
    assert "RULE-1" in artifact.html
    assert "mat-a" in artifact.html
    assert len(artifact.report_id) == 64


def test_report_escapes_untrusted_project_and_source_text():
    package = design_package(project_name="<script>alert(1)</script>")
    artifact = render_final_report(package)
    assert "<script>alert(1)</script>" not in artifact.html
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in artifact.html


def test_report_is_deterministic_for_identical_fixed_input_package():
    package = design_package()
    first = render_final_report(package, standards_evaluation=standards_attachment(), lifecycle_comparison=lifecycle_attachment())
    second = render_final_report(package, standards_evaluation=standards_attachment(), lifecycle_comparison=lifecycle_attachment())
    assert first.html == second.html
    assert first.report_id == second.report_id


def test_tampered_attachment_schema_is_rejected():
    with pytest.raises(ValueError, match="not nitikube.rule_evaluation"):
        render_final_report(design_package(), standards_evaluation={"schema": "wrong"})
    with pytest.raises(ValueError, match="not nitikube.lifecycle_comparison"):
        render_final_report(design_package(), lifecycle_comparison={"schema": "wrong"})


def test_audit_json_carries_report_hash_and_structured_audit():
    artifact = render_final_report(design_package())
    payload = json.loads(audit_json(artifact))
    assert payload["schema"] == "nitikube.final_report_audit"
    assert payload["schema_version"] == "0.22"
    assert payload["report_id"] == artifact.report_id
    assert payload["audit"]["package_hash_valid"] is True
