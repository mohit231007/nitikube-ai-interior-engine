# NitiKube v0.29 — Drainage Route Profile Contract

## Purpose

v0.27 created verified service-network paths and v0.28 made those paths part of whole-home candidate feasibility. v0.29 adds the first discipline-specific calculation on top of that route geometry: drainage elevation and slope.

## Core maths

For a route segment:

\[
\text{fall}_{in}=(z_{start}-z_{end})\times 12
\]

For a non-vertical segment:

\[
\text{slope}_{\%}=\frac{\text{fall}_{in}}{\text{plan run}_{ft}\times12}\times100
\]

For an explicitly sourced required slope:

\[
\text{required fall}_{in}=\text{plan run}_{ft}\times12\times\frac{\text{required slope}_{\%}}{100}
\]

The route plan run is the sum of the target-access segment and verified network node-to-node plan segments. If a routed edge bends, the network should contain intermediate verified nodes so its plan geometry represents the actual path rather than a long chord.

## No bundled plumbing threshold

`min_slope_percent` is required from the caller and must carry a non-empty `source_ref`.

The threshold can come from:

- a lawful/sourced standard;
- manufacturer documentation;
- qualified professional input;
- another explicitly identified project evidence source.

NitiKube refuses an unsourced numeric drainage threshold.

`max_slope_percent` is optional and is evaluated only when supplied.

## PASS / FAIL / UNKNOWN / NOT APPLICABLE

### PASS

All requested profile checks pass with complete elevation evidence.

### FAIL

Examples:

- average slope below the supplied minimum;
- average slope above an explicitly supplied maximum;
- a segment slope violates the supplied threshold when per-segment evaluation is enabled;
- a local rise exists while monotonic fall is required.

### UNKNOWN

Examples:

- target Z is missing;
- any route-node Z is missing;
- the path references missing nodes;
- route edge/node cardinality is inconsistent;
- the drainage brief references a service requirement that has no network assignment.

Missing evidence is never converted to PASS.

### NOT APPLICABLE

The selected assignment is not a drain service.

## Local-rise protection

End-to-end average fall can be misleading. A route may fall substantially near the end while first rising above the fixture outlet.

Therefore, when:

```text
require_monotonic_fall = true
```

any local rise from target toward drain endpoint is a failure regardless of the final average slope.

This setting is explicit and can be disabled for a system where gravity monotonicity is not the intended model.

## Vertical drops

Percentage slope is undefined when horizontal plan run is zero.

A pure vertical downward segment is therefore labelled as a vertical drop. NitiKube does not invent an infinite or arbitrary slope percentage for it.

A vertical rise still conflicts with monotonic gravity fall when that requirement is enabled.

## Model boundary

A drainage profile PASS is not a complete plumbing design. v0.29 does **not** calculate or certify:

- pipe diameter;
- fixture units / discharge loading;
- hydraulic capacity;
- trap design;
- venting;
- cleanout requirements;
- branch/stack sizing;
- connection legality;
- waterproofing;
- local code compliance.

Those must be separate sourced engineering layers.
