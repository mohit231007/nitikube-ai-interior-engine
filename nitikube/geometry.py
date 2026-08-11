from __future__ import annotations

from dataclasses import dataclass
from math import ceil
from typing import Iterable, Sequence

FT2_TO_M2 = 0.09290304
M2_TO_FT2 = 1 / FT2_TO_M2


def feet_inches(feet: float = 0, inches: float = 0) -> float:
    """Convert feet + inches to decimal feet."""
    if inches < 0:
        raise ValueError("inches must be non-negative")
    return float(feet) + float(inches) / 12.0


def ft2_to_m2(area_ft2: float) -> float:
    return float(area_ft2) * FT2_TO_M2


def m2_to_ft2(area_m2: float) -> float:
    return float(area_m2) * M2_TO_FT2


def rectangle_area(length_ft: float, width_ft: float) -> float:
    if length_ft <= 0 or width_ft <= 0:
        raise ValueError("room dimensions must be positive")
    return float(length_ft) * float(width_ft)


def polygon_area(points: Sequence[tuple[float, float]]) -> float:
    """Shoelace-area calculation for an arbitrary simple polygon."""
    if len(points) < 3:
        raise ValueError("at least three polygon points are required")
    total = 0.0
    for i, (x1, y1) in enumerate(points):
        x2, y2 = points[(i + 1) % len(points)]
        total += x1 * y2 - x2 * y1
    return abs(total) / 2.0


def grid_positions(length_ft: float, width_ft: float, rows: int, cols: int) -> list[tuple[float, float]]:
    """Return evenly distributed fixture centres with half-cell wall offsets.

    Coordinates are (x across width, y along length), measured from one corner.
    """
    if rows < 1 or cols < 1:
        raise ValueError("rows and cols must be >= 1")
    x_step = width_ft / rows
    y_step = length_ft / cols
    return [
        ((r + 0.5) * x_step, (c + 0.5) * y_step)
        for c in range(cols)
        for r in range(rows)
    ]


@dataclass(frozen=True)
class GridLayout:
    rows: int
    cols: int
    width_spacing_ft: float
    length_spacing_ft: float
    side_offset_ft: float
    end_offset_ft: float

    @property
    def fixtures(self) -> int:
        return self.rows * self.cols


def grid_layout(length_ft: float, width_ft: float, rows: int, cols: int) -> GridLayout:
    if min(length_ft, width_ft) <= 0:
        raise ValueError("room dimensions must be positive")
    if rows < 1 or cols < 1:
        raise ValueError("rows and cols must be >= 1")
    return GridLayout(
        rows=rows,
        cols=cols,
        width_spacing_ft=width_ft / rows,
        length_spacing_ft=length_ft / cols,
        side_offset_ft=width_ft / (2 * rows),
        end_offset_ft=length_ft / (2 * cols),
    )


def factor_grids(n: int) -> list[tuple[int, int]]:
    """All row/column integer layouts whose product is n."""
    if n < 1:
        raise ValueError("n must be >= 1")
    out: list[tuple[int, int]] = []
    for rows in range(1, int(n**0.5) + 1):
        if n % rows == 0:
            cols = n // rows
            out.extend([(rows, cols)] if rows == cols else [(rows, cols), (cols, rows)])
    return out


def choose_grid(length_ft: float, width_ft: float, fixtures: int, preferred_rows: int | None = None) -> GridLayout:
    """Choose a practical factor-grid for a rectangular room.

    If preferred_rows is valid, use it. Otherwise minimise anisotropy between
    normalized row/column spacing while lightly favouring more columns along
    the room's longer axis.
    """
    grids = factor_grids(fixtures)
    if preferred_rows and fixtures % preferred_rows == 0:
        return grid_layout(length_ft, width_ft, preferred_rows, fixtures // preferred_rows)

    aspect = length_ft / width_ft
    best = min(
        grids,
        key=lambda rc: abs((rc[1] / rc[0]) - aspect),
    )
    return grid_layout(length_ft, width_ft, best[0], best[1])
