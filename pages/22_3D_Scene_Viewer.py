from __future__ import annotations

import json

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from nitikube.scene3d import (
    BoxObject,
    OpeningLine,
    SceneRoom,
    build_scene_meshes,
    load_boxes_json,
    scene_bounds,
    scene_to_json,
)
from nitikube.verified_geometry import geometry_from_project_json


st.set_page_config(page_title="NitiKube — 3D Scene Viewer", page_icon="◇", layout="wide")
st.title("Verified-Geometry 3D Scene Viewer")
st.caption(
    "Extrude verified room polygons into browser-rendered 3D walls/floors and add parametric furniture boxes. This avoids making paid generative-image rendering a core dependency."
)
st.warning(
    "Geometry is dimension-driven; visual appearance is not photorealistic product evidence. Openings are currently displayed as line overlays rather than subtracted wall voids, and furniture boxes are parametric envelopes rather than exact manufacturer models."
)

st.subheader("1 · Load authoritative geometry")
geometry_file = st.file_uploader("Upload `nitikube_verified_geometry.json`", type=["json"], key="scene_geometry")
rooms: list[SceneRoom] = []
opening_lines: list[OpeningLine] = []
project_name = "NitiKube Project"
wall_height = st.number_input("Wall / ceiling height ft", min_value=1.0, value=9.0, step=0.25)

if geometry_file:
    try:
        project_name, verified_rooms, openings, metadata = geometry_from_project_json(geometry_file.getvalue().decode("utf-8"))
        for room in verified_rooms:
            if not room.verified:
                continue
            rooms.append(
                SceneRoom(
                    room_id=room.room_id,
                    name=room.name,
                    polygon_ft=tuple((float(x), float(y)) for x, y in room.polygon_ft),
                    wall_height_ft=float(wall_height),
                )
            )
        for opening in openings:
            if not opening.verified:
                continue
            opening_lines.append(
                OpeningLine(
                    opening_id=opening.opening_id,
                    kind=opening.kind,
                    start_ft=(float(opening.start_ft[0]), float(opening.start_ft[1])),
                    end_ft=(float(opening.end_ft[0]), float(opening.end_ft[1])),
                    room_a=opening.room_a,
                    room_b=opening.room_b,
                )
            )
        st.success(f"Loaded {len(rooms)} verified room(s) and {len(opening_lines)} verified opening segment(s) from `{project_name}`.")
    except Exception as exc:
        st.error(f"Verified geometry could not be converted into a scene: {exc}")

st.subheader("2 · Parametric furniture / object boxes")
st.caption(
    "Furniture boxes use exact x/y/z/width/depth/height inputs in feet. Leave the table empty for geometry-only 3D, or upload a `{'boxes': [...]}` JSON file."
)
box_file = st.file_uploader("Optional furniture/object-box JSON", type=["json"], key="scene_boxes")
boxes: list[BoxObject] = []
if box_file:
    try:
        boxes = load_boxes_json(box_file.getvalue())
        st.success(f"Loaded {len(boxes)} parametric object box(es).")
    except Exception as exc:
        st.error(f"Object boxes could not be loaded: {exc}")

if rooms:
    if not boxes:
        box_df = pd.DataFrame(
            [
                {
                    "object_id": "",
                    "label": "",
                    "room_id": rooms[0].room_id,
                    "x_ft": None,
                    "y_ft": None,
                    "z_ft": 0.0,
                    "width_ft": None,
                    "depth_ft": None,
                    "height_ft": None,
                    "kind": "furniture",
                }
            ]
        )
    else:
        box_df = pd.DataFrame(
            [
                {
                    "object_id": box.object_id,
                    "label": box.label,
                    "room_id": box.room_id,
                    "x_ft": box.x_ft,
                    "y_ft": box.y_ft,
                    "z_ft": box.z_ft,
                    "width_ft": box.width_ft,
                    "depth_ft": box.depth_ft,
                    "height_ft": box.height_ft,
                    "kind": box.kind,
                }
                for box in boxes
            ]
        )
    edited_boxes = st.data_editor(box_df, use_container_width=True, hide_index=True, num_rows="dynamic", key="scene_box_editor")
    parsed_boxes: list[BoxObject] = []
    errors = []
    for index, row in edited_boxes.iterrows():
        object_id = str(row.get("object_id") or "").strip()
        if not object_id:
            continue
        try:
            numeric = {
                field: float(row[field])
                for field in ("x_ft", "y_ft", "z_ft", "width_ft", "depth_ft", "height_ft")
            }
            parsed_boxes.append(
                BoxObject(
                    object_id=object_id,
                    label=str(row.get("label") or object_id),
                    room_id=str(row.get("room_id") or "") or None,
                    kind=str(row.get("kind") or "furniture"),
                    **numeric,
                )
            )
        except Exception as exc:
            errors.append(f"row {index + 1}: {exc}")
    for error in errors:
        st.warning(error)
    boxes = parsed_boxes

st.subheader("3 · Render 3D scene")
include_floor = st.checkbox("Show floors", value=True)
include_walls = st.checkbox("Show walls", value=True)
include_ceiling = st.checkbox("Show ceiling surfaces", value=False)
show_openings = st.checkbox("Show verified opening segments", value=True)

if rooms and st.button("Build 3D scene", type="primary"):
    try:
        meshes = build_scene_meshes(
            rooms,
            boxes=boxes,
            include_floor=include_floor,
            include_walls=include_walls,
            include_ceiling=include_ceiling,
        )
        minimum, maximum = scene_bounds(meshes)
        st.session_state["scene3d_meshes"] = meshes
        st.session_state["scene3d_bounds"] = (minimum, maximum)
        st.session_state["scene3d_boxes"] = boxes
        st.session_state["scene3d_rooms"] = rooms
        st.session_state["scene3d_openings"] = opening_lines
    except Exception as exc:
        st.error(f"3D scene could not be built: {exc}")

meshes = st.session_state.get("scene3d_meshes")
if meshes:
    fig = go.Figure()
    for mesh in meshes:
        xs = [vertex[0] for vertex in mesh.vertices]
        ys = [vertex[1] for vertex in mesh.vertices]
        zs = [vertex[2] for vertex in mesh.vertices]
        ii = [triangle[0] for triangle in mesh.triangles]
        jj = [triangle[1] for triangle in mesh.triangles]
        kk = [triangle[2] for triangle in mesh.triangles]
        opacity = 0.22 if mesh.kind == "walls" else 0.72 if mesh.kind == "floor" else 0.55 if mesh.kind == "ceiling" else 0.92
        fig.add_trace(
            go.Mesh3d(
                x=xs,
                y=ys,
                z=zs,
                i=ii,
                j=jj,
                k=kk,
                name=mesh.label,
                opacity=opacity,
                flatshading=True,
                hovertemplate=f"{mesh.label}<extra></extra>",
                showlegend=True,
            )
        )
    if show_openings:
        for opening in st.session_state.get("scene3d_openings", []):
            fig.add_trace(
                go.Scatter3d(
                    x=[opening.start_ft[0], opening.end_ft[0]],
                    y=[opening.start_ft[1], opening.end_ft[1]],
                    z=[0.08, 0.08],
                    mode="lines+markers",
                    name=f"{opening.kind}: {opening.opening_id}",
                    line={"width": 8},
                    hovertemplate=(
                        f"{opening.kind} · {opening.opening_id}<br>"
                        f"rooms: {opening.room_a or '-'} / {opening.room_b or '-'}<extra></extra>"
                    ),
                )
            )
    minimum, maximum = st.session_state["scene3d_bounds"]
    span_x = max(maximum[0] - minimum[0], 1.0)
    span_y = max(maximum[1] - minimum[1], 1.0)
    span_z = max(maximum[2] - minimum[2], 1.0)
    fig.update_layout(
        title=f"{project_name} — verified geometry scene",
        scene={
            "xaxis_title": "X (ft)",
            "yaxis_title": "Y (ft)",
            "zaxis_title": "Z (ft)",
            "aspectmode": "manual",
            "aspectratio": {
                "x": span_x / max(span_x, span_y),
                "y": span_y / max(span_x, span_y),
                "z": span_z / max(span_x, span_y),
            },
        },
        height=760,
        margin={"l": 0, "r": 0, "t": 45, "b": 0},
    )
    st.plotly_chart(fig, use_container_width=True)

    st.subheader("4 · Export zero-cost scene artifacts")
    scene_json = scene_to_json(
        st.session_state["scene3d_rooms"],
        meshes,
        st.session_state.get("scene3d_openings", []),
        metadata={
            "project_name": project_name,
            "geometry_source": "verified_nitikube_geometry",
            "wall_height_ft": float(wall_height),
        },
    )
    st.download_button(
        "Download NitiKube 3D scene JSON",
        scene_json.encode("utf-8"),
        "nitikube_scene3d.json",
        "application/json",
    )
    html = fig.to_html(full_html=True, include_plotlyjs=True)
    st.download_button(
        "Download self-contained interactive 3D HTML",
        html.encode("utf-8"),
        "nitikube_scene3d.html",
        "text/html",
    )
    st.caption(
        "The self-contained HTML includes Plotly JavaScript so the downloaded viewer does not require a paid image-generation/rendering service. File size is larger because the rendering library is embedded."
    )

st.subheader("5 · Furniture-box JSON template")
box_template = {
    "boxes": [
        {
            "object_id": "example-sofa",
            "label": "Example furniture envelope",
            "room_id": "REPLACE-WITH-ROOM-ID",
            "x_ft": 0,
            "y_ft": 0,
            "z_ft": 0,
            "width_ft": 1,
            "depth_ft": 1,
            "height_ft": 1,
            "kind": "furniture"
        }
    ]
}
st.download_button(
    "Download furniture-box JSON template",
    json.dumps(box_template, indent=2).encode("utf-8"),
    "nitikube_scene_boxes_template.json",
    "application/json",
)

st.caption(
    "Next steps: planner-native 3D boxes, actual opening void subtraction, windows/doors with heights, parametric cabinetry/sanitaryware, material textures linked to verified product evidence, COB photometric cones and daylight/solar overlays."
)
