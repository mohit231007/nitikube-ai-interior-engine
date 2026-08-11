from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np


@dataclass(frozen=True)
class RegionCandidate:
    candidate_id: int
    x: int
    y: int
    width_px: int
    height_px: int
    area_px: int
    bbox_area_px: int
    rectangularity: float
    area_fraction: float
    heuristic_score: float
    touches_border: bool


@dataclass(frozen=True)
class RegionDetectionResult:
    image_bgr: np.ndarray
    wall_mask: np.ndarray
    free_space_mask: np.ndarray
    overlay_bgr: np.ndarray
    candidates: tuple[RegionCandidate, ...]


def detect_candidate_regions(
    image_bytes: bytes,
    *,
    dark_threshold: int = 200,
    wall_dilation_px: int = 2,
    min_area_fraction: float = 0.01,
    max_area_fraction: float = 0.80,
    min_rectangularity: float = 0.45,
) -> RegionDetectionResult:
    """Propose enclosed/near-enclosed free-space regions in a floor-plan image.

    This is intentionally a heuristic CV proposal stage. It must not be used
    as authoritative room geometry until the user verifies boundaries and a
    physical scale. Door gaps, text, furniture and scanning artifacts can merge
    or split components.
    """
    if not 0 <= dark_threshold <= 255:
        raise ValueError("dark_threshold must be in [0,255]")
    if wall_dilation_px < 0 or wall_dilation_px > 25:
        raise ValueError("wall_dilation_px must be in [0,25]")
    if not 0 < min_area_fraction < max_area_fraction <= 1:
        raise ValueError("invalid area fraction bounds")
    if not 0 <= min_rectangularity <= 1:
        raise ValueError("min_rectangularity must be in [0,1]")

    raw = np.frombuffer(image_bytes, dtype=np.uint8)
    image = cv2.imdecode(raw, cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError("Could not decode floor-plan image")

    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    wall_mask = np.where(gray < dark_threshold, 255, 0).astype(np.uint8)
    if wall_dilation_px > 0:
        kernel_size = wall_dilation_px * 2 + 1
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (kernel_size, kernel_size))
        wall_mask = cv2.dilate(wall_mask, kernel, iterations=1)

    free_space = cv2.bitwise_not(wall_mask)
    n_labels, labels, stats, _ = cv2.connectedComponentsWithStats(free_space, connectivity=8)
    image_area = image.shape[0] * image.shape[1]
    candidates: list[RegionCandidate] = []

    for label in range(1, n_labels):
        x = int(stats[label, cv2.CC_STAT_LEFT])
        y = int(stats[label, cv2.CC_STAT_TOP])
        w = int(stats[label, cv2.CC_STAT_WIDTH])
        h = int(stats[label, cv2.CC_STAT_HEIGHT])
        area = int(stats[label, cv2.CC_STAT_AREA])
        bbox_area = max(w * h, 1)
        area_fraction = area / image_area
        rectangularity = area / bbox_area
        touches = x <= 0 or y <= 0 or x + w >= image.shape[1] or y + h >= image.shape[0]

        if touches:
            continue
        if not (min_area_fraction <= area_fraction <= max_area_fraction):
            continue
        if rectangularity < min_rectangularity:
            continue

        # Heuristic, not calibrated probability. Favors sizeable, reasonably
        # rectangular enclosed areas while keeping the score interpretable.
        size_score = min(area_fraction / max(min_area_fraction * 4, 1e-12), 1.0)
        shape_score = rectangularity
        heuristic = 100.0 * (0.55 * shape_score + 0.45 * size_score)
        candidates.append(
            RegionCandidate(
                candidate_id=len(candidates) + 1,
                x=x,
                y=y,
                width_px=w,
                height_px=h,
                area_px=area,
                bbox_area_px=bbox_area,
                rectangularity=rectangularity,
                area_fraction=area_fraction,
                heuristic_score=heuristic,
                touches_border=touches,
            )
        )

    candidates.sort(key=lambda c: c.area_px, reverse=True)
    candidates = [
        RegionCandidate(
            candidate_id=i + 1,
            x=c.x,
            y=c.y,
            width_px=c.width_px,
            height_px=c.height_px,
            area_px=c.area_px,
            bbox_area_px=c.bbox_area_px,
            rectangularity=c.rectangularity,
            area_fraction=c.area_fraction,
            heuristic_score=c.heuristic_score,
            touches_border=c.touches_border,
        )
        for i, c in enumerate(candidates)
    ]

    overlay = image.copy()
    for candidate in candidates:
        p1 = (candidate.x, candidate.y)
        p2 = (candidate.x + candidate.width_px, candidate.y + candidate.height_px)
        cv2.rectangle(overlay, p1, p2, (0, 140, 255), 2)
        cv2.putText(
            overlay,
            f"R{candidate.candidate_id} {candidate.heuristic_score:.0f}",
            (candidate.x + 4, max(candidate.y - 6, 12)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.45,
            (0, 90, 200),
            1,
            cv2.LINE_AA,
        )

    return RegionDetectionResult(
        image_bgr=image,
        wall_mask=wall_mask,
        free_space_mask=free_space,
        overlay_bgr=overlay,
        candidates=tuple(candidates),
    )


def candidate_dimensions_ft(candidate: RegionCandidate, feet_per_pixel: float) -> tuple[float, float, float]:
    if feet_per_pixel <= 0:
        raise ValueError("feet_per_pixel must be positive")
    width_ft = candidate.width_px * feet_per_pixel
    height_ft = candidate.height_px * feet_per_pixel
    component_area_ft2 = candidate.area_px * feet_per_pixel**2
    return width_ft, height_ft, component_area_ft2
