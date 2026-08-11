# NitiKube v0.26 — Service-Aware Whole-Home Factory

This milestone makes verified service evidence part of the whole-home candidate pipeline before cross-room optimization.

## Shipped

- service-aware whole-home factory wrapper over the v0.23 factory
- room-level `service_rules` using the v0.25 candidate-service contract
- candidate regeneration integrity check before binding actual target coordinates
- service failures/warnings carried into candidate evidence
- `service_total_route_ft` / `service_max_route_ft` candidate metrics only after evaluation
- service-invalid candidates marked infeasible before optimizer selection
- required rooms must retain at least one feasible optimizer option after service filtering
- rooms with no service rules remain explicitly `not_configured`, never fake PASS
- service-aware room audit counts
- direct whole-home optimization after service filtering
- `nitikube.design_package` v0.26 with verified service-point and service-aware-brief artifact hashes included in the package hash
- existing design-package hash verification remains valid
- Streamlit page 27 with service-aware whole-home audit, optimization and artifact downloads
- deterministic regression tests, contract and CI smoke coverage

## Decision rule

```text
candidate can reach optimizer as feasible
only if
existing geometry feasibility = PASS
AND configured service feasibility = PASS
```

Costs and subjective decision scores remain governed by the existing explicit v0.23 promotion contract.

## Next

Move beyond rectangular rooms and straight-line service lower bounds toward arbitrary-polygon planners plus wall/shaft-aware service-network routing.