from __future__ import annotations

import pandas as pd
import streamlit as st

from nitikube.drainage_profile import (
    DrainageStatus,
    drainage_profile_brief_template,
    drainage_profile_evaluation_json,
    evaluate_drainage_artifacts,
)


st.set_page_config(page_title="NitiKube — Drainage Route Profile", page_icon="↘", layout="wide")
st.title("Drainage Route Elevation + Slope Lab")
st.caption(
    "Use the verified routing graph plus explicit target/node elevations to calculate route fall, segment slopes and sourced slope-threshold compliance without bundling invented plumbing standards."
)
st.warning(
    "The slope thresholds in this page must come from a cited standard, verified manufacturer requirement or qualified professional input. NitiKube supplies the maths and evidence state; it does not invent the required slope."
)

st.subheader("1 · Existing routed evidence")
network_file = st.file_uploader(
    "Upload `nitikube.service_network` JSON",
    type=["json"],
    key="drainage_network",
)
routing_eval_file = st.file_uploader(
    "Upload `nitikube.network_routing_evaluation` JSON",
    type=["json"],
    key="drainage_network_evaluation",
)
routing_brief_file = st.file_uploader(
    "Upload the service-routing brief used to create the route targets",
    type=["json"],
    key="drainage_routing_brief",
)

st.subheader("2 · Drainage engineering thresholds")
st.download_button(
    "Download drainage-profile brief template",
    drainage_profile_brief_template().encode("utf-8"),
    "nitikube_drainage_profile_brief_template.json",
    "application/json",
)
st.caption(
    "The template deliberately leaves `min_slope_percent` and `source_ref` empty. A numeric rule without provenance is rejected."
)
drainage_file = st.file_uploader(
    "Upload `nitikube.drainage_profile_brief` JSON",
    type=["json"],
    key="drainage_profile_brief",
)

if network_file and routing_eval_file and routing_brief_file and drainage_file and st.button(
    "Evaluate drainage route profiles",
    type="primary",
):
    try:
        evaluations = evaluate_drainage_artifacts(
            network_file.getvalue(),
            routing_eval_file.getvalue(),
            routing_brief_file.getvalue(),
            drainage_file.getvalue(),
        )
        st.session_state["drainage_profile_evaluations"] = evaluations
    except Exception as exc:
        st.error(f"Drainage profile evaluation could not run: {exc}")

evaluations = st.session_state.get("drainage_profile_evaluations")
if evaluations:
    st.subheader("3 · Profile audit")
    counts = {status: sum(item.status == status for item in evaluations) for status in DrainageStatus}
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("PASS", counts[DrainageStatus.PASS])
    c2.metric("FAIL", counts[DrainageStatus.FAIL])
    c3.metric("UNKNOWN", counts[DrainageStatus.UNKNOWN])
    c4.metric("N/A", counts[DrainageStatus.NOT_APPLICABLE])

    rows = []
    for item in evaluations:
        rows.append(
            {
                "service_requirement_id": item.service_requirement_id,
                "target_id": item.target_id,
                "service_point": item.point_id,
                "status": item.status.value.upper(),
                "plan_run_ft": item.total_plan_run_ft,
                "fall_in": item.total_fall_in,
                "avg_slope_percent": item.average_slope_percent,
                "required_min_fall_in": item.required_minimum_fall_in,
                "fall_margin_in": item.fall_margin_in,
                "source_ref": item.source_ref,
                "failed": " | ".join(item.failed),
                "unknown": " | ".join(item.unknown),
                "warnings": " | ".join(item.warnings),
            }
        )
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

    for item in evaluations:
        with st.expander(f"{item.service_requirement_id} · {item.status.value.upper()}"):
            st.write(f"**Threshold source:** `{item.source_ref}`")
            if item.segments:
                st.dataframe(
                    pd.DataFrame(
                        [
                            {
                                "segment": segment.segment_id,
                                "from": segment.start_label,
                                "to": segment.end_label,
                                "plan_run_ft": segment.plan_run_ft,
                                "start_z_ft": segment.start_z_ft,
                                "end_z_ft": segment.end_z_ft,
                                "fall_in": segment.fall_in,
                                "slope_percent": segment.slope_percent,
                                "vertical": segment.vertical,
                            }
                            for segment in item.segments
                        ]
                    ),
                    use_container_width=True,
                    hide_index=True,
                )
            for failure in item.failed:
                st.error(failure)
            for unknown in item.unknown:
                st.warning(f"UNKNOWN: {unknown}")
            for warning in item.warnings:
                st.info(warning)
            st.caption(item.model_note)

    st.download_button(
        "Download drainage profile evaluation JSON",
        drainage_profile_evaluation_json(evaluations).encode("utf-8"),
        "nitikube_drainage_profile_evaluation.json",
        "application/json",
    )

st.subheader("4 · Maths")
st.latex(r"\text{fall}_{in}=(z_{start}-z_{end})\times 12")
st.latex(r"\text{slope}_{\%}=\frac{\text{fall}_{in}}{\text{plan run}_{ft}\times 12}\times100")
st.latex(r"\text{required fall}_{in}=\text{plan run}_{ft}\times12\times\frac{\text{required slope}_{\%}}{100}")
st.write(
    "NitiKube checks both end-to-end fall and, when requested, every sloped segment. A later drop cannot hide an earlier local rise. Pure vertical drops are reported as vertical rather than assigning a meaningless percentage slope."
)

st.subheader("5 · Model boundary")
st.write(
    "This layer evaluates elevation geometry only. PASS does not establish drain diameter, discharge capacity, trap/vent design, fixture units, cleanout spacing, connection legality, waterproofing or jurisdictional compliance. Those require additional sourced rules and discipline-specific engineering."
)
