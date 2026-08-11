from __future__ import annotations

import json

import pandas as pd
import streamlit as st

from nitikube.guardrails import (
    ArtifactSensitivity,
    PrivacyPolicy,
    ProviderBudgetPolicy,
    SessionUsageLedger,
    artifact_should_be_retained,
    authorize_provider_call,
    check_external_transfer,
    fingerprint_artifact,
    policy_manifest,
    record_authorized_call,
    safe_telemetry_event,
)


st.set_page_config(page_title="NitiKube — Privacy + Zero-Cost Guardrails", page_icon="◈", layout="wide")
st.title("Privacy + Zero-Paid-Cost Guardrails")
st.caption(
    "Make external-service limits and home-data transfer rules explicit before a public deployment. The default posture is: sensitive home artifacts are not retained or sent externally, and positive-cost provider calls are blocked."
)

st.warning(
    "Application-side quota gates are defense-in-depth, not a guarantee against a provider changing pricing or account billing behaviour. Production must also configure provider-side hard spending limits/disabled paid overage wherever the provider supports them."
)

st.subheader("1 · Privacy policy")
p1, p2 = st.columns(2)
retain_any = p1.checkbox("Permit uploaded-artifact retention", value=False)
external_transfer = p2.checkbox("Permit external artifact transfer at all", value=False)

r1, r2, r3 = st.columns(3)
retain_plan = r1.checkbox("Retain raw floor plans", value=False, disabled=not retain_any)
retain_photo = r2.checkbox("Retain raw home photos", value=False, disabled=not retain_any)
retain_quote = r3.checkbox("Retain raw quotations", value=False, disabled=not retain_any)
consent_required = st.checkbox("Require explicit consent before sending sensitive artifacts to a third party", value=True)
telemetry_mode = st.radio("Telemetry mode", ["metadata_only", "off"], horizontal=True)
privacy = PrivacyPolicy(
    retain_uploaded_artifacts=retain_any,
    retain_raw_floor_plans=retain_plan,
    retain_raw_home_photos=retain_photo,
    retain_raw_quotations=retain_quote,
    external_artifact_transfer_enabled=external_transfer,
    require_explicit_user_consent_for_sensitive_transfer=consent_required,
    telemetry_mode=telemetry_mode,
)

retention_df = pd.DataFrame([
    {
        "artifact_type": sensitivity.value,
        "retained_under_current_policy": artifact_should_be_retained(privacy, sensitivity),
    }
    for sensitivity in ArtifactSensitivity
])
st.dataframe(retention_df, use_container_width=True, hide_index=True)

st.subheader("2 · Test a sensitive-artifact transfer")
t1, t2, t3 = st.columns(3)
sensitivity = ArtifactSensitivity(t1.selectbox("Artifact sensitivity", [item.value for item in ArtifactSensitivity], index=4))
provider = t2.text_input("Third-party provider", "example-provider")
user_consent = t3.checkbox("User explicitly consented to this transfer", value=False)
try:
    transfer = check_external_transfer(
        privacy,
        sensitivity=sensitivity,
        provider=provider,
        user_consent=user_consent,
    )
    st.write({
        "decision": transfer.decision.value,
        "reason": transfer.reason,
        "sensitivity": transfer.sensitivity.value,
        "provider": transfer.provider,
        "user_consent": transfer.user_consent,
    })
except Exception as exc:
    st.error(str(exc))

st.subheader("3 · Zero-paid-cost provider policy")
z1, z2, z3 = st.columns(3)
provider_name = z1.text_input("Provider", "search-provider")
operation = z2.text_input("Operation", "product_search")
max_calls = z3.number_input("Maximum calls per session", min_value=0, value=5, step=1)

z4, z5, z6 = st.columns(3)
estimated_cost = z4.number_input("Declared estimated cost per call", min_value=0.0, value=0.0, step=0.001, format="%.4f")
paid_enabled = z5.checkbox("Allow paid usage", value=False)
max_paid_cost = z6.number_input("Maximum paid cost per session", min_value=0.0, value=0.0, step=0.01, disabled=not paid_enabled)

try:
    provider_policy = ProviderBudgetPolicy(
        provider=provider_name,
        operation=operation,
        max_calls_per_session=int(max_calls),
        estimated_cost_per_call=float(estimated_cost),
        max_paid_cost_per_session=float(max_paid_cost),
        currency="USD",
        paid_usage_enabled=paid_enabled,
    )
    if "guardrail_ledger" not in st.session_state:
        st.session_state["guardrail_ledger"] = SessionUsageLedger()
    ledger: SessionUsageLedger = st.session_state["guardrail_ledger"]

    authorization = authorize_provider_call(provider_policy, ledger)
    a1, a2, a3 = st.columns(3)
    a1.metric("Call allowed?", "YES" if authorization.allowed else "NO")
    a2.metric("Projected calls", authorization.projected_calls)
    a3.metric("Projected declared cost", f"{authorization.projected_estimated_cost:.4f} {authorization.currency}")
    st.write(authorization.reason)

    if st.button("Record one simulated authorized provider call", disabled=not authorization.allowed):
        record_authorized_call(provider_policy, ledger, authorization)
        st.rerun()

    if ledger.records:
        st.dataframe(pd.DataFrame([{
            "provider": record.provider,
            "operation": record.operation,
            "call_number": record.call_number,
            "estimated_cost": record.estimated_cost,
            "currency": record.currency,
            "at": record.at,
        } for record in ledger.records]), use_container_width=True, hide_index=True)
        if st.button("Reset simulated session ledger"):
            st.session_state["guardrail_ledger"] = SessionUsageLedger()
            st.rerun()
except Exception as exc:
    st.error(f"Provider policy invalid: {exc}")
    provider_policy = None

st.subheader("4 · Metadata-only artifact telemetry example")
sample = st.text_area("Sample local artifact content (never placed in telemetry output)", "private floor-plan bytes/content")
fp = fingerprint_artifact(sample.encode("utf-8"), ArtifactSensitivity.FLOOR_PLAN, mime_type="application/octet-stream")
st.write({
    "sha256": fp.sha256,
    "bytes_size": fp.bytes_size,
    "sensitivity": fp.sensitivity.value,
})
try:
    event = safe_telemetry_event(
        privacy,
        event_name="artifact_processed",
        fingerprint=fp,
        extra_metadata={"module": "privacy_lab"},
    )
    st.code(json.dumps(event, indent=2), language="json")
except Exception as exc:
    st.error(str(exc))

st.subheader("5 · Export deployment guardrail policy")
providers = [provider_policy] if provider_policy is not None else []
try:
    manifest = policy_manifest(privacy, providers)
    st.download_button(
        "Download guardrail policy JSON",
        json.dumps(manifest, indent=2, ensure_ascii=False).encode("utf-8"),
        "nitikube_guardrail_policy.json",
        "application/json",
    )
except Exception as exc:
    st.error(f"Guardrail manifest could not be built: {exc}")

st.caption(
    "Important production gap: session/process counters do not enforce an account-wide monthly provider free tier across multiple replicas/users. NitiKube must pair application gates with provider-side hard caps or a shared persistent quota service before claiming zero-cost operation at public scale."
)
