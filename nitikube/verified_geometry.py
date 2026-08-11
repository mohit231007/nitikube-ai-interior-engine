from __future__ import annotations

from dataclasses import asdict, dataclass
import json
import math
import re
from typing import Iterable, Sequence


Point = tuple[float, float]


@dataclass(frozen=True)
class VerifiedRoom:
    room_id: str
    name: str
    polygon_ft: tuple[Point, ...]
    ceiling_height_ft: float
    verified: bool = True
    source: str = "manual"

    @property
    def area_ft2(self) -> float:
        return polygon_area(self.polygon_ft)

    @property
    def bounds_ft(self) -> tuple[float, float, float, float]:
        xs = [p[0] for p in self.polygon_ft]
        ys = [p[1] for p in self.polygon_ft]
        return min(xs), min(ys), max(xs), max(ys)


@dataclass(frozen=True)
class VerifiedOpening:
    opening_id: str
    kind: str
    start_ft: Point
    end_ft: Point
    room_a: str | None = None
    room_b: str | None = None
    verified: bool = True
    source: str = "manual"

    @property
    def width_ft(self) -> float:
        return math.dist(self.start_ft, self.end_ft)


@dataclass(frozen=True)
class AdjacencyEdge:
    room_a: str
    room_b: str
    shared_boundary_ft: float
    connected_by_opening: bool = False
    opening_ids: tuple[str, ...] = ()


def parse_length_ft(value: str | float | int) -> float:
    """Parse common architectural lengths into decimal feet.

    Supported examples: 10.5, "10.5 ft", "10' 7\"", "10 ft 7 in",
    "127 in". Plain numbers are interpreted as feet. This parser is
    deterministic and intentionally does not attempt OCR correction.
    """
    if isinstance(value, (int, float)):
        result = float(value)
        if result < 0:
            raise ValueError("length cannot be negative")
        return result

    text = value.strip().lower().replace("′", "'").replace("″", '"')
    if not text:
        raise ValueError("length cannot be empty")

    try:
        result = float(text)
        if result < 0:
            raise ValueError("length cannot be negative")
        return result
    except ValueError:
        pass

    inch_only = re.fullmatch(r"\s*([0-9]+(?:\.[0-9]+)?)\s*(?:in|inch|inches|\")\s*", text)
    if inch_only:
        return float(inch_only.group(1)) / 12.0

    feet_decimal = re.fullmatch(r"\s*([0-9]+(?:\.[0-9]+)?)\s*(?:ft|feet|foot|')\s*", text)
    if feet_decimal:
        return float(feet_decimal.group(1))

    patterns = [
        r"\s*(\d+(?:\.\d+)?)\s*'\s*(\d+(?:\.\d+)?)?\s*(?:\"|in|inch|inches)?\s*",
        r"\s*(\d+(?:\.\d+)?)\s*(?:ft|feet|foot)\s*(\d+(?:\.\d+)?)?\s*(?:in|inch|inches|\")?\s*",
    ]
    for pattern in patterns:
        match = re.fullmatch(pattern, text)
        if match:
            feet = float(match.group(1))
            inches = float(match.group(2) or 0.0)
            if inches >= 12:
                raise ValueError("inch component must be less than 12")
            return feet + inches / 12.0

    raise ValueError(f"Unsupported architectural length: {value!r}")


def rectangle_room(
    room_id: str,
    name: str,
    x_ft: float,
    y_ft: float,
    width_ft: float,
    height_ft: float,
    ceiling_height_ft: float,
    *,
    verified: bool = True,
    source: str = "manual",
) -> VerifiedRoom:
    for label, number in {
        "x_ft": x_ft,
        "y_ft": y_ft,
        "width_ft": width_ft,
        "height_ft": height_ft,
        "ceiling_height_ft": ceiling_height_ft,
    }.items():
        if not math.isfinite(float(number)):
            raise ValueError(f"{label} must be finite")
    if width_ft <= 0 or height_ft <= 0 or ceiling_height_ft <= 0:
        raise ValueError("width, height and ceiling height must be positive")
    polygon = (
        (float(x_ft), float(y_ft)),
        (float(x_ft + width_ft), float(y_ft)),
        (float(x_ft + width_ft), float(y_ft + height_ft)),
        (float(x_ft), float(y_ft + height_ft)),
    )
    room = VerifiedRoom(
        room_id=str(room_id).strip(),
        name=str(name).strip(),
        polygon_ft=polygon,
        ceiling_height_ft=float(ceiling_height_ft),
        verified=bool(verified),
        source=str(source),
    )
    validate_room(room)
    return room


def polygon_area(points: Sequence[Point]) -> float:
    if len(points) < 3:
        raise ValueError("polygon requires at least three points")
    total = 0.0
    for i, (x1, y1) in enumerate(points):
        x2, y2 = points[(i + 1) % len(points)]
        total += x1 * y2 - x2 * y1
    return abs(total) / 2.0


def polygon_centroid(points: Sequence[Point]) -> Point:
    signed_twice_area = 0.0
    cx = 0.0
    cy = 0.0
    for i, (x1, y1) in enumerate(points):
        x2, y2 = points[(i + 1) % len(points)]
        cross = x1 * y2 - x2 * y1
        signed_twice_area += cross
        cx += (x1 + x2) * cross
        cy += (y1 + y2) * cross
    if abs(signed_twice_area) < 1e-12:
        raise ValueError("polygon area must be non-zero")
    factor = 1.0 / (3.0 * signed_twice_area)
    return cx * factor, cy * factor


def _orientation(a: Point, b: Point, c: Point, tol: float = 1e-9) -> int:
    value = (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])
    if abs(value) <= tol:
        return 0
    return 1 if value > 0 else -1


def _on_segment(a: Point, b: Point, p: Point, tol: float = 1e-9) -> bool:
    return (
        min(a[0], b[0]) - tol <= p[0] <= max(a[0], b[0]) + tol
        and min(a[1], b[1]) - tol <= p[1] <= max(a[1], b[1]) + tol
        and _orientation(a, b, p, tol) == 0
    )


def _segments_intersect(a: Point, b: Point, c: Point, d: Point, tol: float = 1e-9) -> bool:
    o1 = _orientation(a, b, c, tol)
    o2 = _orientation(a, b, d, tol)
    o3 = _orientation(c, d, a, tol)
    o4 = _orientation(c, d, b, tol)
    if o1 != o2 and o3 != o4:
        return True
    return (
        (o1 == 0 and _on_segment(a, b, c, tol))
        or (o2 == 0 and _on_segment(a, b, d, tol))
        or (o3 == 0 and _on_segment(c, d, a, tol))
        or (o4 == 0 and _on_segment(c, d, b, tol))
    )


def validate_room(room: VerifiedRoom) -> None:
    if not room.room_id:
        raise ValueError("room_id cannot be empty")
    if not room.name:
        raise ValueError("room name cannot be empty")
    if room.ceiling_height_ft <= 0:
        raise ValueError("ceiling height must be positive")
    points = room.polygon_ft
    if len(points) < 3:
        raise ValueError("room polygon requires at least three points")
    if polygon_area(points) <= 1e-9:
        raise ValueError("room polygon must have non-zero area")
    for i in range(len(points)):
        if math.dist(points[i], points[(i + 1) % len(points)]) <= 1e-9:
            raise ValueError("room polygon contains a zero-length edge")
    edges = [(points[i], points[(i + 1) % len(points)]) for i in range(len(points))]
    for i, edge_a in enumerate(edges):
        for j, edge_b in enumerate(edges):
            if j <= i:
                continue
            if j in {i - 1, i + 1} or (i == 0 and j == len(edges) - 1):
                continue
            if _segments_intersect(*edge_a, *edge_b):
                raise ValueError(f"room {room.room_id} polygon self-intersects")


def _collinear_overlap_length(a: Point, b: Point, c: Point, d: Point, tol: float = 1e-7) -> float:
    ab = (b[0] - a[0], b[1] - a[1])
    length = math.hypot(*ab)
    if length <= tol:
        return 0.0
    if abs(ab[0] * (c[1] - a[1]) - ab[1] * (c[0] - a[0])) > tol * length:
        return 0.0
    if abs(ab[0] * (d[1] - a[1]) - ab[1] * (d[0] - a[0])) > tol * length:
        return 0.0
    ux, uy = ab[0] / length, ab[1] / length
    t_c = (c[0] - a[0]) * ux + (c[1] - a[1]) * uy
    t_d = (d[0] - a[0]) * ux + (d[1] - a[1]) * uy
    low = max(0.0, min(t_c, t_d))
    high = min(length, max(t_c, t_d))
    return max(0.0, high - low)


def shared_boundary_length(room_a: VerifiedRoom, room_b: VerifiedRoom, tol: float = 1e-7) -> float:
    total = 0.0
    a_points = room_a.polygon_ft
    b_points = room_b.polygon_ft
    for i, a1 in enumerate(a_points):
        a2 = a_points[(i + 1) % len(a_points)]
        for j, b1 in enumerate(b_points):
            b2 = b_points[(j + 1) % len(b_points)]
            total += _collinear_overlap_length(a1, a2, b1, b2, tol)
    return total


def _point_on_polygon_boundary(point: Point, room: VerifiedRoom, tol: float = 1e-6) -> bool:
    points = room.polygon_ft
    return any(_on_segment(points[i], points[(i + 1) % len(points)], point, tol) for i in range(len(points)))


def opening_boundary_rooms(opening: VerifiedOpening, rooms: Sequence[VerifiedRoom], tol: float = 1e-5) -> tuple[str, ...]:
    matches = []
    for room in rooms:
        if _point_on_polygon_boundary(opening.start_ft, room, tol) and _point_on_polygon_boundary(opening.end_ft, room, tol):
            matches.append(room.room_id)
    return tuple(matches)


def validate_opening(opening: VerifiedOpening, rooms: Sequence[VerifiedRoom] | None = None) -> None:
    if not opening.opening_id:
        raise ValueError("opening_id cannot be empty")
    if opening.kind.lower() not in {"door", "window", "opening"}:
        raise ValueError("opening kind must be door, window or opening")
    if opening.width_ft <= 1e-9:
        raise ValueError("opening must have positive width")
    if rooms is not None and opening.verified:
        matches = opening_boundary_rooms(opening, rooms)
        declared = {r for r in (opening.room_a, opening.room_b) if r}
        if declared and not declared.issubset(set(matches)):
            raise ValueError(
                f"opening {opening.opening_id} is not geometrically on every declared room boundary; "
                f"boundary matches={matches}"
            )
        if not matches:
            raise ValueError(f"opening {opening.opening_id} does not lie on a verified room boundary")


def build_adjacency_graph(
    rooms: Sequence[VerifiedRoom],
    openings: Sequence[VerifiedOpening] = (),
    *,
    min_shared_boundary_ft: float = 0.05,
    verified_only: bool = True,
) -> tuple[AdjacencyEdge, ...]:
    active_rooms = [room for room in rooms if room.verified or not verified_only]
    room_ids = {room.room_id for room in active_rooms}
    opening_map: dict[frozenset[str], list[str]] = {}
    for opening in openings:
        if verified_only and not opening.verified:
            continue
        linked = [r for r in (opening.room_a, opening.room_b) if r in room_ids]
        if len(linked) == 2:
            opening_map.setdefault(frozenset(linked), []).append(opening.opening_id)

    edges: list[AdjacencyEdge] = []
    for i, room_a in enumerate(active_rooms):
        for room_b in active_rooms[i + 1 :]:
            shared = shared_boundary_length(room_a, room_b)
            key = frozenset((room_a.room_id, room_b.room_id))
            opening_ids = tuple(opening_map.get(key, []))
            if shared >= min_shared_boundary_ft or opening_ids:
                edges.append(
                    AdjacencyEdge(
                        room_a=room_a.room_id,
                        room_b=room_b.room_id,
                        shared_boundary_ft=shared,
                        connected_by_opening=bool(opening_ids),
                        opening_ids=opening_ids,
                    )
                )
    return tuple(edges)


def validate_geometry(rooms: Sequence[VerifiedRoom], openings: Sequence[VerifiedOpening] = ()) -> list[str]:
    errors: list[str] = []
    seen_rooms: set[str] = set()
    for room in rooms:
        if room.room_id in seen_rooms:
            errors.append(f"duplicate room_id: {room.room_id}")
        seen_rooms.add(room.room_id)
        try:
            validate_room(room)
        except ValueError as exc:
            errors.append(str(exc))

    seen_openings: set[str] = set()
    room_lookup = {room.room_id for room in rooms}
    for opening in openings:
        if opening.opening_id in seen_openings:
            errors.append(f"duplicate opening_id: {opening.opening_id}")
        seen_openings.add(opening.opening_id)
        for declared in (opening.room_a, opening.room_b):
            if declared and declared not in room_lookup:
                errors.append(f"opening {opening.opening_id} references unknown room {declared}")
        try:
            validate_opening(opening, rooms)
        except ValueError as exc:
            errors.append(str(exc))
    return errors


def geometry_to_project_json(
    project_name: str,
    rooms: Sequence[VerifiedRoom],
    openings: Sequence[VerifiedOpening] = (),
    *,
    location: str | None = None,
    notes: Sequence[str] = (),
    indent: int = 2,
) -> str:
    payload = {
        "schema": "nitikube.verified_geometry",
        "schema_version": "0.7",
        "project_name": project_name,
        "location": location,
        "rooms": [asdict(room) for room in rooms],
        "openings": [asdict(opening) for opening in openings],
        "notes": list(notes),
    }
    return json.dumps(payload, indent=indent, ensure_ascii=False)


def geometry_from_project_json(payload: str) -> tuple[str, list[VerifiedRoom], list[VerifiedOpening], dict]:
    data = json.loads(payload)
    if data.get("schema") != "nitikube.verified_geometry":
        raise ValueError("unsupported geometry schema")
    rooms = [
        VerifiedRoom(
            room_id=item["room_id"],
            name=item["name"],
            polygon_ft=tuple(tuple(float(v) for v in point) for point in item["polygon_ft"]),
            ceiling_height_ft=float(item["ceiling_height_ft"]),
            verified=bool(item.get("verified", True)),
            source=item.get("source", "imported"),
        )
        for item in data.get("rooms", [])
    ]
    openings = [
        VerifiedOpening(
            opening_id=item["opening_id"],
            kind=item["kind"],
            start_ft=tuple(float(v) for v in item["start_ft"]),
            end_ft=tuple(float(v) for v in item["end_ft"]),
            room_a=item.get("room_a"),
            room_b=item.get("room_b"),
            verified=bool(item.get("verified", True)),
            source=item.get("source", "imported"),
        )
        for item in data.get("openings", [])
    ]
    errors = validate_geometry(rooms, openings)
    if errors:
        raise ValueError("invalid verified geometry: " + "; ".join(errors))
    metadata = {k: v for k, v in data.items() if k not in {"rooms", "openings"}}
    return data.get("project_name", "NitiKube Project"), rooms, openings, metadata


def geometry_svg(
    rooms: Sequence[VerifiedRoom],
    openings: Sequence[VerifiedOpening] = (),
    *,
    padding_px: int = 50,
    scale_px_per_ft: float = 24.0,
) -> str:
    if scale_px_per_ft <= 0:
        raise ValueError("scale_px_per_ft must be positive")
    if not rooms:
        raise ValueError("at least one room is required")
    all_points = [point for room in rooms for point in room.polygon_ft]
    min_x = min(p[0] for p in all_points)
    min_y = min(p[1] for p in all_points)
    max_x = max(p[0] for p in all_points)
    max_y = max(p[1] for p in all_points)
    width = max(300, int((max_x - min_x) * scale_px_per_ft + 2 * padding_px))
    height = max(300, int((max_y - min_y) * scale_px_per_ft + 2 * padding_px))

    def tx(point: Point) -> tuple[float, float]:
        return (
            padding_px + (point[0] - min_x) * scale_px_per_ft,
            padding_px + (point[1] - min_y) * scale_px_per_ft,
        )

    chunks = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="#ffffff"/>',
        '<g font-family="Arial, sans-serif">',
    ]
    for room in rooms:
        pts = " ".join(f"{x:.1f},{y:.1f}" for x, y in map(tx, room.polygon_ft))
        fill = "#eef6ff" if room.verified else "#f3f4f6"
        stroke = "#16324f" if room.verified else "#9ca3af"
        chunks.append(f'<polygon points="{pts}" fill="{fill}" stroke="{stroke}" stroke-width="3"/>')
        cx, cy = tx(polygon_centroid(room.polygon_ft))
        label = _xml_escape(room.name)
        status = "verified" if room.verified else "proposal"
        chunks.append(f'<text x="{cx:.1f}" y="{cy:.1f}" text-anchor="middle" font-size="15" font-weight="700" fill="#111827">{label}</text>')
        chunks.append(f'<text x="{cx:.1f}" y="{cy + 18:.1f}" text-anchor="middle" font-size="11" fill="#4b5563">{room.area_ft2:.1f} ft² · {status}</text>')
    for opening in openings:
        x1, y1 = tx(opening.start_ft)
        x2, y2 = tx(opening.end_ft)
        color = "#d97706" if opening.kind.lower() == "door" else "#059669"
        opacity = "1" if opening.verified else "0.45"
        chunks.append(
            f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" '
            f'stroke="{color}" stroke-width="7" stroke-linecap="round" opacity="{opacity}"/>'
        )
    chunks.append('</g></svg>')
    return "".join(chunks)


def _xml_escape(value: str) -> str:
    return (
        value.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&apos;")
    )
