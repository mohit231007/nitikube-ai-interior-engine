from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from html import escape
import math
from typing import Iterable, Mapping, Sequence


@dataclass(frozen=True)
class Rect:
    x_ft: float
    y_ft: float
    width_ft: float
    depth_ft: float

    @property
    def right_ft(self) -> float:
        return self.x_ft + self.width_ft

    @property
    def bottom_ft(self) -> float:
        return self.y_ft + self.depth_ft

    @property
    def area_ft2(self) -> float:
        return self.width_ft * self.depth_ft

    @property
    def center(self) -> tuple[float, float]:
        return (self.x_ft + self.width_ft / 2.0, self.y_ft + self.depth_ft / 2.0)


@dataclass(frozen=True)
class FurnitureSpec:
    item_id: str
    label: str
    width_ft: float
    depth_ft: float
    clearance_ft: float = 0.0


@dataclass(frozen=True)
class PlacedFurniture:
    spec: FurnitureSpec
    x_ft: float
    y_ft: float
    rotation_deg: int = 0

    @property
    def rect(self) -> Rect:
        rotation = self.rotation_deg % 180
        if rotation == 0:
            width, depth = self.spec.width_ft, self.spec.depth_ft
        elif rotation == 90:
            width, depth = self.spec.depth_ft, self.spec.width_ft
        else:
            raise ValueError("Only 0°/90° axis-aligned furniture rotations are supported in this generator")
        return Rect(self.x_ft, self.y_ft, width, depth)

    @property
    def reserved_rect(self) -> Rect:
        return inflate_rect(self.rect, self.spec.clearance_ft)


@dataclass(frozen=True)
class KeepoutZone:
    zone_id: str
    label: str
    rect: Rect
    source: str = "user_input"


@dataclass(frozen=True)
class LayoutCandidate:
    layout_id: str
    name: str
    placements: tuple[PlacedFurniture, ...]
    zones: tuple[tuple[str, Rect], ...] = ()
    notes: tuple[str, ...] = ()


@dataclass(frozen=True)
class LayoutRequirements:
    wall_margin_ft: float = 0.0
    min_pair_gap_ft: float = 0.0
    passage_width_ft: float = 0.0
    grid_step_ft: float = 0.25
    require_reserved_clearance_inside_room: bool = True


@dataclass(frozen=True)
class LayoutEvaluation:
    layout_id: str
    feasible: bool
    failed: tuple[str, ...]
    warnings: tuple[str, ...]
    furniture_area_ft2: float
    reserved_area_ft2: float
    open_area_ratio: float
    minimum_pair_gap_ft: float | None
    circulation_largest_component_ratio: float | None
    circulation_walkable_ratio: float | None
    geometry_score: float


@dataclass(frozen=True)
class OpeningSegment:
    opening_id: str
    start_ft: tuple[float, float]
    end_ft: tuple[float, float]
    kind: str = "opening"


_EPS = 1e-9


def validate_rect(rect: Rect) -> None:
    values = (rect.x_ft, rect.y_ft, rect.width_ft, rect.depth_ft)
    if any(not math.isfinite(value) for value in values):
        raise ValueError("rectangle values must be finite")
    if rect.width_ft <= 0 or rect.depth_ft <= 0:
        raise ValueError("rectangle width/depth must be positive")


def validate_furniture_spec(spec: FurnitureSpec) -> None:
    if not spec.item_id.strip() or not spec.label.strip():
        raise ValueError("furniture item_id and label are required")
    if spec.width_ft <= 0 or spec.depth_ft <= 0:
        raise ValueError(f"{spec.item_id}: furniture dimensions must be positive")
    if spec.clearance_ft < 0:
        raise ValueError(f"{spec.item_id}: clearance cannot be negative")


def inflate_rect(rect: Rect, margin_ft: float) -> Rect:
    validate_rect(rect)
    if margin_ft < 0:
        raise ValueError("margin cannot be negative")
    return Rect(
        rect.x_ft - margin_ft,
        rect.y_ft - margin_ft,
        rect.width_ft + 2 * margin_ft,
        rect.depth_ft + 2 * margin_ft,
    )


def inset_rect(rect: Rect, margin_ft: float) -> Rect:
    validate_rect(rect)
    if margin_ft < 0:
        raise ValueError("margin cannot be negative")
    width = rect.width_ft - 2 * margin_ft
    depth = rect.depth_ft - 2 * margin_ft
    if width <= 0 or depth <= 0:
        raise ValueError("margin consumes the entire room rectangle")
    return Rect(rect.x_ft + margin_ft, rect.y_ft + margin_ft, width, depth)


def rect_contains(outer: Rect, inner: Rect, *, tolerance_ft: float = 1e-7) -> bool:
    validate_rect(outer)
    validate_rect(inner)
    return (
        inner.x_ft >= outer.x_ft - tolerance_ft
        and inner.y_ft >= outer.y_ft - tolerance_ft
        and inner.right_ft <= outer.right_ft + tolerance_ft
        and inner.bottom_ft <= outer.bottom_ft + tolerance_ft
    )


def rect_overlap(a: Rect, b: Rect, *, touching_counts: bool = False, tolerance_ft: float = 1e-7) -> bool:
    validate_rect(a)
    validate_rect(b)
    if touching_counts:
        return not (
            a.right_ft < b.x_ft - tolerance_ft
            or b.right_ft < a.x_ft - tolerance_ft
            or a.bottom_ft < b.y_ft - tolerance_ft
            or b.bottom_ft < a.y_ft - tolerance_ft
        )
    return not (
        a.right_ft <= b.x_ft + tolerance_ft
        or b.right_ft <= a.x_ft + tolerance_ft
        or a.bottom_ft <= b.y_ft + tolerance_ft
        or b.bottom_ft <= a.y_ft + tolerance_ft
    )


def rect_gap(a: Rect, b: Rect) -> float:
    """Shortest Euclidean distance between two closed axis-aligned rectangles."""
    validate_rect(a)
    validate_rect(b)
    dx = max(a.x_ft - b.right_ft, b.x_ft - a.right_ft, 0.0)
    dy = max(a.y_ft - b.bottom_ft, b.y_ft - a.bottom_ft, 0.0)
    return math.hypot(dx, dy)


def opening_keepout(
    room: Rect,
    opening: OpeningSegment,
    *,
    inward_depth_ft: float,
    side_padding_ft: float = 0.0,
    tolerance_ft: float = 1e-5,
) -> KeepoutZone:
    """Convert an opening segment lying on a rectangular room wall into an inward keepout.

    This is a conservative rectangular keepout, not a door-swing arc. The depth
    and side padding are explicit design inputs; callers must not present them
    as code requirements unless separately sourced.
    """
    validate_rect(room)
    if inward_depth_ft <= 0:
        raise ValueError("inward_depth_ft must be positive")
    if side_padding_ft < 0:
        raise ValueError("side_padding_ft cannot be negative")
    (x1, y1), (x2, y2) = opening.start_ft, opening.end_ft
    for value in (x1, y1, x2, y2):
        if not math.isfinite(value):
            raise ValueError("opening coordinates must be finite")

    horizontal = abs(y1 - y2) <= tolerance_ft
    vertical = abs(x1 - x2) <= tolerance_ft
    if not horizontal and not vertical:
        raise ValueError("opening segment must be axis-aligned")

    if horizontal:
        left = min(x1, x2) - side_padding_ft
        right = max(x1, x2) + side_padding_ft
        if abs(y1 - room.y_ft) <= tolerance_ft:
            rect = Rect(left, room.y_ft, right - left, min(inward_depth_ft, room.depth_ft))
        elif abs(y1 - room.bottom_ft) <= tolerance_ft:
            depth = min(inward_depth_ft, room.depth_ft)
            rect = Rect(left, room.bottom_ft - depth, right - left, depth)
        else:
            raise ValueError("horizontal opening is not on a room boundary")
    else:
        top = min(y1, y2) - side_padding_ft
        bottom = max(y1, y2) + side_padding_ft
        if abs(x1 - room.x_ft) <= tolerance_ft:
            rect = Rect(room.x_ft, top, min(inward_depth_ft, room.width_ft), bottom - top)
        elif abs(x1 - room.right_ft) <= tolerance_ft:
            width = min(inward_depth_ft, room.width_ft)
            rect = Rect(room.right_ft - width, top, width, bottom - top)
        else:
            raise ValueError("vertical opening is not on a room boundary")

    # Clip padded keepout to the room so side padding near corners remains valid.
    x = max(room.x_ft, rect.x_ft)
    y = max(room.y_ft, rect.y_ft)
    right = min(room.right_ft, rect.right_ft)
    bottom = min(room.bottom_ft, rect.bottom_ft)
    if right - x <= _EPS or bottom - y <= _EPS:
        raise ValueError("opening keepout has no area inside the room")
    return KeepoutZone(opening.opening_id, f"{opening.kind}: {opening.opening_id}", Rect(x, y, right - x, bottom - y), "verified_opening")


def _grid_shape(room: Rect, step_ft: float) -> tuple[int, int]:
    if step_ft <= 0:
        raise ValueError("grid step must be positive")
    cols = max(1, math.ceil(room.width_ft / step_ft))
    rows = max(1, math.ceil(room.depth_ft / step_ft))
    return rows, cols


def _cell_center(room: Rect, row: int, col: int, step_ft: float) -> tuple[float, float]:
    return (
        min(room.right_ft - _EPS, room.x_ft + (col + 0.5) * step_ft),
        min(room.bottom_ft - _EPS, room.y_ft + (row + 0.5) * step_ft),
    )


def _point_in_rect(point: tuple[float, float], rect: Rect) -> bool:
    x, y = point
    return rect.x_ft <= x <= rect.right_ft and rect.y_ft <= y <= rect.bottom_ft


def circulation_metrics(
    room: Rect,
    obstacles: Sequence[Rect],
    *,
    passage_width_ft: float,
    grid_step_ft: float = 0.25,
) -> tuple[float, float]:
    """Approximate walkable area/connectivity after Minkowski-style obstacle inflation.

    Furniture/keepout obstacles are inflated by half the requested passage width
    and rasterized. The largest connected component ratio is a geometry metric,
    not a code-compliance certificate.
    """
    validate_rect(room)
    if passage_width_ft < 0:
        raise ValueError("passage_width_ft cannot be negative")
    if grid_step_ft <= 0:
        raise ValueError("grid_step_ft must be positive")

    radius = passage_width_ft / 2.0
    inflated = [inflate_rect(obstacle, radius) for obstacle in obstacles]
    rows, cols = _grid_shape(room, grid_step_ft)
    blocked: set[tuple[int, int]] = set()
    for row in range(rows):
        for col in range(cols):
            point = _cell_center(room, row, col, grid_step_ft)
            if any(_point_in_rect(point, obstacle) for obstacle in inflated):
                blocked.add((row, col))

    total = rows * cols
    walkable = total - len(blocked)
    if walkable <= 0:
        return 0.0, 0.0

    seen: set[tuple[int, int]] = set()
    largest = 0
    for start_row in range(rows):
        for start_col in range(cols):
            start = (start_row, start_col)
            if start in blocked or start in seen:
                continue
            queue = deque([start])
            seen.add(start)
            component = 0
            while queue:
                row, col = queue.popleft()
                component += 1
                for dr, dc in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    nxt = (row + dr, col + dc)
                    if not (0 <= nxt[0] < rows and 0 <= nxt[1] < cols):
                        continue
                    if nxt in blocked or nxt in seen:
                        continue
                    seen.add(nxt)
                    queue.append(nxt)
            largest = max(largest, component)

    return largest / walkable, walkable / total


def evaluate_layout(
    room: Rect,
    candidate: LayoutCandidate,
    *,
    keepouts: Sequence[KeepoutZone] = (),
    requirements: LayoutRequirements | None = None,
) -> LayoutEvaluation:
    requirements = requirements or LayoutRequirements()
    validate_rect(room)
    if requirements.wall_margin_ft < 0 or requirements.min_pair_gap_ft < 0 or requirements.passage_width_ft < 0:
        raise ValueError("layout clearances cannot be negative")
    if requirements.grid_step_ft <= 0:
        raise ValueError("grid_step_ft must be positive")

    failed: list[str] = []
    warnings: list[str] = []
    seen_ids: set[str] = set()
    rects: list[tuple[str, Rect, Rect]] = []
    usable_room = inset_rect(room, requirements.wall_margin_ft) if requirements.wall_margin_ft > 0 else room

    for placement in candidate.placements:
        validate_furniture_spec(placement.spec)
        if placement.spec.item_id in seen_ids:
            failed.append(f"duplicate furniture item_id:{placement.spec.item_id}")
        seen_ids.add(placement.spec.item_id)
        try:
            rect = placement.rect
            reserved = placement.reserved_rect
        except ValueError as exc:
            failed.append(f"{placement.spec.item_id}:{exc}")
            continue
        if not rect_contains(usable_room, rect):
            failed.append(f"outside_room_or_wall_margin:{placement.spec.item_id}")
        if requirements.require_reserved_clearance_inside_room and not rect_contains(room, reserved):
            failed.append(f"reserved_clearance_outside_room:{placement.spec.item_id}")
        for keepout in keepouts:
            if rect_overlap(rect, keepout.rect):
                failed.append(f"keepout_collision:{placement.spec.item_id}:{keepout.zone_id}")
        rects.append((placement.spec.item_id, rect, reserved))

    min_gap: float | None = None
    for i, (id_a, rect_a, _) in enumerate(rects):
        for id_b, rect_b, _ in rects[i + 1 :]:
            if rect_overlap(rect_a, rect_b):
                failed.append(f"furniture_collision:{id_a}:{id_b}")
                gap = 0.0
            else:
                gap = rect_gap(rect_a, rect_b)
                if gap + 1e-7 < requirements.min_pair_gap_ft:
                    failed.append(f"pair_gap:{id_a}:{id_b}")
            min_gap = gap if min_gap is None else min(min_gap, gap)

    furniture_area = sum(rect.area_ft2 for _, rect, _ in rects)
    reserved_area = sum(reserved.area_ft2 for _, _, reserved in rects)
    open_area_ratio = max(0.0, 1.0 - furniture_area / room.area_ft2)

    circulation_component = None
    walkable_ratio = None
    if requirements.passage_width_ft > 0:
        obstacles = [rect for _, rect, _ in rects] + [zone.rect for zone in keepouts]
        circulation_component, walkable_ratio = circulation_metrics(
            room,
            obstacles,
            passage_width_ft=requirements.passage_width_ft,
            grid_step_ft=requirements.grid_step_ft,
        )
        if circulation_component < 0.95:
            warnings.append("walkable_space_is_fragmented_at_requested_passage_width")

    # Geometry-only score. It deliberately excludes aesthetics/style and has no
    # claim of ergonomic/code compliance. Feasibility stays separate.
    gap_component = 1.0
    if requirements.min_pair_gap_ft > 0 and min_gap is not None:
        gap_component = min(1.0, min_gap / requirements.min_pair_gap_ft)
    circulation_component_for_score = 1.0 if circulation_component is None else circulation_component
    walkable_for_score = open_area_ratio if walkable_ratio is None else walkable_ratio
    geometry_score = 100.0 * (
        0.35 * open_area_ratio
        + 0.20 * gap_component
        + 0.30 * circulation_component_for_score
        + 0.15 * walkable_for_score
    )
    if failed:
        geometry_score = min(geometry_score, 49.99)

    return LayoutEvaluation(
        layout_id=candidate.layout_id,
        feasible=not failed,
        failed=tuple(dict.fromkeys(failed)),
        warnings=tuple(dict.fromkeys(warnings)),
        furniture_area_ft2=furniture_area,
        reserved_area_ft2=reserved_area,
        open_area_ratio=open_area_ratio,
        minimum_pair_gap_ft=min_gap,
        circulation_largest_component_ratio=circulation_component,
        circulation_walkable_ratio=walkable_ratio,
        geometry_score=round(geometry_score, 2),
    )


def _centered_rect(container: Rect, width_ft: float, depth_ft: float) -> Rect:
    return Rect(
        container.x_ft + (container.width_ft - width_ft) / 2.0,
        container.y_ft + (container.depth_ft - depth_ft) / 2.0,
        width_ft,
        depth_ft,
    )


def _place_against_vertical_wall(
    spec: FurnitureSpec,
    zone: Rect,
    *,
    wall: str,
    wall_margin_ft: float,
) -> PlacedFurniture:
    # Rotate the item's width/length so its long width runs along the vertical wall.
    width_x = spec.depth_ft
    depth_y = spec.width_ft
    y = zone.y_ft + max(0.0, (zone.depth_ft - depth_y) / 2.0)
    if wall == "left":
        x = zone.x_ft + wall_margin_ft
    elif wall == "right":
        x = zone.right_ft - wall_margin_ft - width_x
    else:
        raise ValueError("wall must be left or right")
    return PlacedFurniture(spec, x, y, 90)


def generate_drawing_dining_candidates(
    room: Rect,
    *,
    sofa: FurnitureSpec,
    tv_console: FurnitureSpec,
    coffee_table: FurnitureSpec,
    dining_table: FurnitureSpec,
    living_fraction: float = 0.58,
    zone_gap_ft: float = 0.5,
    wall_margin_ft: float = 0.25,
) -> tuple[LayoutCandidate, ...]:
    """Generate deterministic long-rectangular drawing/dining arrangements.

    The generator explores living/dining order, sofa wall and dining-table
    rotation. Furniture dimensions, zone split and margins are caller inputs;
    no ergonomic standard is hidden inside this function.
    """
    validate_rect(room)
    for spec in (sofa, tv_console, coffee_table, dining_table):
        validate_furniture_spec(spec)
    if not 0.25 <= living_fraction <= 0.75:
        raise ValueError("living_fraction must be in [0.25,0.75]")
    if zone_gap_ft < 0 or wall_margin_ft < 0:
        raise ValueError("zone gap and wall margin cannot be negative")
    available_depth = room.depth_ft - zone_gap_ft
    if available_depth <= 0:
        raise ValueError("zone gap consumes the room")
    living_depth = available_depth * living_fraction
    dining_depth = available_depth - living_depth

    candidates: list[LayoutCandidate] = []
    counter = 1
    for living_first in (True, False):
        if living_first:
            living_zone = Rect(room.x_ft, room.y_ft, room.width_ft, living_depth)
            dining_zone = Rect(room.x_ft, room.y_ft + living_depth + zone_gap_ft, room.width_ft, dining_depth)
            order_name = "Living near top"
        else:
            dining_zone = Rect(room.x_ft, room.y_ft, room.width_ft, dining_depth)
            living_zone = Rect(room.x_ft, room.y_ft + dining_depth + zone_gap_ft, room.width_ft, living_depth)
            order_name = "Dining near top"

        for sofa_wall in ("left", "right"):
            tv_wall = "right" if sofa_wall == "left" else "left"
            sofa_placement = _place_against_vertical_wall(sofa, living_zone, wall=sofa_wall, wall_margin_ft=wall_margin_ft)
            tv_placement = _place_against_vertical_wall(tv_console, living_zone, wall=tv_wall, wall_margin_ft=wall_margin_ft)

            coffee_width = min(coffee_table.width_ft, living_zone.width_ft)
            coffee_depth = min(coffee_table.depth_ft, living_zone.depth_ft)
            coffee_rect = _centered_rect(living_zone, coffee_width, coffee_depth)
            coffee_placement = PlacedFurniture(coffee_table, coffee_rect.x_ft, coffee_rect.y_ft, 0)

            for dining_rotation in (0, 90):
                dining_w = dining_table.width_ft if dining_rotation == 0 else dining_table.depth_ft
                dining_d = dining_table.depth_ft if dining_rotation == 0 else dining_table.width_ft
                dining_rect = _centered_rect(dining_zone, dining_w, dining_d)
                dining_placement = PlacedFurniture(
                    dining_table,
                    dining_rect.x_ft,
                    dining_rect.y_ft,
                    dining_rotation,
                )
                candidates.append(
                    LayoutCandidate(
                        layout_id=f"DD-{counter:02d}",
                        name=f"{order_name} · sofa {sofa_wall} · dining {dining_rotation}°",
                        placements=(sofa_placement, tv_placement, coffee_placement, dining_placement),
                        zones=(("Living", living_zone), ("Dining", dining_zone)),
                        notes=(
                            "Generated from axis-aligned room/furniture geometry.",
                            "Zone split, clearances and furniture dimensions are explicit scenario inputs.",
                        ),
                    )
                )
                counter += 1
    return tuple(candidates)


def rank_layouts(
    room: Rect,
    candidates: Iterable[LayoutCandidate],
    *,
    keepouts: Sequence[KeepoutZone] = (),
    requirements: LayoutRequirements | None = None,
) -> list[tuple[LayoutCandidate, LayoutEvaluation]]:
    evaluated = [
        (candidate, evaluate_layout(room, candidate, keepouts=keepouts, requirements=requirements))
        for candidate in candidates
    ]
    return sorted(
        evaluated,
        key=lambda pair: (
            pair[1].feasible,
            pair[1].geometry_score,
            pair[1].circulation_largest_component_ratio or 0.0,
            pair[1].open_area_ratio,
        ),
        reverse=True,
    )


def layout_svg(
    room: Rect,
    candidate: LayoutCandidate,
    evaluation: LayoutEvaluation | None = None,
    *,
    keepouts: Sequence[KeepoutZone] = (),
    pixels_per_foot: float = 28.0,
    margin_px: float = 60.0,
) -> str:
    validate_rect(room)
    if pixels_per_foot <= 0:
        raise ValueError("pixels_per_foot must be positive")
    room_w = room.width_ft * pixels_per_foot
    room_h = room.depth_ft * pixels_per_foot
    side_panel = 330.0
    width = room_w + 2 * margin_px + side_panel
    height = max(room_h + 2 * margin_px, 520.0)
    x0 = margin_px
    y0 = margin_px

    def sx(value: float) -> float:
        return x0 + (value - room.x_ft) * pixels_per_foot

    def sy(value: float) -> float:
        return y0 + (value - room.y_ft) * pixels_per_foot

    styles = (
        "text{font-family:Arial,sans-serif;fill:#17202a}"
        ".wall{fill:#fff;stroke:#1f2937;stroke-width:4}"
        ".zone{fill:none;stroke:#94a3b8;stroke-width:1.5;stroke-dasharray:6 5}"
        ".furniture{fill:#e8eef5;stroke:#334155;stroke-width:1.5}"
        ".reserved{fill:none;stroke:#94a3b8;stroke-width:1;stroke-dasharray:3 3}"
        ".keepout{fill:#fef3c7;stroke:#d97706;stroke-width:1.5;stroke-dasharray:4 3}"
        ".label{font-size:12px}.title{font-size:19px;font-weight:700}.note{font-size:12px}"
    )
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width:.0f}" height="{height:.0f}" viewBox="0 0 {width:.0f} {height:.0f}">',
        '<rect width="100%" height="100%" fill="#ffffff"/>',
        f'<style>{styles}</style>',
        f'<rect class="wall" x="{x0:.1f}" y="{y0:.1f}" width="{room_w:.1f}" height="{room_h:.1f}"/>',
    ]

    for zone_name, zone in candidate.zones:
        parts.append(
            f'<rect class="zone" x="{sx(zone.x_ft):.1f}" y="{sy(zone.y_ft):.1f}" '
            f'width="{zone.width_ft * pixels_per_foot:.1f}" height="{zone.depth_ft * pixels_per_foot:.1f}"/>'
        )
        parts.append(
            f'<text class="label" x="{sx(zone.x_ft) + 6:.1f}" y="{sy(zone.y_ft) + 16:.1f}">{escape(zone_name)}</text>'
        )

    for keepout in keepouts:
        rect = keepout.rect
        parts.append(
            f'<rect class="keepout" x="{sx(rect.x_ft):.1f}" y="{sy(rect.y_ft):.1f}" '
            f'width="{rect.width_ft * pixels_per_foot:.1f}" height="{rect.depth_ft * pixels_per_foot:.1f}"/>'
        )
        parts.append(
            f'<text class="label" x="{sx(rect.x_ft) + 4:.1f}" y="{sy(rect.y_ft) + 14:.1f}">{escape(keepout.label)}</text>'
        )

    for placement in candidate.placements:
        reserved = placement.reserved_rect
        rect = placement.rect
        if placement.spec.clearance_ft > 0:
            parts.append(
                f'<rect class="reserved" x="{sx(reserved.x_ft):.1f}" y="{sy(reserved.y_ft):.1f}" '
                f'width="{reserved.width_ft * pixels_per_foot:.1f}" height="{reserved.depth_ft * pixels_per_foot:.1f}"/>'
            )
        parts.append(
            f'<rect class="furniture" x="{sx(rect.x_ft):.1f}" y="{sy(rect.y_ft):.1f}" '
            f'width="{rect.width_ft * pixels_per_foot:.1f}" height="{rect.depth_ft * pixels_per_foot:.1f}"/>'
        )
        cx, cy = rect.center
        parts.append(
            f'<text class="label" x="{sx(cx):.1f}" y="{sy(cy):.1f}" text-anchor="middle">{escape(placement.spec.label)}</text>'
        )

    panel_x = x0 + room_w + 35
    parts.append(f'<text class="title" x="{panel_x:.1f}" y="{y0 + 25:.1f}">{escape(candidate.name)}</text>')
    parts.append(
        f'<text class="note" x="{panel_x:.1f}" y="{y0 + 50:.1f}">Room: {room.width_ft:.2f} × {room.depth_ft:.2f} ft</text>'
    )
    if evaluation is not None:
        status = "FEASIBLE" if evaluation.feasible else "NOT FEASIBLE"
        parts.extend(
            [
                f'<text class="note" x="{panel_x:.1f}" y="{y0 + 76:.1f}">Status: {status}</text>',
                f'<text class="note" x="{panel_x:.1f}" y="{y0 + 98:.1f}">Geometry score: {evaluation.geometry_score:.1f}/100</text>',
                f'<text class="note" x="{panel_x:.1f}" y="{y0 + 120:.1f}">Open-area ratio: {evaluation.open_area_ratio:.1%}</text>',
            ]
        )
        if evaluation.minimum_pair_gap_ft is not None:
            parts.append(
                f'<text class="note" x="{panel_x:.1f}" y="{y0 + 142:.1f}">Minimum furniture gap: {evaluation.minimum_pair_gap_ft:.2f} ft</text>'
            )
        if evaluation.circulation_largest_component_ratio is not None:
            parts.append(
                f'<text class="note" x="{panel_x:.1f}" y="{y0 + 164:.1f}">Walkable connectivity: {evaluation.circulation_largest_component_ratio:.1%}</text>'
            )
        line_y = y0 + 194
        for failure in evaluation.failed[:8]:
            parts.append(f'<text class="note" x="{panel_x:.1f}" y="{line_y:.1f}">• {escape(failure)}</text>')
            line_y += 18
    parts.append('</svg>')
    return "".join(parts)


def evaluation_rows(ranked: Sequence[tuple[LayoutCandidate, LayoutEvaluation]]) -> list[dict]:
    return [
        {
            "layout_id": candidate.layout_id,
            "name": candidate.name,
            "feasible": evaluation.feasible,
            "geometry_score": evaluation.geometry_score,
            "open_area_ratio": evaluation.open_area_ratio,
            "minimum_pair_gap_ft": evaluation.minimum_pair_gap_ft,
            "circulation_connectivity": evaluation.circulation_largest_component_ratio,
            "circulation_walkable_ratio": evaluation.circulation_walkable_ratio,
            "failed": ", ".join(evaluation.failed),
            "warnings": ", ".join(evaluation.warnings),
        }
        for candidate, evaluation in ranked
    ]
