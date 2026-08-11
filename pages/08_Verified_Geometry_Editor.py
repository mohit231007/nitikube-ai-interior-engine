from __future__ import annotations

import json
from io import StringIO

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

from nitikube.verified_geometry import (
    VerifiedOpening,
    build_adjacency_graph,
    geometry_from_project_json,
    geometry_svg,
    geometry_to_project_json,
    rectangle_room,
    validate_geometry,
)


st.set_page_config(page_title="NitiKube — Verified Geometry Editor", page_icon="⌗", layout="wide")
st.title("Verified Geometry Editor")
st.caption(
    "This page is the authority gate between computer-vision proposals and engineering calculations. "
    "Only dimensions the user explicitly verifies should become authoritative room geometry."
)

st.info(
    "Current editor scope: axis-aligned room rectangles plus explicit door/window/opening segments. "
    "The core geometry schema already stores polygons, so a future drag-handle polygon editor can replace this table without changing downstream engines."
)


def _default_rooms_df() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "room_id": "R1",
                "name": "Drawing / Dining",
                "x_ft": 0.0,
                "y_ft": 0.0,
                "width_ft": 10 + 7 / 12,
                "height_ft": 22 + 9 / 12,
                "ceiling_height_ft": 9.0,
                "verified": True,
                "source": "manual benchmark",
            }
        ]
    )


def _default_openings_df() -> pd.DataFrame:
    return pd.DataFrame(
        columns=["opening_id", "kind", "x1_ft", "y1_ft", "x2_ft", "y2_ft", "room_a", "room_b", "verified", "source"]
    )


if "geometry_rooms_df" not in st.session_state:
    st.session_state.geometry_rooms_df = _default_rooms_df()
if "geometry_openings_df" not in st.session_state:
    st.session_state.geometry_openings_df = _default_openings_df()

with st.expander("Import CV region CSV or NitiKube geometry JSON", expanded=False):
    import_mode = st.radio("Import type", ["CV region CSV", "Verified geometry JSON"], horizontal=True)
    uploaded = st.file_uploader("Choose file", type=["csv", "json"], key="verified_geometry_import")
    if uploaded and st.button("Load import into editor"):
        try:
            if import_mode == "Verified geometry JSON":
                project_name, rooms, openings, metadata = geometry_from_project_json(uploaded.getvalue().decode("utf-8"))
                room_rows = []
                for room in rooms:
                    min_x, min_y, max_x, max_y = room.bounds_ft
                    room_rows.append(
                        {
                            "room_id": room.room_id,
                            "name": room.name,
                            "x_ft": min_x,
                            "y_ft": min_y,
                            "width_ft": max_x - min_x,
                            "height_ft": max_y - min_y,
                            "ceiling_height_ft": room.ceiling_height_ft,
                            "verified": room.verified,
                            "source": room.source,
                        }
                    )
                opening_rows = [
                    {
                        "opening_id": op.opening_id,
                        "kind": op.kind,
                        "x1_ft": op.start_ft[0],
                        "y1_ft": op.start_ft[1],
                        "x2_ft": op.end_ft[0],
                        "y2_ft": op.end_ft[1],
                        "room_a": op.room_a or "",
                        "room_b": op.room_b or "",
                        "verified": op.verified,
                        "source": op.source,
                    }
                    for op in openings
                ]
                st.session_state.geometry_rooms_df = pd.DataFrame(room_rows)
                st.session_state.geometry_openings_df = pd.DataFrame(opening_rows)
                st.success(f"Loaded {len(rooms)} rooms from {project_name}.")
                if metadata.get("location"):
                    st.caption(f"Imported location: {metadata['location']}")
            else:
                df = pd.read_csv(StringIO(uploaded.getvalue().decode("utf-8")))
                required = {"candidate", "width_ft_from_scale", "height_ft_from_scale"}
                missing = required - set(df.columns)
                if missing:
                    raise ValueError(f"CV CSV is missing columns: {sorted(missing)}")
                x_col = "x_ft_from_scale" if "x_ft_from_scale" in df.columns else None
                y_col = "y_ft_from_scale" if "y_ft_from_scale" in df.columns else None
                rows = []
                cursor_x = 0.0
                for _, row in df.iterrows():
                    x_ft = float(row[x_col]) if x_col else cursor_x
                    y_ft = float(row[y_col]) if y_col else 0.0
                    width_ft = float(row["width_ft_from_scale"])
                    height_ft = float(row["height_ft_from_scale"])
                    rows.append(
                        {
                            "room_id": str(row["candidate"]),
                            "name": str(row.get("room_name", row["candidate"])),
                            "x_ft": x_ft,
                            "y_ft": y_ft,
                            "width_ft": width_ft,
                            "height_ft": height_ft,
                            "ceiling_height_ft": 9.0,
                            "verified": True,
                            "source": "verified CV region import",
                        }
                    )
                    cursor_x += width_ft + 1.0
                st.session_state.geometry_rooms_df = pd.DataFrame(rows)
                st.session_state.geometry_openings_df = _default_openings_df()
                if not x_col or not y_col:
                    st.warning(
                        "This older region CSV has dimensions but no scaled x/y origin. Rooms were laid out sequentially for editing; "
                        "their positions must be corrected before using adjacency/topology."
                    )
                st.success(f"Loaded {len(rows)} region rows into the editor.")
        except Exception as exc:
            st.error(f"Import failed: {exc}")

st.subheader("1 · Authoritative room rectangles")
st.write(
    "Edit x/y positions and dimensions in **feet**. A row only enters the authoritative engineering graph when `verified` is checked. "
    "Computer-vision origin values are proposals; manual correction wins."
)
room_df = st.data_editor(
    st.session_state.geometry_rooms_df,
    num_rows="dynamic",
    use_container_width=True,
    hide_index=True,
    key="room_geometry_editor",
    column_config={
        "verified": st.column_config.CheckboxColumn("verified", default=False),
        "x_ft": st.column_config.NumberColumn("x_ft", min_value=0.0, step=0.25),
        "y_ft": st.column_config.NumberColumn("y_ft", min_value=0.0, step=0.25),
        "width_ft": st.column_config.NumberColumn("width_ft", min_value=0.01, step=0.25),
        "height_ft": st.column_config.NumberColumn("height_ft", min_value=0.01, step=0.25),
        "ceiling_height_ft": st.column_config.NumberColumn("ceiling_height_ft", min_value=1.0, step=0.25),
    },
)
st.session_state.geometry_rooms_df = room_df

st.subheader("2 · Doors, windows and open passages")
st.write(
    "Opening endpoints must lie on declared verified room boundaries. For a door/open passage between rooms, set both `room_a` and `room_b`. "
    "Windows normally have only one adjacent room."
)
opening_df = st.data_editor(
    st.session_state.geometry_openings_df,
    num_rows="dynamic",
    use_container_width=True,
    hide_index=True,
    key="opening_geometry_editor",
    column_config={
        "kind": st.column_config.SelectboxColumn("kind", options=["door", "window", "opening"]),
        "verified": st.column_config.CheckboxColumn("verified", default=False),
    },
)
st.session_state.geometry_openings_df = opening_df

rooms = []
row_errors = []
for idx, row in room_df.iterrows():
    try:
        room_id = str(row.get("room_id", "")).strip()
        if not room_id or pd.isna(row.get("width_ft")) or pd.isna(row.get("height_ft")):
            continue
        rooms.append(
            rectangle_room(
                room_id=room_id,
                name=str(row.get("name") or room_id),
                x_ft=float(row.get("x_ft", 0.0)),
                y_ft=float(row.get("y_ft", 0.0)),
                width_ft=float(row["width_ft"]),
                height_ft=float(row["height_ft"]),
                ceiling_height_ft=float(row.get("ceiling_height_ft", 9.0)),
                verified=bool(row.get("verified", False)),
                source=str(row.get("source") or "manual editor"),
            )
        )
    except Exception as exc:
        row_errors.append(f"Room row {idx + 1}: {exc}")

openings = []
for idx, row in opening_df.iterrows():
    try:
        opening_id = str(row.get("opening_id", "")).strip()
        if not opening_id:
            continue
        required_coords = [row.get("x1_ft"), row.get("y1_ft"), row.get("x2_ft"), row.get("y2_ft")]
        if any(pd.isna(value) for value in required_coords):
            row_errors.append(f"Opening row {idx + 1}: coordinates are incomplete")
            continue
        room_a = str(row.get("room_a") or "").strip() or None
        room_b = str(row.get("room_b") or "").strip() or None
        openings.append(
            VerifiedOpening(
                opening_id=opening_id,
                kind=str(row.get("kind") or "opening").lower(),
                start_ft=(float(row["x1_ft"]), float(row["y1_ft"])),
                end_ft=(float(row["x2_ft"]), float(row["y2_ft"])),
                room_a=room_a,
                room_b=room_b,
                verified=bool(row.get("verified", False)),
                source=str(row.get("source") or "manual editor"),
            )
        )
    except Exception as exc:
        row_errors.append(f"Opening row {idx + 1}: {exc}")

geometry_errors = row_errors + validate_geometry(rooms, openings)
verified_rooms = [room for room in rooms if room.verified]
verified_openings = [opening for opening in openings if opening.verified]

st.subheader("3 · Verification diagnostics")
m1, m2, m3, m4 = st.columns(4)
m1.metric("Rooms", len(rooms))
m2.metric("Verified rooms", len(verified_rooms))
m3.metric("Verified area", f"{sum(room.area_ft2 for room in verified_rooms):,.1f} ft²")
m4.metric("Verified openings", len(verified_openings))

if geometry_errors:
    st.error("Geometry is not authoritative yet. Fix these items before downstream use:")
    for error in geometry_errors:
        st.write(f"- {error}")
else:
    st.success("Geometry validation passed. Verified rows can be exported as authoritative NitiKube geometry.")

if rooms:
    try:
        svg = geometry_svg(rooms, openings)
        components.html(svg, height=min(850, 250 + int(max(r.bounds_ft[3] for r in rooms) * 24)), scrolling=True)
    except Exception as exc:
        st.warning(f"Plan preview unavailable: {exc}")

st.subheader("4 · Room adjacency / topology")
edges = build_adjacency_graph(rooms, openings, verified_only=True) if rooms else ()
edge_df = pd.DataFrame(
    [
        {
            "room_a": edge.room_a,
            "room_b": edge.room_b,
            "shared_boundary_ft": round(edge.shared_boundary_ft, 3),
            "connected_by_opening": edge.connected_by_opening,
            "opening_ids": ", ".join(edge.opening_ids),
        }
        for edge in edges
    ]
)
if edge_df.empty:
    st.info("No verified adjacency edges yet. Add neighbouring verified rooms and, where relevant, verified openings.")
else:
    st.dataframe(edge_df, use_container_width=True, hide_index=True)
    st.download_button(
        "Download room adjacency CSV",
        edge_df.to_csv(index=False).encode("utf-8"),
        "nitikube_room_adjacency.csv",
        "text/csv",
    )

st.subheader("5 · Authoritative project export")
p1, p2 = st.columns(2)
project_name = p1.text_input("Project name", "NitiKube Home")
location = p2.text_input("Location", "")

if geometry_errors:
    st.warning("Downloads remain disabled while authoritative geometry has validation errors.")
else:
    authoritative_json = geometry_to_project_json(
        project_name,
        verified_rooms,
        verified_openings,
        location=location or None,
        notes=[
            "Export contains only user-verified room/opening records.",
            "CV proposals do not become authoritative unless the user verifies/corrects them.",
        ],
    )
    export_svg = geometry_svg(verified_rooms, verified_openings) if verified_rooms else None
    d1, d2 = st.columns(2)
    d1.download_button(
        "Download verified geometry JSON",
        authoritative_json.encode("utf-8"),
        "nitikube_verified_geometry.json",
        "application/json",
        disabled=not bool(verified_rooms),
    )
    d2.download_button(
        "Download verified geometry SVG",
        (export_svg or "").encode("utf-8"),
        "nitikube_verified_geometry.svg",
        "image/svg+xml",
        disabled=not bool(export_svg),
    )

st.caption(
    "Safety contract: verified interior geometry may drive lighting, quantities and layout checks. "
    "It is not a surveyed/legal/stamped plan and does not authorize structural modification."
)
