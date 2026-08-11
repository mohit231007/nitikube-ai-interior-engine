import json

import pytest

from nitikube.scene3d import (
    BoxObject,
    SceneRoom,
    box_mesh,
    build_scene_meshes,
    ceiling_mesh,
    floor_mesh,
    load_boxes_json,
    scene_bounds,
    scene_to_json,
    triangulate_polygon,
    wall_mesh,
)


def triangle_area(a, b, c):
    return abs((b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])) / 2


def test_triangulate_rectangle_yields_two_triangles_and_preserves_area():
    polygon = ((0, 0), (10, 0), (10, 6), (0, 6))
    triangles = triangulate_polygon(polygon)
    assert len(triangles) == 2
    area = sum(triangle_area(polygon[i], polygon[j], polygon[k]) for i, j, k in triangles)
    assert area == pytest.approx(60)


def test_clockwise_polygon_is_supported():
    polygon = ((0, 0), (0, 6), (10, 6), (10, 0))
    triangles = triangulate_polygon(polygon)
    assert len(triangles) == 2
    area = sum(triangle_area(polygon[i], polygon[j], polygon[k]) for i, j, k in triangles)
    assert area == pytest.approx(60)


def test_concave_polygon_triangulates_to_n_minus_two():
    polygon = ((0, 0), (6, 0), (6, 2), (3, 2), (3, 5), (0, 5))
    triangles = triangulate_polygon(polygon)
    assert len(triangles) == len(polygon) - 2
    area = sum(triangle_area(polygon[i], polygon[j], polygon[k]) for i, j, k in triangles)
    # 6×5 rectangle minus 3×3 upper-right notch.
    assert area == pytest.approx(21)


def test_degenerate_polygon_fails_closed():
    with pytest.raises(ValueError, match="zero/degenerate"):
        triangulate_polygon(((0, 0), (1, 0), (2, 0)))
    with pytest.raises(ValueError, match="at least three"):
        triangulate_polygon(((0, 0), (1, 0)))


def test_floor_ceiling_and_wall_mesh_counts():
    room = SceneRoom("R1", "Living", ((0, 0), (10, 0), (10, 6), (0, 6)), 9)
    floor = floor_mesh(room)
    ceiling = ceiling_mesh(room)
    walls = wall_mesh(room)
    assert len(floor.vertices) == 4
    assert len(floor.triangles) == 2
    assert all(vertex[2] == 0 for vertex in floor.vertices)
    assert all(vertex[2] == 9 for vertex in ceiling.vertices)
    assert len(walls.vertices) == 16  # 4 vertices per wall segment
    assert len(walls.triangles) == 8  # 2 triangles per wall segment


def test_box_mesh_has_six_faces_as_twelve_triangles():
    mesh = box_mesh(BoxObject("sofa", "Sofa", 1, 2, 0, 6, 3, 2.5, room_id="R1"))
    assert len(mesh.vertices) == 8
    assert len(mesh.triangles) == 12
    assert mesh.room_id == "R1"
    assert mesh.kind == "furniture"


def test_invalid_box_dimensions_fail_closed():
    with pytest.raises(ValueError, match="positive"):
        box_mesh(BoxObject("x", "X", 0, 0, 0, 0, 2, 3))


def test_build_scene_meshes_combines_rooms_and_furniture():
    rooms = [
        SceneRoom("R1", "Living", ((0, 0), (10, 0), (10, 6), (0, 6)), 9),
        SceneRoom("R2", "Bedroom", ((10, 0), (18, 0), (18, 6), (10, 6)), 9),
    ]
    meshes = build_scene_meshes(
        rooms,
        boxes=[BoxObject("bed", "Bed", 11, 1, 0, 6, 5, 2, room_id="R2")],
        include_floor=True,
        include_walls=True,
        include_ceiling=False,
    )
    assert len(meshes) == 5  # floor + wall for two rooms + one box
    minimum, maximum = scene_bounds(meshes)
    assert minimum == pytest.approx((0, 0, 0))
    assert maximum == pytest.approx((18, 6, 9))


def test_box_json_loader_requires_unique_ids_and_valid_geometry():
    payload = {
        "boxes": [
            {
                "object_id": "sofa",
                "label": "Sofa",
                "x_ft": 1,
                "y_ft": 1,
                "width_ft": 6,
                "depth_ft": 3,
                "height_ft": 2.5,
                "room_id": "R1",
            }
        ]
    }
    loaded = load_boxes_json(json.dumps(payload))
    assert loaded[0].z_ft == pytest.approx(0)
    payload["boxes"].append(payload["boxes"][0])
    with pytest.raises(ValueError, match="unique"):
        load_boxes_json(json.dumps(payload))


def test_scene_json_records_units_and_visualization_boundary():
    room = SceneRoom("R1", "Living", ((0, 0), (10, 0), (10, 6), (0, 6)), 9)
    meshes = build_scene_meshes([room])
    payload = json.loads(scene_to_json([room], meshes, metadata={"geometry_source": "verified"}))
    assert payload["schema"] == "nitikube.scene3d"
    assert payload["schema_version"] == "0.21"
    assert payload["units"] == "ft"
    assert payload["metadata"]["geometry_source"] == "verified"
    assert "approximations" in payload["visualization_note"]
