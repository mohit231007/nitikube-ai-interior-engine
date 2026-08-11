# NitiKube Standards / Guidance Evidence Contract

NitiKube must never convert an unsourced internet rule-of-thumb into a hidden engineering threshold.

The standards registry therefore stores **structured numeric requirements with provenance**, and evaluates them separately from the room-planner algorithms.

## No bundled fake standards

The production registry starts empty. A rule enters the system only with source metadata such as:

```text
title
authority
jurisdiction
document version
source URL
checked timestamp
effective date when known
clause/page/table locator when known
```

A downloadable template may contain zero placeholders for schema demonstration, but those placeholders are explicitly not design rules.

## Numeric rule model

A numeric rule contains:

```text
rule_id
subject
metric
operator: min | max | range | equal
value
optional upper value
unit
room types
applicability tags
mandatory flag
source metadata
summary
```

Examples of future metrics include passage width, fixture-front clearance, illuminance, air changes, thermal performance, work-triangle limits, slip performance or other sourced numeric requirements.

## Unit normalization

Supported values are normalized within known dimension families before comparison. Current families include:

- length → metres;
- area → m²;
- illuminance → lux;
- airflow → m³/h;
- angles → degrees;
- percent;
- air changes per hour;
- dimensionless ratios.

NitiKube rejects incompatible conversions. For example, `lux` cannot be compared to `mm`.

Absolute temperature conversion is deliberately not included in this generic converter because Celsius/Fahrenheit are offset units and can refer to either absolute temperatures or temperature differences. A dedicated thermal evidence layer should handle that context explicitly.

## PASS / FAIL / UNKNOWN / NOT APPLICABLE

A sourced rule evaluation returns one of four states:

### PASS
The actual value exists, the units are compatible, the rule applies to the supplied context and the normalized value satisfies the numeric interval.

### FAIL
The rule applies and the known actual value is outside the interval.

### UNKNOWN
The rule applies but the actual value/unit is missing or incompatible. UNKNOWN is **not** treated as compliant.

### NOT_APPLICABLE
Room type, tags or jurisdiction do not match the rule's declared applicability.

This four-state model is important because absence of evidence is not compliance.

## Applicability

Rules can be scoped by:

```text
jurisdiction
room types
applicability tags
```

Rule IDs, not prose labels, should be carried into downstream evidence.

A rule declared `Global` or `International` can apply under a specific jurisdiction context; a rule tied to a different specific jurisdiction does not.

## Conflict detection

NitiKube groups rules only when they have the same:

- subject;
- metric;
- jurisdiction;
- room-type scope;
- applicability tags;
- mandatory state.

Within that same scope, each min/max/range/equality rule is converted to a canonical interval. If the intersection of all intervals is empty, NitiKube reports a conflict.

It does **not** automatically average or choose between conflicting rules.

Different jurisdictions are not called conflicts merely because their values differ.

## Legal / licensing boundary

A standards evidence registry is not permission to redistribute copyrighted or paywalled standards documents.

NitiKube should store/source only what is permitted, such as structured facts, citations, document identifiers, URLs and locators. Users/organizations remain responsible for lawful access to the original standard and professional/legal interpretation where required.

## Planner integration contract

Room planners currently expose explicit scenario thresholds. When a threshold is later supplied from the standards registry, the planner output should retain:

```text
metric
value / unit
rule_id
source authority
document version
jurisdiction
source locator
checked_at
```

A standards-sourced threshold must not become an anonymous default.

If multiple applicable standards conflict, the planner must surface the conflict and request/require a resolution policy or professional interpretation rather than silently selecting a convenient number.

## Current limitation

The v0.18 registry is an ingestion, normalization, applicability, conflict and numeric evaluation framework. It does **not** ship a production corpus of Indian, Norwegian or other jurisdiction standards.

Building that corpus requires source-by-source licensing review, version tracking and subject-matter validation.
