# NitiKube Kitchen Planner Contract

The kitchen planner is a deterministic room-specific candidate generator. Its job is to create transparent wall-run arrangements, calculate geometry, and reject layouts that violate the user's verified room/opening geometry or explicit design constraints.

It does **not** treat a visual kitchen rendering as evidence that a kitchen physically works.

## Current layout families

For an axis-aligned rectangular kitchen the generator explores:

- one-wall kitchens on each wall;
- galley kitchens on each opposite-wall pair;
- four L-shaped wall combinations;
- four U-shaped wall combinations.

This produces up to fourteen deterministic candidates before constraints remove impossible variants.

## Explicit input geometry

The user/design brief supplies:

```text
room width / depth
counter depth
wall/end margin
sink module width/depth
hob module width/depth
fridge/tall-unit width/depth
verified openings / keepout depth
minimum acceptable counter-run length
passage width to test
circulation raster resolution
optional work-triangle limits
```

Defaults in the UI are starting scenario values only. They are **not** automatically building-code or ergonomic standards.

## Counter runs

Each counter run is an axis-aligned rectangle attached to one verified room wall. The planner retains both:

- gross run length; and
- counter footprint.

For L/U corners, countertop area is calculated from the geometric **union of rectangles**, so overlapping corner area is not counted twice.

## Work centres and triangle

The current work centres are:

```text
sink
hob / cooktop
fridge / tall unit
```

Each has an explicit module width along the run and module depth. Candidate generation places these modules deterministically on counter runs and rejects modules that cannot fit.

The work triangle is calculated from actual module-centre coordinates:

```text
sink ↔ hob
hob ↔ fridge
fridge ↔ sink
perimeter = sum of the three legs
```

NitiKube can enforce user/sourced minimum/maximum leg and total-perimeter thresholds, but the engine contains **no hidden universal work-triangle standard**. When standards are connected later, the threshold must carry jurisdiction/version/source provenance.

The triangle area is used only as one geometry-ranking signal to distinguish a non-degenerate arrangement from three nearly collinear centres; it is not a beauty or compliance score.

## Openings

Verified door/window/open-passage segments from the authoritative geometry layer can be converted into conservative inward rectangular keepouts. A counter run or work-centre module colliding with the keepout becomes infeasible.

The keepout is not yet an exact hinged-door swing, window-service envelope or appliance-clearance standard.

## Passage / circulation approximation

Kitchen counter footprints and opening keepouts are fed to the existing deterministic passage-width raster engine. Obstacles are inflated by half the requested passage width, then the remaining walkable grid is tested for connectivity.

If the user enables `require connected walkable space`, a fragmented/closed path at the requested width is a hard failure.

This is a geometry approximation, **not** an accessibility/code certificate.

## Quantities

For a selected candidate the planner can calculate geometric envelopes for:

- gross counter run;
- base-cabinet front area;
- wall-cabinet run from an explicit fraction;
- wall-cabinet front area;
- geometric countertop area;
- countertop purchase area after explicit waste factor.

These are not yet manufacturing cut lists. Real cabinetry requires panel thicknesses, carcass construction, corner hardware, standard sheet/module sizes, appliance voids, fillers, kickboards, hinges/slides and manufacturer installation constraints.

## Whole-home optimizer bridge

A feasible kitchen candidate can be exported as a `RoomDesignOption`-compatible package. Geometry-derived information remains separate from:

```text
price
quality
durability
aesthetics
comfort
maintainability
```

The UI asks the user/evidence layer for those inputs. NitiKube does not copy the kitchen geometry score into subjective or market/economic scores.

## Current limitations / next engineering layers

The current kitchen planner still needs:

- arbitrary polygon rooms;
- exact door swing arcs;
- window sill/opening constraints;
- plumbing/drain service points;
- gas and electrical service points;
- hood/duct/ventilation path requirements;
- appliance-manufacturer service clearances;
- cabinet module/standard-size libraries;
- corner cabinet logic;
- tall-unit/pantry-specific placement;
- countertop slab nesting/seam optimisation;
- sink/hob setback rules with sourced evidence;
- sourced jurisdictional kitchen standards;
- product-linked cabinet/appliance procurement;
- 3D visualization.

Those should extend the deterministic/evidence model rather than be guessed by a generative image.
