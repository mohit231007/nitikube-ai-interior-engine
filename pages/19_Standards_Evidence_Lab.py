from __future__ import annotations

import json

import pandas as pd
import streamlit as st

from nitikube.standards import (
    RuleContext,
    RuleStatus,
    detect_conflicts,
    evaluate_rules,
    evaluation_rows,
    load_rules_csv,
    load_rules_json,
    rule_rows,
)


st.set_page_config(page_title="NitiKube — Standards Evidence Lab", page_icon="§", layout="wide")
st.title("Standards / Guidance Evidence Lab")
st.caption(
    "Load sourced numeric rules with authority, jurisdiction, document version, URL, locator and checked timestamp. NitiKube normalizes compatible units, evaluates actual project values, and surfaces conflicts instead of hiding them behind generic 'best practice'."
)

st.warning(
    "This page ships with no production code/standard values. A rule is only as reliable/current/applicable as its source metadata. Legal/regulatory compliance still requires jurisdiction-specific professional verification where applicable."
)

st.subheader("1 · Import sourced rules")
format_choice = st.radio("Rule file format", ["JSON", "CSV"], horizontal=True)
rule_file = st.file_uploader("Upload standards/guidance rule evidence", type=["json"] if format_choice == "JSON" else ["csv"], key="standards_rules")
rules = []
if rule_file:
    try:
        rules = load_rules_json(rule_file.getvalue()) if format_choice == "JSON" else load_rules_csv(rule_file.getvalue())
        st.success(f"Loaded {len(rules)} sourced numeric rule(s).")
        st.dataframe(pd.DataFrame(rule_rows(rules)), use_container_width=True, hide_index=True)
    except Exception as exc:
        st.error(f"Rules could not be loaded: {exc}")

example = {
    "rules": [
        {
            "rule_id": "EXAMPLE-ONLY-001",
            "subject": "circulation",
            "metric": "passage_width",
            "operator": "min",
            "value": 0,
            "unit": "mm",
            "room_types": ["example-room"],
            "applicability_tags": ["example-only"],
            "mandatory": False,
            "summary": "Template only. Replace the zero placeholder with a value from a real source; do not use this as a design rule.",
            "source": {
                "title": "REPLACE WITH REAL SOURCE TITLE",
                "authority": "REPLACE WITH REAL AUTHORITY",
                "jurisdiction": "REPLACE WITH JURISDICTION",
                "document_version": "REPLACE WITH VERSION",
                "source_url": "https://example.com/replace-me",
                "checked_at": "2026-08-11T18:00:00+00:00",
                "effective_date": None,
                "locator": "REPLACE WITH CLAUSE/PAGE/TABLE"
            }
        }
    ]
}
st.download_button(
    "Download rule JSON template",
    json.dumps(example, indent=2).encode("utf-8"),
    "nitikube_standard_rule_template.json",
    "application/json",
)

if rules:
    st.subheader("2 · Source/rule conflict scan")
    conflicts = detect_conflicts(rules)
    if conflicts:
        st.error(f"Detected {len(conflicts)} same-scope numeric conflict group(s). NitiKube will not silently choose one rule.")
        conflict_rows = []
        for conflict in conflicts:
            conflict_rows.append({
                "metric": conflict.metric,
                "rule_ids": ", ".join(conflict.rule_ids),
                "normalized_unit": conflict.normalized_unit,
                "intervals": str(conflict.intervals),
                "reason": conflict.reason,
            })
        st.dataframe(pd.DataFrame(conflict_rows), use_container_width=True, hide_index=True)
    else:
        st.success("No disjoint numeric intervals were detected among rules with identical applicability signatures.")

    st.subheader("3 · Define project applicability context")
    all_rooms = sorted({room for rule in rules for room in rule.room_types})
    all_tags = sorted({tag for rule in rules for tag in rule.applicability_tags})
    all_jurisdictions = sorted({rule.source.jurisdiction for rule in rules})
    c1, c2, c3 = st.columns(3)
    room_type = c1.selectbox("Room type", ["(unspecified)"] + all_rooms)
    jurisdiction = c2.selectbox("Jurisdiction", ["(unspecified)"] + all_jurisdictions)
    tags = c3.multiselect("Applicability tags", all_tags, default=all_tags)
    context = RuleContext(
        room_type=None if room_type == "(unspecified)" else room_type,
        tags=tuple(tags),
        jurisdiction=None if jurisdiction == "(unspecified)" else jurisdiction,
    )

    st.subheader("4 · Enter actual project measurements")
    metrics = sorted({rule.metric for rule in rules})
    input_rows = pd.DataFrame([{"metric": metric, "actual_value": None, "actual_unit": ""} for metric in metrics])
    edited = st.data_editor(input_rows, use_container_width=True, hide_index=True, num_rows="fixed", key="standard_actuals")
    actuals = {}
    for _, row in edited.iterrows():
        metric = str(row.get("metric") or "").strip()
        if not metric:
            continue
        value = row.get("actual_value")
        unit = str(row.get("actual_unit") or "").strip()
        actuals[metric] = (None if pd.isna(value) else float(value), unit or None)

    if st.button("Evaluate project values against sourced rules", type="primary"):
        evaluations = evaluate_rules(rules, actuals, context=context)
        st.session_state["standards_evaluations"] = evaluations

    evaluations = st.session_state.get("standards_evaluations")
    if evaluations:
        result_df = pd.DataFrame(evaluation_rows(evaluations))
        st.dataframe(result_df, use_container_width=True, hide_index=True)
        status_counts = result_df["status"].value_counts().to_dict()
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("PASS", status_counts.get(RuleStatus.PASS.value, 0))
        m2.metric("FAIL", status_counts.get(RuleStatus.FAIL.value, 0))
        m3.metric("UNKNOWN", status_counts.get(RuleStatus.UNKNOWN.value, 0))
        m4.metric("N/A", status_counts.get(RuleStatus.NOT_APPLICABLE.value, 0))

        mandatory_failures = [item for item in evaluations if item.mandatory and item.status in {RuleStatus.FAIL, RuleStatus.UNKNOWN}]
        if mandatory_failures:
            st.error(
                f"{len(mandatory_failures)} mandatory applicable rule(s) are FAIL/UNKNOWN. NitiKube should not promote this state as verified compliant."
            )
        else:
            st.success("No mandatory applicable rule is currently FAIL/UNKNOWN in this evaluation set.")

        export = {
            "schema": "nitikube.rule_evaluation",
            "schema_version": "0.18",
            "context": {
                "room_type": context.room_type,
                "tags": list(context.tags),
                "jurisdiction": context.jurisdiction,
            },
            "results": evaluation_rows(evaluations),
            "note": "Compliance interpretation is limited to the uploaded sourced numeric rules and supplied context. Professional/legal verification may still be required.",
        }
        st.download_button(
            "Download rule-evaluation JSON",
            json.dumps(export, indent=2, ensure_ascii=False).encode("utf-8"),
            "nitikube_rule_evaluation.json",
            "application/json",
        )

st.subheader("5 · How this connects to room planners")
st.write(
    "A future adapter can map sourced metrics such as `passage_width`, `fixture_front_clearance`, `work_triangle_leg`, `illuminance`, `air_changes`, or waterproofing requirements into the deterministic planner inputs. "
    "The key architectural rule is that the planner must carry the rule ID/source when a threshold is claimed as a standard, and must preserve UNKNOWN/conflict states instead of turning them into arbitrary defaults."
)
st.caption(
    "NitiKube's standards registry is an evidence framework, not a pirated standards database. Source documents may be copyrighted/licensed; store citations/locators and permitted structured facts, and respect access/licensing restrictions."
)
