# Service-Aware Candidate Feasibility Contract — v0.25

## Purpose

A room layout can be geometrically attractive and still be impractical because its sink, hob, WC, basin, shower, desk or other target cannot be connected to verified services under the supplied constraints.

v0.25 therefore makes service evidence a **separate hard candidate-feasibility gate**:

```text
planner candidate
→ deterministic geometry evaluation
→ actual candidate target coordinates
→ verified service assignment
→ combined feasibility
```

The permanent rule is:

```text
overall_feasible = geometry_feasible AND service_feasible
```

Neither side can rescue a failure on the other side.

---

## Candidate service rule schema

Schema:

```text
nitikube.candidate_service_rules
schema_version: 0.25
```

Rules contain:

- requirement ID
- planner target ID
- allowed service kinds
- optional maximum straight-line route distance
- required vs optional state
- whether service points may be shared
- plan vs 3D distance mode

The rule file does not invent product requirements. For example, whether a hob needs gas, electrical or both must come from product/evidence/professional inputs.

---

## Actual candidate coordinates

Service targets are generated from the candidate being evaluated, not from a room-centre placeholder.

Supported deterministic adapters:

### Kitchen
- `sink`
- `hob`
- `fridge`

### Bathroom
- `shower`
- WC fixture ID
- basin fixture ID

### Bedroom
- `bed`
- `wardrobe`
- optional `desk`

### Drawing / dining
Every furniture `item_id` in the generic layout candidate.

Because candidate geometry changes target coordinates, different layouts can pass/fail the same service rules differently.

---

## Missing candidate targets

A rule may reference a target not present in a particular candidate.

Examples:

- a bedroom rule requires desk power but this candidate has no desk
- a candidate family omits an optional appliance

Semantics:

- missing **required** target → service failure
- missing **optional** target → warning

The evaluator does not throw away the whole audit and does not silently ignore the requirement.

---

## Geometry and service separation

The existing planner geometry score remains unchanged.

Service routing:

- does not add points to geometry score
- does not subtract points from geometry score
- does not become aesthetics/comfort/quality

The combined record preserves:

- geometry feasible state
- service feasible state
- overall feasible state
- geometry score
- geometry failures/warnings
- service failures/warnings
- assigned service points
- total/max straight-line service distance

This keeps reasoning inspectable.

---

## Ranking

Service feasibility is a hard gate.

For ranking candidates:

1. overall-feasible candidates first;
2. higher deterministic geometry score next;
3. lower total straight-line service distance is only a transparent tie-breaker;
4. deterministic candidate ID tie-break last.

The service distance is not normalized into a hidden weighted score.

---

## Planner integration

The deterministic core provides wrappers for:

- kitchen candidates
- bathroom candidates
- bedroom/wardrobe candidates
- drawing/dining/generic layout candidates

Each wrapper runs the planner's existing geometry evaluator first and the v0.24 service assignment evaluator alongside it.

Existing keepouts and planner requirements still apply unchanged.

---

## Evidence / routing boundary

Service assignment still uses the v0.24 routing model:

- verified service points only
- same-room service matching
- explicit allowed kinds
- optional max route constraint
- plan/3D straight-line distance
- exact unique assignment unless sharing is explicitly allowed

This remains a geometric lower-bound service check, not a construction route.

It does not certify:

- pipe routing
- drain slope network
- hydraulic capacity
- voltage drop
- electrical circuit capacity
- gas system safety
- ventilation pressure losses
- fire stopping / penetrations
- local code compliance

---

## Streamlit

Page 26 currently demonstrates the service-aware pipeline for kitchen candidates using:

- authoritative verified room geometry
- verified service-point artifact
- explicit kitchen module dimensions
- deterministic kitchen candidate families
- candidate service-rule file
- combined candidate table
- selected candidate service assignments / failures
- downloadable combined evaluation JSON

The deterministic core already supports bathroom, bedroom and drawing/dining candidates; UI workflows can be expanded without changing the contract.

---

## Fail-closed behavior

A candidate does not become overall-feasible when:

- geometry fails but services pass;
- services fail but geometry passes;
- a required target is absent;
- a required verified service point cannot be assigned;
- a required 3D service link lacks authoritative height;
- explicit max-route constraints cannot be satisfied;
- unique assignment is impossible under `allow_shared_points=false`.

---

## Next integration

The next step is to connect this service-aware feasibility layer into the v0.23 Whole-Home Candidate Factory so candidates rejected by service evidence never become optimizer-ready room options.