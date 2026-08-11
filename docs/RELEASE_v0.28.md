# NitiKube v0.28 — Network-Aware Whole-Home Factory

v0.28 makes the v0.27 verified service-routing graph part of real candidate feasibility and whole-home optimization.

## What changed

For configured service rooms, NitiKube no longer promotes an option merely because its service point is geometrically nearby. It now requires a route through explicit compatible verified graph edges.

```text
candidate
  → geometry gate
  → candidate target coordinates
  → verified routing graph gate
  → optimizer option
  → whole-home optimizer
```

## New core

`nitikube/network_aware_factory.py`:

- reuses existing deterministic room planners;
- regenerates raw planner candidates only to recover exact service-target coordinates;
- verifies candidate ID equality with the base whole-home factory;
- applies project/room network-routing policy;
- routes each candidate through `nitikube.service_network`;
- rejects route-invalid candidates before optimizer promotion;
- preserves geometry and route metrics separately;
- blocks optimization when a required room has no surviving option;
- adds service-network evidence to the final design package and re-hashes it.

## New UI

Page 29 — **Verified-Network Whole-Home Candidate Factory** — accepts:

- verified geometry;
- verified service points;
- verified service network;
- network-aware service/room brief.

It exports:

- room/service audit;
- filtered optimizer options;
- evidence hashes;
- provenance-hashed design package.

## Important semantic rule

```text
no service_rules ≠ PASS
```

Such rooms are recorded as `not_configured`.

## Next

The next discipline layer should use the routed graph to check service-specific engineering. Drainage is a strong first candidate because route geometry can support explicit fall/slope calculations once route elevation and drain destination evidence are available.
