import json

import pytest

from nitikube.project import ProjectSnapshot
from nitikube.verified_geometry import (
    VerifiedOpening,
    VerifiedRoom,
    build_adjacency_graph,
    geometry_from_project_json,
    geometry_svg,
    geometry_to_project_json,
    parse_length_ft,
    polygon_centroid,
    rectangle_room,
    shared_boundary_length,
    validate_geometry,
    validate_room,
)


def test_parse_architectural_lengths():
    assert parse_length_ft("10' 7\"") == pytest.approx(10 + 7 / 12)
    assert parse_length_ft("10 ft 7 in") == pytest.approx(10 + 7 / 12)
    assert parse_length_ft("127 in") == pytest.approx(127 / 12)
    assert parse_length_ft("10.5 ft") == pytest.approx(10.5)
    assert parse_length_ft(9) == pytest.approx(9.0)
    with pytest.raises(ValueError):
        parse_length_ft("10 ft 13 in")


def test_rectangle_room_area_bounds_and_centroid():
    room = rectangle_room("R1", "Drawing", 2.0, 3.0, 10.0, 20.0, 9.0)
    assert room.area_ft2 == pytest.approx(200.0)
    assert room.bounds_ft == pytest.approx((2.0, 3.0, 12.0, 23.0))
    assert polygon_centroid(room.polygon_ft) == pytest.approx((7.0, 13.0))


def test_self_intersecting_polygon_rejected():
    room = VerifiedRoom(
        room_id="X",
        name="Crossed polygon",
        polygon_ft=((0.0, 0.0), (4.0, 4.0), (0.0, 5.0), (5.0, 0.0)),
        ceiling_height_ft=9.0,
    )
    with pytest.raises(ValueError, match="self-intersects"):
        validate_room(room)


def test_adjacency_and_opening_topology():
    a = rectangle_room("A", "Living", 0.0, 0.0, 10.0, 10.0, 9.0)
    b = rectangle_room("B", "Dining", 10.0, 0.0, 5.0, 10.0, 9.0)
    door = VerifiedOpening(
        opening_id="D1",
        kind="door",
        start_ft=(10.0, 3.0),
        end_ft=(10.0, 6.0),
        room_a="A",
        room_b="B",
        verified=True,
    )
    assert shared_boundary_length(a, b) == pytest.approx(10.0)
    assert validate_geometry([a, b], [door]) == []
    edges = build_adjacency_graph([a, b], [door])
    assert len(edges) == 1
    assert edges[0].shared_boundary_ft == pytest.approx(10.0)
    assert edges[0].connected_by_opening is True
    assert edges[0].opening_ids == ("D1",)


def test_opening_must_match_declared_boundaries():
    a = rectangle_room("A", "Living", 0.0, 0.0, 10.0, 10.0, 9.0)
    bad = VerifiedOpening(
        opening_id="D1",
        kind="door",
        start_ft=(3.0, 3.0),
        end_ft=(6.0, 3.0),
        room_a="A",
        verified=True,
    )
    errors = validate_geometry([a], [bad])
    assert any(
        "declared room boundary" in error or "does not lie on a verified room boundary" in error
        for error in errors
    )


def test_unverified_opening_does_not_block_geometry():
    a = rectangle_room("A", "Living", 0.0, 0.0, 10.0, 10.0, 9.0)
    proposal = VerifiedOpening(
        opening_id="P1",
        kind="window",
        start_ft=(3.0, 3.0),
        end_ft=(6.0, 3.0),
        room_a="A",
        verified=False,
        source="cv proposal",
    )
    assert validate_geometry([a], [proposal]) == []


def test_geometry_json_round_trip_and_schema():
    a = rectangle_room("A", "Living", 0.0, 0.0, 10.0, 10.0, 9.0)
    payload = geometry_to_project_json("Home", [a], location="Gurugram")
    raw = json.loads(payload)
    assert raw["schema"] == "nitikube.verified_geometry"
    assert raw["schema_version"] == "0.7"
    project_name, rooms, openings, metadata = geometry_from_project_json(payload)
    assert project_name == "Home"
    assert len(rooms) == 1
    assert rooms[0].area_ft2 == pytest.approx(100.0)
    assert openings == []
    assert metadata["location"] == "Gurugram"


def test_project_snapshot_can_persist_verified_geometry():
    room = rectangle_room("A", "Living", 0.0, 0.0, 10.0, 10.0, 9.0)
    geometry_payload = geometry_to_project_json("Home", [room])
    project = ProjectSnapshot(project_name="Home")
    project.attach_verified_geometry(geometry_payload)
    round_tripped = ProjectSnapshot.from_json(project.to_json())
    assert round_tripped.verified_geometry is not None
    assert round_tripped.verified_geometry["schema"] == "nitikube.verified_geometry"
    assert round_tripped.verified_geometry["rooms"][0]["room_id"] == "A"


def test_svg_contains_room_and_opening():
    a = rectangle_room("A", "Living & Dining", 0.0, 0.0, 10.0, 10.0, 9.0)
    window = VerifiedOpening(
        opening_id="W1",
        kind="window",
        start_ft=(2.0, 0.0),
        end_ft=(5.0, 0.0),
        room_a="A",
    )
    svg = geometry_svg([a], [window])
    assert svg.startswith("<svg")
    assert "Living &amp; Dining" in svg
    assert svg.count("<polygon") == 1
    assert svg.count("<line") == 1
