from __future__ import annotations

import json

import streamlit as st

from nitikube.whole_home_factory import (
    brief_template_from_geometry,
    build_whole_home_candidates,
    candidate_rows,
    factory_audit_json,
    factory_rows,
    room_options_json,
)


st.set_page_config(page_title="NitiKube — Whole-Home Candidate Factory", page_icon="⌂", layout="wide")
st.title("Whole-Home Candidate Factory")
st.caption(
    "Verified geometry + an explicit homeowner/design brief → deterministic room candidates → optimizer-ready options → optional whole-home selection + hashed design package."
)
st.warning(
    "This page does not invent furniture dimensions, product costs, decision scores, circulation thresholds or opening-clearance depths. Missing inputs remain blocked/unknown."
)

st.subheader("1 · Authoritative verified geometry")
geometry_file = st.file_uploader(
    "Upload `nitikube_verified_geometry.json`",
    type=["json"],
    key="whole_home_factory_geometry",
)

geometry_bytes = geometry_file.getvalue() if geometry_file else None
if geometry_bytes:
    try:
        template = brief_template_from_geometry(geometry_bytes)
        st.success("Verified geometry parsed. A room-aware design-brief template is ready.")
        st.download_button(
            "Download room-aware brief template",
            template.encode("utf-8"),
            "nitikube_whole_home_brief_template.json",
            "application/json",
        )
        with st.expander("Preview generated brief template"):
            st.json(json.loads(template))
    except Exception as exc:
        st.error(f"Verified geometry cannot be used by the factory: {exc}")

st.subheader("2 · Explicit design brief")
brief_file = st.file_uploader(
    "Upload a completed `nitikube.whole_home_brief` JSON",
    type=["json"],
    key="whole_home_factory_brief",
)
brief_text = st.text_area(
    "Or paste the completed brief JSON",
    value="",
    height=260,
    placeholder="Paste the room-aware template after filling its explicit dimensions, costs, decision scores and optional optimization settings.",
)

st.caption(
    "Room-name keywords can deterministically infer kitchen / bedroom / bathroom / drawing+dining roles, but an explicit `role` in the brief always wins. Anonymous or ambiguous rooms stay unresolved."
)

if geometry_bytes and (brief_file or brief_text.strip()) and st.button("Generate whole-home candidates", type="primary"):
    try:
        brief_payload = brief_file.getvalue() if brief_file else brief_text.strip()
        result = build_whole_home_candidates(
            geometry_bytes,
            brief_payload,
            geometry_artifact_name=geometry_file.name if geometry_file else "nitikube_verified_geometry.json",
        )
        st.session_state["whole_home_factory_result"] = result
    except Exception as exc:
        st.error(f"Whole-home factory could not run: {exc}")

result = st.session_state.get("whole_home_factory_result")
if result:
    st.subheader("3 · Room factory audit")
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Required rooms", len(result.required_room_ids))
    m2.metric("Generated candidates", sum(len(room.candidates) for room in result.room_results))
    m3.metric("Optimizer options", len(result.optimizer_options))
    m4.metric("Optimizer-ready scope", "YES" if result.optimizer_ready else "NO")

    st.dataframe(factory_rows(result), use_container_width=True, hide_index=True)
    for diagnostic in result.diagnostics:
        st.warning(diagnostic)

    candidates = candidate_rows(result)
    if candidates:
        st.subheader("4 · Candidate geometry")
        st.dataframe(candidates, use_container_width=True, hide_index=True)
        st.caption(
            "`geometry_score` remains a deterministic geometry/circulation signal. It does not become aesthetics, comfort or any other decision score unless the brief explicitly maps it through `geometry_score_blend`."
        )

    st.subheader("5 · Whole-home optimization")
    if result.optimization is None:
        st.info("Optimization was not run. Complete explicit cost + decision-score inputs for every required room and include an `optimization` object with a budget.")
    else:
        optimization = result.optimization
        o1, o2, o3, o4 = st.columns(4)
        o1.metric("Feasible", "YES" if optimization.feasible else "NO")
        o2.metric("Selected cost", f"{optimization.selected_cost:,.2f}" if optimization.selected_cost is not None else "—")
        o3.metric("Budget remaining", f"{optimization.budget_remaining:,.2f}" if optimization.budget_remaining is not None else "—")
        o4.metric("States considered", optimization.states_considered)
        st.write(optimization.message)
        if optimization.selected:
            st.dataframe(
                [
                    {
                        "room_id": item.room_id,
                        "option_id": item.option_id,
                        "option_name": item.option_name,
                        "cost": item.cost,
                        "utility": item.utility,
                    }
                    for item in optimization.selected
                ],
                use_container_width=True,
                hide_index=True,
            )

    st.subheader("6 · Reproducible artifacts")
    st.write(f"**Verified geometry SHA-256:** `{result.geometry_sha256}`")
    if result.option_artifact_sha256:
        st.write(f"**Generated room-option artifact SHA-256:** `{result.option_artifact_sha256}`")

    d1, d2, d3 = st.columns(3)
    d1.download_button(
        "Download factory audit JSON",
        factory_audit_json(result).encode("utf-8"),
        "nitikube_whole_home_factory_audit.json",
        "application/json",
    )
    if result.optimizer_options:
        d2.download_button(
            "Download optimizer room options",
            room_options_json(result.optimizer_options, project_name=result.project_name).encode("utf-8"),
            "nitikube_factory_room_options.json",
            "application/json",
        )
    if result.design_package:
        d3.download_button(
            "Download hashed design package",
            json.dumps(result.design_package, indent=2, ensure_ascii=False).encode("utf-8"),
            "nitikube_design_package.json",
            "application/json",
        )
        st.success(
            "A feasible whole-home selection was converted directly into a provenance-preserving `nitikube.design_package`. It can feed the 3D/report/handoff layers."
        )

    st.subheader("7 · Evidence boundary")
    st.write(
        "The factory automates planner dispatch and project assembly, not truth creation. Explicit dimensions/rates/scores remain attributable brief inputs; verified openings remain geometry constraints; non-rectangular rooms fail rather than being replaced by bounding boxes; professional-verification flags survive into the final design package."
    )
else:
    st.info(
        "Upload verified geometry, download/fill the room-aware brief template, then run the factory. Geometry-only candidates can still be produced without costs/scores, but they will not be promoted into optimizer-ready recommendations."
    )
