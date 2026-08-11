import math

from nitikube.materials import material_units, paint_litres


def test_tile_quantity_with_8_percent_waste():
    est = material_units(net_area=180, unit_area=8, waste_fraction=0.08)
    assert math.isclose(est.gross_area, 194.4)
    assert est.units_required == 25


def test_paint_quantity_example():
    est = paint_litres(
        paintable_area_ft2=740,
        coats=2,
        coverage_ft2_per_litre_per_coat=120,
        waste_fraction=0.10,
    )
    assert math.isclose(est.litres_required, 13.566666666666668)
