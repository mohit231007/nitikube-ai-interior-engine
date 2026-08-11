from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from html import escape
import math
from typing import Iterable, Sequence

from .room_layout import KeepoutZone, Rect, circulation_metrics, rect_contains, rect_overlap


class KitchenLayoutKind(str, Enum):
    ONE_WALL = "one_wall"
    GALLEY = "galley"
    L_SHAPE = "l_shape"
    U_SHAPE = "u_shape"


_WALLS = {"top", "bottom", "left", "right"}
_EPS = 1e-8


@dataclass(frozen=True)
class CounterRun:
    run_id: str
    wall: str
    rect: Rect

    @property
    def length_ft(self) -> float:
        return self.rect.width_ft if self.wall in {"top", "bottom"} else self.rect.depth_ft

    @property
    def depth_ft(self) -> float:
        return self.rect.depth_ft if self.wall in {"top", "bottom"} else self.rect.width_ft


@dataclass(frozen=True)
class WorkCenterSpec:
    center_id: str
    label: str
    width_along_run_ft: float
    depth_ft: float


@dataclass(frozen=True)
class PlacedWorkCenter:
    spec: WorkCenterSpec
    run_id: str
    fraction_along_run: float
    rect: Rect

    @property
    def center(self) -> tuple[float, float]:
        return self.rect.center


@dataclass(frozen=True)
class KitchenCandidate:
    layout_id: str
    name: str
    kind: KitchenLayoutKind
    counter_runs: tuple[CounterRun, ...]
    work_centers: tuple[PlacedWorkCenter, ...]
    notes: tuple[str, ...] = ()


@dataclass(frozen=True)
class KitchenRequirements:
    min_counter_run_ft: float = 0.0
    passage_width_ft: float = 0.0
    grid_step_ft: float = 0.25
    require_connected_passage: bool = True
    work_triangle_leg_min_ft: float | None = None
    work_triangle_leg_max_ft: float | None = None
    work_triangle_total_min_ft: float | None = None
    work_triangle_total_max_ft: float | None = None


@dataclass(frozen=True)
class WorkTriangle:
    sink_to_hob_ft: float
    hob_to_fridge_ft: float
    fridge_to_sink_ft: float
    perimeter_ft: float
    area_ft2: float

    @property
    def legs(self) -> tuple[float, float, float]:
        return self.sink_to_hob_ft, self.hob_to_fridge_ft, self.fridge_to_sink_ft


@dataclass(frozen=True)
class KitchenEvaluation:
    layout_id: str
    feasible: bool
    failed: tuple[str, ...]
    warnings: tuple[str, ...]
    gross_counter_run_ft: float
    countertop_union_area_ft2: float
    work_triangle: WorkTriangle | None
    circulation_connectivity: float | None
    circulation_walkable_ratio: float | None
    geometry_score: float


def _validate_center(spec: WorkCenterSpec) -> None:
    if not spec.center_id.strip() or not spec.label.strip():
        raise ValueError("work-center id and label are required")
    if spec.width_along_run_ft <= 0 or spec.depth_ft <= 0:
        raise ValueError(f"{spec.center_id}: dimensions must be positive")


def counter_run_for_wall(
    room: Rect,
    wall: str,
    *,
    counter_depth_ft: float,
    wall_margin_ft: float = 0.0,
    run_id: str | None = None,
) -> CounterRun:
    if wall not in _WALLS:
        raise ValueError(f"wall must be one of {sorted(_WALLS)}")
    if counter_depth_ft <= 0 or wall_margin_ft < 0:
        raise ValueError("counter depth must be positive and margin non-negative")
    if 2 * wall_margin_ft >= min(room.width_ft, room.depth_ft):
        raise ValueError("wall margin is too large for the room")

    if wall == "top":
        rect = Rect(room.x_ft + wall_margin_ft, room.y_ft + wall_margin_ft, room.width_ft - 2 * wall_margin_ft, counter_depth_ft)
    elif wall == "bottom":
        rect = Rect(room.x_ft + wall_margin_ft, room.bottom_ft - wall_margin_ft - counter_depth_ft, room.width_ft - 2 * wall_margin_ft, counter_depth_ft)
    elif wall == "left":
        rect = Rect(room.x_ft + wall_margin_ft, room.y_ft + wall_margin_ft, counter_depth_ft, room.depth_ft - 2 * wall_margin_ft)
    else:
        rect = Rect(room.right_ft - wall_margin_ft - counter_depth_ft, room.y_ft + wall_margin_ft, counter_depth_ft, room.depth_ft - 2 * wall_margin_ft)
    if not rect_contains(room, rect):
        raise ValueError("counter depth/margin places the run outside the room")
    return CounterRun(run_id or f"run-{wall}", wall, rect)


def place_work_center(run: CounterRun, spec: WorkCenterSpec, fraction_along_run: float) -> PlacedWorkCenter:
    _validate_center(spec)
    if not 0 <= fraction_along_run <= 1:
        raise ValueError("fraction_along_run must be in [0,1]")
    if spec.width_along_run_ft > run.length_ft + _EPS:
        raise ValueError(f"{spec.center_id}: module is wider than counter run {run.run_id}")
    if spec.depth_ft > run.depth_ft + _EPS:
        raise ValueError(f"{spec.center_id}: module depth exceeds counter run depth")

    start = (run.length_ft - spec.width_along_run_ft) * fraction_along_run
    if run.wall in {"top", "bottom"}:
        x = run.rect.x_ft + start
        y = run.rect.y_ft if run.wall == "top" else run.rect.bottom_ft - spec.depth_ft
        rect = Rect(x, y, spec.width_along_run_ft, spec.depth_ft)
    else:
        y = run.rect.y_ft + start
        x = run.rect.x_ft if run.wall == "left" else run.rect.right_ft - spec.depth_ft
        rect = Rect(x, y, spec.depth_ft, spec.width_along_run_ft)
    return PlacedWorkCenter(spec, run.run_id, fraction_along_run, rect)


def _union_area(rectangles: Sequence[Rect]) -> float:
    if not rectangles:
        return 0.0
    xs = sorted({v for r in rectangles for v in (r.x_ft, r.right_ft)})
    total = 0.0
    for x0, x1 in zip(xs, xs[1:]):
        if x1 - x0 <= _EPS:
            continue
        probe = (x0 + x1) / 2
        intervals = sorted((r.y_ft, r.bottom_ft) for r in rectangles if r.x_ft - _EPS <= probe <= r.right_ft + _EPS)
        if not intervals:
            continue
        start, end = intervals[0]
        merged = 0.0
        for a, b in intervals[1:]:
            if a <= end + _EPS:
                end = max(end, b)
            else:
                merged += end - start
                start, end = a, b
        merged += end - start
        total += (x1 - x0) * merged
    return total


def work_triangle(work_centers: Sequence[PlacedWorkCenter]) -> WorkTriangle | None:
    by_id = {c.spec.center_id.casefold(): c for c in work_centers}
    if not all(name in by_id for name in ("sink", "hob", "fridge")):
        return None
    sink, hob, fridge = (by_id[name].center for name in ("sink", "hob", "fridge"))
    sh, hf, fs = math.dist(sink, hob), math.dist(hob, fridge), math.dist(fridge, sink)
    area = abs(
        sink[0] * (hob[1] - fridge[1])
        + hob[0] * (fridge[1] - sink[1])
        + fridge[0] * (sink[1] - hob[1])
    ) / 2
    return WorkTriangle(sh, hf, fs, sh + hf + fs, area)


def _triangle_failures(triangle: WorkTriangle | None, req: KitchenRequirements) -> list[str]:
    configured = any(v is not None for v in (
        req.work_triangle_leg_min_ft,
        req.work_triangle_leg_max_ft,
        req.work_triangle_total_min_ft,
        req.work_triangle_total_max_ft,
    ))
    if triangle is None:
        return ["work_triangle_missing"] if configured else []
    failed: list[str] = []
    if req.work_triangle_leg_min_ft is not None and min(triangle.legs) < req.work_triangle_leg_min_ft:
        failed.append("work_triangle_leg_below_min")
    if req.work_triangle_leg_max_ft is not None and max(triangle.legs) > req.work_triangle_leg_max_ft:
        failed.append("work_triangle_leg_above_max")
    if req.work_triangle_total_min_ft is not None and triangle.perimeter_ft < req.work_triangle_total_min_ft:
        failed.append("work_triangle_total_below_min")
    if req.work_triangle_total_max_ft is not None and triangle.perimeter_ft > req.work_triangle_total_max_ft:
        failed.append("work_triangle_total_above_max")
    return failed


def evaluate_kitchen(
    room: Rect,
    candidate: KitchenCandidate,
    *,
    keepouts: Sequence[KeepoutZone] = (),
    requirements: KitchenRequirements | None = None,
) -> KitchenEvaluation:
    req = requirements or KitchenRequirements()
    if req.min_counter_run_ft < 0 or req.passage_width_ft < 0 or req.grid_step_ft <= 0:
        raise ValueError("invalid kitchen requirement values")

    failed: list[str] = []
    warnings: list[str] = []
    run_ids: set[str] = set()
    for run in candidate.counter_runs:
        if run.run_id in run_ids:
            failed.append(f"duplicate_run_id:{run.run_id}")
        run_ids.add(run.run_id)
        if run.wall not in _WALLS or not rect_contains(room, run.rect):
            failed.append(f"invalid_counter_run:{run.run_id}")
        if run.length_ft + _EPS < req.min_counter_run_ft:
            failed.append(f"counter_run_too_short:{run.run_id}")
        for keepout in keepouts:
            if rect_overlap(run.rect, keepout.rect):
                failed.append(f"counter_keepout_collision:{run.run_id}:{keepout.zone_id}")

    center_ids: set[str] = set()
    for center in candidate.work_centers:
        key = center.spec.center_id.casefold()
        if key in center_ids:
            failed.append(f"duplicate_work_center:{center.spec.center_id}")
        center_ids.add(key)
        run = next((r for r in candidate.counter_runs if r.run_id == center.run_id), None)
        if run is None or not rect_contains(run.rect, center.rect):
            failed.append(f"work_center_outside_run:{center.spec.center_id}")
        for keepout in keepouts:
            if rect_overlap(center.rect, keepout.rect):
                failed.append(f"work_center_keepout_collision:{center.spec.center_id}:{keepout.zone_id}")

    for i, a in enumerate(candidate.work_centers):
        for b in candidate.work_centers[i + 1:]:
            if rect_overlap(a.rect, b.rect):
                failed.append(f"work_center_collision:{a.spec.center_id}:{b.spec.center_id}")

    triangle = work_triangle(candidate.work_centers)
    failed.extend(_triangle_failures(triangle, req))

    connectivity = walkable = None
    if req.passage_width_ft > 0 and candidate.counter_runs:
        connectivity, walkable = circulation_metrics(
            room,
            [r.rect for r in candidate.counter_runs] + [k.rect for k in keepouts],
            passage_width_ft=req.passage_width_ft,
            grid_step_ft=req.grid_step_ft,
        )
        if req.require_connected_passage and connectivity < 0.95:
            failed.append("passage_not_connected_at_requested_width")
        elif connectivity < 0.95:
            warnings.append("walkable_space_fragmented_at_requested_width")

    gross_run = sum(r.length_ft for r in candidate.counter_runs)
    counter_area = _union_area([r.rect for r in candidate.counter_runs])
    run_component = min(1.0, gross_run / max(room.width_ft + room.depth_ft, _EPS))
    open_component = 1.0 - min(1.0, counter_area / room.area_ft2)
    circulation_component = 1.0 if connectivity is None else connectivity
    triangle_component = 0.0 if triangle is None else min(1.0, triangle.area_ft2 / max(room.area_ft2 * 0.08, _EPS))
    score = 100 * (0.25 * run_component + 0.25 * open_component + 0.30 * circulation_component + 0.20 * triangle_component)
    if failed:
        score = min(score, 49.99)

    return KitchenEvaluation(
        candidate.layout_id,
        not failed,
        tuple(dict.fromkeys(failed)),
        tuple(dict.fromkeys(warnings)),
        gross_run,
        counter_area,
        triangle,
        connectivity,
        walkable,
        round(score, 2),
    )


def _centers_for_runs(runs: Sequence[CounterRun], sink: WorkCenterSpec, hob: WorkCenterSpec, fridge: WorkCenterSpec) -> tuple[PlacedWorkCenter, ...]:
    if len(runs) == 1:
        assignments = ((fridge, runs[0], 0.02), (sink, runs[0], 0.50), (hob, runs[0], 0.98))
    elif len(runs) == 2:
        assignments = ((sink, runs[0], 0.50), (hob, runs[1], 0.50), (fridge, runs[0], 0.02))
    elif len(runs) >= 3:
        assignments = ((sink, runs[0], 0.50), (hob, runs[1], 0.50), (fridge, runs[2], 0.50))
    else:
        raise ValueError("at least one run is required")
    return tuple(place_work_center(run, spec, fraction) for spec, run, fraction in assignments)


def generate_kitchen_candidates(
    room: Rect,
    *,
    counter_depth_ft: float,
    wall_margin_ft: float,
    sink: WorkCenterSpec,
    hob: WorkCenterSpec,
    fridge: WorkCenterSpec,
    include_kinds: Sequence[KitchenLayoutKind] = (
        KitchenLayoutKind.ONE_WALL,
        KitchenLayoutKind.GALLEY,
        KitchenLayoutKind.L_SHAPE,
        KitchenLayoutKind.U_SHAPE,
    ),
) -> tuple[KitchenCandidate, ...]:
    for spec in (sink, hob, fridge):
        _validate_center(spec)
    candidates: list[KitchenCandidate] = []
    serial = 1

    def add(kind: KitchenLayoutKind, walls: Sequence[str], name: str) -> None:
        nonlocal serial
        try:
            runs = tuple(counter_run_for_wall(
                room, wall, counter_depth_ft=counter_depth_ft, wall_margin_ft=wall_margin_ft,
                run_id=f"{kind.value}-{wall}",
            ) for wall in walls)
            centers = _centers_for_runs(runs, sink, hob, fridge)
        except ValueError:
            return
        candidates.append(KitchenCandidate(
            f"K-{serial:02d}", name, kind, runs, centers,
            ("Generated from transparent wall-run geometry.", "Thresholds are evaluated separately as explicit inputs."),
        ))
        serial += 1

    include = set(include_kinds)
    if KitchenLayoutKind.ONE_WALL in include:
        for wall in ("top", "bottom", "left", "right"):
            add(KitchenLayoutKind.ONE_WALL, (wall,), f"One-wall · {wall}")
    if KitchenLayoutKind.GALLEY in include:
        add(KitchenLayoutKind.GALLEY, ("top", "bottom"), "Galley · top + bottom")
        add(KitchenLayoutKind.GALLEY, ("left", "right"), "Galley · left + right")
    if KitchenLayoutKind.L_SHAPE in include:
        for walls in (("top", "left"), ("top", "right"), ("bottom", "left"), ("bottom", "right")):
            add(KitchenLayoutKind.L_SHAPE, walls, f"L-shape · {' + '.join(walls)}")
    if KitchenLayoutKind.U_SHAPE in include:
        for walls in (("top", "left", "right"), ("bottom", "left", "right"), ("left", "top", "bottom"), ("right", "top", "bottom")):
            add(KitchenLayoutKind.U_SHAPE, walls, f"U-shape · {' + '.join(walls)}")
    return tuple(candidates)


def rank_kitchens(room: Rect, candidates: Iterable[KitchenCandidate], *, keepouts: Sequence[KeepoutZone] = (), requirements: KitchenRequirements | None = None) -> list[tuple[KitchenCandidate, KitchenEvaluation]]:
    evaluated = [(c, evaluate_kitchen(room, c, keepouts=keepouts, requirements=requirements)) for c in candidates]
    return sorted(evaluated, key=lambda pair: (pair[1].feasible, pair[1].geometry_score, pair[1].circulation_connectivity or 0.0, pair[1].gross_counter_run_ft), reverse=True)


def kitchen_quantity_summary(
    candidate: KitchenCandidate,
    evaluation: KitchenEvaluation,
    *,
    base_cabinet_height_ft: float,
    wall_cabinet_height_ft: float = 0.0,
    wall_cabinet_run_fraction: float = 0.0,
    countertop_waste_fraction: float = 0.0,
) -> dict[str, float]:
    if base_cabinet_height_ft <= 0 or wall_cabinet_height_ft < 0:
        raise ValueError("invalid cabinet heights")
    if not 0 <= wall_cabinet_run_fraction <= 1 or countertop_waste_fraction < 0:
        raise ValueError("invalid quantity fractions")
    run = evaluation.gross_counter_run_ft
    return {
        "gross_counter_run_ft": run,
        "base_cabinet_front_area_ft2": run * base_cabinet_height_ft,
        "wall_cabinet_run_ft": run * wall_cabinet_run_fraction,
        "wall_cabinet_front_area_ft2": run * wall_cabinet_run_fraction * wall_cabinet_height_ft,
        "countertop_geometric_area_ft2": evaluation.countertop_union_area_ft2,
        "countertop_purchase_area_ft2": evaluation.countertop_union_area_ft2 * (1 + countertop_waste_fraction),
    }


def kitchen_svg(room: Rect, candidate: KitchenCandidate, evaluation: KitchenEvaluation | None = None, *, keepouts: Sequence[KeepoutZone] = (), pixels_per_foot: float = 32.0, margin_px: float = 55.0) -> str:
    room_w, room_h = room.width_ft * pixels_per_foot, room.depth_ft * pixels_per_foot
    width, height = room_w + 2 * margin_px + 360, max(room_h + 2 * margin_px, 560)
    x0 = y0 = margin_px
    sx = lambda x: x0 + (x - room.x_ft) * pixels_per_foot
    sy = lambda y: y0 + (y - room.y_ft) * pixels_per_foot
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width:.0f}" height="{height:.0f}" viewBox="0 0 {width:.0f} {height:.0f}">',
        '<rect width="100%" height="100%" fill="#fff"/>',
        '<style>text{font-family:Arial,sans-serif;fill:#17202a}.wall{fill:#fff;stroke:#1f2937;stroke-width:4}.counter{fill:#e5e7eb;stroke:#475569;stroke-width:1.5}.keepout{fill:#fef3c7;stroke:#d97706;stroke-width:1.5;stroke-dasharray:4 3}.sink{fill:#dbeafe;stroke:#2563eb}.hob{fill:#fee2e2;stroke:#dc2626}.fridge{fill:#dcfce7;stroke:#16a34a}.center{stroke-width:2}.label{font-size:11px}.title{font-size:18px;font-weight:700}.note{font-size:12px}</style>',
        f'<rect class="wall" x="{x0}" y="{y0}" width="{room_w:.1f}" height="{room_h:.1f}"/>',
    ]
    for zone in keepouts:
        r = zone.rect
        parts.append(f'<rect class="keepout" x="{sx(r.x_ft):.1f}" y="{sy(r.y_ft):.1f}" width="{r.width_ft*pixels_per_foot:.1f}" height="{r.depth_ft*pixels_per_foot:.1f}"/>')
    for run in candidate.counter_runs:
        r = run.rect
        parts.append(f'<rect class="counter" x="{sx(r.x_ft):.1f}" y="{sy(r.y_ft):.1f}" width="{r.width_ft*pixels_per_foot:.1f}" height="{r.depth_ft*pixels_per_foot:.1f}"/>')
    by_id = {}
    for center in candidate.work_centers:
        r = center.rect
        key = center.spec.center_id.casefold()
        by_id[key] = center
        css = key if key in {"sink", "hob", "fridge"} else "counter"
        parts.append(f'<rect class="center {css}" x="{sx(r.x_ft):.1f}" y="{sy(r.y_ft):.1f}" width="{r.width_ft*pixels_per_foot:.1f}" height="{r.depth_ft*pixels_per_foot:.1f}"/>')
        cx, cy = center.center
        parts.append(f'<text class="label" x="{sx(cx):.1f}" y="{sy(cy):.1f}" text-anchor="middle">{escape(center.spec.label)}</text>')
    triangle = evaluation.work_triangle if evaluation else work_triangle(candidate.work_centers)
    if triangle and all(k in by_id for k in ("sink", "hob", "fridge")):
        pts = [by_id[k].center for k in ("sink", "hob", "fridge", "sink")]
        parts.append('<polyline points="' + ' '.join(f'{sx(x):.1f},{sy(y):.1f}' for x, y in pts) + '" fill="none" stroke="#7c3aed" stroke-width="2" stroke-dasharray="5 4"/>')
    panel_x = x0 + room_w + 30
    parts.append(f'<text class="title" x="{panel_x:.1f}" y="{y0+24:.1f}">{escape(candidate.name)}</text>')
    if evaluation:
        lines = [
            f"Status: {'FEASIBLE' if evaluation.feasible else 'NOT FEASIBLE'}",
            f"Geometry score: {evaluation.geometry_score:.1f}/100",
            f"Counter run: {evaluation.gross_counter_run_ft:.1f} ft",
            f"Countertop area: {evaluation.countertop_union_area_ft2:.1f} ft²",
        ]
        if triangle:
            lines += [f"Triangle perimeter: {triangle.perimeter_ft:.1f} ft", f"Triangle area: {triangle.area_ft2:.1f} ft²"]
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


def evaluation_rows(ranked: Sequence[tuple[KitchenCandidate, KitchenEvaluation]]) -> list[dict]:
    rows = []
    for candidate, evaluation in ranked:
        t = evaluation.work_triangle
        rows.append({
            "layout_id": candidate.layout_id,
            "kind": candidate.kind.value,
            "name": candidate.name,
            "feasible": evaluation.feasible,
            "geometry_score": evaluation.geometry_score,
            "gross_counter_run_ft": round(evaluation.gross_counter_run_ft, 2),
            "countertop_area_ft2": round(evaluation.countertop_union_area_ft2, 2),
            "triangle_sink_hob_ft": round(t.sink_to_hob_ft, 2) if t else None,
            "triangle_hob_fridge_ft": round(t.hob_to_fridge_ft, 2) if t else None,
            "triangle_fridge_sink_ft": round(t.fridge_to_sink_ft, 2) if t else None,
            "triangle_total_ft": round(t.perimeter_ft, 2) if t else None,
            "circulation_connectivity": evaluation.circulation_connectivity,
            "walkable_ratio": evaluation.circulation_walkable_ratio,
            "failed": ", ".join(evaluation.failed),
            "warnings": ", ".join(evaluation.warnings),
        })
    return rows
