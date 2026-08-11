from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd
import streamlit as st

from nitikube.geography import geocode_location
from nitikube.material_db import MaterialProperty, MaterialRecord, validate_material
from nitikube.provenance import EvidenceState
from nitikube.spec_match import ProductRequirement, ProductSpecification, rank_products


st.set_page_config(page_title="NitiKube — Material + Product Intelligence", page_icon="▧", layout="wide")
st.title("Material + Product Intelligence")
st.caption("A material or product fact is only as trustworthy as its measurement and provenance. Unknown values remain unknown; they are never silently treated as matches.")

material_tab, product_tab, geo_tab = st.tabs(["Material Evidence", "Specification Matching", "Location Resolver"])

with material_tab:
    st.subheader("Validate a material property before it enters the verified database")
    a, b, c = st.columns(3)
    material_name = a.text_input("Material", value="Candidate material")
    category = b.text_input("Category", value="cabinetry")
    property_name = c.text_input("Property", value="water_absorption")

    d, e, f = st.columns(3)
    value = d.number_input("Numeric value", value=0.0, step=0.1)
    unit = e.text_input("Unit", value="%")
    state = f.selectbox("Evidence state", list(EvidenceState), format_func=lambda x: x.value.replace("_", " ").title())

    source_url = st.text_input("Source URL", value="")
    checked_at = st.text_input("Checked at (ISO timestamp)", value="")

    record = MaterialRecord(
        material_id="interactive-material",
        name=material_name,
        category=category,
        properties={
            property_name: MaterialProperty(
                name=property_name,
                value=value,
                unit=unit or None,
                state=state,
                source_url=source_url or None,
                checked_at=checked_at or None,
            )
        },
    )
    validation = validate_material(record)
    if validation.valid_for_verified_recommendation:
        st.success("Record passes structural validation for the selected evidence state.")
    else:
        st.error("Record cannot be treated as verified evidence.")
    if validation.errors:
        st.write("**Errors**")
        for msg in validation.errors:
            st.write(f"- {msg}")
    if validation.warnings:
        st.write("**Warnings**")
        for msg in validation.warnings:
            st.write(f"- {msg}")
    st.info("For a numeric property marked VERIFIED, NitiKube requires both a source URL and a verification timestamp. A user-provided value can be stored as user-provided, but must not be mislabeled as independently verified.")

with product_tab:
    st.subheader("Deterministic product-specification matching")
    st.write("Edit the candidate rows with values taken from actual product pages/datasheets. The starter rows are synthetic examples for testing the matcher and are **not** product recommendations or current market facts.")

    r1, r2, r3, r4 = st.columns(4)
    req_category = r1.text_input("Required category", value="COB downlight")
    req_lum_min = r2.number_input("Min lumens", min_value=0.0, value=450.0, step=25.0)
    req_lum_max = r3.number_input("Max lumens", min_value=0.0, value=550.0, step=25.0)
    req_cri = r4.number_input("Minimum CRI", min_value=0.0, max_value=100.0, value=90.0, step=1.0)

    s1, s2, s3 = st.columns(3)
    req_kelvin = s1.number_input("Required Kelvin", min_value=1000, value=3000, step=100)
    req_beam = s2.number_input("Target beam angle", min_value=1.0, value=36.0, step=1.0)
    req_beam_tol = s3.number_input("Beam tolerance ±°", min_value=0.0, value=3.0, step=1.0)

    defaults = pd.DataFrame([
        {"name": "Example A", "category": "COB downlight", "watts": 7.0, "lumens": 500.0, "kelvin": 3000, "beam_angle_deg": 36.0, "cri": 90.0, "price": None, "source_url": "", "verified_at": ""},
        {"name": "Example B", "category": "COB downlight", "watts": 7.0, "lumens": 650.0, "kelvin": 3000, "beam_angle_deg": 36.0, "cri": 80.0, "price": None, "source_url": "", "verified_at": ""},
        {"name": "Example C", "category": "COB downlight", "watts": 5.0, "lumens": 480.0, "kelvin": 4000, "beam_angle_deg": 24.0, "cri": 95.0, "price": None, "source_url": "", "verified_at": ""},
    ])
    edited = st.data_editor(defaults, use_container_width=True, num_rows="dynamic", key="product_candidates")

    req = ProductRequirement(
        category=req_category,
        lumens_min=req_lum_min,
        lumens_max=req_lum_max,
        kelvin_allowed=(int(req_kelvin),),
        beam_angle_target_deg=req_beam,
        beam_angle_tolerance_deg=req_beam_tol,
        cri_min=req_cri,
    )

    products = []
    for _, row in edited.iterrows():
        def optional_float(v):
            return None if pd.isna(v) or v == "" else float(v)
        products.append(
            ProductSpecification(
                name=str(row["name"]),
                category=str(row["category"]),
                watts=optional_float(row["watts"]),
                lumens=optional_float(row["lumens"]),
                kelvin=None if pd.isna(row["kelvin"]) else int(row["kelvin"]),
                beam_angle_deg=optional_float(row["beam_angle_deg"]),
                cri=optional_float(row["cri"]),
                price=optional_float(row["price"]),
                source_url=str(row["source_url"]) or None,
                verified_at=str(row["verified_at"]) or None,
            )
        )

    ranked = rank_products(products, req)
    out = pd.DataFrame([
        {
            "product": p.name,
            "feasible": m.feasible,
            "match score": m.score,
            "matched": ", ".join(m.matched),
            "failed": ", ".join(m.failed),
            "unknown": ", ".join(m.unknown),
            "price verified": p.price_verified,
        }
        for p, m in ranked
    ])
    st.dataframe(out, use_container_width=True, hide_index=True)
    st.caption("Unknown specifications reduce the match score and remain visible. Price verification requires price + source URL + verification timestamp.")

with geo_tab:
    st.subheader("Resolve a location to coordinates before climate calculations")
    query = st.text_input("City / locality", value="Gurugram")
    if st.button("Resolve location"):
        try:
            results = geocode_location(query)
            if results:
                df = pd.DataFrame([
                    {
                        "label": x.label,
                        "latitude": x.latitude,
                        "longitude": x.longitude,
                        "elevation_m": x.elevation_m,
                        "timezone": x.timezone,
                    }
                    for x in results
                ])
                st.dataframe(df, use_container_width=True, hide_index=True)
                st.info("Coordinates are provider results, not assumptions. The selected location should still be confirmed by the user before climate-sensitive recommendations are generated.")
            else:
                st.warning("No locations returned.")
        except Exception as exc:
            st.error(f"Geocoding provider unavailable: {exc}")
