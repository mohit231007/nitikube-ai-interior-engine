from __future__ import annotations

from dataclasses import asdict, dataclass
import json
import math
from typing import Any, Iterable, Mapping, Sequence


Point2D = tuple[float, float]
Point3D = tuple[float, float, float]
Triangle = tuple[int, int, int]


@dataclass(frozen=True)
class Mesh3D:
    mesh_id: str
    label: str
    vertices: tuple[Point3D, ...]
    triangles: tuple[Triangle, ...]
    kind: str
    room_id: str | None = None


@dataclass(frozen=True)
class BoxObject:
    object_id: str
    label: str
    x_ft: float
    y_ft: float
    z_ft: float
    width_ft: float
    depth_ft: float
    height_ft: float
    room_id: str | None = None
    kind: str = "furniture"


@dataclass(frozen=True)
class SceneRoom:
    room_id: str
    name: str
    polygon_ft: tuple[Point2D, ...]
    wall_height_ft: float
    floor_z_ft: float = 0.0


@dataclass(frozen=True)
class OpeningLine:
    opening_id: str
    kind: str
    start_ft: Point2D
    end_ft: Point2D
    room_a: str | None = None
    room_b: str | None = None


def _signed_area(points: Sequence[Point2D]) -> float:
    return 0.5 * sum(
        x1 * y2 - x2 * y1
        for (x1, y1), (x2, y2) in zip(points, points[1:] + points[:1])
    )


def _clean_polygon(points: Sequence[Point2D]) -> tuple[Point2D, ...]:
    cleaned: list[Point2D] = []
    for raw in points:
        if len(raw) != 2:
            raise ValueError("polygon points must be x/y pairs")
        point = (float(raw[0]), float(raw[1]))
        if not all(math.isfinite(value) for value in point):
            raise ValueError("polygon coordinates must be finite")
        if not cleaned or math.dist(point, cleaned[-1]) > 1e-10:
            cleaned.append(point)
    if len(cleaned) >= 2 and math.dist(cleaned[0], cleaned[-1]) <= 1e-10:
        cleaned.pop()
    if len(cleaned) < 3:
        raise ValueError("polygon requires at least three distinct points")
    if abs(_signed_area(cleaned)) <= 1e-10:
        raise ValueError("polygon area is zero/degenerate")
    return tuple(cleaned)


def _cross(a: Point2D, b: Point2D, c: Point2D) -> float:
    return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])


def _point_in_triangle(point: Point2D, a: Point2D, b: Point2D, c: Point2D, *, eps: float = 1e-10) -> bool:
    c1 = _cross(a, b, point)
    c2 = _cross(b, c, point)
    c3 = _cross(c, a, point)
    has_neg = c1 < -eps or c2 < -eps or c3 < -eps
    has_pos = c1 > eps or c2 > eps or c3 > eps
    return not (has_neg and has_pos)


def triangulate_polygon(points: Sequence[Point2D]) -> tuple[Triangle, ...]:
    """Triangulate a simple polygon with deterministic ear clipping.

    The polygon may be clockwise or counter-clockwise. The algorithm fails
    closed if it cannot find an ear, which usually indicates self-intersection
    or other unsupported/degenerate geometry.
    """
    polygon = _clean_polygon(points)
    n = len(polygon)
    if n == 3:
        return ((0, 1, 2),)

    ccw = _signed_area(polygon) > 0
    remaining = list(range(n))
    triangles: list[Triangle] = []
    guard = 0
    while len(remaining) > 3:
        ear_found = False
        for position, current in enumerate(remaining):
            previous = remaining[position - 1]
            following = remaining[(position + 1) % len(remaining)]
            a, b, c = polygon[previous], polygon[current], polygon[following]
            cross = _cross(a, b, c)
            if (ccw and cross <= 1e-10) or ((not ccw) and cross >= -1e-10):
                continue
            contains_other = any(
                index not in {previous, current, following}
                and _point_in_triangle(polygon[index], a, b, c)
                for index in remaining
            )
            if contains_other:
                continue
            triangles.append((previous, current, following) if ccw else (following, current, previous))
            del remaining[position]
            ear_found = True
            break
        if not ear_found:
            raise ValueError("polygon could not be triangulated; verify that it is simple and non-degenerate")
        guard += 1
        if guard > n * n:
            raise ValueError("polygon triangulation exceeded safety guard")
    a, b, c = remaining
    triangles.append((a, b, c) if ccw else (c, b, a))
    return tuple(triangles)


def floor_mesh(room: SceneRoom) -> Mesh3D:
    if room.wall_height_ft <= 0:
        raise ValueError("wall_height_ft must be positive")
    polygon = _clean_polygon(room.polygon_ft)
    vertices = tuple((x, y, room.floor_z_ft) for x, y in polygon)
    return Mesh3D(
        mesh_id=f"floor:{room.room_id}",
        label=f"{room.name} floor",
        vertices=vertices,
        triangles=triangulate_polygon(polygon),
        kind="floor",
        room_id=room.room_id,
    )


def wall_mesh(room: SceneRoom) -> Mesh3D:
    if room.wall_height_ft <= 0:
        raise ValueError("wall_height_ft must be positive")
    polygon = _clean_polygon(room.polygon_ft)
    vertices: list[Point3D] = []
    triangles: list[Triangle] = []
    z0 = room.floor_z_ft
    z1 = z0 + room.wall_height_ft
    for start, end in zip(polygon, polygon[1:] + polygon[:1]):
        base = len(vertices)
        vertices.extend(
            [
                (start[0], start[1], z0),
                (end[0], end[1], z0),
                (end[0], end[1], z1),
                (start[0], start[1], z1),
            ]
        )
        triangles.extend([(base, base + 1, base + 2), (base, base + 2, base + 3)])
    return Mesh3D(
        mesh_id=f"walls:{room.room_id}",
        label=f"{room.name} walls",
        vertices=tuple(vertices),
        triangles=tuple(triangles),
        kind="walls",
        room_id=room.room_id,
    )


def ceiling_mesh(room: SceneRoom) -> Mesh3D:
    polygon = _clean_polygon(room.polygon_ft)
    z = room.floor_z_ft + room.wall_height_ft
    vertices = tuple((x, y, z) for x, y in polygon)
    return Mesh3D(
        mesh_id=f"ceiling:{room.room_id}",
        label=f"{room.name} ceiling",
        vertices=vertices,
        triangles=triangulate_polygon(polygon),
        kind="ceiling",
        room_id=room.room_id,
    )


def box_mesh(box: BoxObject) -> Mesh3D:
    if not box.object_id.strip() or not box.label.strip():
        raise ValueError("box object_id and label are required")
    if min(box.width_ft, box.depth_ft, box.height_ft) <= 0:
        raise ValueError("box dimensions must be positive")
    if not all(math.isfinite(value) for value in (
        box.x_ft, box.y_ft, box.z_ft, box.width_ft, box.depth_ft, box.height_ft
    )):
        raise ValueError("box geometry must be finite")
    x0, y0, z0 = box.x_ft, box.y_ft, box.z_ft
    x1, y1, z1 = x0 + box.width_ft, y0 + box.depth_ft, z0 + box.height_ft
    vertices = (
        (x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0),
        (x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1),
    )
    triangles = (
        (0, 1, 2), (0, 2, 3),
        (4, 6, 5), (4, 7, 6),
        (0, 4, 5), (0, 5, 1),
        (1, 5, 6), (1, 6, 2),
        (2, 6, 7), (2, 7, 3),
        (3, 7, 4), (3, 4, 0),
    )
    return Mesh3D(
        mesh_id=f"box:{box.object_id}",
        label=box.label,
        vertices=vertices,
        triangles=triangles,
        kind=box.kind,
        room_id=box.room_id,
    )


def build_scene_meshes(
    rooms: Sequence[SceneRoom],
    *,
    boxes: Sequence[BoxObject] = (),
    include_floor: bool = True,
    include_walls: bool = True,
    include_ceiling: bool = False,
) -> tuple[Mesh3D, ...]:
    if not rooms:
        raise ValueError("at least one scene room is required")
    meshes: list[Mesh3D] = []
    for room in rooms:
        if include_floor:
            meshes.append(floor_mesh(room))
        if include_walls:
            meshes.append(wall_mesh(room))
        if include_ceiling:
            meshes.append(ceiling_mesh(room))
    meshes.extend(box_mesh(box) for box in boxes)
    return tuple(meshes)


def scene_bounds(meshes: Sequence[Mesh3D]) -> tuple[Point3D, Point3D]:
    vertices = [vertex for mesh in meshes for vertex in mesh.vertices]
    if not vertices:
        raise ValueError("scene has no vertices")
    mins = tuple(min(vertex[axis] for vertex in vertices) for axis in range(3))
    maxs = tuple(max(vertex[axis] for vertex in vertices) for axis in range(3))
    return mins, maxs


def box_from_dict(data: Mapping[str, Any]) -> BoxObject:
    return BoxObject(
        object_id=str(data.get("object_id") or ""),
        label=str(data.get("label") or data.get("object_id") or ""),
        x_ft=float(data["x_ft"]),
        y_ft=float(data["y_ft"]),
        z_ft=float(data.get("z_ft", 0.0)),
        width_ft=float(data["width_ft"]),
        depth_ft=float(data["depth_ft"]),
        height_ft=float(data["height_ft"]),
        room_id=str(data["room_id"]) if data.get("room_id") not in {None, ""} else None,
        kind=str(data.get("kind") or "furniture"),
    )


def load_boxes_json(payload: str | bytes) -> list[BoxObject]:
    if isinstance(payload, bytes):
        payload = payload.decode("utf-8")
    data = json.loads(payload)
    rows = data.get("boxes") if isinstance(data, dict) else data
    if not isinstance(rows, list):
        raise ValueError("box JSON must be a list or {'boxes': [...]} object")
    boxes = [box_from_dict(row) for row in rows]
    ids = [box.object_id for box in boxes]
    if len(ids) != len(set(ids)):
        raise ValueError("box object_id values must be unique")
    # Force geometry validation now rather than waiting for renderer.
    for box in boxes:
        box_mesh(box)
    return boxes


def mesh_to_dict(mesh: Mesh3D) -> dict[str, Any]:
    return asdict(mesh)


def scene_to_json(
    rooms: Sequence[SceneRoom],
    meshes: Sequence[Mesh3D],
    openings: Sequence[OpeningLine] = (),
    *,
    metadata: Mapping[str, Any] | None = None,
) -> str:
    payload = {
        "schema": "nitikube.scene3d",
        "schema_version": "0.21",
        "units": "ft",
        "rooms": [asdict(room) for room in rooms],
        "meshes": [mesh_to_dict(mesh) for mesh in meshes],
        "openings": [asdict(opening) for opening in openings],
        "metadata": dict(metadata or {}),
        "visualization_note": (
            "Geometry dimensions come from the supplied room/box model. Visual colors/materials are approximations unless separately tied to sourced product/material evidence."
        ),
    }
    return json.dumps(payload, indent=2, ensure_ascii=False)
