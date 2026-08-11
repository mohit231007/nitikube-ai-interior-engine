# NitiKube Kitchen Planner Contract

The kitchen planner generates transparent room-specific candidates and rejects them using verified geometry and explicit constraints before any aesthetic ranking.

## Current candidate families

For an axis-aligned rectangular room the generator explores up to fourteen wall-run arrangements:

- four one-wall orientations;
- two galley orientations;
- four L-shaped combinations;
- four U-shaped combinations.

## Explicit inputs, not hidden standards

The caller supplies room dimensions, counter depth, wall/end margin, sink/hob/fridge module dimensions, opening keepout depth, minimum counter run, passage width, raster resolution and any work-triangle limits. UI defaults are scenario starting values only.

## Counter and work-centre geometry

Counter runs are rectangles attached to room walls. Sink, hob and fridge/tall-unit modules have explicit width-along-run and depth. Oversized modules are rejected rather than clipped.

The work triangle uses actual module-centre coordinates:

```text
sink ↔ hob
hob ↔ fridge
fridge ↔ sink
perimeter = sum(legs)
```

Optional minimum/maximum triangle-leg and perimeter limits are user/sourced inputs. NitiKube does not embed a universal kitchen-work-triangle standard.

## Openings and circulation

Verified openings can be converted through the existing room-layout engine into conservative inward keepout rectangles. Counter/work-centre overlap with a keepout is a hard failure.

Counter runs and keepouts are also fed into the passage-width raster engine. If connected passage at the requested width is required, fragmented/closed walkable space is a hard failure. This is a computational geometry diagnostic, not an accessibility/code certificate.

## Quantity geometry

The planner calculates:

- gross counter run;
- base-cabinet front area;
- wall-cabinet run and front area from an explicit fraction;
- countertop geometric area;
- countertop purchase area after explicit waste.

L/U corner overlap is handled using rectangle-union area so the same countertop corner is not counted twice.

These are geometric envelopes, not cabinet manufacturing cut lists. Carcass construction, panel thickness, standard sheet/module sizes, appliance voids, fillers, corner hardware and manufacturer installation instructions remain separate inputs.

## Whole-home bridge

A feasible candidate can be exported as a whole-home optimizer option. Cost, quality, durability, aesthetics, comfort and maintainability remain separate evidence/user inputs. The geometry score is never silently reused as a subjective or market score.

## Current limitations

Still required for higher-fidelity kitchen engineering:

- arbitrary polygon rooms;
- exact door swing arcs and window constraints;
- plumbing/drain, electrical and gas service points;
- hood/duct/ventilation paths;
- appliance manufacturer clearances;
- cabinet module/standard-size libraries;
- corner cabinet and pantry logic;
- countertop slab nesting/seams;
- sourced jurisdictional kitchen standards;
- product-linked cabinet/appliance procurement;
- 3D visualisation.
