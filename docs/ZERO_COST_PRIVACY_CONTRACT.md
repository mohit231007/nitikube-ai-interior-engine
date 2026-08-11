# NitiKube Zero-Paid-Cost + Home-Data Privacy Contract

The project goal is to keep the public MVP free for the homeowner and avoid silently creating paid API bills for the operator. Home floor plans, photos, verified geometry and contractor quotations are also sensitive project data.

NitiKube therefore needs explicit **cost authorization before external calls** and explicit **privacy authorization before artifact transfer**.

## Zero-paid-cost does not mean 'assume the provider is free'

Every external adapter should declare a `ProviderBudgetPolicy` containing:

```text
provider
operation
maximum calls per session
declared estimated cost per call
maximum paid cost per session
currency
paid usage enabled?
```

The safe default is:

```text
paid_usage_enabled = false
max_paid_cost_per_session = 0
```

A positive estimated-cost call is blocked before execution when paid usage is disabled.

## Call-cap enforcement

The session ledger records only calls that passed authorization. A call is blocked when it would exceed the declared session call cap.

This protects a session from accidental loops/retries, but it is **not sufficient for public-scale account billing** because separate users/processes/replicas can have separate ledgers.

Production requires defense-in-depth:

1. app-side per-call/session gates;
2. provider-side disabled overage / hard spending limit where available;
3. shared persistent quota accounting if account-level free-tier limits must be divided across users;
4. up-to-date provider pricing/free-tier configuration.

If provider pricing changes, an old `estimated_cost_per_call = 0` declaration can become stale. Therefore the application cannot truthfully guarantee free operation without current provider policy/configuration.

## Privacy classification

Current artifact sensitivity classes include:

```text
public
project metadata
product data
quotation
floor plan
home photo
verified geometry
```

Floor plans, photos, quotations and verified geometry are treated as sensitive. Structured geometry is not considered harmless simply because it is JSON; it can reveal the home's layout.

## Default retention policy

Default `PrivacyPolicy`:

```text
retain uploaded artifacts = false
retain raw floor plans = false
retain raw home photos = false
retain raw quotations = false
external artifact transfer = false
sensitive third-party transfer requires explicit consent = true
telemetry = metadata only
```

When general upload retention is disabled, no raw uploaded artifact should be intentionally persisted by NitiKube.

This contract does not override infrastructure/provider logs or browser/cloud-hosting behavior; production deployment must verify those separately and document retention accurately.

## Third-party transfer

A sensitive artifact can be sent to a third party only when:

1. external artifact transfer is enabled by policy; and
2. explicit user consent exists when the policy requires it.

Otherwise the decision is BLOCK or CONSENT_REQUIRED.

Public artifacts can be transferred without sensitive-artifact consent.

The future application should show the destination provider and purpose before consent rather than using a generic blanket consent.

## Metadata-only telemetry

`safe_telemetry_event()` is designed to exclude raw file contents by construction. It can record:

```text
event name
artifact sensitivity
SHA-256 fingerprint
byte size
MIME type
non-sensitive module metadata
```

It rejects known raw-content fields such as `content`, `payload`, `floor_plan`, `photo`, `quotation_text` and `geometry_json`.

A fingerprint is still potentially linkable metadata and should be handled under the privacy policy; hashing is not anonymization.

## File-name minimization

`fingerprint_artifact()` does not retain an original file name by default. File names can contain personal information or addresses, so retaining them should be an explicit product decision.

## What app-side guardrails can and cannot prove

They **can** prove that application code refused a call that violated the configured policy and that raw artifact transfer was blocked by the configured privacy policy.

They **cannot** prove:

- the provider will never bill outside the declared price model;
- a provider's free tier has not been consumed elsewhere;
- hosting infrastructure has zero logs/caches;
- a third party deleted previously transferred data;
- SHA-256 metadata is anonymous.

These require provider/account configuration, deployment review and accurate privacy documentation.

## Integration requirement

Every future external adapter that can cost money or receive sensitive home data should be wrapped in both gates:

```text
privacy transfer check
      ↓
provider cost/quota authorization
      ↓
external call
      ↓
record authorized usage
```

The application must not call a paid/search/AI/CV provider first and attempt to check the budget after the fact.
