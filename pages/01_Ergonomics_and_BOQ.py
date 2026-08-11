from __future__ import annotations

import pandas as pd
import streamlit as st

from nitikube.boq import BOQItem, audit_quantity, boq_rows, total_known_cost
from nitikube.ergonomics import dining_envelope, rectangular_fit, viewing_distance_for_horizontal_fov_ft
from nitikube.project import ProjectSnapshot, RoomInput


st.set_page_config(page_title="NitiKube — Ergonomics + BOQ", page_icon="▦", layout="wide")
st.title("Ergonomics + BOQ Audit")
st.caption("Pure geometry and auditable quantities. Any clearance presented as a standard must be sourced separately; this page lets the user choose the assumptions explicitly.")

room_tab, tv_tab, boq_tab, export_tab = st.tabs(["Dining / Furniture Fit", "TV Geometry", "BOQ Audit", "Project Export"])

with room_tab:
    st.subheader("Dining envelope and room fit")
    c1, c2, c3, c4 = st.columns(4)
    room_l = c1.number_input("Room length (ft)", min_value=1.0, value=22.75, step=0.25)
    room_w = c2.number_input("Room width (ft)", min_value=1.0, value=10.583, step=0.25, format="%.3f")
    table_l = c3.number_input("Table length (ft)", min_value=1.0, value=6.0, step=0.25)
    table_w = c4.number_input("Table width (ft)", min_value=1.0, value=3.0, step=0.25)

    c5, c6 = st.columns(2)
    chair_depth = c5.number_input("Chair depth assumption (ft)", min_value=0.5, value=1.7, step=0.1)
    pullback = c6.number_input("Pull-back / movement clearance beyond chair (ft)", min_value=0.0, value=1.5, step=0.1)

    envelope = dining_envelope(
        table_length_ft=table_l,
        table_width_ft=table_w,
        chair_depth_ft=chair_depth,
        pullback_clearance_ft=pullback,
    )
    fit = rectangular_fit(
        room_length_ft=room_l,
        room_width_ft=room_w,
        item_length_ft=envelope.required_length_ft,
        item_width_ft=envelope.required_width_ft,
        allow_rotation=True,
    )

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Required envelope length", f"{envelope.required_length_ft:.2f} ft")
    m2.metric("Required envelope width", f"{envelope.required_width_ft:.2f} ft")
    m3.metric("Length margin", f"{fit.length_margin_ft:.2f} ft")
    m4.metric("Width margin", f"{fit.width_margin_ft:.2f} ft")

    if fit.fits:
        st.success("The selected dining envelope geometrically fits the room, including the clearances you entered.")
    else:
        st.error("The selected dining envelope does not fit the room with the clearances you entered.")
    st.latex(r"Envelope = Table + 2(Chair\ Depth + Pullback\ Clearance)")
    st.info("NitiKube treats the clearance values above as user-selected assumptions unless a later standards/provenance layer attaches a verified source.")

with tv_tab:
    st.subheader("Screen viewing distance from chosen field of view")
    c1, c2 = st.columns(2)
    diagonal = c1.number_input("TV diagonal (in)", min_value=10.0, value=65.0, step=1.0)
    fov = c2.number_input("Chosen horizontal field of view (degrees)", min_value=5.0, max_value=120.0, value=30.0, step=1.0)
    distance = viewing_distance_for_horizontal_fov_ft(diagonal, fov)
    st.metric("Geometric viewing distance", f"{distance:.2f} ft")
    st.latex(r"d = \frac{screen\ width}{2\tan(FOV/2)}")
    st.caption("This is geometry only. NitiKube deliberately does not label a particular FOV as a recommended cinema/TV standard unless that recommendation is attached to a sourced standard or manufacturer guidance.")

with boq_tab:
    st.subheader("Quoted quantity vs NitiKube calculated quantity")
    q1, q2, q3, q4 = st.columns(4)
    category = q1.text_input("Category", value="Lighting")
    description = q2.text_input("Description", value="36° COB downlight")
    calculated = q3.number_input("Calculated quantity", min_value=0.01, value=12.0, step=1.0)
    quoted = q4.number_input("Quoted quantity", min_value=0.0, value=15.0, step=1.0)

    u1, u2, u3 = st.columns(3)
    unit = u1.text_input("Unit", value="pcs")
    tolerance = u2.number_input("Audit tolerance (%)", min_value=0.0, value=5.0, step=1.0)
    unit_rate = u3.number_input("Optional quoted unit rate (₹)", min_value=0.0, value=0.0, step=50.0)

    audit = audit_quantity(calculated, quoted, tolerance)
    a, b, c = st.columns(3)
    a.metric("Difference", f"{audit.absolute_difference:+.2f} {unit}")
    b.metric("Difference %", f"{audit.percent_difference:+.1f}%")
    c.metric("Audit status", audit.status.replace("_", " ").title())

    if audit.status == "quoted_above_calculated":
        st.warning("The quoted quantity exceeds the calculated quantity beyond the selected tolerance. Investigate waste assumptions, pack sizes, scope differences and contractor rationale before calling it excess.")
    elif audit.status == "quoted_below_calculated":
        st.warning("The quote is below the calculated requirement beyond tolerance. Check whether the scope or calculation assumptions differ.")
    else:
        st.success("Quoted and calculated quantities are within the selected tolerance.")

    item = BOQItem(
        category=category,
        description=description,
        calculated_quantity=calculated,
        unit=unit,
        unit_rate=unit_rate if unit_rate > 0 else None,
    )
    st.dataframe(pd.DataFrame(boq_rows([item])), use_container_width=True, hide_index=True)
    if item.unit_rate is not None:
        st.metric("Known line cost", f"₹{total_known_cost([item]):,.2f}")
        st.error("Price is NOT marked verified because no source URL + verification timestamp were supplied. NitiKube must not present this as a current market price.")

with export_tab:
    st.subheader("Portable project snapshot")
    project_name = st.text_input("Project name", value="My NitiKube Home")
    location = st.text_input("Location", value="Gurugram, Haryana, India")
    budget = st.number_input("Budget (₹)", min_value=0.0, value=1_200_000.0, step=50_000.0)
    snapshot = ProjectSnapshot(
        project_name=project_name,
        location=location,
        budget_inr=budget or None,
        rooms=[RoomInput(name="Drawing / Dining", length_ft=22.75, width_ft=10.583, ceiling_height_ft=9.0)],
        verified_inputs={"drawing_dining_dimensions": True},
        notes=["Portable JSON snapshot generated by NitiKube."],
    )
    payload = snapshot.to_json()
    st.code(payload, language="json")
    st.download_button(
        "Download project JSON",
        data=payload,
        file_name="nitikube_project.json",
        mime="application/json",
    )
