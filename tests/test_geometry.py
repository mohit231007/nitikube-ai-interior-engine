import math

from nitikube.geometry import feet_inches, grid_layout, polygon_area, rectangle_area


def test_feet_inches_current_room():
    assert math.isclose(feet_inches(10, 7), 10 + 7/12)
    assert math.isclose(feet_inches(22, 9), 22.75)


def test_rectangle_area_current_room():
    area = rectangle_area(feet_inches(22, 9), feet_inches(10, 7))
    assert math.isclose(area, 240.77083333333331, rel_tol=1e-10)


def test_polygon_area_shoelace():
    assert polygon_area([(0, 0), (4, 0), (4, 3), (0, 3)]) == 12


def test_12_cob_three_by_four_layout():
    layout = grid_layout(feet_inches(22, 9), feet_inches(10, 7), rows=3, cols=4)
    assert layout.fixtures == 12
    assert math.isclose(layout.width_spacing_ft, feet_inches(10, 7) / 3)
    assert math.isclose(layout.length_spacing_ft, 22.75 / 4)
