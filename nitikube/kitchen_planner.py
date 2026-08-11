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
    wall_margin_ft: float = 0.0
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


_EPS = 1e-8


def validate_work_center_spec(spec: WorkCenterSpec) -> None:
    if not spec.center_id.strip() or not spec.label.strip():
        raise ValueError("work-center id and label are required")
    if spec.width_along_run_ft <= 0 or spec.depth_ft <= 0:
        raise ValueError(f"{spec.center_id}: work-center dimensions must be positive")


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
    if counter_depth_ft <= 0:
        raise ValueError("counter depth must be positive")
    if wall_margin_ft < 0:
        raise ValueError("wall margin cannot be negative")
    if 2 * wall_margin_ft >= min(room.width_ft, room.depth_ft):
        raise ValueError("wall margin is too large for the room")

    if wall == "top":
        rect = Rect(
            room.x_ft + wall_margin_ft,
            room.y_ft + wall_margin_ft,
            room.width_ft - 2 * wall_margin_ft,
            counter_depth_ft,
        )
    elif wall == "bottom":
        rect = Rect(
            room.x_ft + wall_margin_ft,
            room.bottom_ft - wall_margin_ft - counter_depth_ft,
            room.width_ft - 2 * wall_margin_ft,
            counter_depth_ft,
        )
    elif wall == "left":
        rect = Rect(
            room.x_ft + wall_margin_ft,
            room.y_ft + wall_margin_ft,
            counter_depth_ft,
            room.depth_ft - 2 * wall_margin_ft,
        )
    else:
        rect = Rect(
            room.right_ft - wall_margin_ft - counter_depth_ft,
            room.y_ft + wall_margin_ft,
            counter_depth_ft,
            room.depth_ft - 2 * wall_margin_ft,
        )
    if not rect_contains(room, rect):
        raise ValueError("counter depth/margin places the run outside the room")
    return CounterRun(run_id or f"run-{wall}", wall, rect)


def place_work_center(
    run: CounterRun,
    spec: WorkCenterSpec,
    fraction_along_run: float,
) -> PlacedWorkCenter:
    validate_work_center_spec(spec)
    if not 0 <= fraction_along_run <= 1:
        raise ValueError("fraction_along_run must be in [0,1]")
    if spec.width_along_run_ft > run.length_ft + _EPS:
        raise ValueError(f"{spec.center_id}: module is wider than counter run {run.run_id}")
    if spec.depth_ft > run.depth_ft + _EPS:
        raise ValueError(f"{spec.center_id}: module depth exceeds counter run depth")

    usable = run.length_ft - spec.width_along_run_ft
    start_along = usable * fraction_along_run
    if run.wall in {"top", "bottom"}:
        x = run.rect.x_ft + start_along
        # Align to the wall-side edge of the counter footprint.
        y = run.rect.y_ft if run.wall == "top" else run.rect.bottom_ft - spec.depth_ft
        rect = Rect(x, y, spec.width_along_run_ft, spec.depth_ft)
    else:
        y = run.rect.y_ft + start_along
        x = run.rect.x_ft if run.wall == "left" else run.rect.right_ft - spec.depth_ft
        rect = Rect(x, y, spec.depth_ft, spec.width_along_run_ft)
    return PlacedWorkCenter(spec, run.run_id, fraction_along_run, rect)


def _rect_union_area(rectangles: Sequence[Rect]) -> float:
    if not rectangles:
        return 0.0
    xs = sorted({value for rect in rectangles for value in (rect.x_ft, rect.right_ft)})
    area = 0.0
    for x0, x1 in zip(xs, xs[1:]):
        if x1 - x0 <= _EPS:
            continue
        intervals = []
        probe = (x0 + x1) / 2.0
        for rect in rectangles:
            if rect.x_ft - _EPS <= probe <= rect.right_ft + _EPS:
                intervals.append((rect.y_ft, rect.bottom_ft))
        if not intervals:
            continue
        intervals.sort()
        merged_length = 0.0
        start, end = intervals[0]
        for next_start, next_end in intervals[1:]:
            if next_start <= end + _EPS:
                end = max(end, next_end)
            else:
                merged_length += end - start
                start, end = next_start, next_end
        merged_length += end - start
        area += (x1 - x0) * merged_length
    return area


def work_triangle(work_centers: Sequence[PlacedWorkCenter]) -> WorkTriangle | None:
    by_id = {center.spec.center_id.casefold(): center for center in work_centers}
    required = ("sink", "hob", "fridge")
    if not all(name in by_id for name in required):
        return None
    sink = by_id["sink"].center
    hob = by_id["hob"].center
    fridge = by_id["fridge"].center
    sh = math.dist(sink, hob)
    hf = math.dist(hob, fridge)
    fs = math.dist(fridge, sink)
    area = abs(
        sink[0] * (hob[1] - fridge[1])
        + hob[0] * (fridge[1] - sink[1])
        + fridge[0] * (sink[1] - hob[1])
    ) / 2.0
    return WorkTriangle(sh, hf, fs, sh + hf + fs, area)


def _triangle_constraint_failures(triangle: WorkTriangle | None, requirements: KitchenRequirements) -> list[str]:
    thresholds = (
        requirements.work_triangle_leg_min_ft,
        requirements.work_triangle_leg_max_ft,
        requirements.work_triangle_total_min_ft,
        requirements.work_triangle_total_max_ft,
    )
    if triangle is None:
        return ["work_triangle_missing"] if any(value is not None for value in thresholds) else []
    failed = []
    if requirements.work_triangle_leg_min_ft is not None and min(triangle.legs) < requirements.work_triangle_leg_min_ft:
        failed.append("work_triangle_leg_below_min")
    if requirements.work_triangle_leg_max_ft is not None and max(triangle.legs) > requirements.work_triangle_leg_max_ft:
        failed.append("work_triangle_leg_above_max")
    if requirements.work_triangle_total_min_ft is not None and triangle.perimeter_ft < requirements.work_triangle_total_min_ft:
        failed.append("work_triangle_total_below_min")
    if requirements.work_triangle_total_max_ft is not None and triangle.perimeter_ft > requirements.work_triangle_total_max_ft:
        failed.append("work_triangle_total_above_max")
    return failed


def evaluate_kitchen(
    room: Rect,
    candidate: KitchenCandidate,
    *,
    keepouts: Sequence[KeepoutZone] = (),
    requirements: KitchenRequirements | None = None,
) -> KitchenEvaluation:
    requirements = requirements or KitchenRequirements()
    if requirements.wall_margin_ft < 0 or requirements.min_counter_run_ft < 0 or requirements.passage_width_ft < 0:
        raise ValueError("kitchen requirements cannot contain negative clearances")
    if requirements.grid_step_ft <= 0:
        raise ValueError("grid_step_ft must be positive")

    failed: list[str] = []
    warnings: list[str] = []
    run_ids = set()
    for run in candidate.counter_runs:
        if run.wall not in _WALLS:
            failed.append(f"invalid_wall:{run.run_id}")
        if run.run_id in run_ids:
            failed.append(f"duplicate_run_id:{run.run_id}")
        run_ids.add(run.run_id)
        if not rect_contains(room, run.rect):
            failed.append(f"counter_outside_room:{run.run_id}")
        if run.length_ft + _EPS < requirements.min_counter_run_ft:
            failed.append(f"counter_run_too_short:{run.run_id}")
        for keepout in keepouts:
            if rect_overlap(run.rect, keepout.rect):
                failed.append(f"counter_keepout_collision:{run.run_id}:{keepout.zone_id}")

    center_ids = set()
    for center in candidate.work_centers:
        if center.spec.center_id in center_ids:
            failed.append(f"duplicate_work_center:{center.spec.center_id}")
        center_ids.add(center.spec.center_id)
        matching_run = next((run for run in candidate.counter_runs if run.run_id == center.run_id), None)
        if matching_run is None:
            failed.append(f"work_center_missing_run:{center.spec.center_id}")
        elif not rect_contains(matching_run.rect, center.rect):
            failed.append(f"work_center_outside_run:{center.spec.center_id}")
        for keepout in keepouts:
            if rect_overlap(center.rect, keepout.rect):
                failed.append(f"work_center_keepout_collision:{center.spec.center_id}:{keepout.zone_id}")

    # Work centers represent modules inside counter runs and must not occupy the
    # same physical module footprint.
    for index, a in enumerate(candidate.work_centers):
        for b in candidate.work_centers[index + 1 :]:
            if rect_overlap(a.rect, b.rect):
                failed.append(f"work_center_collision:{a.spec.center_id}:{b.spec.center_id}")

    triangle = work_triangle(candidate.work_centers)
    failed.extend(_triangle_constraint_failures(triangle, requirements))

    circulation_connectivity = None
    walkable_ratio = None
    if requirements.passage_width_ft > 0 and candidate.counter_runs:
        circulation_connectivity, walkable_ratio = circulation_metrics(
            room,
            [run.rect for run in candidate.counter_runs] + [zone.rect for zone in keepouts],
            passage_width_ft=requirements.passage_width_ft,
            grid_step_ft=requirements.grid_step_ft,
        )
        if requirements.require_connected_passage and circulation_connectivity < 0.95:
            failed.append("passage_not_connected_at_requested_width")
        elif circulation_connectivity < 0.95:
            warnings.append("walkable_space_fragmented_at_requested_width")

    gross_run = sum(run.length_ft for run in candidate.counter_runs)
    counter_area = _rect_union_area([run.rect for run in candidate.counter_runs])

    # Geometry score ranks only candidates surviving or approaching the same
    # visible constraints. It is not an aesthetic or code-compliance score.
    run_component = min(1.0, gross_run / max(room.width_ft + room.depth_ft, _EPS))
    open_component = 1.0 - min(1.0, counter_area / room.area_ft2)
    circulation_component = 1.0 if circulation_connectivity is None else circulation_connectivity
    triangle_component = 0.0
    if triangle is not None:
        # Non-degenerate triangle gets more geometry credit than three nearly
        # collinear centers, while no hidden optimum perimeter is assumed.
        triangle_component = min(1.0, triangle.area_ft2 / max(room.area_ft2 * 0.08, _EPS))
    score = 100.0 * (
        0.25 * run_component
        + 0.25 * open_component
        + 0.30 * circulation_component
        + 0.20 * triangle_component
    )
    if failed:
        score = min(score, 49.99)

    return KitchenEvaluation(
        layout_id=candidate.layout_id,
        feasible=not failed,
        failed=tuple(dict.fromkeys(failed)),
        warnings=tuple(dict.fromkeys(warnings)),
        gross_counter_run_ft=gross_run,
        countertop_union_area_ft2=counter_area,
        work_triangle=triangle,
        circulation_connectivity=circulation_connectivity,
        circulation_walkable_ratio=walkable_ratio,
        geometry_score=round(score, 2),
    )


def _work_centers_for_runs(
    runs: Sequence[CounterRun],
    sink: WorkCenterSpec,
    hob: WorkCenterSpec,
    fridge: WorkCenterSpec,
) -> tuple[PlacedWorkCenter, ...]:
    if not runs:
        raise ValueError("at least one counter run is required")
    if len(runs) == 1:
        assignments = ((fridge, runs[0], 0.02), (sink, runs[0], 0.50), (hob, runs[0], 0.98))
    elif len(runs) == 2:
        assignments = ((sink, runs[0], 0.50), (hob, runs[1], 0.50), (fridge, runs[0], 0.02))
    else:
        assignments = ((sink, runs[0], 0.50), (hob, runs[1], 0.50), (fridge, runs[2], 0.50))
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
    """Generate transparent wall-run candidates for a rectangular kitchen.

    Counter depth, wall margin and work-center module sizes are inputs. The
    generator does not embed jurisdictional aisle/work-triangle standards.
    Candidates that cannot physically contain the modules are skipped.
    """
    for spec in (sink, hob, fridge):
        validate_work_center_spec(spec)
    if counter_depth_ft <= 0:
        raise ValueError("counter_depth_ft must be positive")

    candidates: list[KitchenCandidate] = []
    counter = 1

    def add(kind: KitchenLayoutKind, walls: Sequence[str], name: str) -> None:
        nonlocal counter
        try:
            runs = tuple(
                counter_run_for_wall(
                    room,
                    wall,
                    counter_depth_ft=counter_depth_ft,
                    wall_margin_ft=wall_margin_ft,
                    run_id=f"{kind.value}-{wall}",
                )
                for wall in walls
            )
            centers = _work_centers_for_runs(runs, sink, hob, fridge)
        except ValueError:
            return
        candidates.append(
            KitchenCandidate(
                layout_id=f"K-{counter:02d}",
                name=name,
                kind=kind,
                counter_runs=runs,
                work_centers=centers,
                notes=(
                    "Generated from rectangular verified/manual room geometry.",
                    "Work-triangle and passage thresholds are evaluated separately as explicit inputs.",
                ),
            )
        )
        counter += 1

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
        for walls in (
            ("top", "left", "right"),
            ("bottom", "left", "right"),
            ("left", "top", "bottom"),
            ("right", "top", "bottom"),
        ):
            add(KitchenLayoutKind.U_SHAPE, walls, f"U-shape · {' + '.join(walls)}")
    return tuple(candidates)


def rank_kitchens(
    room: Rect,
    candidates: Iterable[KitchenCandidate],
    *,
    keepouts: Sequence[KeepoutZone] = (),
    requirements: KitchenRequirements | None = None,
) -> list[tuple[KitchenCandidate, KitchenEvaluation]]:
    evaluated = [
        (candidate, evaluate_kitchen(room, candidate, keepouts=keepouts, requirements=requirements))
        for candidate in candidates
    ]
    return sorted(
        evaluated,
        key=lambda pair: (
            pair[1].feasible,
            pair[1].geometry_score,
            pair[1].circulation_connectivity or 0.0,
            pair[1].gross_counter_run_ft,
        ),
        reverse=True,
    )


def kitchen_quantity_summary(
    candidate: KitchenCandidate,
    evaluation: KitchenEvaluation,
    *,
    base_cabinet_height_ft: float,
    wall_cabinet_height_ft: float = 0.0,
    wall_cabinet_run_fraction: float = 0.0,
    countertop_waste_fraction: float = 0.0,
) -> dict[str, float]:
    if base_cabinet_height_ft <= 0:
        raise ValueError("base_cabinet_height_ft must be positive")
    if wall_cabinet_height_ft < 0:
        raise ValueError("wall_cabinet_height_ft cannot be negative")
    if not 0 <= wall_cabinet_run_fraction <= 1:
        raise ValueError("wall_cabinet_run_fraction must be in [0,1]")
    if countertop_waste_fraction < 0:
        raise ValueError("countertop_waste_fraction cannot be negative")
    gross_run = evaluation.gross_counter_run_ft
    return {
        "gross_counter_run_ft": gross_run,
        "base_cabinet_front_area_ft2": gross_run * base_cabinet_height_ft,
        "wall_cabinet_run_ft": gross_run * wall_cabinet_run_fraction,
        "wall_cabinet_front_area_ft2": gross_run * wall_cabinet_run_fraction * wall_cabinet_height_ft,
        "countertop_geometric_area_ft2": evaluation.countertop_union_area_ft2,
        "countertop_purchase_area_ft2": evaluation.countertop_union_area_ft2 * (1.0 + countertop_waste_fraction),
    }


def kitchen_svg(
    room: Rect,
    candidate: KitchenCandidate,
    evaluation: KitchenEvaluation | None = None,
    *,
    keepouts: Sequence[KeepoutZone] = (),
    pixels_per_foot: float = 32.0,
    margin_px: float = 55.0,
) -> str:
    if pixels_per_foot <= 0:
        raise ValueError("pixels_per_foot must be positive")
    room_w = room.width_ft * pixels_per_foot
    room_h = room.depth_ft * pixels_per_foot
    side_panel = 360.0
    width = room_w + 2 * margin_px + side_panel
    height = max(room_h + 2 * margin_px, 560.0)
    x0, y0 = margin_px, margin_px

    def sx(x: float) -> float:
        return x0 + (x - room.x_ft) * pixels_per_foot

    def sy(y: float) -> float:
        return y0 + (y - room.y_ft) * pixels_per_foot

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width:.0f}" height="{height:.0f}" viewBox="0 0 {width:.0f} {height:.0f}">',
        '<rect width="100%" height="100%" fill="#fff"/>',
        '<style>text{font-family:Arial,sans-serif;fill:#17202a}.wall{fill:#fff;stroke:#1f2937;stroke-width:4}.counter{fill:#e5e7eb;stroke:#475569;stroke-width:1.5}.keepout{fill:#fef3c7;stroke:#d97706;stroke-width:1.5;stroke-dasharray:4 3}.sink{fill:#dbeafe;stroke:#2563eb}.hob{fill:#fee2e2;stroke:#dc2626}.fridge{fill:#dcfce7;stroke:#16a34a}.center{stroke-width:2}.label{font-size:11px}.title{font-size:18px;font-weight:700}.note{font-size:12px}</style>',
        f'<rect class="wall" x="{x0:.1f}" y="{y0:.1f}" width="{room_w:.1f}" height="{room_h:.1f}"/>',
    ]
    for zone in keepouts:
        rect = zone.rect
        parts.append(
            f'<rect class="keepout" x="{sx(rect.x_ft):.1f}" y="{sy(rect.y_ft):.1f}" width="{rect.width_ft * pixels_per_foot:.1f}" height="{rect.depth_ft * pixels_per_foot:.1f}"/>'
        )
    for run in candidate.counter_runs:
        rect = run.rect
        parts.append(
            f'<rect class="counter" x="{sx(rect.x_ft):.1f}" y="{sy(rect.y_ft):.1f}" width="{rect.width_ft * pixels_per_foot:.1f}" height="{rect.depth_ft * pixels_per_foot:.1f}"/>'
        )
    for center in candidate.work_centers:
        rect = center.rect
        css = center.spec.center_id.casefold() if center.spec.center_id.casefold() in {"sink", "hob", "fridge"} else "counter"
        parts.append(
            f'<rect class="center {css}" x="{sx(rect.x_ft):.1f}" y="{sy(rect.y_ft):.1f}" width="{rect.width_ft * pixels_per_foot:.1f}" height="{rect.depth_ft * pixels_per_foot:.1f}"/>'
        )
        cx, cy = center.center
        parts.append(f'<text class="label" x="{sx(cx):.1f}" y="{sy(cy):.1f}" text-anchor="middle">{escape(center.spec.label)}</text>')

    # Draw work triangle between actual module centers.
    triangle = evaluation.work_triangle if evaluation else work_triangle(candidate.work_centers)
    by_id = {center.spec.center_id.casefold(): center for center in candidate.work_centers}
    if triangle is not None and all(key in by_id for key in ("sink", "hob", "fridge")):
        points = [by_id[key].center for key in ("sink", "hob", "fridge", "sink")]
        path = " ".join(f"{sx(x):.1f},{sy(y):.1f}" for x, y in points)
        parts.append(f'<polyline points="{path}" fill="none" stroke="#7c3aed" stroke-width="2" stroke-dasharray="5 4"/>')

    panel_x = x0 + room_w + 30
    parts.append(f'<text class="title" x="{panel_x:.1f}" y="{y0 + 24:.1f}">{escape(candidate.name)}</text>')
    if evaluation:
        status = "FEASIBLE" if evaluation.feasible else "NOT FEASIBLE"
        lines = [
            f"Status: {status}",
            f"Geometry score: {evaluation.geometry_score:.1f}/100",
            f"Counter run: {evaluation.gross_counter_run_ft:.1f} ft",
            f"Countertop area: {evaluation.countertop_union_area_ft2:.1f} ft²",
        ]
        if triangle:
            lines += [
                f"Triangle perimeter: {triangle.perimeter_ft:.1f} ft",
                f"Triangle area: {triangle.area_ft2:.1f} ft²",
            ]
        if evaluation.circulation_connectivity is not None:
            lines.append(f"Walkable connectivity: {evaluation.circulation_connectivity:.1%}")
        y = y0 + 54
        for line in lines:
            parts.append(f'<text class="note" x="{panel_x:.1f}" y="{y:.1f}">{escape(line)}</text>')
            y += 20
        y += 10
        for failure in evaluation.failed[:8]:
            parts.append(f'<text class="note" x="{panel_x:.1f}" y="{y:.1f}">• {escape(failure)}</text>')
            y += 18
    parts.append('</svg>')
    return "".join(parts)


def evaluation_rows(ranked: Sequence[tuple[KitchenCandidate, KitchenEvaluation]]) -> list[dict]:
    rows = []
    for candidate, evaluation in ranked:
        triangle = evaluation.work_triangle
        rows.append(
            {
                "layout_id": candidate.layout_id,
                "kind": candidate.kind.value,
                "name": candidate.name,
                "feasible": evaluation.feasible,
                "geometry_score": evaluation.geometry_score,
                "gross_counter_run_ft": round(evaluation.gross_counter_run_ft, 2),
                "countertop_area_ft2": round(evaluation.countertop_union_area_ft2, 2),
                "triangle_sink_hob_ft": round(triangle.sink_to_hob_ft, 2) if triangle else None,
                "triangle_hob_fridge_ft": round(triangle.hob_to_fridge_ft, 2) if triangle else None,
                "triangle_fridge_sink_ft": round(triangle.fridge_to_sink_ft, 2) if triangle else None,
                "triangle_total_ft": round(triangle.perimeter_ft, 2) if triangle else None,
                "circulation_connectivity": evaluation.circulation_connectivity,
                "walkable_ratio": evaluation.circulation_walkable_ratio,
                "failed": ", ".join(evaluation.failed),
                "warnings": ", ".join(evaluation.warnings),
            }
        )
    return rows
