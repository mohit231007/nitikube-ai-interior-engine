# NitiKube Lifecycle Cost / Material Value Contract

Upfront price is not the same as long-term value. NitiKube therefore separates material/product suitability from **lifecycle cost** and makes every economic assumption visible.

## Required numeric inputs

The current lifecycle model requires:

```text
material cost per area
labour cost per area
annual maintenance cost
service life in years
```

and can additionally include:

```text
initial fixed cost
material waste fraction
replacement cost fraction
disposal cost per replacement
performance score
feature tags
```

A missing required lifecycle field is UNKNOWN. It is not replaced with zero.

## Evidence states

Each numeric field can carry:

```text
VERIFIED
USER_PROVIDED
UNVERIFIED
```

VERIFIED evidence requires an HTTP(S) source URL and timezone-aware checked timestamp.

The user can require VERIFIED evidence for all core lifecycle fields. In that mode, a known but unsourced number is not considered ready for a verified comparison.

## Initial installed cost

The current model treats material waste separately from labour:

```text
initial installed cost
= area × [material_cost_per_area × (1 + waste_fraction)
          + labour_cost_per_area]
  + initial_fixed_cost
```

This avoids automatically applying material cutting waste to labour cost.

## Annual maintenance

Maintenance is modeled as an end-of-year cash flow and can use an explicit annual escalation rate.

```text
maintenance_cost(year)
= base_annual_maintenance × (1 + escalation)^year
```

No maintenance frequency or escalation value is hidden inside the engine.

## Replacements

A replacement is scheduled every service-life interval strictly before the analysis horizon.

The current annual model requires service-life multiples to land on integer years. A 7.5-year service-life cycle therefore fails closed instead of silently placing half-year cash flows into an annual model.

Replacement base cost:

```text
initial_installed_cost × replacement_cost_fraction
+ disposal_cost_per_replacement
```

It is then escalated to the replacement year and discounted to present value.

## Residual value

When enabled, NitiKube credits the unused fraction of the last installed/replaced material at the analysis horizon:

```text
remaining_service_fraction
= remaining_life / service_life

residual_value
= replacement_value × remaining_service_fraction
```

The residual credit is an explicit model assumption. Users can disable it.

## Net present cost

For discount rate `r`:

```text
PV(year t) = cash_flow_t / (1 + r)^t
NPV cost = sum(PV)
```

The discount rate is an explicit scenario input. NitiKube does not claim a universal financial rate.

## Equivalent annual cost

For a positive/negative non-zero discount rate the capital-recovery factor is used:

```text
EAC = NPV × r(1+r)^n / [(1+r)^n - 1]
```

For zero discount rate:

```text
EAC = NPV / n
```

This helps compare options with different replacement cycles over the same horizon.

## Deterministic sensitivity

The current uncertainty layer is not Monte Carlo. The user supplies low/high cost multipliers such as:

```text
0.90 × base costs
1.20 × base costs
```

NitiKube computes deterministic low/base/high NPV. These are **what-if bounds**, not confidence intervals unless a separate statistical model and evidence justify a probability interpretation.

## Cost × performance Pareto comparison

A material/product option can also carry an explicit `performance_score` from a separate evidence/ranking process.

NitiKube marks an option Pareto-efficient when no other feasible option is:

- lower/equal lifecycle NPV cost; and
- higher/equal performance;
- with at least one strict improvement.

The lifecycle engine never invents the performance score.

## Feature constraints

Required/excluded feature tags can act as hard feasibility constraints, for example:

```text
required: moisture-resistant
excluded: high-maintenance
```

The tags themselves should eventually come from the material evidence/suitability system rather than marketing prose.

## Limits

The current model does not yet include:

- price probability distributions;
- inflation/discount-rate scenario consistency guidance;
- stochastic service life;
- repair-event distributions;
- exact pack/slab/sheet purchase granularity;
- labour regionalization;
- taxes/financing;
- embodied carbon / environmental lifecycle assessment;
- salvage-market evidence;
- downtime/occupancy disruption cost.

Those can be layered in without changing the rule that unknown evidence remains unknown and every economic assumption stays visible.
