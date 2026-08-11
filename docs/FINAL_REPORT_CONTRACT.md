# NitiKube Final Design Report Contract

The final report is a deterministic assembly layer over NitiKube artifacts. It is intended for homeowner review, contractor coordination and evidence handoff.

It must never upgrade an UNKNOWN, unverified, conflicting or professionally flagged input into a clean-looking false conclusion.

## Required input

The report requires a valid:

```text
nitikube.design_package
```

produced by the Project Orchestrator.

By default, report generation is blocked if the package SHA-256 self-check fails.

A forensic/debug override can render a tampered/invalid package, but the report prominently shows:

```text
Package hash: FAIL / OVERRIDDEN
```

## Optional attachments

The report can also consume:

```text
nitikube.rule_evaluation
nitikube.lifecycle_comparison
```

When an optional artifact is absent, the report states that it is absent. It does not infer PASS/FAIL or lifecycle value from missing data.

## Executive audit

Before rendering, the report counts:

- selected vs required rooms;
- professional-verification flags;
- standards/guidance PASS;
- FAIL;
- UNKNOWN;
- NOT APPLICABLE;
- mandatory FAIL/UNKNOWN results;
- lifecycle feasible options;
- lifecycle non-feasible/unknown options.

Report-level warnings are generated for material gaps such as:

- invalid design-package hash;
- selected-room count differing from required-room count;
- no standards artifact;
- unresolved mandatory standards/guidance results;
- no lifecycle artifact;
- non-feasible lifecycle options;
- open professional-verification flags.

## Selected room packages

Each selected room option remains linked to:

```text
room ID
option ID
name
cost
utility
score source
source artifact
source artifact SHA-256
```

The final report does not collapse source provenance into an anonymous recommendation.

## Artifact provenance

The report lists the geometry and room-option artifact hashes carried by the design package.

A source hash identifies the exact bytes referenced by the project package. It does not prove the source's factual truth.

## Professional-verification flags

Open professional flags are placed in a dedicated section. The report cannot clear those flags.

Examples may include structural work, major electrical service changes, waterproofing details, statutory approvals or other scopes requiring licensed/site verification.

## Standards/guidance evidence

Every attached rule result remains one of:

```text
PASS
FAIL
UNKNOWN
NOT_APPLICABLE
```

Mandatory FAIL/UNKNOWN results are highlighted in the report audit.

The report is not a legal compliance certificate merely because all uploaded rules pass; the uploaded rule corpus may be incomplete or require professional interpretation.

## Lifecycle material value

Lifecycle results retain:

- feasibility;
- initial installed cost;
- replacement count;
- NPV cost;
- equivalent annual cost;
- NPV per area;
- unknown fields;
- failed constraints.

Unknown service-life/price evidence therefore stays visible in the homeowner handoff.

## HTML safety

Project names, labels, warnings, source fields and table cells are HTML-escaped before rendering so an uploaded string such as a `<script>` tag is displayed as text rather than executed.

## Report identity

The rendered report receives:

```text
report_id = SHA256(rendered_html_bytes)
```

For identical input artifacts and a design package with a fixed creation timestamp, the rendered HTML and report ID are deterministic.

The report ID is an integrity identifier, not an approval signature.

## Print/PDF path

The primary generated artifact is print-friendly HTML.

A homeowner can open the HTML and use the browser's Print → Save as PDF feature. This keeps the application free of a mandatory paid document-rendering service and keeps the deterministic HTML as the source artifact.

## Persistent evidence boundary

The report reiterates these permanent rules:

1. geometry/hard feasibility is deterministic;
2. lighting is calculated from explicit photometric/lumen/beam evidence;
3. material/product/price/standard facts require evidence states;
4. geography recommendations use measured/modelled climate variables;
5. budget optimisation cannot make an unsafe layout feasible;
6. lifecycle cost is conditional on explicit assumptions;
7. professional/regulatory verification remains where flagged.

A polished report must never become a mechanism for hiding uncertainty.
