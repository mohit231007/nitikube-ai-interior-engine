# NitiKube v0.27 — Verified Routing Graph

## Problem fixed

Previous service-aware releases deliberately used Euclidean/3D point-to-point distance as a lower bound. That was transparent but could not stop a conceptual route from crossing a wall, column, shaft boundary or other building fabric.

v0.27 introduces an explicit verified routing graph.

## New pipeline

```text
verified service point
      │ explicit attachment
      ▼
network node
      │
      ├── compatible verified edge
      ├── compatible verified edge
      └── compatible verified edge
      │
      ▼
room access node
      │ bounded final connector
      ▼
candidate target
```

## New deterministic core

`nitikube/service_network.py` adds:

- `NetworkNode`
- `NetworkEdge`
- `ServicePointAttachment`
- `ServiceNetwork`
- `NetworkRoutingPolicy`
- Dijkstra shortest path by service kind
- exact multi-requirement assignment
- plan/3D distance modes
- required/optional failure semantics
- JSON import/export and audit output

## Evidence semantics

A route edge is data. NitiKube never invents one because two coordinates are nearby.

Unverified edges/nodes/attachments are excluded by default. Same-room target access is the default. Missing Z evidence blocks geometry-derived 3D routing rather than silently falling back to plan distance.

## UI

Page 28 — **Verified Service Network** — lets the user inspect the nodes/edges/attachments, apply the existing service routing brief, set the final target-access allowance and download a routed audit artifact.

## Deliberate boundary

The result is a geometrically constrained routing path, not plumbing/electrical/MEP certification. Diameter, pressure, slope, load, conductor, voltage drop, duct loss, gas safety, fire stopping and local code are future discipline layers.

## Next

v0.28 should make candidate feasibility and whole-home optimization use this routed graph instead of the earlier straight-line service lower bound whenever a verified network artifact is supplied.
