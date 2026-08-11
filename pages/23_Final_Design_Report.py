from __future__ import annotations

import json

import streamlit as st
import streamlit.components.v1 as components

from nitikube.final_report import audit_json, audit_report_inputs, render_final_report


st.set_page_config(page_title="NitiKube — Final Design Report", page_icon="▤", layout="wide")
st.title("Final Design Package Report")
st.caption(
    "Turn a hashed NitiKube project package plus optional standards/lifecycle evidence artifacts into one print-friendly deterministic homeowner/contractor report."
)
st.warning(
    "The report does not turn missing or unverified inputs into facts. Open professional-verification flags, mandatory FAIL/UNKNOWN rules and lifecycle unknowns remain visible."
)

st.subheader("1 · Design package")
package_file = st.file_uploader("Upload `nitikube_design_package.json`", type=["json"], key="final_report_package")
standards_file = st.file_uploader(
    "Optional standards/guidance evaluation JSON",
    type=["json"],
    key="final_report_standards",
)
lifecycle_file = st.file_uploader(
    "Optional lifecycle material comparison JSON",
    type=["json"],
    key="final_report_lifecycle",
)
allow_invalid_hash = st.checkbox(
    "Allow report generation even if design-package hash verification FAILS",
    value=False,
    help="Default is blocked. Enable only for forensic/debugging review; the report will display FAIL / OVERRIDDEN.",
)

if package_file:
    package_bytes = package_file.getvalue()
    standards_bytes = standards_file.getvalue() if standards_file else None
    lifecycle_bytes = lifecycle_file.getvalue() if lifecycle_file else None
    try:
        audit = audit_report_inputs(
            package_bytes,
            standards_evaluation=standards_bytes,
            lifecycle_comparison=lifecycle_bytes,
        )
        st.subheader("2 · Pre-render audit")
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Package hash", "PASS" if audit.package_hash_valid else "FAIL")
        m2.metric("Selected rooms", f"{audit.selected_room_count} / {audit.required_room_count}")
        m3.metric("Professional flags", audit.professional_verification_flag_count)
        m4.metric("Mandatory rule unresolved", audit.mandatory_standard_unresolved_count)

        s1, s2, s3, s4 = st.columns(4)
        s1.metric("Rule PASS", audit.standard_pass_count)
        s2.metric("Rule FAIL", audit.standard_fail_count)
        s3.metric("Rule UNKNOWN", audit.standard_unknown_count)
        s4.metric("Lifecycle non-feasible/unknown", audit.lifecycle_nonfeasible_count)
        for warning in audit.warnings:
            st.warning(warning)

        if st.button("Render final report", type="primary"):
            artifact = render_final_report(
                package_bytes,
                standards_evaluation=standards_bytes,
                lifecycle_comparison=lifecycle_bytes,
                allow_invalid_package_hash=allow_invalid_hash,
            )
            st.session_state["final_report_artifact"] = artifact
    except Exception as exc:
        st.error(f"Report inputs are invalid/incompatible: {exc}")

artifact = st.session_state.get("final_report_artifact")
if artifact:
    st.subheader("3 · Report preview")
    st.write(f"**Report ID (SHA-256 of rendered HTML):** `{artifact.report_id}`")
    components.html(artifact.html, height=1100, scrolling=True)
    st.subheader("4 · Download")
    d1, d2 = st.columns(2)
    d1.download_button(
        "Download print-friendly HTML report",
        artifact.html.encode("utf-8"),
        "nitikube_final_design_report.html",
        "text/html",
    )
    d2.download_button(
        "Download report audit JSON",
        audit_json(artifact).encode("utf-8"),
        "nitikube_final_report_audit.json",
        "application/json",
    )
    st.caption(
        "Open the HTML in a browser and use Print → Save as PDF if a PDF copy is needed. The generated HTML remains the deterministic source report artifact."
    )
else:
    st.info("Upload a design package to audit and render. Standards/lifecycle attachments are optional; when absent, the report says they are absent rather than fabricating conclusions.")

st.subheader("5 · Report evidence boundary")
st.write(
    "A valid report hash/package hash provides integrity/reproducibility. It does not certify that an input measurement, product price, material service life, standard interpretation or professional scope is correct. NitiKube keeps those source/evidence responsibilities visible in the final handoff."
)
