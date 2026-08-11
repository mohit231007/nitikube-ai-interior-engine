import math

import pytest

from nitikube.calibration import calibrate_scale, pixel_distance, pixel_polygon_area_ft2, scale_from_reference
from nitikube.drawing import room_lighting_svg


def test_pixel_distance():
    assert pixel_distance((0, 0), (3, 4)) == 5


def test_single_reference_scale():
    scale = scale_from_reference(100, 10)
    assert math.isclose(scale, 0.1)


def test_consistent_multi_reference_calibration():
    calibration = calibrate_scale([(100, 10), (250, 25), (500, 50)])
    assert math.isclose(calibration.feet_per_pixel, 0.1)
    assert math.isclose(calibration.pixels_per_foot, 10.0)
    assert calibration.relative_spread == 0.0
    assert calibration.reference_count == 3


def test_inconsistent_references_expose_spread():
    calibration = calibrate_scale([(100, 10), (100, 12)])
    assert calibration.relative_spread > 0.08


def test_pixel_polygon_area_converts_scale_squared():
    # 100 px × 50 px at 0.1 ft/px -> 10 ft × 5 ft -> 50 ft².
    area = pixel_polygon_area_ft2([(0, 0), (100, 0), (100, 50), (0, 50)], 0.1)
    assert math.isclose(area, 50.0)


def test_invalid_reference_rejected():
    with pytest.raises(ValueError):
        scale_from_reference(0, 10)


def test_svg_contains_exact_fixture_count():
    svg = room_lighting_svg(
        room_name="Drawing / Dining",
        length_ft=22.75,
        width_ft=10 + 7/12,
        rows=3,
        cols=4,
        beam_diameter_ft=4.22,
    )
    assert svg.startswith("<svg")
    assert svg.count('<circle class="fixture"') == 12
    assert svg.count('<circle class="beam"') == 12
    assert "Drawing / Dining" in svg
