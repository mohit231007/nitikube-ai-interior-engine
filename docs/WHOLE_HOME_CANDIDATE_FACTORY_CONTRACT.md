# Whole-Home Candidate Factory Contract — v0.23

## Purpose

The Whole-Home Candidate Factory is the deterministic bridge between NitiKube's verified geometry and its existing room planners / whole-home optimizer / design-package layer.

It exists to move the product toward:

```text
verified floor-plan geometry
+ explicit homeowner / product / professional inputs
→ deterministic room planner dispatch
→ candidate generation
→ hard geometry rejection
→ explicit cost + score mapping
→ cross-room optimization
→ reproducible design package
```

It does **not** create missing evidence or silently turn geometric convenience heuristics into professional standards.

## Inputs

### 1. Verified geometry

The authoritative geometry artifact must be readable by `nitikube.verified_geometry`.

The current factory supports exact axis-aligned rectangular rooms for planner dispatch because the current kitchen, bedroom, bathroom and drawing/dining generators are rectangle-based.

A non-rectangular verified polygon is **not** replaced with a bounding box. The room is blocked until an arbitrary-polygon planner exists or the verified geometry is intentionally transformed by a future supported workflow.

### 2. Whole-home brief

Schema:

```text
nitikube.whole_home_brief
schema_version: 0.23
```

The brief is keyed by authoritative `room_id` values. A profile can explicitly set a room role or allow deterministic room-name keyword inference.

Supported planner roles:

- `drawing_dining`
- `kitchen`
- `bedroom`
- `bathroom`

Anonymous or ambiguous room names remain unresolved until the brief supplies a role.

## No-invention rule

The room-aware template intentionally leaves the following values null where they are not known from verified geometry:

- furniture/appliance/fixture dimensions
- homeowner decision scores
- product / labour / package costs
- optimization budget
- room-specific planner inputs such as a living-zone fraction
- opening keepout depth where required

These fields must come from homeowner choices, verified product data, quotations, lawful sourced guidance or professionally supplied requirements.

## Verified openings

Verified `door` / generic `opening` segments are not silently ignored when they are relevant to a room.

For current rectangular planners, the factory converts them into conservative inward rectangular keepouts using an **explicit** `inward_depth_ft` and optional side padding.

If such an opening exists and no keepout depth is supplied, the room is blocked.

Verified windows are not automatically converted into floor-level furniture keepouts because sill height, head height and wall/opening vertical geometry are not yet authoritative. A brief may explicitly include `window` in the keepout kinds if that conservative treatment is intended.

## Room planner dispatch

### Drawing / dining

Uses the deterministic drawing/dining generator and evaluator:

- living/dining zone order
- sofa-wall alternatives
- dining-table rotation alternatives
- collision / pair-gap / wall-margin checks
- opening keepouts
- passage-width raster metrics

### Kitchen

Uses the deterministic kitchen generator and evaluator:

- one-wall
- galley
- L-shape
- U-shape
- sink / hob / fridge placement
- work-triangle arithmetic
- counter-run geometry
- opening keepouts
- circulation

### Bedroom / wardrobe

Uses the deterministic bedroom generator and evaluator:

- bed-wall alternatives
- wardrobe-wall alternatives
- optional desk alternatives
- directional bed clearances
- wardrobe-front access
- opening keepouts
- passage-width connectivity

### Bathroom

Uses the deterministic bathroom generator and evaluator:

- shower-corner alternatives
- WC-wall alternatives
- basin-wall alternatives
- fixture-front clearance zones
- opening keepouts
- passage-width connectivity

## Geometry score boundary

Every planner may emit a deterministic `geometry_score`.

That score is **not** automatically interpreted as:

- aesthetics
- quality
- durability
- comfort
- maintainability

The whole-home optimizer uses those five separate decision dimensions. Therefore, a candidate becomes optimizer-ready only when the brief provides all five explicit decision scores.

An explicit `geometry_score_blend` may be supplied to blend the deterministic geometry score into one or more decision dimensions. For a target metric:

```text
mapped_score = (1 - blend) × explicit_brief_score + blend × geometry_score
```

with `blend ∈ [0, 1]`.

The resulting `score_source` records that mapping. No mapping occurs by default.

## Cost model boundary

A candidate becomes optimizer-ready only when an explicit cost model is supplied.

The current model is transparent:

```text
candidate_cost
= fixed_cost
+ Σ(candidate_metric × explicit_metric_rate)
```

Examples of candidate metrics include:

- kitchen counter run
- kitchen countertop area
- bedroom wardrobe run
- wardrobe front area
- furniture occupied area
- bathroom occupied area
- room floor area

A cost model that references a metric not produced by that planner is rejected.

No missing rate is treated as zero unless the caller explicitly supplies a zero rate.

## Global option identity

Planner-local IDs such as `B-01` or `K-03` repeat across rooms. The factory therefore creates globally unique optimizer IDs:

```text
<room_id>::<role>::<planner_layout_id>
```

This preserves compatibility with the whole-home optimizer and project orchestrator's global option-ID rule.

## Optimization

Optimization runs only if every `required_room_id` has optimizer-ready options.

`required_room_ids` is the explicit scope boundary. The factory never silently removes an unsupported or incomplete required room to make the optimization succeed.

When supplied, the optimization block can include:

- budget
- reserve
- decision weights
- room policies
- homeowner locks
- fixed creation timestamp for reproducible test/package generation

The existing exact additive-utility / Pareto-state optimizer remains authoritative.

## Design package bridge

When whole-home optimization is feasible, the factory creates a normal `nitikube.design_package` through the existing project-orchestrator contract.

The package retains:

- verified-geometry SHA-256
- generated room-option artifact SHA-256
- selected option source artifact / SHA
- required room scope
- budget / reserve / selected cost
- decision weights
- homeowner locks
- professional-verification flags

The candidate factory does not invent a separate weaker handoff format.

## Audit outputs

The factory exposes:

- room-level status / errors / warnings
- raw deterministic candidates
- feasibility and failure reasons
- candidate geometry metrics
- optimizer-ready option count
- whole-home optimization result
- input/output artifact hashes
- design-package ID when produced

This is exported as `nitikube.whole_home_factory_audit`.

## Fail-closed behavior

The factory blocks or withholds optimizer promotion when any of the following occurs:

- room role unresolved
- verified room is not a supported exact rectangle
- required planner dimensions are missing
- relevant verified opening exists but its keepout depth is unspecified
- cost model is incomplete or invalid
- decision scores are incomplete or invalid
- a cost model references an unavailable metric
- required room scope lacks optimizer-ready options
- optimization is infeasible

Geometry-only candidates may still be generated when costs/scores are missing, but they are not promoted into optimizer claims.

## Professional / regulatory boundary

The factory coordinates deterministic interior-planning candidates. It does not certify:

- structural adequacy
- electrical code compliance
- plumbing code compliance
- fire / egress compliance
- accessibility compliance
- gas-system design
- statutory approvals
- professional standard interpretation

Existing professional-verification flags are deliberately carried into the final design package rather than cleared by optimization.

## Current limitations / next layer

The next production steps after v0.23 are:

1. arbitrary-polygon room planner support;
2. service-point-aware kitchen/bathroom generation;
3. planner-native object geometry into the 3D scene;
4. sourced standards rule binding into planner constraints;
5. product/catalog-backed dimensions and prices;
6. richer household requirement / style preference capture;
7. automatic generation of room profiles from verified product/evidence registries without inventing missing facts;
8. regression testing on complete real homes.
