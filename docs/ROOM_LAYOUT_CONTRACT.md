# NitiKube Room Layout Generation Contract

The room-layout generator is the bridge between **verified geometry** and the candidate packages consumed by the whole-home optimizer.

It must answer a narrower, auditable question before aesthetics:

> Can these furniture objects physically coexist in this verified room under the user's stated clearances, opening keepouts and circulation assumptions?

## Geometry first

The current v0.12 generator supports axis-aligned rectangular rooms and furniture rectangles. Every placement is evaluated against:

- room containment;
- wall margin;
- furniture/furniture collision;
- pairwise gap requirement;
- user-reserved furniture clearance envelope;
- verified opening keepouts;
- optional circulation-connectivity approximation.

A failed hard geometry constraint makes the layout non-feasible regardless of its ranking score.

## Explicit scenario inputs

NitiKube does not hide ergonomic or code thresholds inside the generator. The user/design brief supplies values such as:

```text
wall margin
minimum pairwise furniture gap
passage width to test
opening keepout depth
furniture reserved clearance
living/dining zone split
```

A UI default is only a starting scenario value. It is not to be described as a code requirement or universal ergonomic standard unless a separate standards/evidence layer supplies that provenance.

## Furniture geometry

Each furniture item has:

```text
item_id
label
width
physical depth
reserved clearance
```

Placements currently allow 0° and 90° rotations. The physical rectangle participates in collision checks. The reserved-clearance rectangle must remain inside the room when that policy is enabled.

The reserved envelope is useful for chair pull-back/service space, but the current implementation deliberately does not pretend every reserved envelope is a legal or ergonomic standard.

## Opening keepouts

Verified door/window/open-passage segments from the geometry graph can be converted into conservative rectangular inward keepouts.

For a wall opening, the caller supplies:

```text
inward keepout depth
optional side padding
```

The current keepout is **not a door-swing arc**. It is a conservative rectangle used to stop furniture from occupying the immediate opening zone. Door-swing geometry is a later enhancement.

## Circulation approximation

For a requested passage width `P`, obstacles are inflated by `P / 2` and rasterized at the user-selected grid step.

The engine reports:

1. `walkable ratio` — fraction of raster cells remaining walkable;
2. `largest connected component ratio` — fraction of walkable cells belonging to the largest 4-neighbour connected region.

This is a deterministic computational-geometry approximation. It is **not** an accessibility/code-compliance certificate.

Reducing the raster step increases spatial resolution and compute cost. The chosen step is therefore part of the analysis input and must remain visible.

## Drawing/dining candidate generator

The first automatic room generator targets a long rectangular combined drawing/dining room, matching the benchmark that triggered NitiKube.

It systematically explores:

```text
living-first vs dining-first zone order
sofa on left vs right long wall
dining table at 0° vs 90°
```

This produces eight deterministic starting arrangements from the same dimensions. Sofa, TV console, coffee-table and dining-table sizes all come from user/product inputs.

The generator is intentionally small and testable rather than pretending to solve every interior layout with an opaque model.

## Geometry ranking

Feasibility and ranking are separate. Among generated candidates, the current geometry score combines visible geometry-derived factors:

```text
open-area ratio
minimum-gap attainment
walkable connectedness
walkable-area ratio
```

The score excludes aesthetic/style taste. A non-feasible layout is capped below a feasible-ranking range so a visually open but colliding layout cannot outrank a valid one.

This score is a heuristic ordering of geometry outcomes, not a scientific comfort or beauty score.

## Whole-home optimizer bridge

A user can promote a feasible generated layout into an optimizer-compatible room package. The geometry result is retained, but NitiKube deliberately asks separately for:

```text
package cost
quality score
durability score
aesthetic score
comfort score
maintainability score
score-source label
```

The geometry score is **not silently copied into those subjective/economic fields**.

That separation preserves the architecture:

```text
verified geometry
    ↓
room candidate generation
    ↓
hard geometry rejection
    ↓
material / product / climate / cost evidence
    ↓
room-package scores
    ↓
whole-home constrained optimizer
```

## Current limitations

The current implementation does not yet solve:

- arbitrary polygon rooms;
- angled/curved furniture;
- exact door-swing arcs;
- individual dining chairs;
- windows/radiators/electrical points as specialized constraints;
- sofa-to-TV sightline/FOV alignment in the generator;
- bedrooms, kitchens, bathrooms and wardrobes;
- continuous nonlinear placement optimization.

Those features should extend this deterministic geometry model rather than bypass it with image-generation guesses.
