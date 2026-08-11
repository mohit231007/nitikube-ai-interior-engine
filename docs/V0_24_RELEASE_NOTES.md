# NitiKube v0.24 — Verified Service Points + Routing

This milestone adds a first evidence-grounded service-location layer so room layouts no longer have to pretend that plumbing, drainage, electricity, gas, exhaust or data exist wherever a candidate places an appliance/fixture.

## Shipped

- `nitikube.service_points` schema for surveyed/verified service coordinates
- room-geometry validation of service-point coordinates
- cold/hot water, drain, electrical, gas, exhaust, data, HVAC-condensate and generic service kinds
- empty room-aware service-point template generated from verified geometry
- explicit service targets + routing requirements
- same-room / allowed-kind / verified-only matching
- optional explicit maximum straight-line route limits
- plan-distance and 3D-distance modes
- fail-closed 3D links when endpoint height is unknown
- exact minimum-total-distance unique assignment when service points cannot be shared
- explicit shared-point mode when the brief permits sharing
- required-service failure vs optional-service warning semantics
- kitchen, bathroom, bedroom and generic room-layout candidate target adapters
- `nitikube.service_routing_evaluation` JSON output
- Streamlit page 25: **Verified Service Points + Routing Lab**
- deterministic test coverage
- dedicated service-routing evidence contract

## Evidence boundary

The current routing distance is a geometric lower bound between service point and target. It is not a routed pipe/cable/duct length and does not calculate pressure drop, drainage hydraulics, pipe sizing, voltage drop, circuit capacity, ventilation losses, gas safety or code compliance.

No service coordinate is inferred simply because a room has a particular role.

## Next

The immediate next layer is candidate-level service-aware feasibility: each kitchen/bathroom/etc. candidate should derive its own service targets and be rejected when required verified service assignments cannot be made under the explicit routing brief.