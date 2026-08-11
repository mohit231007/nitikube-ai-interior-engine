import math

import pytest

from nitikube.photometry import (
    FT_TO_M,
    PhotometricFixture,
    candela_at,
    direct_horizontal_illuminance_lux,
    even_fixture_grid_from_feet,
    grid_matrix,
    illuminance_grid,
    parse_ies,
    summarize_illuminance,
    total_direct_illuminance_lux,
)


SYMMETRIC_IES = """IESNA:LM-63-2002
[TEST] NITIKUBE-SYNTHETIC-TEST
[MANUFAC] Test only
TILT=NONE
1 1000 1 3 1 1 2 0.1 0.1 0.1
1 1 100
0 45 90
0
1000 500 0
"""

FULL_HORIZONTAL_IES = """IESNA:LM-63-2002
[TEST] NITIKUBE-FULL-HORIZONTAL
TILT=NONE
1 -1 1 2 3 1 2 0.1 0.1 0.1
1 1 20
0 90
0 180 360
1000 0
500 0
1000 0
"""


def test_parse_symmetric_type_c_ies():
    ies = parse_ies(SYMMETRIC_IES)
    assert ies.photometric_type == 1
    assert ies.units_type == 2
    assert ies.rotationally_symmetric is True
    assert ies.vertical_angles_deg == (0.0, 45.0, 90.0)
    assert ies.horizontal_angles_deg == (0.0,)
    assert ies.candela_values[0] == (1000.0, 500.0, 0.0)
    assert ies.input_watts == pytest.approx(100.0)
    assert ies.total_nominal_lamp_lumens == pytest.approx(1000.0)


def test_absolute_photometry_negative_lumens_stays_unknown_not_fabricated():
    ies = parse_ies(FULL_HORIZONTAL_IES)
    assert ies.total_nominal_lamp_lumens is None


def test_parser_rejects_tilt_and_non_type_c_instead_of_guessing():
    tilt = SYMMETRIC_IES.replace("TILT=NONE", "TILT=INCLUDE")
    with pytest.raises(NotImplementedError, match="TILT=NONE"):
        parse_ies(tilt)

    type_b = SYMMETRIC_IES.replace("3 1 1 2", "3 1 2 2")
    with pytest.raises(NotImplementedError, match="Type C"):
        parse_ies(type_b)


def test_parser_rejects_partial_horizontal_symmetry_planes_for_now():
    partial = FULL_HORIZONTAL_IES.replace("0 180 360", "0 90 180")
    with pytest.raises(NotImplementedError, match="partial symmetry"):
        parse_ies(partial)


def test_vertical_candela_interpolation_is_linear():
    ies = parse_ies(SYMMETRIC_IES)
    assert candela_at(ies, 0) == pytest.approx(1000)
    assert candela_at(ies, 22.5) == pytest.approx(750)
    assert candela_at(ies, 45) == pytest.approx(500)
    assert candela_at(ies, 90) == pytest.approx(0)
    assert candela_at(ies, 120) == pytest.approx(0)


def test_full_horizontal_interpolation_respects_azimuth():
    ies = parse_ies(FULL_HORIZONTAL_IES)
    assert candela_at(ies, 0, 0) == pytest.approx(1000)
    assert candela_at(ies, 0, 180) == pytest.approx(500)
    assert candela_at(ies, 0, 90) == pytest.approx(750)
    assert candela_at(ies, 0, 270) == pytest.approx(750)


def test_inverse_square_cosine_illuminance_at_nadir():
    ies = parse_ies(SYMMETRIC_IES)
    fixture = PhotometricFixture("F1", 0, 0, height_above_plane_m=2.0)
    # E = 1000 cd / (2 m)^2 = 250 lux at nadir.
    assert direct_horizontal_illuminance_lux(ies, fixture, 0, 0) == pytest.approx(250.0)


def test_off_axis_illuminance_uses_candela_cosine_and_distance():
    ies = parse_ies(SYMMETRIC_IES)
    fixture = PhotometricFixture("F1", 0, 0, height_above_plane_m=2.0)
    # At x=2m, gamma=45°, r²=8, I=500 cd.
    expected = 500.0 * math.cos(math.radians(45)) / 8.0
    assert direct_horizontal_illuminance_lux(ies, fixture, 2, 0) == pytest.approx(expected)


def test_multiple_fixture_illuminance_adds_linearly_and_maintenance_factor_is_explicit():
    ies = parse_ies(SYMMETRIC_IES)
    fixtures = [
        PhotometricFixture("F1", 0, 0, 2),
        PhotometricFixture("F2", 0, 0, 2),
    ]
    assert total_direct_illuminance_lux(ies, fixtures, 0, 0, maintenance_factor=1.0) == pytest.approx(500)
    assert total_direct_illuminance_lux(ies, fixtures, 0, 0, maintenance_factor=0.8) == pytest.approx(400)


def test_even_fixture_grid_converts_feet_and_work_plane_height():
    fixtures = even_fixture_grid_from_feet(
        room_length_ft=20,
        room_width_ft=10,
        rows=2,
        cols=4,
        ceiling_height_ft=9,
        evaluation_plane_height_ft=2.5,
    )
    assert len(fixtures) == 8
    assert fixtures[0].x_m == pytest.approx(2.5 * FT_TO_M)
    assert fixtures[0].y_m == pytest.approx(2.5 * FT_TO_M)
    assert fixtures[0].height_above_plane_m == pytest.approx(6.5 * FT_TO_M)


def test_point_grid_summary_and_target_band():
    ies = parse_ies(SYMMETRIC_IES)
    fixture = PhotometricFixture("F1", 1, 1, 2)
    points = illuminance_grid(
        ies,
        [fixture],
        room_width_m=2,
        room_length_m=2,
        x_samples=3,
        y_samples=3,
        maintenance_factor=1.0,
    )
    assert len(points) == 9
    summary = summarize_illuminance(points, maintenance_factor=1.0, target_min_lux=100, target_max_lux=300)
    assert summary.minimum_lux >= 0
    assert summary.maximum_lux == pytest.approx(250.0)
    assert 0 <= summary.min_to_avg <= 1
    assert 0 <= summary.target_band_fraction <= 1
    matrix = grid_matrix(points, x_samples=3, y_samples=3)
    assert len(matrix) == 3
    assert len(matrix[0]) == 3
    assert matrix[1][1] == pytest.approx(250.0)


def test_invalid_maintenance_factor_and_grid_shape_raise():
    ies = parse_ies(SYMMETRIC_IES)
    fixture = PhotometricFixture("F1", 0, 0, 2)
    with pytest.raises(ValueError, match="maintenance_factor"):
        total_direct_illuminance_lux(ies, [fixture], 0, 0, maintenance_factor=0)
    with pytest.raises(ValueError, match="grid shape"):
        grid_matrix([], x_samples=2, y_samples=2)
