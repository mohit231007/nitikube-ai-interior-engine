from __future__ import annotations

from dataclasses import dataclass
from html import escape
import math
from typing import Iterable, Sequence

from .room_layout import KeepoutZone, Rect, circulation_metrics, rect_contains, rect_overlap


_WALLS = ("top", "bottom", "left", "right")
_CORNERS = ("top_left", "top_right", "bottom_left", "bottom_right")


@dataclass(frozen=True)
class FixtureSpec:
    fixture_id: str
    label: str
    width_ft: float
    depth_ft: float
    front_clearance_ft: float = 0.0


@dataclass(frozen=True)
class PlacedFixture:
    spec: FixtureSpec
    wall: str
    rect: Rect


@dataclass(frozen=True)
class ShowerSpec:
    width_ft: float
    depth_ft: float


@dataclass(frozen=True)
class ShowerPlacement:
    corner: str
    rect: Rect
    wall_lengths_ft: tuple[float, float]


@dataclass(frozen=True)
class BathroomCandidate:
    layout_id: str
    name: str
    shower: ShowerPlacement
    wc: PlacedFixture
    basin: PlacedFixture
    wc_front_zone: Rect | None
    basin_front_zone: Rect | None

    @property
    def physical_rects(self) -> tuple[Rect, ...]:
        return self.shower.rect, self.wc.rect, self.basin.rect


@dataclass(frozen=True)
class BathroomRequirements:
    passage_width_ft: float = 0.0
    grid_step_ft: float = 0.20
    require_connected_passage: bool = True
    require_fixture_front_clearance_inside_room: bool = True


@dataclass(frozen=True)
class BathroomEvaluation:
    layout_id: str
    feasible: bool
    failed: tuple[str, ...]
    warnings: tuple[str, ...]
    occupied_area_ft2: float
    open_area_ratio: float
    circulation_connectivity: float | None
    circulation_walkable_ratio: float | None
    geometry_score: float


@dataclass(frozen=True)
class BathroomQuantitySummary:
    floor_area_ft2: float
    floor_purchase_area_ft2: float
    gross_wall_tile_area_ft2: float
    net_wall_tile_area_ft2: float
    wet_wall_waterproof_area_ft2: float
    floor_waterproof_area_ft2: float
    total_waterproof_area_ft2: float
    required_exhaust_cfm: float | None
    drainage_fall_in: float | None


def _validate_fixture(spec: FixtureSpec) -> None:
    if not spec.fixture_id.strip() or not spec.label.strip():
        raise ValueError("fixture id and label are required")
    if spec.width_ft <= 0 or spec.depth_ft <= 0:
        raise ValueError(f"{spec.fixture_id}: dimensions must be positive")
    if spec.front_clearance_ft < 0:
        raise ValueError(f"{spec.fixture_id}: front clearance cannot be negative")


def _center_wall_rect(room: Rect, wall: str, width_along_wall_ft: float, depth_ft: float, margin_ft: float = 0.0) -> Rect:
    if wall not in _WALLS:
        raise ValueError("invalid wall")
    if margin_ft < 0:
        raise ValueError("margin cannot be negative")
    if wall in {"top", "bottom"}:
        if width_along_wall_ft > room.width_ft + 1e-8 or depth_ft + margin_ft > room.depth_ft + 1e-8:
            raise ValueError("fixture does not fit wall")
        x = room.x_ft + (room.width_ft - width_along_wall_ft) / 2
        y = room.y_ft + margin_ft if wall == "top" else room.bottom_ft - margin_ft - depth_ft
        return Rect(x, y, width_along_wall_ft, depth_ft)
    if width_along_wall_ft > room.depth_ft + 1e-8 or depth_ft + margin_ft > room.width_ft + 1e-8:
        raise ValueError("fixture does not fit wall")
    y = room.y_ft + (room.depth_ft - width_along_wall_ft) / 2
    x = room.x_ft + margin_ft if wall == "left" else room.right_ft - margin_ft - depth_ft
    return Rect(x, y, depth_ft, width_along_wall_ft)


def place_fixture(room: Rect, wall: str, spec: FixtureSpec, *, margin_ft: float = 0.0) -> PlacedFixture:
    _validate_fixture(spec)
    return PlacedFixture(spec, wall, _center_wall_rect(room, wall, spec.width_ft, spec.depth_ft, margin_ft))


def fixture_front_zone(fixture: PlacedFixture) -> Rect | None:
    clearance = fixture.spec.front_clearance_ft
    if clearance == 0:
        return None
    r = fixture.rect
    if fixture.wall == "top":
        return Rect(r.x_ft, r.bottom_ft, r.width_ft, clearance)
    if fixture.wall == "bottom":
        return Rect(r.x_ft, r.y_ft - clearance, r.width_ft, clearance)
    if fixture.wall == "left":
        return Rect(r.right_ft, r.y_ft, clearance, r.depth_ft)
    return Rect(r.x_ft - clearance, r.y_ft, clearance, r.depth_ft)


def place_shower(room: Rect, corner: str, spec: ShowerSpec, *, margin_ft: float = 0.0) -> ShowerPlacement:
    if corner not in _CORNERS:
        raise ValueError("invalid shower corner")
    if spec.width_ft <= 0 or spec.depth_ft <= 0 or margin_ft < 0:
        raise ValueError("invalid shower dimensions/margin")
    if spec.width_ft + margin_ft > room.width_ft or spec.depth_ft + margin_ft > room.depth_ft:
        raise ValueError("shower does not fit room")
    if corner == "top_left":
        rect = Rect(room.x_ft + margin_ft, room.y_ft + margin_ft, spec.width_ft, spec.depth_ft)
    elif corner == "top_right":
        rect = Rect(room.right_ft - margin_ft - spec.width_ft, room.y_ft + margin_ft, spec.width_ft, spec.depth_ft)
    elif corner == "bottom_left":
        rect = Rect(room.x_ft + margin_ft, room.bottom_ft - margin_ft - spec.depth_ft, spec.width_ft, spec.depth_ft)
    else:
        rect = Rect(room.right_ft - margin_ft - spec.width_ft, room.bottom_ft - margin_ft - spec.depth_ft, spec.width_ft, spec.depth_ft)
    return ShowerPlacement(corner, rect, (spec.width_ft, spec.depth_ft))


def generate_bathroom_candidates(
    room: Rect,
    *,
    shower: ShowerSpec,
    wc: FixtureSpec,
    basin: FixtureSpec,
    wall_margin_ft: float = 0.0,
) -> tuple[BathroomCandidate, ...]:
    _validate_fixture(wc)
    _validate_fixture(basin)
    candidates: list[BathroomCandidate] = []
    serial = 1
    for corner in _CORNERS:
        try:
            shower_p = place_shower(room, corner, shower, margin_ft=wall_margin_ft)
        except ValueError:
            continue
        for wc_wall in _WALLS:
            try:
                wc_p = place_fixture(room, wc_wall, wc, margin_ft=wall_margin_ft)
            except ValueError:
                continue
            for basin_wall in _WALLS:
                if basin_wall == wc_wall:
                    continue
                try:
                    basin_p = place_fixture(room, basin_wall, basin, margin_ft=wall_margin_ft)
                except ValueError:
                    continue
                candidates.append(BathroomCandidate(
                    layout_id=f"BA-{serial:03d}",
                    name=f"Shower {corner} · WC {wc_wall} · basin {basin_wall}",
                    shower=shower_p,
                    wc=wc_p,
                    basin=basin_p,
                    wc_front_zone=fixture_front_zone(wc_p),
                    basin_front_zone=fixture_front_zone(basin_p),
                ))
                serial += 1
    return tuple(candidates)


def evaluate_bathroom(
    room: Rect,
    candidate: BathroomCandidate,
    *,
    keepouts: Sequence[KeepoutZone] = (),
    requirements: BathroomRequirements | None = None,
) -> BathroomEvaluation:
    req = requirements or BathroomRequirements()
    if req.passage_width_ft < 0 or req.grid_step_ft <= 0:
        raise ValueError("invalid bathroom requirements")
    failed: list[str] = []
    warnings: list[str] = []
    physical = [
        ("shower", candidate.shower.rect),
        (candidate.wc.spec.fixture_id, candidate.wc.rect),
        (candidate.basin.spec.fixture_id, candidate.basin.rect),
    ]
    for item_id, rect in physical:
        if not rect_contains(room, rect):
            failed.append(f"outside_room:{item_id}")
        for keepout in keepouts:
            if rect_overlap(rect, keepout.rect):
                failed.append(f"keepout_collision:{item_id}:{keepout.zone_id}")
    for i, (id_a, rect_a) in enumerate(physical):
        for id_b, rect_b in physical[i + 1:]:
            if rect_overlap(rect_a, rect_b):
                failed.append(f"fixture_collision:{id_a}:{id_b}")

    zones = [("wc_front", candidate.wc_front_zone), ("basin_front", candidate.basin_front_zone)]
    for zone_id, zone in zones:
        if zone is None:
            continue
        if req.require_fixture_front_clearance_inside_room and not rect_contains(room, zone):
            failed.append(f"clearance_outside_room:{zone_id}")
        for item_id, rect in physical:
            owner = candidate.wc.spec.fixture_id if zone_id == "wc_front" else candidate.basin.spec.fixture_id
            if item_id != owner and rect_overlap(zone, rect):
                failed.append(f"clearance_blocked:{zone_id}:{item_id}")
        for keepout in keepouts:
            if rect_overlap(zone, keepout.rect):
                warnings.append(f"clearance_intersects_opening_keepout:{zone_id}:{keepout.zone_id}")

    connectivity = walkable = None
    if req.passage_width_ft > 0:
        obstacles = [rect for _, rect in physical] + [k.rect for k in keepouts]
        connectivity, walkable = circulation_metrics(
            room,
            obstacles,
            passage_width_ft=req.passage_width_ft,
            grid_step_ft=req.grid_step_ft,
        )
        if req.require_connected_passage and connectivity < 0.95:
            failed.append("passage_not_connected_at_requested_width")
        elif connectivity < 0.95:
            warnings.append("walkable_space_fragmented_at_requested_width")

    occupied = sum(rect.area_ft2 for _, rect in physical)
    open_ratio = max(0.0, 1.0 - occupied / room.area_ft2)
    circulation_component = 1.0 if connectivity is None else connectivity
    separation = min(
        math.dist(candidate.shower.rect.center, candidate.wc.rect.center),
        math.dist(candidate.shower.rect.center, candidate.basin.rect.center),
        math.dist(candidate.wc.rect.center, candidate.basin.rect.center),
    )
    separation_component = min(1.0, separation / max(min(room.width_ft, room.depth_ft) * 0.35, 1e-9))
    score = 100 * (0.45 * open_ratio + 0.35 * circulation_component + 0.20 * separation_component)
    if failed:
        score = min(score, 49.99)
    return BathroomEvaluation(
        layout_id=candidate.layout_id,
        feasible=not failed,
        failed=tuple(dict.fromkeys(failed)),
        warnings=tuple(dict.fromkeys(warnings)),
        occupied_area_ft2=occupied,
        open_area_ratio=open_ratio,
        circulation_connectivity=connectivity,
        circulation_walkable_ratio=walkable,
        geometry_score=round(score, 2),
    )


def rank_bathrooms(
    room: Rect,
    candidates: Iterable[BathroomCandidate],
    *,
    keepouts: Sequence[KeepoutZone] = (),
    requirements: BathroomRequirements | None = None,
) -> list[tuple[BathroomCandidate, BathroomEvaluation]]:
    evaluated = [(c, evaluate_bathroom(room, c, keepouts=keepouts, requirements=requirements)) for c in candidates]
    return sorted(evaluated, key=lambda pair: (pair[1].feasible, pair[1].geometry_score, pair[1].circulation_connectivity or 0.0, pair[1].open_area_ratio), reverse=True)


def required_exhaust_cfm(room_area_ft2: float, ceiling_height_ft: float, air_changes_per_hour: float) -> float:
    if room_area_ft2 <= 0 or ceiling_height_ft <= 0 or air_changes_per_hour <= 0:
        raise ValueError("room area, ceiling height and ACH must be positive")
    volume_ft3 = room_area_ft2 * ceiling_height_ft
    return volume_ft3 * air_changes_per_hour / 60.0


def drainage_fall_inches(run_ft: float, slope_percent: float) -> float:
    if run_ft < 0 or slope_percent < 0:
        raise ValueError("drainage run and slope cannot be negative")
    return run_ft * 12.0 * slope_percent / 100.0


def bathroom_quantities(
    room: Rect,
    candidate: BathroomCandidate,
    *,
    floor_waste_fraction: float,
    wall_tile_height_ft: float,
    wall_opening_deduction_ft2: float = 0.0,
    waterproof_floor_fraction: float = 1.0,
    shower_wet_wall_height_ft: float = 0.0,
    ceiling_height_ft: float | None = None,
    air_changes_per_hour: float | None = None,
    drainage_run_ft: float | None = None,
    drainage_slope_percent: float | None = None,
) -> BathroomQuantitySummary:
    if floor_waste_fraction < 0 or wall_tile_height_ft < 0 or wall_opening_deduction_ft2 < 0:
        raise ValueError("tile quantity inputs cannot be negative")
    if not 0 <= waterproof_floor_fraction <= 1:
        raise ValueError("waterproof_floor_fraction must be in [0,1]")
    if shower_wet_wall_height_ft < 0:
        raise ValueError("shower wet-wall height cannot be negative")
    floor_area = room.area_ft2
    wall_gross = 2 * (room.width_ft + room.depth_ft) * wall_tile_height_ft
    wall_net = max(0.0, wall_gross - wall_opening_deduction_ft2)
    wet_wall = sum(candidate.shower.wall_lengths_ft) * shower_wet_wall_height_ft
    floor_waterproof = floor_area * waterproof_floor_fraction
    exhaust = None
    if air_changes_per_hour is not None or ceiling_height_ft is not None:
        if air_changes_per_hour is None or ceiling_height_ft is None:
            raise ValueError("both ceiling_height_ft and air_changes_per_hour are required for exhaust airflow")
        exhaust = required_exhaust_cfm(floor_area, ceiling_height_ft, air_changes_per_hour)
    fall = None
    if drainage_run_ft is not None or drainage_slope_percent is not None:
        if drainage_run_ft is None or drainage_slope_percent is None:
            raise ValueError("both drainage_run_ft and drainage_slope_percent are required")
        fall = drainage_fall_inches(drainage_run_ft, drainage_slope_percent)
    return BathroomQuantitySummary(
        floor_area_ft2=floor_area,
        floor_purchase_area_ft2=floor_area * (1 + floor_waste_fraction),
        gross_wall_tile_area_ft2=wall_gross,
        net_wall_tile_area_ft2=wall_net,
        wet_wall_waterproof_area_ft2=wet_wall,
        floor_waterproof_area_ft2=floor_waterproof,
        total_waterproof_area_ft2=wet_wall + floor_waterproof,
        required_exhaust_cfm=exhaust,
        drainage_fall_in=fall,
    )


def bathroom_svg(
    room: Rect,
    candidate: BathroomCandidate,
    evaluation: BathroomEvaluation | None = None,
    *,
    keepouts: Sequence[KeepoutZone] = (),
    pixels_per_foot: float = 42.0,
    margin_px: float = 55.0,
) -> str:
    room_w, room_h = room.width_ft * pixels_per_foot, room.depth_ft * pixels_per_foot
    width, height = room_w + 2 * margin_px + 350, max(room_h + 2 * margin_px, 520)
    x0 = y0 = margin_px
    sx = lambda x: x0 + (x - room.x_ft) * pixels_per_foot
    sy = lambda y: y0 + (y - room.y_ft) * pixels_per_foot
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width:.0f}" height="{height:.0f}" viewBox="0 0 {width:.0f} {height:.0f}">',
        '<rect width="100%" height="100%" fill="#fff"/>',
        '<style>text{font-family:Arial,sans-serif;fill:#17202a}.wall{fill:#fff;stroke:#1f2937;stroke-width:4}.shower{fill:#dbeafe;stroke:#2563eb;stroke-width:2}.wc{fill:#f1f5f9;stroke:#475569;stroke-width:2}.basin{fill:#dcfce7;stroke:#16a34a;stroke-width:2}.keepout{fill:#fef3c7;stroke:#d97706;stroke-width:1.5;stroke-dasharray:4 3}.clearance{fill:none;stroke:#64748b;stroke-width:1.2;stroke-dasharray:5 4}.label{font-size:11px}.title{font-size:18px;font-weight:700}.note{font-size:12px}</style>',
        f'<rect class="wall" x="{x0}" y="{y0}" width="{room_w:.1f}" height="{room_h:.1f}"/>',
    ]
    for zone in keepouts:
        r = zone.rect
        parts.append(f'<rect class="keepout" x="{sx(r.x_ft):.1f}" y="{sy(r.y_ft):.1f}" width="{r.width_ft*pixels_per_foot:.1f}" height="{r.depth_ft*pixels_per_foot:.1f}"/>')
    for zone in (candidate.wc_front_zone, candidate.basin_front_zone):
        if zone is not None:
            parts.append(f'<rect class="clearance" x="{sx(zone.x_ft):.1f}" y="{sy(zone.y_ft):.1f}" width="{zone.width_ft*pixels_per_foot:.1f}" height="{zone.depth_ft*pixels_per_foot:.1f}"/>')
    items = (("shower", "Shower", candidate.shower.rect), ("wc", candidate.wc.spec.label, candidate.wc.rect), ("basin", candidate.basin.spec.label, candidate.basin.rect))
    for css, label, r in items:
        parts.append(f'<rect class="{css}" x="{sx(r.x_ft):.1f}" y="{sy(r.y_ft):.1f}" width="{r.width_ft*pixels_per_foot:.1f}" height="{r.depth_ft*pixels_per_foot:.1f}"/>')
        cx, cy = r.center
        parts.append(f'<text class="label" x="{sx(cx):.1f}" y="{sy(cy):.1f}" text-anchor="middle">{escape(label)}</text>')
    panel_x = x0 + room_w + 30
    parts.append(f'<text class="title" x="{panel_x:.1f}" y="{y0+24:.1f}">{escape(candidate.name)}</text>')
    if evaluation:
        lines = [
            f"Status: {'FEASIBLE' if evaluation.feasible else 'NOT FEASIBLE'}",
            f"Geometry score: {evaluation.geometry_score:.1f}/100",
            f"Open area: {evaluation.open_area_ratio:.1%}",
        ]
        if evaluation.circulation_connectivity is not None:
            lines.append(f"Walkable connectivity: {evaluation.circulation_connectivity:.1%}")
        y = y0 + 54
        for line in lines:
            parts.append(f'<text class="note" x="{panel_x:.1f}" y="{y:.1f}">{escape(line)}</text>')
            y += 20
        y += 8
        for failure in evaluation.failed[:8]:
            parts.append(f'<text class="note" x="{panel_x:.1f}" y="{y:.1f}">• {escape(failure)}</text>')
            y += 18
    parts.append('</svg>')
    return ''.join(parts)


def evaluation_rows(ranked: Sequence[tuple[BathroomCandidate, BathroomEvaluation]]) -> list[dict]:
    return [{
        "layout_id": c.layout_id,
        "name": c.name,
        "shower_corner": c.shower.corner,
        "wc_wall": c.wc.wall,
        "basin_wall": c.basin.wall,
        "feasible": e.feasible,
        "geometry_score": e.geometry_score,
        "open_area_ratio": e.open_area_ratio,
        "circulation_connectivity": e.circulation_connectivity,
        "walkable_ratio": e.circulation_walkable_ratio,
        "failed": ", ".join(e.failed),
        "warnings": ", ".join(e.warnings),
    } for c, e in ranked]
