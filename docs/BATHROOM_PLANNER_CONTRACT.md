# NitiKube Bathroom Planner Contract

The bathroom planner generates transparent shower/WC/basin arrangements and applies verified geometry/opening constraints before any subjective ranking.

## Candidate generation

For an axis-aligned rectangular bathroom it explores:

- four shower corners;
- four WC walls;
- each different basin wall.

This yields up to 48 deterministic starting combinations before collisions and clearances remove infeasible candidates.

## Explicit inputs

The planner consumes:

```text
shower width/depth
WC width/depth/front clearance
basin width/depth/front clearance
wall margin
passage width to test
circulation raster resolution
opening keepout depth
floor tile waste
wall tile height/opening deduction
waterproof floor fraction
shower wet-wall height
ceiling height + ACH scenario
drainage run + slope-percent scenario
```

UI defaults are scenario starting values only. They are not silently presented as plumbing, accessibility or building-code standards.

## Fixture and clearance geometry

WC and basin are centred on selected walls and rotated with the wall. Their front-access zones extend only into the room from the fixture face.

Hard failures include:

- physical fixture/shower collision;
- verified-opening keepout collision;
- requested front clearance outside the room;
- requested front clearance blocked by another fixture;
- fragmented/closed passage when connected passage is required.

## Wet-area and tile quantities

The current quantity layer calculates:

```text
floor area
floor purchase area = floor area × (1 + explicit waste)
gross wall tile area = room perimeter × tile height
net wall tile area = gross area - explicit known opening deduction
floor waterproof area = floor area × explicit fraction
shower wet-wall waterproof area = corner-wall lengths × wet height
total waterproof area = floor waterproof + wet walls
```

These are geometric quantity envelopes. They do not include membrane laps/upstands, niches, thresholds, coves, pipe penetrations, substrate preparation, tile-module cutting patterns or manufacturer-specific waterproofing systems.

## Ventilation airflow arithmetic

If the user supplies an air-changes-per-hour scenario:

```text
room_volume_ft3 = floor_area_ft2 × ceiling_height_ft
required_exhaust_cfm = room_volume_ft3 × ACH / 60
```

The ACH value is an explicit input. The result is not a final fan selection because real performance depends on duct length/diameter, fittings, static pressure, fan curve, make-up air and noise.

## Drainage fall arithmetic

For a user/sourced floor-drain slope scenario:

```text
fall_inches = run_ft × 12 × slope_percent / 100
```

The slope percent is not hidden inside NitiKube. A single run/fall is only a first-order diagnostic; real bathroom drainage may require a 2D slope field to one/multiple drains and waterproofing/plumbing verification.

## Whole-home bridge

A feasible bathroom candidate can be exported as a whole-home optimizer option. Cost, quality, durability, aesthetics, comfort and maintainability stay separate user/evidence inputs. Geometry score is never silently copied into them.

## Current limitations

Higher-fidelity bathroom engineering still needs:

- exact door swing and shower-screen/door arcs;
- plumbing stack/drain coordinates;
- water-supply points;
- floor-drain location and 2D slope field;
- electrical wet-zone/IP constraints;
- fixture manufacturer clearances;
- surface-temperature/condensation/mould integration;
- waterproofing system/lap/upstand rules;
- product-linked sanitaryware dimensions;
- sourced jurisdictional plumbing/accessibility standards;
- 3D visualisation.
