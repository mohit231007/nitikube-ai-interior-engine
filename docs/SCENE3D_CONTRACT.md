# NitiKube Verified-Geometry 3D Scene Contract

NitiKube's 3D layer is a **visualization of verified dimensions**, not a generative image that is allowed to change the engineering geometry.

## Geometry ownership

The 3D scene consumes:

```text
verified room polygons
explicit wall/ceiling height
verified opening segments
optional parametric object boxes
```

Room X/Y coordinates remain in the verified floor-plan coordinate system. Wall height is an explicit project input because current verified geometry does not yet contain authoritative ceiling-height geometry for every room.

## Polygon floors

A room polygon is triangulated with deterministic ear clipping.

The algorithm accepts clockwise or counter-clockwise simple polygons and creates `n - 2` floor triangles.

It fails closed when the polygon is degenerate or cannot be triangulated rather than silently replacing an arbitrary polygon with a bounding rectangle.

## Walls

Every polygon edge is extruded from:

```text
floor_z
```

to:

```text
floor_z + wall_height
```

Each wall segment is represented by a quad split into two triangles.

Shared boundaries between rooms can therefore appear as overlapping wall surfaces in the current viewer. This is visually redundant but does not alter the verified room coordinates.

A future whole-building mesh can deduplicate shared walls after topology validation.

## Openings

Verified opening segments are currently rendered as 3D line overlays at floor level.

They are **not yet Boolean-subtracted from wall meshes**, because current opening evidence does not consistently include:

- sill height;
- head height;
- door/window type geometry;
- swing direction;
- wall thickness;
- frame dimensions.

The viewer must not draw a guessed hole and imply it is verified.

## Parametric object boxes

Furniture/fixtures can be represented by explicit boxes:

```text
object ID
label
room ID
x / y / z
width / depth / height
kind
```

A box is a geometry envelope, not an exact manufacturer model unless those dimensions are tied to verified product evidence elsewhere.

The viewer currently does not automatically prove that a manually entered box lies inside the referenced room. Planner-generated object boxes should eventually carry the originating room-layout feasibility result.

## Scene export

The scene JSON schema is:

```text
nitikube.scene3d
schema_version = 0.21
units = ft
```

It carries:

- rooms;
- triangulated meshes;
- verified opening lines;
- metadata;
- explicit visualization boundary note.

The Streamlit page can also export a self-contained Plotly HTML document with Plotly JavaScript embedded.

This allows interactive 3D viewing without a paid image-generation API. The exported HTML is larger because the rendering library is embedded.

## Visual materials are not evidence

Mesh color/opacity is for scene comprehension. It does not prove:

- paint color accuracy;
- fabric color;
- gloss;
- texture scale;
- stone veining;
- manufacturer finish;
- light reflectance;
- thermal/chemical material properties.

When product/material visualization is added, visual texture metadata and physical material evidence must remain distinguishable.

## Current limitations

Still required:

- deduplicated building-wall topology;
- wall thickness;
- actual door/window voids;
- opening heights;
- door swing/leaf models;
- planner-native furniture/fixture scene export;
- parametric cabinetry/sanitaryware;
- product-linked exact 3D dimensions;
- texture/material swapping;
- IES light cones / illuminance overlays;
- solar/daylight overlays;
- collision/clearance visualization;
- browser-side Three.js/WebGL client optimized for large whole-home scenes.

The key rule remains: visualization may become richer, but it cannot silently mutate verified engineering dimensions.
