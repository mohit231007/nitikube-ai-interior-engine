from __future__ import annotations

from dataclasses import dataclass
from html import escape
from typing import Iterable

from .geometry import grid_positions


@dataclass(frozen=True)
class SvgFurniture:
    label: str
    x_ft: float
    y_ft: float
    width_ft: float
    length_ft: float


def room_lighting_svg(
    *,
    room_name: str,
    length_ft: float,
    width_ft: float,
    rows: int,
    cols: int,
    beam_diameter_ft: float | None = None,
    furniture: Iterable[SvgFurniture] = (),
    pixels_per_foot: float = 32.0,
    margin_px: float = 70.0,
) -> str:
    """Create a dependency-free, downloadable SVG top view.

    SVG is a drawing/export layer only; all geometry comes from deterministic
    room/grid calculations.
    """
    if min(length_ft, width_ft, pixels_per_foot) <= 0:
        raise ValueError("room dimensions and scale must be positive")
    if rows < 1 or cols < 1:
        raise ValueError("rows and cols must be >= 1")

    room_w_px = width_ft * pixels_per_foot
    room_h_px = length_ft * pixels_per_foot
    canvas_w = room_w_px + margin_px * 2 + 260
    canvas_h = room_h_px + margin_px * 2
    x0 = margin_px
    y0 = margin_px

    def sx(x_ft: float) -> float:
        return x0 + x_ft * pixels_per_foot

    def sy(y_ft: float) -> float:
        return y0 + y_ft * pixels_per_foot

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{canvas_w:.0f}" height="{canvas_h:.0f}" viewBox="0 0 {canvas_w:.0f} {canvas_h:.0f}">',
        '<rect width="100%" height="100%" fill="white"/>',
        '<style>text{font-family:Arial,sans-serif;fill:#1c1c1c}.dim{font-size:13px}.title{font-size:20px;font-weight:700}.note{font-size:14px}.wall{stroke:#222;stroke-width:5;fill:none}.guide{stroke:#999;stroke-width:1;stroke-dasharray:5 5}.fixture{fill:#f6bf26;stroke:#6b5200;stroke-width:1.5}.beam{fill:none;stroke:#d79b00;stroke-width:1;stroke-dasharray:4 4;opacity:.55}.furniture{fill:#f3f3f3;stroke:#555;stroke-width:1.5}</style>',
        f'<text class="title" x="{x0 + room_w_px + 35:.1f}" y="{y0 + 30:.1f}">{escape(room_name)}</text>',
        f'<text class="note" x="{x0 + room_w_px + 35:.1f}" y="{y0 + 58:.1f}">{width_ft:.2f} ft × {length_ft:.2f} ft</text>',
        f'<text class="note" x="{x0 + room_w_px + 35:.1f}" y="{y0 + 82:.1f}">{rows} × {cols} lighting grid</text>',
        f'<rect class="wall" x="{x0:.1f}" y="{y0:.1f}" width="{room_w_px:.1f}" height="{room_h_px:.1f}"/>',
    ]

    # Grid guides and fixture/beam symbols.
    points = grid_positions(length_ft, width_ft, rows, cols)
    beam_r_px = None if beam_diameter_ft is None else beam_diameter_ft * pixels_per_foot / 2
    for index, (x_ft, y_ft) in enumerate(points, start=1):
        x, y = sx(x_ft), sy(y_ft)
        parts.append(f'<line class="guide" x1="{x:.1f}" y1="{y0:.1f}" x2="{x:.1f}" y2="{y0 + room_h_px:.1f}"/>')
        parts.append(f'<line class="guide" x1="{x0:.1f}" y1="{y:.1f}" x2="{x0 + room_w_px:.1f}" y2="{y:.1f}"/>')
        if beam_r_px:
            parts.append(f'<circle class="beam" cx="{x:.1f}" cy="{y:.1f}" r="{beam_r_px:.1f}"/>')
        parts.append(f'<circle class="fixture" cx="{x:.1f}" cy="{y:.1f}" r="7"/>')
        parts.append(f'<text class="dim" x="{x + 10:.1f}" y="{y - 10:.1f}">{index}</text>')

    # Furniture is optional and remains simple rectangle geometry in v0.3.
    for item in furniture:
        x, y = sx(item.x_ft), sy(item.y_ft)
        w, h = item.width_ft * pixels_per_foot, item.length_ft * pixels_per_foot
        parts.append(f'<rect class="furniture" x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}"/>')
        parts.append(f'<text class="dim" x="{x + 5:.1f}" y="{y + 18:.1f}">{escape(item.label)}</text>')

    # Dimension lines.
    parts.extend([
        f'<line x1="{x0:.1f}" y1="{y0 - 25:.1f}" x2="{x0 + room_w_px:.1f}" y2="{y0 - 25:.1f}" stroke="#222" stroke-width="1"/>',
        f'<text class="dim" x="{x0 + room_w_px/2 - 30:.1f}" y="{y0 - 34:.1f}">W {width_ft:.2f} ft</text>',
        f'<line x1="{x0 - 25:.1f}" y1="{y0:.1f}" x2="{x0 - 25:.1f}" y2="{y0 + room_h_px:.1f}" stroke="#222" stroke-width="1"/>',
        f'<text class="dim" transform="translate({x0 - 38:.1f},{y0 + room_h_px/2 + 30:.1f}) rotate(-90)">L {length_ft:.2f} ft</text>',
        '</svg>',
    ])
    return "".join(parts)
