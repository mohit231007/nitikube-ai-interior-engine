# Deployment and Zero-Cost Guardrails

NitiKube is intentionally designed so its **core engineering functions run without paid AI APIs**. External search/climate/geocoding providers are adapters and must never be allowed to create accidental paid usage.

## Local run

```bash
python -m venv .venv

# Windows
.venv\Scripts\activate

# macOS/Linux
source .venv/bin/activate

pip install -r requirements.txt
streamlit run app.py
```

## Streamlit hosting

The repository is Streamlit-compatible:

- entry point: `app.py`
- dependencies: `requirements.txt`
- theme/server config: `.streamlit/config.toml`
- multipage views: `pages/`

Before public deployment, verify the current hosting provider's free-tier terms and limits. Free-tier policies change over time and are not part of NitiKube's engineering contract.

## Optional secrets

The deterministic app does not require an LLM key.

Optional live web-search adapter:

```text
BRAVE_SEARCH_API_KEY=...
```

The application already falls back to direct retailer search links when a live search key is unavailable.

Do **not** commit secrets into the repository. For hosted Streamlit, use the platform's secrets/environment-variable facility.

## Zero-cost enforcement policy

A production deployment should add a provider-budget adapter with these rules:

1. default budget = zero paid overage
2. track calls per provider
3. stop live calls before free quota is exhausted
4. fall back to deterministic/local behaviour
5. never retry a billable provider indefinitely
6. surface provider-unavailable state to the user
7. cache only where licensing/privacy permits

## Privacy before public launch

Floor plans can reveal sensitive details about a home. A public deployment should therefore define and implement:

- uploaded-file retention policy
- automatic temporary-file deletion
- no floor-plan images in analytics/log payloads
- no raw plan text/geometry sent to third-party AI by default
- opt-in external processing only when clearly disclosed
- deletion controls for persisted projects
- secret/config isolation

NitiKube's long-term architecture should prefer browser/local processing for sensitive plan imagery where practical.

## Public-launch checklist

- [ ] `pytest -q` passes
- [ ] CI green on supported Python versions
- [ ] all Streamlit pages smoke-test
- [ ] no secrets committed
- [ ] uploaded-file retention behavior documented
- [ ] provider quotas hard-limited
- [ ] live price/search results carry source + verification state/timestamp
- [ ] regulated-scope professional-verification warnings visible
- [ ] mobile/browser QA performed
- [ ] accessibility review performed
- [ ] real-home benchmark set tested with permission

## Deployment philosophy

NitiKube should **degrade capability before it incurs unexpected cost or fabricates data**.

Examples:

- no search quota → show specification + retailer search links
- climate provider unavailable → ask for/manual climate inputs or label climate data unavailable
- CV confidence low → require manual geometry
- material property absent → mark unknown, do not invent it
- price not verified → do not call it a current price
