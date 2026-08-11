import json

import pytest

from nitikube.guardrails import (
    ArtifactSensitivity,
    PrivacyPolicy,
    ProviderBudgetPolicy,
    SessionUsageLedger,
    TransferDecision,
    artifact_should_be_retained,
    authorize_provider_call,
    check_external_transfer,
    fingerprint_artifact,
    load_provider_policies_json,
    policy_manifest,
    record_authorized_call,
    safe_telemetry_event,
    validate_provider_policy,
)


def free_policy(**overrides):
    data = {
        "provider": "test-search",
        "operation": "product_search",
        "max_calls_per_session": 3,
        "estimated_cost_per_call": 0.0,
        "max_paid_cost_per_session": 0.0,
        "currency": "USD",
        "paid_usage_enabled": False,
    }
    data.update(overrides)
    return ProviderBudgetPolicy(**data)


def test_free_call_is_allowed_within_declared_session_cap():
    ledger = SessionUsageLedger()
    policy = free_policy()
    auth = authorize_provider_call(policy, ledger)
    assert auth.allowed is True
    record_authorized_call(policy, ledger, auth, at="2026-08-11T18:00:00+00:00")
    assert ledger.calls("test-search", "product_search") == 1
    assert ledger.estimated_cost("test-search", "product_search", "USD") == pytest.approx(0)


def test_call_cap_blocks_before_external_call():
    ledger = SessionUsageLedger()
    policy = free_policy(max_calls_per_session=1)
    auth = authorize_provider_call(policy, ledger)
    record_authorized_call(policy, ledger, auth, at="2026-08-11T18:00:00+00:00")
    blocked = authorize_provider_call(policy, ledger)
    assert blocked.allowed is False
    assert "call cap exceeded" in blocked.reason


def test_positive_estimated_cost_is_blocked_when_paid_usage_disabled():
    ledger = SessionUsageLedger()
    policy = free_policy(estimated_cost_per_call=0.01)
    auth = authorize_provider_call(policy, ledger)
    assert auth.allowed is False
    assert "paid usage is disabled" in auth.reason


def test_paid_policy_respects_explicit_session_cost_cap():
    ledger = SessionUsageLedger()
    policy = free_policy(
        paid_usage_enabled=True,
        estimated_cost_per_call=0.20,
        max_paid_cost_per_session=0.50,
        max_calls_per_session=10,
    )
    for index in range(2):
        auth = authorize_provider_call(policy, ledger)
        assert auth.allowed
        record_authorized_call(policy, ledger, auth, at=f"2026-08-11T18:0{index}:00+00:00")
    third = authorize_provider_call(policy, ledger)
    assert third.allowed is False
    assert "paid-cost cap exceeded" in third.reason


def test_policy_validation_rejects_inconsistent_positive_budget_when_paid_disabled():
    with pytest.raises(ValueError, match="inconsistent"):
        validate_provider_policy(free_policy(max_paid_cost_per_session=1.0))


def test_recording_blocked_call_is_rejected():
    ledger = SessionUsageLedger()
    policy = free_policy(max_calls_per_session=0)
    auth = authorize_provider_call(policy, ledger)
    assert not auth.allowed
    with pytest.raises(ValueError, match="blocked call"):
        record_authorized_call(policy, ledger, auth)


def test_sensitive_artifacts_are_not_retained_by_default():
    policy = PrivacyPolicy()
    assert artifact_should_be_retained(policy, ArtifactSensitivity.FLOOR_PLAN) is False
    assert artifact_should_be_retained(policy, ArtifactSensitivity.HOME_PHOTO) is False
    assert artifact_should_be_retained(policy, ArtifactSensitivity.QUOTATION) is False
    assert artifact_should_be_retained(policy, ArtifactSensitivity.VERIFIED_GEOMETRY) is False


def test_retention_requires_both_general_and_specific_sensitive_flags():
    policy = PrivacyPolicy(
        retain_uploaded_artifacts=True,
        retain_raw_floor_plans=True,
        retain_raw_home_photos=False,
        retain_raw_quotations=True,
    )
    assert artifact_should_be_retained(policy, ArtifactSensitivity.FLOOR_PLAN) is True
    assert artifact_should_be_retained(policy, ArtifactSensitivity.HOME_PHOTO) is False
    assert artifact_should_be_retained(policy, ArtifactSensitivity.QUOTATION) is True
    # Structured geometry is governed by general retention because it can still expose home layout.
    assert artifact_should_be_retained(policy, ArtifactSensitivity.VERIFIED_GEOMETRY) is True


def test_external_transfer_is_blocked_by_default():
    check = check_external_transfer(
        PrivacyPolicy(),
        sensitivity=ArtifactSensitivity.FLOOR_PLAN,
        provider="example-provider",
        user_consent=True,
    )
    assert check.decision == TransferDecision.BLOCK


def test_sensitive_external_transfer_requires_explicit_consent_when_enabled():
    policy = PrivacyPolicy(external_artifact_transfer_enabled=True)
    no_consent = check_external_transfer(
        policy,
        sensitivity=ArtifactSensitivity.HOME_PHOTO,
        provider="example-provider",
        user_consent=False,
    )
    assert no_consent.decision == TransferDecision.CONSENT_REQUIRED
    consent = check_external_transfer(
        policy,
        sensitivity=ArtifactSensitivity.HOME_PHOTO,
        provider="example-provider",
        user_consent=True,
    )
    assert consent.decision == TransferDecision.ALLOW


def test_public_artifact_can_transfer_even_when_external_sensitive_transfer_disabled():
    check = check_external_transfer(
        PrivacyPolicy(),
        sensitivity=ArtifactSensitivity.PUBLIC,
        provider="example-provider",
    )
    assert check.decision == TransferDecision.ALLOW


def test_artifact_fingerprint_contains_hash_not_raw_content():
    fp = fingerprint_artifact(b"secret floor plan bytes", ArtifactSensitivity.FLOOR_PLAN, mime_type="image/png")
    assert len(fp.sha256) == 64
    assert fp.bytes_size == len(b"secret floor plan bytes")
    assert fp.original_name_retained is False


def test_metadata_only_telemetry_excludes_raw_content_fields():
    policy = PrivacyPolicy(telemetry_mode="metadata_only")
    fp = fingerprint_artifact(b"secret", ArtifactSensitivity.QUOTATION)
    event = safe_telemetry_event(policy, event_name="quote_uploaded", fingerprint=fp, extra_metadata={"parser": "csv"})
    assert event["event"] == "quote_uploaded"
    assert "artifact" in event
    assert "secret" not in json.dumps(event)
    with pytest.raises(ValueError, match="raw/sensitive"):
        safe_telemetry_event(policy, event_name="bad", extra_metadata={"content": "secret"})


def test_telemetry_off_returns_empty_event():
    assert safe_telemetry_event(PrivacyPolicy(telemetry_mode="off"), event_name="anything") == {}


def test_policy_manifest_makes_zero_cost_limitations_explicit():
    manifest = policy_manifest(PrivacyPolicy(), [free_policy()])
    assert manifest["schema"] == "nitikube.guardrail_policy"
    assert manifest["schema_version"] == "0.20"
    assert manifest["providers"][0]["paid_usage_enabled"] is False
    assert any("provider-side billing caps" in note for note in manifest["notes"])


def test_provider_policy_loader_validates_declared_zero_cost_policy():
    payload = {
        "providers": [
            {
                "provider": "search",
                "operation": "query",
                "max_calls_per_session": 5,
                "estimated_cost_per_call": 0,
                "max_paid_cost_per_session": 0,
                "currency": "USD",
                "paid_usage_enabled": False,
            }
        ]
    }
    policies = load_provider_policies_json(json.dumps(payload))
    assert policies == [ProviderBudgetPolicy("search", "query", 5, 0.0, 0.0, "USD", False)]
