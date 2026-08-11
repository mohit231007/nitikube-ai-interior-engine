# NitiKube v0.25 — Service-Aware Candidate Feasibility

This milestone moves verified services from a separate audit into room-candidate decision logic.

## Shipped

- `nitikube.candidate_service_rules` schema
- required/optional service rules bound to planner target IDs
- actual candidate target-coordinate extraction
- combined geometry + service feasibility without collapsing the two evidence layers
- required missing target → failure
- optional missing target → warning
- service-aware wrappers for kitchen, bathroom, bedroom/wardrobe and drawing/dining/generic layouts
- service-aware ranking with hard feasibility first, geometry score second and straight-line route distance only as a transparent tie-breaker
- no service-distance mutation of planner geometry scores
- downloadable `nitikube.service_aware_candidate_evaluation`
- Streamlit page 26 demonstrating service-aware kitchen candidate generation/filtering
- deterministic regression tests and evidence contract

## Permanent rule

```text
overall_feasible = geometry_feasible AND service_feasible
```

A candidate with excellent geometry cannot pass when required verified services are unavailable, and a perfect service assignment cannot rescue invalid room geometry.

## Model boundary

Service routing remains the v0.24 straight-line lower-bound assignment model. It is not a construction-ready pipe/cable/duct route or discipline-specific code/compliance calculation.

## Next

Integrate the service-aware gate directly into the v0.23 Whole-Home Candidate Factory so failed service-aware candidates never become optimizer-ready options.