from nitikube.material_db import MaterialProperty, MaterialRecord, numeric_property, validate_material
from nitikube.provenance import EvidenceState
from nitikube.spec_match import ProductRequirement, ProductSpecification, match_product, rank_products


def test_verified_material_numeric_property_requires_provenance():
    record = MaterialRecord(
        material_id="m1",
        name="Material",
        category="test",
        properties={
            "density": MaterialProperty("density", 700, "kg/m3", EvidenceState.VERIFIED)
        },
    )
    validation = validate_material(record)
    assert validation.valid_for_verified_recommendation is False
    assert numeric_property(record, "density", verified_only=True) is None


def test_verified_material_with_source_can_be_used():
    record = MaterialRecord(
        material_id="m1",
        name="Material",
        category="test",
        properties={
            "density": MaterialProperty(
                "density",
                700,
                "kg/m3",
                EvidenceState.VERIFIED,
                source_url="https://example.com/datasheet",
                checked_at="2026-08-11T17:00:00+00:00",
            )
        },
    )
    validation = validate_material(record)
    assert validation.valid_for_verified_recommendation is True
    assert numeric_property(record, "density") == 700


def test_product_match_does_not_treat_unknown_as_match():
    req = ProductRequirement(
        category="COB downlight",
        lumens_min=450,
        lumens_max=550,
        kelvin_allowed=(3000,),
        beam_angle_target_deg=36,
        beam_angle_tolerance_deg=3,
        cri_min=90,
    )
    product = ProductSpecification(
        name="Incomplete",
        category="COB downlight",
        lumens=500,
        kelvin=3000,
        beam_angle_deg=None,
        cri=90,
    )
    result = match_product(product, req)
    assert result.feasible is True
    assert "beam_angle" in result.unknown
    assert result.score < 100


def test_product_failed_spec_is_not_feasible():
    req = ProductRequirement(category="COB downlight", cri_min=90)
    product = ProductSpecification(name="Low CRI", category="COB downlight", cri=80)
    result = match_product(product, req)
    assert result.feasible is False
    assert "cri" in result.failed


def test_rank_products_prefers_higher_spec_match():
    req = ProductRequirement(category="COB downlight", lumens_min=450, lumens_max=550, cri_min=90)
    good = ProductSpecification("Good", "COB downlight", lumens=500, cri=95)
    incomplete = ProductSpecification("Incomplete", "COB downlight", lumens=500, cri=None)
    ranked = rank_products([incomplete, good], req)
    assert ranked[0][0].name == "Good"
