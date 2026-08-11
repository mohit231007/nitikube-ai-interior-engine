import math

from nitikube.boq import BOQItem, all_prices_verified, audit_quantity, total_known_cost
from nitikube.ergonomics import dining_envelope, rectangular_fit, screen_dimensions_in, viewing_distance_for_horizontal_fov_ft
from nitikube.project import ProjectSnapshot, RoomInput
from nitikube.provenance import EvidenceRecord, EvidenceState, validate_numeric_evidence


def test_dining_envelope_math():
    env = dining_envelope(table_length_ft=6, table_width_ft=3, chair_depth_ft=1.7, pullback_clearance_ft=1.5)
    assert math.isclose(env.required_length_ft, 12.4)
    assert math.isclose(env.required_width_ft, 9.4)


def test_dining_envelope_fits_current_room():
    env = dining_envelope(table_length_ft=6, table_width_ft=3, chair_depth_ft=1.7, pullback_clearance_ft=1.5)
    fit = rectangular_fit(
        room_length_ft=22.75,
        room_width_ft=10 + 7/12,
        item_length_ft=env.required_length_ft,
        item_width_ft=env.required_width_ft,
    )
    assert fit.fits is True
    assert fit.width_margin_ft > 1


def test_tv_geometry():
    width, height = screen_dimensions_in(65)
    assert 56 < width < 57
    assert 31 < height < 32
    d = viewing_distance_for_horizontal_fov_ft(65, 30)
    assert 8.7 < d < 8.9


def test_boq_quantity_audit():
    audit = audit_quantity(12, 15, tolerance_pct=5)
    assert audit.status == "quoted_above_calculated"
    assert audit.percent_difference == 25.0


def test_price_verification_contract():
    unverified = BOQItem("Lighting", "COB", 12, "pcs", unit_rate=500)
    verified = BOQItem(
        "Lighting",
        "COB",
        12,
        "pcs",
        unit_rate=500,
        source_url="https://example.com/product",
        verified_at="2026-08-11T17:00:00+00:00",
    )
    assert unverified.price_verified is False
    assert verified.price_verified is True
    assert total_known_cost([verified]) == 6000
    assert all_prices_verified([verified]) is True


def test_numeric_verified_evidence_needs_provenance():
    bad = EvidenceRecord("price", 500, "INR", EvidenceState.VERIFIED)
    ok, reason = validate_numeric_evidence(bad)
    assert ok is False
    assert "source_url" in reason


def test_project_json_round_trip():
    p = ProjectSnapshot(
        project_name="Home",
        location="Gurugram",
        budget_inr=1_200_000,
        rooms=[RoomInput("Drawing", 22.75, 10 + 7/12, 9)],
        verified_inputs={"drawing": True},
    )
    restored = ProjectSnapshot.from_json(p.to_json())
    assert restored.project_name == p.project_name
    assert restored.rooms[0].ceiling_height_ft == 9
