# NitiKube v0.27 — Verified Service Network Contract

## Purpose

v0.24–v0.26 deliberately used straight-line service distance as a lower bound. That was safe as long as it was described honestly, but it could not represent walls, shafts, risers, sleeves or other real routing constraints.

v0.27 introduces an explicit routing graph. A route may traverse only graph edges supplied as verified evidence.

```text
candidate target
    │
    │ short, explicitly capped target-access connector
    ▼
verified access node
    │
    ├── verified wall channel
    ├── verified sleeve
    ├── verified shaft/riser
    └── verified service corridor
    │
    ▼
service-point attachment node
    │
    ▼
verified service point
```

## Non-negotiable evidence rule

NitiKube does **not** create an edge simply because two points are close.

A wall, floor, ceiling, shaft or opening can only be traversed when the project evidence explicitly contains an admissible network edge. This prevents the previous Euclidean model from implicitly routing through solid building fabric.

## Network entities

### `NetworkNode`

Each node has:

- `node_id`
- XY coordinate and optional Z coordinate
- optional `room_id`
- `route_class`
- `can_accept_targets`
- verified state
- source and note

Room-local access nodes should carry `room_id`. Shared risers/shafts may omit it when appropriate.

### `NetworkEdge`

Each edge has:

- `edge_id`
- start and end nodes
- allowed service kinds
- directionality
- optional explicit surveyed length
- route class
- verified state
- source and note

Typical route classes include wall channel, shaft, riser, sleeve and service corridor. These labels are descriptive metadata; they do not create discipline-specific engineering claims.

### `ServicePointAttachment`

A verified service point must be explicitly attached to one network node before graph routing can use it.

The attachment is evidence, not a proximity guess.

## Service-kind filtering

An edge is traversable only when the service kind is included in `allowed_kinds`.

For example, an edge may be suitable for data/electrical but not drainage or gas. NitiKube does not assume that every corridor can carry every discipline.

## Route distance

For a chosen candidate target and service point:

\[
L_{total}=L_{access}+\sum_{e\in P}L_e
\]

where:

- `L_access` is the short target-to-network connector;
- `P` is the verified shortest admissible graph path;
- `L_e` is explicit surveyed edge length when supplied, otherwise geometry-derived node-to-node length.

The access connector is permitted only when:

\[
L_{access}\le L_{access,max}
\]

with `L_access,max` supplied explicitly by the caller.

## Plan vs 3D

`distance_mode = plan` uses XY lengths.

`distance_mode = 3d` requires Z evidence for geometry-derived edges and target access. If required height information is absent, that route is not silently approximated in 2D.

An explicit edge length may still be used when it is itself verified evidence.

## Same-room target access

The default policy is:

```text
same_room_target_access = true
```

A target therefore cannot jump directly into an access node located in another room simply because the XY distance is short.

Cross-room movement must occur through verified graph edges.

## Required vs optional requirements

Required service with no admissible route:

```text
FAIL
```

Optional service with no admissible route:

```text
WARNING
```

Unknown or missing evidence is never converted into PASS.

## Shared service points

By default, service points are not shared across multiple requirements unless:

```text
allow_shared_points = true
```

When sharing is disabled, NitiKube performs an exact minimum-total-distance assignment across required requirements instead of a greedy nearest-neighbour allocation.

## What v0.27 does not claim

A graph route does not prove:

- plumbing diameter;
- water pressure;
- drainage hydraulic capacity;
- drainage slope adequacy;
- electrical load/circuit sizing;
- conductor sizing;
- voltage drop;
- gas safety;
- duct size or pressure loss;
- fire stopping;
- waterproofing;
- structural penetrability;
- local code compliance.

Those remain separate engineering/evidence layers.

## Why this matters

The previous model answered:

> What is the shortest geometric distance between target and service point?

v0.27 answers:

> What is the shortest path through only the routing corridors we have actually verified, plus a bounded final connector?

That is the correct intermediate step before discipline-specific plumbing/electrical/ventilation engineering and before feeding routed service feasibility back into whole-home candidate optimization.
