import math

from nitikube.acoustics import AbsorbingSurface, free_field_level_change_db, room_volume_m3, sabine_rt60_seconds, total_absorption_area_m2
from nitikube.electrical import LoadItem, aggregate_load, conductor_resistance_ohm, energy_kwh, single_phase_current_a, voltage_drop_v
from nitikube.solar import hour_angle_deg, solar_altitude_deg, solar_declination_deg, solar_position


def test_solar_hour_angle():
    assert hour_angle_deg(12) == 0
    assert hour_angle_deg(10) == -30
    assert hour_angle_deg(14) == 30


def test_solar_altitude_equinox_equator_noon_is_near_zenith():
    decl = solar_declination_deg(81)
    altitude = solar_altitude_deg(0, decl, 0)
    assert abs(decl) < 1
    assert altitude > 89


def test_solar_position_changes_with_latitude():
    delhi_like = solar_position(28.46, 172, 12)
    high_latitude = solar_position(50.0, 172, 12)
    assert delhi_like.altitude_deg > high_latitude.altitude_deg


def test_sabine_rt60():
    volume = room_volume_m3(5, 4, 3)
    absorption = total_absorption_area_m2([
        AbsorbingSurface(20, 0.2),
        AbsorbingSurface(20, 0.3),
    ])
    assert absorption == 10
    assert math.isclose(sabine_rt60_seconds(volume, absorption), 0.966, rel_tol=1e-12)


def test_free_field_distance_doubling_is_about_minus_6db():
    delta = free_field_level_change_db(1, 2)
    assert -6.1 < delta < -6.0


def test_single_phase_current():
    assert math.isclose(single_phase_current_a(2300, 230, 1, 1), 10)


def test_energy():
    assert energy_kwh(1000, 5) == 5


def test_conductor_resistance_uses_round_trip_length():
    # With synthetic rho=1 Ωm, 1 m one-way and 1,000,000 mm² (=1 m²), round trip R=2 Ω.
    resistance = conductor_resistance_ohm(1, 1, 1_000_000, round_trip=True)
    assert resistance == 2


def test_load_aggregation():
    connected, diversified = aggregate_load([
        LoadItem("A", 100, 2, 1.0),
        LoadItem("B", 1000, 1, 0.5),
    ])
    assert connected == 1200
    assert diversified == 700
    assert voltage_drop_v(10, 0.2) == 2
