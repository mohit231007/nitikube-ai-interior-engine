# NitiKube v0.29 — Drainage Route Elevation + Slope

v0.29 is the first discipline-specific engineering layer built on top of the verified service-routing graph.

## New deterministic core

`nitikube/drainage_profile.py` adds:

- explicit sourced drainage-profile requirements;
- target/node elevation completeness checks;
- route segment plan runs;
- fall in inches;
- average slope percentage;
- per-segment slope percentage;
- minimum required fall from an explicit slope threshold;
- fall margin;
- local-rise detection;
- vertical-drop semantics;
- PASS / FAIL / UNKNOWN / NOT APPLICABLE;
- artifact-level evaluation and JSON export.

## Evidence rule

No numeric drainage slope is bundled into NitiKube.

Every `min_slope_percent` requires `source_ref`. `max_slope_percent` is evaluated only if explicitly supplied.

## Important improvement

A large endpoint drop can no longer hide a local rise. With `require_monotonic_fall=true`, each route transition must not rise toward the drain endpoint.

## UI

Page 30 — **Drainage Route Elevation + Slope Lab** — consumes the verified service network, network routing evaluation, service routing brief and a sourced drainage-profile brief, then exposes segment maths and downloadable evidence.

## Boundary

This does not size pipes or calculate fixture loads, venting, hydraulic capacity, traps, cleanouts or code compliance.
