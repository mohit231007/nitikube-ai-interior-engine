from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np


@dataclass(frozen=True)
class FloorplanVisionResult:
    image_bgr: np.ndarray
    edges: np.ndarray
    line_overlay_bgr: np.ndarray
    line_count: int


def detect_structural_lines(image_bytes: bytes) -> FloorplanVisionResult:
    """Lightweight CV baseline for floor-plan line detection.

    This is deliberately a *proposal* layer, not an authoritative geometry
    extractor. Detected walls/dimensions must be verified by the user before
    engineering calculations use them.
    """
    raw = np.frombuffer(image_bytes, dtype=np.uint8)
    image = cv2.imdecode(raw, cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError("Could not decode uploaded image")

    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    blur = cv2.GaussianBlur(gray, (3, 3), 0)
    edges = cv2.Canny(blur, 50, 150, apertureSize=3)

    min_dim = min(image.shape[:2])
    min_line = max(20, int(min_dim * 0.08))
    lines = cv2.HoughLinesP(
        edges,
        rho=1,
        theta=np.pi / 180,
        threshold=60,
        minLineLength=min_line,
        maxLineGap=10,
    )

    overlay = image.copy()
    count = 0
    if lines is not None:
        for line in lines[:, 0]:
            x1, y1, x2, y2 = map(int, line)
            cv2.line(overlay, (x1, y1), (x2, y2), (0, 140, 255), 2)
            count += 1

    return FloorplanVisionResult(
        image_bgr=image,
        edges=edges,
        line_overlay_bgr=overlay,
        line_count=count,
    )
