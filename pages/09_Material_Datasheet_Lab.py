from __future__ import annotations

import json

import pandas as pd
import streamlit as st

from nitikube.material_db import validate_material
from nitikube.material_ingest import (
    PROPERTY_SPECS,
    detect_property_conflicts,
    load_datasheet_json,
    load_observations_csv,
    material_record_from_bundle,
    normalize_bundle,
    normalized_rows,
)
from nitikube.material_suitability import NumericRequirement, evaluate_material, suitability_rows


st.set_page_config(page_title="NitiKube — Material Datasheet Lab", page_icon="◫", layout="wide")
st.title("Material Datasheet Evidence Lab")
st.caption(
    "Turn structured manufacturer/user datasheet observations into normalized, provenance-carrying material facts. "
    "Conflicting sources remain visible and are never silently averaged."
)

st.warning(
    "This page does not scrape or invent material properties. Upload structured observations copied from a datasheet/source, "
    "including source URL and checked timestamp when you want a numeric fact to be treated as VERIFIED."
)

with st.expander("Supported canonical property vocabulary", expanded=False):
    vocab = pd.DataFrame(
        [
            {
                "canonical_property": name,
                "canonical_unit": spec.canonical_unit,
                "aliases": ", ".join(spec.aliases),
            }
            for name, spec in PROPERTY_SPECS.items()
        ]
    )
    st.dataframe(vocab, use_container_width=True, hide_index=True)

input_mode = st.radio("Input format", ["Structured JSON bundle", "Observation CSV"], horizontal=True)

bundle = None
if input_mode == "Structured JSON bundle":
    uploaded = st.file_uploader("Upload datasheet bundle JSON", type=["json"], key="material_bundle_json")
    template = {
        "material_id": "your-material-id",
        "material_name": "Your material/product name",
        "category": "your-category",
        "aliases": [],
        "sources": [
            {
                "document_id": "datasheet-1",
                "title": "Manufacturer datasheet title",
                "manufacturer": "Manufacturer",
                "product_name": "Product",
                "source_url": "https://source.example/document",
                "document_version": "version/date if known",
                "checked_at": "2026-08-11T00:00:00+00:00"
            }
        ],
        "observations": [
            {
                "property_name": "thickness",
                "value": 0.0,
                "unit": "mm",
                "source_document_id": "datasheet-1",
                "state": "unverified",
                "note": "Replace placeholder value/state with the sourced observation before use."
            }
        ],
        "notes": ["Template only; placeholder values are not material facts."]
    }
    st.download_button(
        "Download JSON schema template",
        json.dumps(template, indent=2).encode("utf-8"),
        "nitikube_material_datasheet_template.json",
        "application/json",
    )
    if uploaded:
        try:
            bundle = load_datasheet_json(uploaded.getvalue())
        except Exception as exc:
            st.error(f"Could not load bundle: {exc}")
else:
    c1, c2, c3 = st.columns(3)
    material_id = c1.text_input("Material ID", "material-001")
    material_name = c2.text_input("Material name", "Material")
    category = c3.text_input("Category", "surface")
    uploaded = st.file_uploader("Upload observation CSV", type=["csv"], key="material_observation_csv")
    st.caption(
        "CSV required columns: property_name, value, unit, source_document_id. Optional: state, source_url, checked_at, note. "
        "No semantic column guessing is performed."
    )
    if uploaded:
        try:
            bundle = load_observations_csv(
                uploaded.getvalue(),
                material_id=material_id,
                material_name=material_name,
                category=category,
            )
        except Exception as exc:
            st.error(f"Could not load CSV: {exc}")

if bundle is not None:
    st.subheader("1 · Source documents")
    source_rows = [
        {
            "document_id": source.document_id,
            "title": source.title,
            "manufacturer": source.manufacturer,
            "product_name": source.product_name,
            "source_url": source.source_url,
            "document_version": source.document_version,
            "checked_at": source.checked_at,
        }
        for source in bundle.sources.values()
    ]
    if source_rows:
        st.dataframe(pd.DataFrame(source_rows), use_container_width=True, hide_index=True)
    else:
        st.info("No source-document metadata was supplied beyond observation-level fields.")

    st.subheader("2 · Unit normalization")
    try:
        normalized = normalize_bundle(bundle)
        normalized_df = pd.DataFrame(normalized_rows(normalized))
        st.dataframe(normalized_df, use_container_width=True, hide_index=True)
        st.caption(
            "Normalization changes units only through explicit deterministic conversion rules (for example cm → mm or g/cm³ → kg/m³). "
            "Unknown units raise an error rather than being guessed."
        )
    except Exception as exc:
        normalized = []
        st.error(f"Normalization stopped: {exc}")

    if normalized:
        st.subheader("3 · Source conflict detection")
        conflicts = detect_property_conflicts(normalized)
        if conflicts:
            st.error(f"{len(conflicts)} unresolved property conflict(s). NitiKube will omit them from the material record until a source is explicitly selected.")
            for conflict in conflicts:
                with st.expander(f"Conflict: {conflict.canonical_name}", expanded=True):
                    st.write(conflict.reason)
                    st.dataframe(
                        pd.DataFrame(
                            [
                                {
                                    "source_document_id": obs.source_document_id,
                                    "value": obs.canonical_value,
                                    "unit": obs.canonical_unit,
                                    "state": obs.state.value,
                                    "source_url": obs.source_url,
                                    "checked_at": obs.checked_at,
                                }
                                for obs in conflict.observations
                            ]
                        ),
                        use_container_width=True,
                        hide_index=True,
                    )
        else:
            st.success("No cross-source conflicts exceed the current numeric/string tolerance.")

        st.subheader("4 · Resolved material record")
        record, unresolved = material_record_from_bundle(bundle)
        validation = validate_material(record)
        property_rows = [
            {
                "property": name,
                "value": prop.value,
                "unit": prop.unit,
                "state": prop.state.value,
                "source_url": prop.source_url,
                "checked_at": prop.checked_at,
                "note": prop.note,
            }
            for name, prop in record.properties.items()
        ]
        st.dataframe(pd.DataFrame(property_rows), use_container_width=True, hide_index=True)
        if validation.errors:
            st.error("Material cannot drive a verified recommendation yet:\n- " + "\n- ".join(validation.errors))
        elif validation.valid_for_verified_recommendation:
            st.success("Every current material property passes the verified-evidence policy.")
        else:
            st.warning("Material record is usable as evidence storage, but unverified/missing properties prevent it from being labelled fully verified.")
        for warning in validation.warnings:
            st.caption(f"• {warning}")

        st.subheader("5 · Constraint/suitability sandbox")
        st.write(
            "Define a numeric design requirement. NitiKube does not ship a hidden threshold here—the threshold is your design brief unless you also provide a source URL and checked timestamp. Unknown material properties are not treated as passes."
        )
        r1, r2, r3, r4 = st.columns(4)
        property_name = r1.selectbox("Property", sorted(PROPERTY_SPECS))
        comparator = r2.selectbox("Comparator", ["min", "max", "gt", "lt", "eq"])
        threshold = r3.number_input("Threshold", value=0.0, step=0.1)
        canonical_unit = PROPERTY_SPECS[property_name].canonical_unit
        r4.text_input("Canonical unit", canonical_unit or "classification / unitless", disabled=True)
        s1, s2 = st.columns(2)
        threshold_source = s1.text_input("Threshold source URL (optional)")
        threshold_checked = s2.text_input("Threshold checked_at (optional)")

        requirement = NumericRequirement(
            property_name=property_name,
            comparator=comparator,
            threshold=float(threshold),
            unit=canonical_unit,
            source_url=threshold_source or None,
            checked_at=threshold_checked or None,
        )
        result = evaluate_material(record, [requirement], verified_only=True)
        st.metric("Feasible under this requirement", "YES" if result.feasible else "NO")
        st.dataframe(pd.DataFrame(suitability_rows(result)), use_container_width=True, hide_index=True)

        export_payload = {
            "material_id": record.material_id,
            "name": record.name,
            "category": record.category,
            "aliases": record.aliases,
            "properties": {
                name: {
                    "value": prop.value,
                    "unit": prop.unit,
                    "state": prop.state.value,
                    "source_url": prop.source_url,
                    "checked_at": prop.checked_at,
                    "note": prop.note,
                }
                for name, prop in record.properties.items()
            },
            "notes": record.notes,
            "unresolved_conflicts": [conflict.canonical_name for conflict in unresolved],
        }
        st.download_button(
            "Download resolved material record JSON",
            json.dumps(export_payload, indent=2, ensure_ascii=False).encode("utf-8"),
            f"{record.material_id}_nitikube_material.json",
            "application/json",
        )
else:
    st.info("Upload a structured JSON or CSV evidence bundle to start. The lab intentionally ships with no production material facts baked in.")
