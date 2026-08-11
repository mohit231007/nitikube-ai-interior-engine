import math

import cv2
import numpy as np

from nitikube.floorplan_regions import candidate_dimensions_ft, detect_candidate_regions


def synthetic_two_room_plan() -> bytes:
    image = np.full((300, 400, 3), 255, dtype=np.uint8)
    cv2.rectangle(image, (20, 20), (380, 280), (0, 0, 0), 5)
    cv2.line(image, (200, 20), (200, 280), (0, 0, 0), 5)
    ok, encoded = cv2.imencode(".png", image)
    assert ok
    return encoded.tobytes()


def test_detects_two_enclosed_candidate_regions_on_clean_plan():
    result = detect_candidate_regions(
        synthetic_two_room_plan(),
        dark_threshold=200,
        wall_dilation_px=1,
        min_area_fraction=0.05,
        max_area_fraction=0.60,
        min_rectangularity=0.90,
    )
    assert len(result.candidates) == 2
    assert all(candidate.rectangularity > 0.98 for candidate in result.candidates)
    assert all(candidate.touches_border is False for candidate in result.candidates)


def test_candidate_dimensions_use_verified_scale():
    result = detect_candidate_regions(
        synthetic_two_room_plan(),
        wall_dilation_px=1,
        min_area_fraction=0.05,
        max_area_fraction=0.60,
        min_rectangularity=0.90,
    )
    candidate = result.candidates[0]
    width_ft, height_ft, area_ft2 = candidate_dimensions_ft(candidate, 0.1)
    assert math.isclose(width_ft, candidate.width_px * 0.1)
    assert math.isclose(height_ft, candidate.height_px * 0.1)
    assert math.isclose(area_ft2, candidate.area_px * 0.01)


def test_exterior_background_is_not_returned_as_room():
    result = detect_candidate_regions(
        synthetic_two_room_plan(),
        wall_dilation_px=0,
        min_area_fraction=0.01,
        max_area_fraction=0.95,
        min_rectangularity=0.40,
    )
    assert all(not candidate.touches_border for candidate in result.candidates)
