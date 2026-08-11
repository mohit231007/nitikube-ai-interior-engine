# NitiKube Bedroom + Wardrobe Planner Contract

The bedroom planner generates transparent bed/wardrobe/desk wall arrangements from verified room geometry and rejects physically invalid layouts before any subjective design ranking.

## Candidate generation

For a rectangular room, NitiKube explores:

- bed against each wall that can physically contain it;
- wardrobe on each different wall;
- optional desk on each remaining wall.

A room with all four walls usable therefore produces up to 12 bed/wardrobe combinations or 24 combinations when a desk is enabled.

## Explicit geometry inputs

The planner consumes:

```text
bed width / length
wardrobe run / depth / height
optional desk width / depth
wall margin
bed side-clearance target
bed foot-clearance target
wardrobe-front clearance target
passage width to test
circulation raster resolution
verified opening keepouts
```

UI defaults are scenario starting values only. They are not presented as universal accessibility/ergonomic standards.

## Directional clearance

The bed is assumed to have its headboard against the selected wall. Clearance zones are therefore generated only:

- along the two bed sides; and
- at the foot of the bed.

No clearance is required behind the headboard by this geometry model.

The wardrobe uses a directional front-access zone extending into the room. This is more meaningful than applying the same clearance on all four wardrobe sides.

If a requested clearance does not fit inside the room or is blocked by another furniture object, the layout is non-feasible.

## Openings and circulation

Verified door/window/opening segments can be converted to conservative room keepouts by the shared layout engine. Physical furniture overlapping an opening keepout is a hard failure.

The physical furniture footprints and opening keepouts can also be evaluated with the requested passage width through the shared raster connectivity engine. This is a geometry diagnostic, not an accessibility/code certificate.

## Wardrobe quantity geometry

The current planner reports:

```text
wardrobe run length
front elevation area = run × height
internal geometric volume = run × depth × height
```

Internal geometric volume is not equivalent to usable storage capacity. Shelves, drawers, hanging zones, plinth, hardware, panel thickness and door mechanisms reduce real usable volume and remain later layers.

## Geometry score

The current geometry-only ordering combines:

- open-floor ratio;
- walkable connectivity when tested;
- bed-to-wardrobe centre separation.

It is not an aesthetic, sleep-quality or ergonomic score. Hard failures stay separate from ranking.

## Whole-home bridge

A feasible bedroom layout can be exported as a whole-home optimizer package. The user/evidence layer separately provides cost, quality, durability, aesthetics, comfort and maintainability. NitiKube never copies the geometry score into those fields.

## Current limitations

Future bedroom/storage work should add:

- bedside-table placement;
- window/radiator/HVAC constraints;
- electrical outlet and switch access;
- TV sightlines and viewing geometry;
- hinged vs sliding wardrobe-door access zones;
- wardrobe internal compartment optimisation;
- clothes/storage-demand modelling;
- arbitrary polygon rooms;
- product-linked exact furniture dimensions;
- 3D visualisation;
- sourced jurisdictional/accessibility standards.
