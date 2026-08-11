from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
import hashlib
import json
import math
from typing import Any, Mapping, Sequence


class ArtifactSensitivity(str, Enum):
    PUBLIC = "public"
    PROJECT_METADATA = "project_metadata"
    PRODUCT_DATA = "product_data"
    QUOTATION = "quotation"
    FLOOR_PLAN = "floor_plan"
    HOME_PHOTO = "home_photo"
    VERIFIED_GEOMETRY = "verified_geometry"


class TransferDecision(str, Enum):
    ALLOW = "allow"
    BLOCK = "block"
    CONSENT_REQUIRED = "consent_required"


@dataclass(frozen=True)
class ProviderBudgetPolicy:
    provider: str
    operation: str
    max_calls_per_session: int
    estimated_cost_per_call: float = 0.0
    max_paid_cost_per_session: float = 0.0
    currency: str = "USD"
    paid_usage_enabled: bool = False


@dataclass(frozen=True)
class UsageRecord:
    provider: str
    operation: str
    call_number: int
    estimated_cost: float
    currency: str
    at: str


@dataclass
class SessionUsageLedger:
    records: list[UsageRecord] = field(default_factory=list)

    def calls(self, provider: str, operation: str) -> int:
        return sum(1 for item in self.records if item.provider == provider and item.operation == operation)

    def estimated_cost(self, provider: str, operation: str, currency: str) -> float:
        return sum(
            item.estimated_cost
            for item in self.records
            if item.provider == provider and item.operation == operation and item.currency == currency
        )


@dataclass(frozen=True)
class Authorization:
    allowed: bool
    reason: str
    projected_calls: int
    projected_estimated_cost: float
    currency: str


@dataclass(frozen=True)
class PrivacyPolicy:
    retain_uploaded_artifacts: bool = False
    retain_raw_floor_plans: bool = False
    retain_raw_home_photos: bool = False
    retain_raw_quotations: bool = False
    external_artifact_transfer_enabled: bool = False
    require_explicit_user_consent_for_sensitive_transfer: bool = True
    telemetry_mode: str = "metadata_only"


@dataclass(frozen=True)
class ArtifactFingerprint:
    sensitivity: ArtifactSensitivity
    sha256: str
    bytes_size: int
    mime_type: str | None
    original_name_retained: bool


@dataclass(frozen=True)
class TransferCheck:
    decision: TransferDecision
    reason: str
    sensitivity: ArtifactSensitivity
    provider: str
    user_consent: bool


_SENSITIVE = {
    ArtifactSensitivity.QUOTATION,
    ArtifactSensitivity.FLOOR_PLAN,
    ArtifactSensitivity.HOME_PHOTO,
    ArtifactSensitivity.VERIFIED_GEOMETRY,
}


def validate_provider_policy(policy: ProviderBudgetPolicy) -> None:
    if not policy.provider.strip() or not policy.operation.strip():
        raise ValueError("provider and operation are required")
    if policy.max_calls_per_session < 0:
        raise ValueError("max_calls_per_session cannot be negative")
    if not math.isfinite(policy.estimated_cost_per_call) or policy.estimated_cost_per_call < 0:
        raise ValueError("estimated_cost_per_call must be finite and non-negative")
    if not math.isfinite(policy.max_paid_cost_per_session) or policy.max_paid_cost_per_session < 0:
        raise ValueError("max_paid_cost_per_session must be finite and non-negative")
    if not policy.currency.strip():
        raise ValueError("currency is required")
    if not policy.paid_usage_enabled and policy.max_paid_cost_per_session > 0:
        raise ValueError("paid_usage_enabled=False is inconsistent with a positive paid-cost budget")


def authorize_provider_call(
    policy: ProviderBudgetPolicy,
    ledger: SessionUsageLedger,
    *,
    call_count: int = 1,
    estimated_cost_override: float | None = None,
) -> Authorization:
    """Authorize an external operation before a connector/API call occurs.

    The gate is intentionally fail-closed for cost: a provider adapter must
    declare an estimated cost or explicitly declare zero. This cannot know a
    vendor's real bill after the fact; provider-side billing caps are still
    required for production defense-in-depth.
    """
    validate_provider_policy(policy)
    if call_count < 1:
        raise ValueError("call_count must be >= 1")
    per_call = policy.estimated_cost_per_call if estimated_cost_override is None else estimated_cost_override
    if not math.isfinite(per_call) or per_call < 0:
        raise ValueError("estimated call cost must be finite and non-negative")

    current_calls = ledger.calls(policy.provider, policy.operation)
    projected_calls = current_calls + call_count
    current_cost = ledger.estimated_cost(policy.provider, policy.operation, policy.currency)
    projected_cost = current_cost + per_call * call_count

    if projected_calls > policy.max_calls_per_session:
        return Authorization(
            False,
            f"session call cap exceeded: {projected_calls} > {policy.max_calls_per_session}",
            projected_calls,
            projected_cost,
            policy.currency,
        )
    if per_call > 0 and not policy.paid_usage_enabled:
        return Authorization(
            False,
            "paid usage is disabled; any positive estimated call cost is blocked",
            projected_calls,
            projected_cost,
            policy.currency,
        )
    if projected_cost > policy.max_paid_cost_per_session + 1e-12:
        return Authorization(
            False,
            f"session paid-cost cap exceeded: {projected_cost:g} > {policy.max_paid_cost_per_session:g} {policy.currency}",
            projected_calls,
            projected_cost,
            policy.currency,
        )
    return Authorization(
        True,
        "call is within declared session quota/cost policy",
        projected_calls,
        projected_cost,
        policy.currency,
    )


def record_authorized_call(
    policy: ProviderBudgetPolicy,
    ledger: SessionUsageLedger,
    authorization: Authorization,
    *,
    estimated_cost_override: float | None = None,
    at: str | None = None,
) -> UsageRecord:
    if not authorization.allowed:
        raise ValueError("cannot record a blocked call as authorized usage")
    per_call = policy.estimated_cost_per_call if estimated_cost_override is None else estimated_cost_override
    timestamp = at or datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    record = UsageRecord(
        provider=policy.provider,
        operation=policy.operation,
        call_number=ledger.calls(policy.provider, policy.operation) + 1,
        estimated_cost=float(per_call),
        currency=policy.currency,
        at=timestamp,
    )
    ledger.records.append(record)
    return record


def fingerprint_artifact(
    payload: str | bytes,
    sensitivity: ArtifactSensitivity,
    *,
    mime_type: str | None = None,
    retain_original_name: bool = False,
) -> ArtifactFingerprint:
    raw = payload.encode("utf-8") if isinstance(payload, str) else payload
    return ArtifactFingerprint(
        sensitivity=sensitivity,
        sha256=hashlib.sha256(raw).hexdigest(),
        bytes_size=len(raw),
        mime_type=mime_type,
        original_name_retained=retain_original_name,
    )


def artifact_should_be_retained(policy: PrivacyPolicy, sensitivity: ArtifactSensitivity) -> bool:
    if not policy.retain_uploaded_artifacts:
        return False
    if sensitivity == ArtifactSensitivity.FLOOR_PLAN:
        return policy.retain_raw_floor_plans
    if sensitivity == ArtifactSensitivity.HOME_PHOTO:
        return policy.retain_raw_home_photos
    if sensitivity == ArtifactSensitivity.QUOTATION:
        return policy.retain_raw_quotations
    if sensitivity == ArtifactSensitivity.VERIFIED_GEOMETRY:
        # Structured geometry can be as sensitive as the original plan. It is
        # governed by the general retain flag, not silently treated as harmless.
        return policy.retain_uploaded_artifacts
    return True


def check_external_transfer(
    policy: PrivacyPolicy,
    *,
    sensitivity: ArtifactSensitivity,
    provider: str,
    user_consent: bool = False,
) -> TransferCheck:
    if not provider.strip():
        raise ValueError("provider is required")
    if sensitivity == ArtifactSensitivity.PUBLIC:
        return TransferCheck(TransferDecision.ALLOW, "artifact is classified public", sensitivity, provider, user_consent)
    if not policy.external_artifact_transfer_enabled:
        return TransferCheck(
            TransferDecision.BLOCK,
            "external artifact transfer is disabled by privacy policy",
            sensitivity,
            provider,
            user_consent,
        )
    if sensitivity in _SENSITIVE and policy.require_explicit_user_consent_for_sensitive_transfer and not user_consent:
        return TransferCheck(
            TransferDecision.CONSENT_REQUIRED,
            "sensitive artifact requires explicit user consent before third-party transfer",
            sensitivity,
            provider,
            user_consent,
        )
    return TransferCheck(TransferDecision.ALLOW, "transfer allowed by policy and consent state", sensitivity, provider, user_consent)


def safe_telemetry_event(
    policy: PrivacyPolicy,
    *,
    event_name: str,
    fingerprint: ArtifactFingerprint | None = None,
    extra_metadata: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build telemetry that excludes raw artifact content by construction."""
    if policy.telemetry_mode not in {"off", "metadata_only"}:
        raise ValueError("telemetry_mode must be 'off' or 'metadata_only'")
    if policy.telemetry_mode == "off":
        return {}
    if not event_name.strip():
        raise ValueError("event_name is required")
    disallowed_keys = {
        "raw",
        "content",
        "payload",
        "floor_plan",
        "photo",
        "quotation_text",
        "geometry_json",
    }
    metadata = dict(extra_metadata or {})
    unsafe = sorted(key for key in metadata if key.casefold() in disallowed_keys)
    if unsafe:
        raise ValueError(f"raw/sensitive telemetry fields are not allowed: {unsafe}")
    event: dict[str, Any] = {"event": event_name, **metadata}
    if fingerprint is not None:
        event["artifact"] = {
            "sensitivity": fingerprint.sensitivity.value,
            "sha256": fingerprint.sha256,
            "bytes_size": fingerprint.bytes_size,
            "mime_type": fingerprint.mime_type,
        }
    return event


def policy_manifest(
    privacy: PrivacyPolicy,
    providers: Sequence[ProviderBudgetPolicy],
) -> dict[str, Any]:
    for provider in providers:
        validate_provider_policy(provider)
    return {
        "schema": "nitikube.guardrail_policy",
        "schema_version": "0.20",
        "privacy": asdict(privacy),
        "providers": [asdict(provider) for provider in providers],
        "notes": [
            "Session/process enforcement is not a substitute for provider-side billing caps and account-level hard limits.",
            "A zero-cost declaration must be updated if a provider changes pricing/free-tier terms.",
            "Sensitive home artifacts are blocked from external transfer by default.",
        ],
    }


def load_provider_policies_json(payload: str | bytes) -> list[ProviderBudgetPolicy]:
    if isinstance(payload, bytes):
        payload = payload.decode("utf-8")
    data = json.loads(payload)
    rows = data.get("providers") if isinstance(data, dict) else data
    if not isinstance(rows, list):
        raise ValueError("provider policy JSON must be a list or {'providers': [...]} object")
    policies = []
    for row in rows:
        policy = ProviderBudgetPolicy(
            provider=str(row.get("provider") or ""),
            operation=str(row.get("operation") or ""),
            max_calls_per_session=int(row.get("max_calls_per_session", 0)),
            estimated_cost_per_call=float(row.get("estimated_cost_per_call", 0.0)),
            max_paid_cost_per_session=float(row.get("max_paid_cost_per_session", 0.0)),
            currency=str(row.get("currency") or "USD"),
            paid_usage_enabled=bool(row.get("paid_usage_enabled", False)),
        )
        validate_provider_policy(policy)
        policies.append(policy)
    return policies
