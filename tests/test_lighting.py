import math

from nitikube.geometry import feet_inches, ft2_to_m2
from nitikube.lighting import beam_diameter, estimated_maintained_lux, installed_lumens_required


def test_36_degree_beam_at_6_5ft_workplane_distance():
    actual = beam_diameter(6.5, 36)
    expected = 2 * 6.5 * math.tan(math.radians(18))
    assert math.isclose(actual, expected, rel_tol=1e-12)
    assert 4.20 < actual < 4.25


def test_lumen_method_current_room():
    area_ft2 = feet_inches(22, 9) * feet_inches(10, 7)
    area_m2 = ft2_to_m2(area_ft2)
    required = installed_lumens_required(area_m2, 160, 0.65, 0.80)
    assert 6800 < required < 6900


def test_12_500_lumen_cobs_maintained_lux():
    area_m2 = ft2_to_m2(feet_inches(22, 9) * feet_inches(10, 7))
    lux = estimated_maintained_lux(area_m2, 12, 500, 0.65, 0.80)
    assert 139 < lux < 140
