# NitiKube Procurement Evidence Contract

Procurement is where interior advice becomes a real-money decision. NitiKube therefore treats **discovery**, **specification evidence**, **price evidence**, **availability**, and **ranking** as different states.

## 1. Search is discovery, not verification

A web-search result can establish that a page exists. It does not prove:

- that a product has the required specification;
- that the displayed snippet is current;
- that a price applies to the user's location;
- that the item is in stock;
- that the retailer will deliver to the property;
- that a warranty claim is valid.

NitiKube may use live web search or zero-cost retailer search links to discover candidates, but those candidates must pass the structured evidence layer before they are presented as verified procurement options.

## 2. Structured product offer schema

A product offer is a retailer-specific observation of a product at a point in time.

Important fields include:

```text
offer_id
product name
category
brand
model / MPN
SKU
retailer
product URL
technical specifications
price
currency
availability
warranty
delivery location
checked_at
source URL
```

Null values remain unknown. The ranking engine does not fill them from memory or title similarity.

## 3. Price verification and freshness

A price is considered structurally verified only when NitiKube has:

```text
price
source URL
verification timestamp
```

Freshness is then calculated as:

```text
price_age_hours = now_utc - checked_at_utc
```

The design brief supplies a maximum acceptable price age. A stale price can remain visible but cannot satisfy a `require verified/fresh price` constraint.

A future or invalid timestamp is treated as unknown evidence rather than as a negative-age/fresh price.

## 4. Availability

Availability has explicit states:

```text
in_stock
out_of_stock
preorder
unknown
```

If in-stock evidence is required, `unknown` is not a pass.

## 5. Product identity and variant safety

NitiKube deliberately avoids fuzzy title-based product deduplication for purchasing decisions.

Offers are grouped only when an explicit product identity exists, currently:

```text
brand + model/MPN
or
brand + SKU
```

When those identifiers are missing, offers remain separate. This avoids accidentally combining variants with different:

- wattage;
- colour temperature;
- size;
- pack quantity;
- finish;
- voltage;
- material grade;
- model year.

## 6. Specification matching

The existing NitiKube specification matcher evaluates required fields such as:

```text
category
wattage
lumens
Kelvin
beam angle
CRI
price ceiling
```

A required field can be:

```text
matched
failed
unknown
```

An option is feasible only when required fields do not fail and are not unknown.

This makes a product with `CRI unknown` different from a product that is confirmed `CRI 80` when the requirement is `CRI >= 90`:

```text
CRI unknown -> evidence incomplete
CRI 80      -> confirmed failure
```

Both are non-feasible for final approval, but for different reasons.

## 7. Ranking

Ranking is secondary to feasibility. The current transparent rank combines:

- specification-match score;
- required evidence checks;
- price verification/freshness;
- availability/warranty/location constraints where enabled.

A non-feasible result can be ranked for investigation but is not promoted to an approved procurement choice.

## 8. JSON-LD extraction

Many retail/manufacturer pages expose schema.org `Product`/`Offer` JSON-LD. NitiKube can parse that structured data from **HTML uploaded by the user**.

The current public app deliberately does **not** perform arbitrary server-side URL fetching because that would create:

- SSRF/security risk;
- hidden scraping/terms-of-service issues;
- privacy leakage of requested URLs;
- unpredictable network cost and reliability.

Extracted JSON-LD is a proposal. A retailer page can contain incomplete or stale structured data, so the user/adapter must still attach source and checked timestamp before current-price verification.

## 9. Zero-cost live discovery

Live search is optional. The procurement page:

- stays functional without a search API key;
- always provides direct retailer-search fallbacks;
- keeps live discovery disabled by default;
- enforces a small per-session live-call limit;
- tells deployers to configure provider-side billing/overage controls as well.

An application-side session cap cannot prove that an external account will never charge; the provider account must also prevent paid overage. NitiKube's desired production policy is **fail closed before paid overage**.

## 10. What remains

The next procurement steps include trusted retailer/manufacturer adapters, location-aware delivery/stock evidence, warranty normalization, persisted freshness caches, provider-wide quota accounting and procurement-list aggregation. Those adapters must produce the same structured evidence model instead of bypassing it.
