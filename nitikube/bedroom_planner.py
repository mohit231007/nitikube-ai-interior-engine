from __future__ import annotations

from dataclasses import dataclass
from html import escape
import math
from typing import Iterable, Sequence

from .room_layout import KeepoutZone, Rect, circulation_metrics, rect_contains, rect_overlap


_WALLS = ("top", "bottom", "left", "right")
_OPPOSITE = {"top": "bottom", "bottom": "top", "left": "right", "right": "left"}


@dataclass(frozen=True)
class BedSpec:
    width_ft: float
    length_ft: float


@dataclass(frozen=True)
class WardrobeSpec:
    run_ft: float
    depth_ft: float
    height_ft: float


@dataclass(frozen=True)
class DeskSpec:
    width_ft: float
    depth_ft: float


@dataclass(frozen=True)
class WallPlacement:
    item_id: str
    label: str
    wall: str
    rect: Rect


@dataclass(frozen=True)
class BedroomCandidate:
    layout_id: str
    name: str
    bed: WallPlacement
    wardrobe: WallPlacement
    desk: WallPlacement | None
    bed_clearance_zones: tuple[Rect, ...]
    wardrobe_front_zone: Rect | None
    notes: tuple[str, ...] = ()

    @property
    def furniture(self) -> tuple[WallPlacement, ...]:
        return (self.bed, self.wardrobe) + ((self.desk,) if self.desk is not None else ())


@dataclass(frozen=True)
class BedroomRequirements:
    side_clearance_ft: float = 0.0
    foot_clearance_ft: float = 0.0
    wardrobe_front_clearance_ft: float = 0.0
    passage_width_ft: float = 0.0
    grid_step_ft: float = 0.25
    require_connected_passage: bool = True


@dataclass(frozen=True)
class BedroomEvaluation:
    layout_id: str
    feasible: bool
    failed: tuple[str, ...]
    warnings: tuple[str, ...]
    furniture_area_ft2: float
    open_area_ratio: float
    bed_to_wardrobe_center_ft: float
    circulation_connectivity: float | None
    circulation_walkable_ratio: float | None
    wardrobe_run_ft: float
    wardrobe_front_area_ft2: float
    wardrobe_internal_volume_ft3: float
    geometry_score: float


def _validate_bed(spec: BedSpec) -> None:
    if spec.width_ft <= 0 or spec.length_ft <= 0:
        raise ValueError("bed dimensions must be positive")


def _validate_wardrobe(spec: WardrobeSpec) -> None:
    if spec.run_ft <= 0 or spec.depth_ft <= 0 or spec.height_ft <= 0:
        raise ValueError("wardrobe dimensions must be positive")


def _validate_desk(spec: DeskSpec | None) -> None:
    if spec is not None and (spec.width_ft <= 0 or spec.depth_ft <= 0):
        raise ValueError("desk dimensions must be positive")


def _center_along_wall(room: Rect, wall: str, along_ft: float, depth_ft: float, wall_margin_ft: float) -> Rect:
    if wall not in _WALLS:
        raise ValueError("invalid wall")
    if wall_margin_ft < 0:
        raise ValueError("wall margin cannot be negative")
    if wall in {"top", "bottom"}:
        if along_ft > room.width_ft + 1e-8 or depth_ft + wall_margin_ft > room.depth_ft + 1e-8:
            raise ValueError("item does not fit on requested wall")
        x = room.x_ft + (room.width_ft - along_ft) / 2
        y = room.y_ft + wall_margin_ft if wall == "top" else room.bottom_ft - wall_margin_ft - depth_ft
        return Rect(x, y, along_ft, depth_ft)
    if along_ft > room.depth_ft + 1e-8 or depth_ft + wall_margin_ft > room.width_ft + 1e-8:
        raise ValueError("item does not fit on requested wall")
    y = room.y_ft + (room.depth_ft - along_ft) / 2
    x = room.x_ft + wall_margin_ft if wall == "left" else room.right_ft - wall_margin_ft - depth_ft
    return Rect(x, y, depth_ft, along_ft)


def bed_placement(room: Rect, wall: str, spec: BedSpec, *, wall_margin_ft: float = 0.0) -> WallPlacement:
    _validate_bed(spec)
    rect = _center_along_wall(room, wall, spec.width_ft, spec.length_ft, wall_margin_ft)
    return WallPlacement("bed", "Bed", wall, rect)


def wardrobe_placement(room: Rect, wall: str, spec: WardrobeSpec, *, wall_margin_ft: float = 0.0) -> WallPlacement:
    _validate_wardrobe(spec)
    rect = _center_along_wall(room, wall, spec.run_ft, spec.depth_ft, wall_margin_ft)
    return WallPlacement("wardrobe", "Wardrobe", wall, rect)


def desk_placement(room: Rect, wall: str, spec: DeskSpec, *, wall_margin_ft: float = 0.0) -> WallPlacement:
    _validate_desk(spec)
    rect = _center_along_wall(room, wall, spec.width_ft, spec.depth_ft, wall_margin_ft)
    return WallPlacement("desk", "Desk", wall, rect)


def _clip_or_none(room: Rect, rect: Rect) -> Rect | None:
    x = max(room.x_ft, rect.x_ft)
    y = max(room.y_ft, rect.y_ft)
    right = min(room.right_ft, rect.right_ft)
    bottom = min(room.bottom_ft, rect.bottom_ft)
    if right - x <= 1e-9 or bottom - y <= 1e-9:
        return None
    return Rect(x, y, right - x, bottom - y)


def bed_clearance_zones(room: Rect, bed: WallPlacement, *, side_clearance_ft: float, foot_clearance_ft: float) -> tuple[Rect, ...]:
    if side_clearance_ft < 0 or foot_clearance_ft < 0:
        raise ValueError("bed clearances cannot be negative")
    r = bed.rect
    zones: list[Rect] = []
    if bed.wall in {"top", "bottom"}:
        if side_clearance_ft > 0:
            zones += [Rect(r.x_ft - side_clearance_ft, r.y_ft, side_clearance_ft, r.depth_ft), Rect(r.right_ft, r.y_ft, side_clearance_ft, r.depth_ft)]
        if foot_clearance_ft > 0:
            y = r.bottom_ft if bed.wall == "top" else r.y_ft - foot_clearance_ft
            zones.append(Rect(r.x_ft, y, r.width_ft, foot_clearance_ft))
    else:
        if side_clearance_ft > 0:
            zones += [Rect(r.x_ft, r.y_ft - side_clearance_ft, r.width_ft, side_clearance_ft), Rect(r.x_ft, r.bottom_ft, r.width_ft, side_clearance_ft)]
        if foot_clearance_ft > 0:
            x = r.right_ft if bed.wall == "left" else r.x_ft - foot_clearance_ft
            zones.append(Rect(x, r.y_ft, foot_clearance_ft, r.depth_ft))
    # Preserve full requested zones, including any part outside the room; the
    # evaluator then fails them rather than silently clipping away missing clearance.
    return tuple(zones)


def wardrobe_front_zone(room: Rect, wardrobe: WallPlacement, *, clearance_ft: float) -> Rect | None:
    if clearance_ft < 0:
        raise ValueError("wardrobe-front clearance cannot be negative")
    if clearance_ft == 0:
        return None
    r = wardrobe.rect
    if wardrobe.wall == "top":
        return Rect(r.x_ft, r.bottom_ft, r.width_ft, clearance_ft)
    if wardrobe.wall == "bottom":
        return Rect(r.x_ft, r.y_ft - clearance_ft, r.width_ft, clearance_ft)
    if wardrobe.wall == "left":
        return Rect(r.right_ft, r.y_ft, clearance_ft, r.depth_ft)
    return Rect(r.x_ft - clearance_ft, r.y_ft, clearance_ft, r.depth_ft)


def generate_bedroom_candidates(
    room: Rect,
    *,
    bed: BedSpec,
    wardrobe: WardrobeSpec,
    desk: DeskSpec | None = None,
    wall_margin_ft: float = 0.0,
    side_clearance_ft: float = 0.0,
    foot_clearance_ft: float = 0.0,
    wardrobe_front_clearance_ft: float = 0.0,
) -> tuple[BedroomCandidate, ...]:
    _validate_bed(bed)
    _validate_wardrobe(wardrobe)
    _validate_desk(desk)
    if wall_margin_ft < 0:
        raise ValueError("wall margin cannot be negative")
    candidates: list[BedroomCandidate] = []
    serial = 1
    for bed_wall in _WALLS:
        try:
            bed_p = bed_placement(room, bed_wall, bed, wall_margin_ft=wall_margin_ft)
        except ValueError:
            continue
        wardrobe_walls = [_OPPOSITE[bed_wall]] + [wall for wall in _WALLS if wall not in {bed_wall, _OPPOSITE[bed_wall]}]
        for wardrobe_wall in wardrobe_walls:
            try:
                wardrobe_p = wardrobe_placement(room, wardrobe_wall, wardrobe, wall_margin_ft=wall_margin_ft)
            except ValueError:
                continue
            desk_walls: list[str | None]
            if desk is None:
                desk_walls = [None]
            else:
                desk_walls = [wall for wall in _WALLS if wall not in {bed_wall, wardrobe_wall}]
            for desk_wall in desk_walls:
                try:
                    desk_p = desk_placement(room, desk_wall, desk, wall_margin_ft=wall_margin_ft) if desk is not None and desk_wall else None
                except ValueError:
                    continue
                candidates.append(BedroomCandidate(
                    layout_id=f"B-{serial:02d}",
                    name=f"Bed {bed_wall} · wardrobe {wardrobe_wall}" + (f" · desk {desk_wall}" if desk_wall else ""),
                    bed=bed_p,
                    wardrobe=wardrobe_p,
                    desk=desk_p,
                    bed_clearance_zones=bed_clearance_zones(room, bed_p, side_clearance_ft=side_clearance_ft, foot_clearance_ft=foot_clearance_ft),
                    wardrobe_front_zone=wardrobe_front_zone(room, wardrobe_p, clearance_ft=wardrobe_front_clearance_ft),
                    notes=("Generated from explicit rectangular furniture geometry.", "Clearances are scenario inputs, not hidden standards."),
                ))
                serial += 1
    return tuple(candidates)


def evaluate_bedroom(
    room: Rect,
    candidate: BedroomCandidate,
    wardrobe_spec: WardrobeSpec,
    *,
    keepouts: Sequence[KeepoutZone] = (),
    requirements: BedroomRequirements | None = None,
) -> BedroomEvaluation:
    req = requirements or BedroomRequirements()
    if min(req.side_clearance_ft, req.foot_clearance_ft, req.wardrobe_front_clearance_ft, req.passage_width_ft) < 0 or req.grid_step_ft <= 0:
        raise ValueError("invalid bedroom requirements")
    _validate_wardrobe(wardrobe_spec)

    failed: list[str] = []
    warnings: list[str] = []
    furniture = candidate.furniture
    for item in furniture:
        if not rect_contains(room, item.rect):
            failed.append(f"outside_room:{item.item_id}")
        for keepout in keepouts:
            if rect_overlap(item.rect, keepout.rect):
                failed.append(f"keepout_collision:{item.item_id}:{keepout.zone_id}")
    for i, a in enumerate(furniture):
        for b in furniture[i + 1:]:
            if rect_overlap(a.rect, b.rect):
                failed.append(f"furniture_collision:{a.item_id}:{b.item_id}")

    # The candidate was generated with a clearance scenario. Rebuild it if the
    # evaluation requirements differ, so the evaluator is authoritative.
    bed_zones = bed_clearance_zones(room, candidate.bed, side_clearance_ft=req.side_clearance_ft, foot_clearance_ft=req.foot_clearance_ft)
    for index, zone in enumerate(bed_zones, start=1):
        if not rect_contains(room, zone):
            failed.append(f"bed_clearance_outside_room:{index}")
        for item in furniture:
            if item.item_id != "bed" and rect_overlap(zone, item.rect):
                failed.append(f"bed_clearance_blocked:{index}:{item.item_id}")
        for keepout in keepouts:
            if rect_overlap(zone, keepout.rect):
                warnings.append(f"bed_clearance_intersects_opening_keepout:{index}:{keepout.zone_id}")

    wardrobe_zone = wardrobe_front_zone(room, candidate.wardrobe, clearance_ft=req.wardrobe_front_clearance_ft)
    if wardrobe_zone is not None:
        if not rect_contains(room, wardrobe_zone):
            failed.append("wardrobe_front_clearance_outside_room")
        for item in furniture:
            if item.item_id != "wardrobe" and rect_overlap(wardrobe_zone, item.rect):
                failed.append(f"wardrobe_front_clearance_blocked:{item.item_id}")
        for keepout in keepouts:
            if rect_overlap(wardrobe_zone, keepout.rect):
                warnings.append(f"wardrobe_front_clearance_intersects_opening_keepout:{keepout.zone_id}")

    connectivity = walkable = None
    if req.passage_width_ft > 0:
        obstacles = [item.rect for item in furniture] + [zone.rect for zone in keepouts]
        connectivity, walkable = circulation_metrics(room, obstacles, passage_width_ft=req.passage_width_ft, grid_step_ft=req.grid_step_ft)
        if req.require_connected_passage and connectivity < 0.95:
            failed.append("passage_not_connected_at_requested_width")
        elif connectivity < 0.95:
            warnings.append("walkable_space_fragmented_at_requested_width")

    furniture_area = sum(item.rect.area_ft2 for item in furniture)
    open_ratio = max(0.0, 1.0 - furniture_area / room.area_ft2)
    bed_to_wardrobe = math.dist(candidate.bed.rect.center, candidate.wardrobe.rect.center)
    wardrobe_front_area = wardrobe_spec.run_ft * wardrobe_spec.height_ft
    wardrobe_volume = wardrobe_spec.run_ft * wardrobe_spec.depth_ft * wardrobe_spec.height_ft
    circulation_component = 1.0 if connectivity is None else connectivity
    distance_component = min(1.0, bed_to_wardrobe / max(math.hypot(room.width_ft, room.depth_ft) * 0.5, 1e-9))
    score = 100 * (0.40 * open_ratio + 0.35 * circulation_component + 0.25 * distance_component)
    if failed:
        score = min(score, 49.99)

    return BedroomEvaluation(
        layout_id=candidate.layout_id,
        feasible=not failed,
        failed=tuple(dict.fromkeys(failed)),
        warnings=tuple(dict.fromkeys(warnings)),
        furniture_area_ft2=furniture_area,
        open_area_ratio=open_ratio,
        bed_to_wardrobe_center_ft=bed_to_wardrobe,
        circulation_connectivity=connectivity,
        circulation_walkable_ratio=walkable,
        wardrobe_run_ft=wardrobe_spec.run_ft,
        wardrobe_front_area_ft2=wardrobe_front_area,
        wardrobe_internal_volume_ft3=wardrobe_volume,
        geometry_score=round(score, 2),
    )


def rank_bedrooms(
    room: Rect,
    candidates: Iterable[BedroomCandidate],
    wardrobe_spec: WardrobeSpec,
    *,
    keepouts: Sequence[KeepoutZone] = (),
    requirements: BedroomRequirements | None = None,
) -> list[tuple[BedroomCandidate, BedroomEvaluation]]:
    evaluated = [(c, evaluate_bedroom(room, c, wardrobe_spec, keepouts=keepouts, requirements=requirements)) for c in candidates]
    return sorted(evaluated, key=lambda pair: (pair[1].feasible, pair[1].geometry_score, pair[1].circulation_connectivity or 0.0, pair[1].open_area_ratio), reverse=True)


def bedroom_svg(
    room: Rect,
    candidate: BedroomCandidate,
    evaluation: BedroomEvaluation | None = None,
    *,
    keepouts: Sequence[KeepoutZone] = (),
    pixels_per_foot: float = 32.0,
    margin_px: float = 55.0,
) -> str:
    room_w, room_h = room.width_ft * pixels_per_foot, room.depth_ft * pixels_per_foot
    width, height = room_w + 2 * margin_px + 360, max(room_h + 2 * margin_px, 560)
    x0 = y0 = margin_px
    sx = lambda x: x0 + (x - room.x_ft) * pixels_per_foot
    sy = lambda y: y0 + (y - room.y_ft) * pixels_per_foot
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width:.0f}" height="{height:.0f}" viewBox="0 0 {width:.0f} {height:.0f}">',
        '<rect width="100%" height="100%" fill="#fff"/>',
        '<style>text{font-family:Arial,sans-serif;fill:#17202a}.wall{fill:#fff;stroke:#1f2937;stroke-width:4}.bed{fill:#e0e7ff;stroke:#4f46e5;stroke-width:2}.wardrobe{fill:#dcfce7;stroke:#15803d;stroke-width:2}.desk{fill:#f3e8ff;stroke:#7e22ce;stroke-width:2}.keepout{fill:#fef3c7;stroke:#d97706;stroke-width:1.5;stroke-dasharray:4 3}.clearance{fill:none;stroke:#64748b;stroke-width:1.2;stroke-dasharray:5 4}.label{font-size:11px}.title{font-size:18px;font-weight:700}.note{font-size:12px}</style>',
        f'<rect class="wall" x="{x0}" y="{y0}" width="{room_w:.1f}" height="{room_h:.1f}"/>',
    ]
    for zone in keepouts:
        r = zone.rect
        parts.append(f'<rect class="keepout" x="{sx(r.x_ft):.1f}" y="{sy(r.y_ft):.1f}" width="{r.width_ft*pixels_per_foot:.1f}" height="{r.depth_ft*pixels_per_foot:.1f}"/>')
    for zone in candidate.bed_clearance_zones:
        parts.append(f'<rect class="clearance" x="{sx(zone.x_ft):.1f}" y="{sy(zone.y_ft):.1f}" width="{zone.width_ft*pixels_per_foot:.1f}" height="{zone.depth_ft*pixels_per_foot:.1f}"/>')
    if candidate.wardrobe_front_zone is not None:
        r = candidate.wardrobe_front_zone
        parts.append(f'<rect class="clearance" x="{sx(r.x_ft):.1f}" y="{sy(r.y_ft):.1f}" width="{r.width_ft*pixels_per_foot:.1f}" height="{r.depth_ft*pixels_per_foot:.1f}"/>')
    for item in candidate.furniture:
        r = item.rect
        parts.append(f'<rect class="{item.item_id}" x="{sx(r.x_ft):.1f}" y="{sy(r.y_ft):.1f}" width="{r.width_ft*pixels_per_foot:.1f}" height="{r.depth_ft*pixels_per_foot:.1f}"/>')
        cx, cy = r.center
        parts.append(f'<text class="label" x="{sx(cx):.1f}" y="{sy(cy):.1f}" text-anchor="middle">{escape(item.label)}</text>')
    panel_x = x0 + room_w + 30
    parts.append(f'<text class="title" x="{panel_x:.1f}" y="{y0+24:.1f}">{escape(candidate.name)}</text>')
    if evaluation:
        lines = [
            f"Status: {'FEASIBLE' if evaluation.feasible else 'NOT FEASIBLE'}",
            f"Geometry score: {evaluation.geometry_score:.1f}/100",
            f"Open area: {evaluation.open_area_ratio:.1%}",
            f"Bed↔wardrobe centres: {evaluation.bed_to_wardrobe_center_ft:.1f} ft",
            f"Wardrobe front: {evaluation.wardrobe_front_area_ft2:.1f} ft²",
            f"Wardrobe volume: {evaluation.wardrobe_internal_volume_ft3:.1f} ft³",
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


def evaluation_rows(ranked: Sequence[tuple[BedroomCandidate, BedroomEvaluation]]) -> list[dict]:
    return [{
        "layout_id": candidate.layout_id,
        "name": candidate.name,
        "bed_wall": candidate.bed.wall,
        "wardrobe_wall": candidate.wardrobe.wall,
        "desk_wall": candidate.desk.wall if candidate.desk else None,
        "feasible": evaluation.feasible,
        "geometry_score": evaluation.geometry_score,
        "open_area_ratio": evaluation.open_area_ratio,
        "bed_to_wardrobe_center_ft": round(evaluation.bed_to_wardrobe_center_ft, 2),
        "circulation_connectivity": evaluation.circulation_connectivity,
        "wardrobe_run_ft": evaluation.wardrobe_run_ft,
        "wardrobe_front_area_ft2": evaluation.wardrobe_front_area_ft2,
        "wardrobe_internal_volume_ft3": evaluation.wardrobe_internal_volume_ft3,
        "failed": ", ".join(evaluation.failed),
        "warnings": ", ".join(evaluation.warnings),
    } for candidate, evaluation in ranked]
