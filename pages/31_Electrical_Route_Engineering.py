from __future__ import annotations

import pandas as pd
import streamlit as st

from nitikube.electrical_route import (
    ElectricalStatus,
    electrical_route_brief_template,
    electrical_route_evaluation_json,
    evaluate_electrical_artifacts,
)


st.set_page_config(page_title="NitiKube — Electrical Route Engineering", page_icon="⚡", layout="wide")
st.title("Routed Electrical Voltage Drop + Conductor Loss Lab")
st.caption(
    "Use verified routed cable length plus sourced conductor R/X evidence to calculate voltage drop and I²R losses. Thresholds and conductor properties remain explicit evidence inputs."
)
st.warning(
    "This is not an electrical-safety certificate. NitiKube does not infer cable size, ampacity, protective-device rating, earthing, fault current, short-circuit withstand or code compliance from this calculation."
)

st.subheader("1 · Routed evidence")
network_file = st.file_uploader(
    "Upload `nitikube.service_network` JSON",
    type=["json"],
    key="electrical_network",
)
routing_eval_file = st.file_uploader(
    "Upload `nitikube.network_routing_evaluation` JSON",
    type=["json"],
    key="electrical_routing_eval",
)

st.subheader("2 · Circuit / conductor evidence")
st.download_button(
    "Download electrical-route brief template",
    electrical_route_brief_template().encode("utf-8"),
    "nitikube_electrical_route_brief_template.json",
    "application/json",
)
st.caption(
    "The template deliberately leaves voltage, current, conductor resistance, conductor source and voltage-drop limit empty. AC PASS/FAIL is withheld when reactance evidence is absent."
)
electrical_file = st.file_uploader(
    "Upload `nitikube.electrical_route_brief` JSON",
    type=["json"],
    key="electrical_route_brief",
)

if network_file and routing_eval_file and electrical_file and st.button(
    "Evaluate routed electrical circuits",
    type="primary",
):
    try:
        evaluations = evaluate_electrical_artifacts(
            network_file.getvalue(),
            routing_eval_file.getvalue(),
            electrical_file.getvalue(),
        )
        st.session_state["electrical_route_evaluations"] = evaluations
    except Exception as exc:
        st.error(f"Electrical route evaluation could not run: {exc}")

evaluations = st.session_state.get("electrical_route_evaluations")
if evaluations:
    st.subheader("3 · Circuit audit")
    counts = {status: sum(item.status == status for item in evaluations) for status in ElectricalStatus}
    cols = st.columns(5)
    cols[0].metric("PASS", counts[ElectricalStatus.PASS])
    cols[1].metric("FAIL", counts[ElectricalStatus.FAIL])
    cols[2].metric("CALCULATED", counts[ElectricalStatus.CALCULATED])
    cols[3].metric("UNKNOWN", counts[ElectricalStatus.UNKNOWN])
    cols[4].metric("N/A", counts[ElectricalStatus.NOT_APPLICABLE])

    st.dataframe(
        pd.DataFrame(
            [
                {
                    "service_requirement_id": item.service_requirement_id,
                    "point_id": item.point_id,
                    "topology": item.topology,
                    "status": item.status.value.upper(),
                    "route_ft": item.routed_length_ft,
                    "design_length_ft": item.design_length_ft,
                    "R_eff_ohm_per_km": item.effective_resistance_ohm_per_km,
                    "X_eff_ohm_per_km": item.effective_reactance_ohm_per_km,
                    "drop_V": item.voltage_drop_v,
                    "drop_%": item.voltage_drop_percent,
                    "receiving_V": item.receiving_voltage_v,
                    "copper_loss_W": item.copper_loss_w,
                    "energy_loss_kWh": item.energy_loss_kwh,
                    "limit_%": item.max_voltage_drop_percent,
                    "margin_pp": item.margin_percent_points,
                    "conductor_source": item.conductor_source_ref,
                    "limit_source": item.voltage_drop_limit_source_ref,
                }
                for item in evaluations
            ]
        ),
        use_container_width=True,
        hide_index=True,
    )

    for item in evaluations:
        with st.expander(f"{item.service_requirement_id} · {item.status.value.upper()}"):
            st.write(f"**Conductor evidence:** `{item.conductor_source_ref}`")
            if item.voltage_drop_limit_source_ref:
                st.write(f"**Voltage-drop limit evidence:** `{item.voltage_drop_limit_source_ref}`")
            for failure in item.failed:
                st.error(failure)
            for unknown in item.unknown:
                st.warning(f"UNKNOWN: {unknown}")
            for warning in item.warnings:
                st.info(warning)
            st.caption(item.model_note)

    st.download_button(
        "Download electrical route evaluation JSON",
        electrical_route_evaluation_json(evaluations).encode("utf-8"),
        "nitikube_electrical_route_evaluation.json",
        "application/json",
    )

st.subheader("4 · Maths")
st.write("For a two-wire DC circuit:")
st.latex(r"\Delta V = 2 I L R")
st.write("For a single-phase AC circuit:")
st.latex(r"\Delta V = 2 I L (R\cos\phi + X\sin\phi)")
st.write("For a balanced three-phase AC circuit:")
st.latex(r"\Delta V = \sqrt{3} I L (R\cos\phi + X\sin\phi)")
st.write("Percentage voltage drop and routed conductor loss:")
st.latex(r"\Delta V_{\%}=100\frac{\Delta V}{V_{nom}}\qquad P_{loss}=n I^2 R_{line}")
st.caption(
    "Here L is one-way routed cable length in km after explicit slack, R/X are effective per-phase conductor values after optional temperature and parallel-conductor adjustment, and n is 2 for two-wire circuits or 3 for the balanced three-phase copper-loss calculation."
)

st.subheader("5 · Evidence boundary")
st.write(
    "A voltage-drop PASS only means the supplied circuit model is at or below the supplied sourced voltage-drop limit. It does not prove that the conductor is safely sized or that the circuit is compliant. Ampacity, installation method, grouping, ambient temperature, protective devices, fault loop/short-circuit behavior, earthing and jurisdictional rules remain separate evidence layers."
)
