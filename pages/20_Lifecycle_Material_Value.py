from __future__ import annotations

import json

import pandas as pd
import streamlit as st

from nitikube.lifecycle import (
    LifecycleAssumptions,
    cashflow_rows,
    lifecycle_cost,
    lifecycle_rows,
    load_options_csv,
    load_options_json,
    pareto_value_comparison,
    sensitivity_band,
)


st.set_page_config(page_title="NitiKube — Lifecycle Material Value", page_icon="₹", layout="wide")
st.title("Lifecycle Material Value + Substitution Lab")
st.caption(
    "Compare material/finish alternatives over an explicit analysis horizon using installed cost, maintenance, replacement, disposal, residual value and discounting. Missing price/service-life evidence stays UNKNOWN rather than being treated as zero."
)
st.warning(
    "This is lifecycle cost engineering, not an investment-return forecast. Discount rate, escalation, service life, maintenance and replacement assumptions are visible inputs and must be sourced/user-verified for project decisions."
)

st.subheader("1 · Import material/finish options")
format_choice = st.radio("Option file format", ["JSON (supports evidence metadata)", "CSV (user-provided values)"], horizontal=True)
file_type = ["json"] if format_choice.startswith("JSON") else ["csv"]
uploaded = st.file_uploader("Upload lifecycle material options", type=file_type, key="lifecycle_options")
options = []
if uploaded:
    try:
        options = load_options_json(uploaded.getvalue()) if format_choice.startswith("JSON") else load_options_csv(uploaded.getvalue())
        st.success(f"Loaded {len(options)} option(s).")
        st.dataframe(pd.DataFrame([{
            "option_id": option.option_id,
            "name": option.name,
            "currency": option.currency,
            "area": option.area,
            "area_unit": option.area_unit,
            "material_cost_per_area": option.material_cost_per_area,
            "labour_cost_per_area": option.labour_cost_per_area,
            "annual_maintenance_cost": option.annual_maintenance_cost,
            "service_life_years": option.service_life_years,
            "waste_fraction": option.waste_fraction,
            "performance_score": option.performance_score,
            "features": " | ".join(option.features),
            "evidence_fields": " | ".join(field for field, _ in option.evidence),
        } for option in options]), use_container_width=True, hide_index=True)
    except Exception as exc:
        st.error(f"Lifecycle options could not be loaded: {exc}")

example = {
    "options": [
        {
            "option_id": "REPLACE-ME",
            "name": "Replace with real material/product",
            "currency": "INR",
            "area": 100,
            "area_unit": "ft2",
            "material_cost_per_area": None,
            "labour_cost_per_area": None,
            "initial_fixed_cost": 0,
            "annual_maintenance_cost": None,
            "service_life_years": None,
            "replacement_cost_fraction": 1.0,
            "disposal_cost_per_replacement": 0,
            "waste_fraction": 0,
            "performance_score": None,
            "features": [],
            "evidence": {
                "material_cost_per_area": {
                    "state": "unverified",
                    "source_url": None,
                    "checked_at": None,
                    "note": "Populate from a current retailer/manufacturer/quotation source."
                },
                "service_life_years": {
                    "state": "unverified",
                    "source_url": None,
                    "checked_at": None,
                    "note": "Populate from manufacturer/sourced lifecycle evidence."
                }
            }
        }
    ]
}
st.download_button(
    "Download lifecycle JSON template",
    json.dumps(example, indent=2).encode("utf-8"),
    "nitikube_lifecycle_material_template.json",
    "application/json",
)

st.subheader("2 · Analysis assumptions")
a1, a2, a3 = st.columns(3)
horizon = a1.number_input("Analysis horizon years", min_value=1, max_value=100, value=20, step=1)
discount_rate = a2.number_input("Annual discount rate", min_value=-0.99, max_value=1.0, value=0.05, step=0.01, format="%.3f")
escalation = a3.number_input("Annual cost escalation rate", min_value=-0.99, max_value=1.0, value=0.03, step=0.01, format="%.3f")
include_residual = st.checkbox("Credit residual service value at analysis horizon", value=True)
require_verified = st.checkbox(
    "Require VERIFIED evidence for material cost, labour cost, annual maintenance and service life",
    value=False,
    help="When enabled, a known number without VERIFIED source evidence is still treated as not ready for a verified lifecycle comparison.",
)

f1, f2 = st.columns(2)
required_features_text = f1.text_input("Required features (comma-separated)", "")
excluded_features_text = f2.text_input("Excluded features (comma-separated)", "")
required_features = tuple(part.strip() for part in required_features_text.split(",") if part.strip())
excluded_features = tuple(part.strip() for part in excluded_features_text.split(",") if part.strip())
assumptions = LifecycleAssumptions(
    horizon_years=int(horizon),
    discount_rate=float(discount_rate),
    annual_cost_escalation_rate=float(escalation),
    include_residual_value=include_residual,
)

s1, s2 = st.columns(2)
low_multiplier = s1.number_input("Low-cost sensitivity multiplier", min_value=0.01, max_value=1.0, value=0.90, step=0.05)
high_multiplier = s2.number_input("High-cost sensitivity multiplier", min_value=1.0, value=1.20, step=0.05)
st.caption("Sensitivity multipliers are deterministic what-if bounds. NitiKube does not claim they are probability intervals unless a separate statistical model and evidence justify that interpretation.")

if options and st.button("Calculate lifecycle costs and substitutions", type="primary"):
    results = {}
    sensitivities = {}
    errors = []
    for option in options:
        try:
            result = lifecycle_cost(
                option,
                assumptions,
                require_verified_evidence=require_verified,
                required_features=required_features,
                excluded_features=excluded_features,
            )
            results[option.option_id] = result
            sensitivities[option.option_id] = sensitivity_band(
                option,
                assumptions,
                low_multiplier=float(low_multiplier),
                high_multiplier=float(high_multiplier),
                require_verified_evidence=require_verified,
                required_features=required_features,
                excluded_features=excluded_features,
            )
        except Exception as exc:
            errors.append(f"{option.option_id}: {exc}")
    st.session_state["lifecycle_results"] = results
    st.session_state["lifecycle_sensitivity"] = sensitivities
    st.session_state["lifecycle_errors"] = errors

results = st.session_state.get("lifecycle_results", {})
sensitivities = st.session_state.get("lifecycle_sensitivity", {})
errors = st.session_state.get("lifecycle_errors", [])
for error in errors:
    st.error(error)

if options and results:
    st.subheader("3 · Lifecycle result")
    ordered_results = [results[option.option_id] for option in options if option.option_id in results]
    table = pd.DataFrame(lifecycle_rows(ordered_results))
    st.dataframe(table.drop(columns=["cashflows"], errors="ignore"), use_container_width=True, hide_index=True)

    comparison = pareto_value_comparison(options, results)
    comparison_df = pd.DataFrame([{
        "option_id": row.option_id,
        "name": row.name,
        "feasible": row.feasible,
        "npv_cost": row.npv_cost,
        "equivalent_annual_cost": row.equivalent_annual_cost,
        "performance_score": row.performance_score,
        "performance_per_npv_currency": row.npv_performance_cost,
        "pareto_efficient": row.pareto_efficient,
    } for row in comparison])
    st.subheader("4 · Cost × performance Pareto comparison")
    st.dataframe(comparison_df, use_container_width=True, hide_index=True)
    st.caption("Performance score is an explicit input/evidence result, not generated by lifecycle cost maths. Pareto-efficient means no other feasible option is both cheaper (NPV) and at least as high performing with one strict improvement.")

    sensitivity_df = pd.DataFrame([{
        "option_id": option_id,
        "low_npv": band.low_npv,
        "base_npv": band.base_npv,
        "high_npv": band.high_npv,
        "low_multiplier": band.low_multiplier,
        "high_multiplier": band.high_multiplier,
    } for option_id, band in sensitivities.items()])
    st.subheader("5 · Deterministic cost sensitivity")
    st.dataframe(sensitivity_df, use_container_width=True, hide_index=True)

    feasible_options = [option for option in options if results.get(option.option_id) and results[option.option_id].feasible]
    if feasible_options:
        option_map = {f"{option.option_id} · {option.name}": option for option in feasible_options}
        selected_label = st.selectbox("Inspect lifecycle cash flow", list(option_map))
        selected = option_map[selected_label]
        selected_result = results[selected.option_id]
        cashflow_df = pd.DataFrame(cashflow_rows(selected_result))
        st.dataframe(cashflow_df, use_container_width=True, hide_index=True)
        st.download_button(
            "Download selected lifecycle cash flows CSV",
            cashflow_df.to_csv(index=False).encode("utf-8"),
            f"{selected.option_id}_lifecycle_cashflows.csv",
            "text/csv",
        )

    export = {
        "schema": "nitikube.lifecycle_comparison",
        "schema_version": "0.19",
        "assumptions": {
            "horizon_years": assumptions.horizon_years,
            "discount_rate": assumptions.discount_rate,
            "annual_cost_escalation_rate": assumptions.annual_cost_escalation_rate,
            "include_residual_value": assumptions.include_residual_value,
            "require_verified_evidence": require_verified,
            "required_features": list(required_features),
            "excluded_features": list(excluded_features),
            "low_multiplier": float(low_multiplier),
            "high_multiplier": float(high_multiplier),
        },
        "results": table.drop(columns=["cashflows"], errors="ignore").to_dict(orient="records"),
        "pareto": comparison_df.to_dict(orient="records"),
        "sensitivity": sensitivity_df.to_dict(orient="records"),
        "note": "Lifecycle cost is conditional on the explicit input/evidence assumptions; it is not a guarantee of future price, maintenance frequency or service life.",
    }
    st.download_button(
        "Download lifecycle comparison JSON",
        json.dumps(export, indent=2, ensure_ascii=False, default=str).encode("utf-8"),
        "nitikube_lifecycle_comparison.json",
        "application/json",
    )

st.subheader("6 · Interpretation")
st.write(
    "NitiKube can use this layer to answer questions such as: 'Material B costs more today, but does it still cost more over 20 years after replacement and maintenance?' or 'Which options remain non-dominated when both lifecycle cost and a separately sourced performance score matter?'"
)
st.caption(
    "Next layers: labour-region evidence, pack/slab/sheet purchase granularity, price-history uncertainty, service-life probability models, carbon/embodied-energy lifecycle metrics, repairability, salvage/disposal evidence and direct integration with the whole-home optimizer."
)
