# Service-Aware Whole-Home Factory Contract — v0.26

## Purpose

v0.26 wires verified service evidence directly into the v0.23 Whole-Home Candidate Factory.

The pipeline becomes:

```text
verified geometry
+ explicit room/design brief
+ verified service points
→ deterministic room candidates
→ geometry feasibility
→ candidate-specific service feasibility
→ optimizer-ready options
→ whole-home optimization
→ hashed design package
```

A candidate rejected by configured required-service evidence does not become a feasible optimizer choice.

## Input artifacts

### Verified geometry

`nitikube.verified_geometry` remains the authoritative spatial source.

### Service-aware whole-home brief

The factory accepts the existing `nitikube.whole_home_brief` structure or the explicit extension:

```text
nitikube.service_aware_whole_home_brief
schema_version: 0.26
```

Each room profile may include:

```text
service_rules: nitikube.candidate_service_rules
```

### Verified service points

`nitikube.service_points` provides the surveyed service coordinates.

Service points are validated against verified room geometry before candidate filtering.

## Room service state

Service evaluation is deliberately explicit.

A room can be:

- `evaluated` — service rules were supplied and evaluated candidate-by-candidate;
- `not_configured` — no `service_rules` block was supplied;
- `blocked` — service-aware candidate generation/evaluation could not be performed;
- `not_evaluated_base_room_blocked` — the underlying v0.23 room factory already failed.

`not_configured` is **not** equivalent to PASS.

## Candidate regeneration integrity

The service-aware layer regenerates raw planner candidates using the same verified room and planner inputs in order to recover the actual sink/hob/fridge/etc. target coordinates.

The regenerated planner layout-ID set must exactly match the v0.23 factory layout-ID set. If it diverges, the room fails closed rather than binding service evidence to the wrong candidate.

## Candidate feasibility

For configured service rules:

```text
service_aware_feasible
= existing_factory_candidate_feasible
AND candidate_service_routing_feasible
```

Service failures/warnings are appended to the candidate audit with a `service:` prefix.

Service route metrics are added only after service evaluation:

- `service_total_route_ft`
- `service_max_route_ft`

The feature list records `service_evaluated`.

## Optimizer promotion

The same v0.23 promotion rules still apply:

- explicit cost model;
- all five decision scores;
- optional explicit geometry-score blending;
- globally unique option IDs.

Service-aware feasibility changes only whether the option is feasible. It does not fabricate costs or subjective scores.

A required room must have at least one **feasible** optimizer option after service filtering before whole-home optimization starts.

The factory does not silently remove a service-blocked required room from optimization scope.

## Service rules absent

If a room has no service rules, the v0.23 geometry/cost/score behavior is retained for that room and the room audit says `not_configured`.

This allows non-service-critical rooms to remain usable without pretending a service evaluation happened.

## Design package provenance

When optimization is feasible, the normal `nitikube.design_package` is produced and then extended without breaking its hash contract.

The package hash covers:

- verified geometry artifact metadata/hash;
- generated service-aware option artifact metadata/hash;
- verified service-point artifact metadata/hash;
- service-aware whole-home brief artifact metadata/hash;
- required-room scope;
- selected choices;
- budget/reserve/weights/locks;
- professional-verification flags.

The package schema remains `nitikube.design_package` with `schema_version: 0.26`.

The package ID is recomputed after adding the service evidence references, so `verify_design_package_hash` and the existing Final Design Report continue to validate it.

## Evidence boundary

A valid package hash proves artifact integrity/reproducibility, not truth of the surveyed coordinates or engineering adequacy.

Service distance remains the v0.24/v0.25 straight-line lower-bound model. It does not certify:

- actual pipe/cable/duct routes;
- penetrations/shafts/bends;
- drainage hydraulics/slope networks;
- pressure drop or pipe sizing;
- electrical load/voltage drop;
- gas safety;
- ventilation pressure losses;
- code/professional compliance.

Professional verification flags remain part of the final package.

## UI

Page 27 provides:

- verified geometry upload;
- verified service-point upload;
- service-aware whole-home brief upload/paste;
- geometry-derived brief/service templates;
- room/service coverage audit;
- optional whole-home optimization;
- geometry/service/brief/option SHA-256 display;
- service-filtered option export;
- service-aware factory audit export;
- hashed design-package export.

## Next layer

After v0.26, the highest-value geometry step is arbitrary-polygon/service-network routing so the factory can operate on realistic room shapes and route around walls/shafts instead of using straight-line lower bounds.