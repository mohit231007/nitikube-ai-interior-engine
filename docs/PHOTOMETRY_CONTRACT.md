# NitiKube Photometry / IES Lighting Contract

NitiKube's lighting engine should prefer **manufacturer photometry** over guessing illumination from wattage or beam-angle labels.

A fixture described only as:

```text
7 W
500 lm
36° beam
3000 K
```

does not uniquely define its candela distribution. Two luminaires with the same nominal values can produce different centre-beam intensity, spill, cut-off and uniformity.

## Current verified input: IES LM-63 photometry

The v0.13 point-by-point engine parses the core numeric block of common IES LM-63 files and currently accepts only:

```text
TILT=NONE
photometric type = Type C
```

It supports:

1. rotationally symmetric Type-C files with one horizontal plane; or
2. explicit full 0°–360° horizontal C-planes.

It rejects rather than guesses:

- Type A/B photometry;
- `TILT=INCLUDE` / external tilt data;
- partial horizontal symmetry planes that require a dedicated LM-63 symmetry interpreter;
- malformed/truncated photometric data.

This fail-closed behaviour is deliberate.

## IES values retained

The parser retains:

```text
header metadata lines
number of lamps
lumens per lamp
candela multiplier
vertical angles
horizontal angles
candela table
photometric type
units type
luminous dimensions
ballast factor
input watts
```

For absolute LED photometry, IES files can indicate that nominal lamp lumens are not available. NitiKube preserves that as unknown instead of inventing a lumen total.

## Candela interpolation

For a requested Type-C direction, NitiKube linearly interpolates the IES candela table.

For rotationally symmetric luminaires, candela depends only on vertical angle `γ`.

For a file with explicit 0°–360° horizontal C-planes, NitiKube interpolates:

1. vertically on each neighbouring horizontal plane;
2. horizontally between those planes.

## Point-by-point illuminance

For a downward ceiling fixture and a point on a horizontal evaluation plane:

```text
r² = horizontal_distance² + vertical_distance²
γ = atan(horizontal_distance / vertical_distance)
E = I(γ,C) × cos(γ) / r²
```

where:

- `I` is interpolated luminous intensity in candela;
- `r` is fixture-to-point distance in metres;
- `cos(γ)` is the incidence factor for the horizontal plane;
- `E` is direct illuminance in lux.

Contributions from multiple fixtures add linearly.

## Maintenance factor

The user can supply an explicit maintenance factor `MF` in `(0,1]`:

```text
E_maintained_direct = MF × Σ E_fixture
```

The UI default `MF=1.0` means **no depreciation allowance** is being applied. NitiKube does not hide a maintenance-factor assumption inside the calculation.

## What the current calculation includes

- real uploaded candela distribution;
- inverse-square distance;
- horizontal-plane cosine incidence;
- multiple fixture superposition;
- even rows × columns fixture coordinates;
- user-selected work/evaluation plane;
- explicit maintenance factor;
- point-grid minimum / average / maximum;
- min-to-average / min-to-max ratios;
- user-defined lux target-band coverage.

## What it intentionally does not yet include

The current map is **direct illuminance only**. It does not yet model:

- interreflection from walls/ceiling/floor;
- surface reflectance;
- room-cavity ratios / radiosity;
- daylight;
- furniture/partition shadows;
- fixture tilt/aiming;
- lens/diffuser mismatch between the IES file and purchased SKU;
- glare metrics such as UGR;
- emergency-lighting compliance;
- code/standard certification.

Those are separate physics/evidence modules and must not be implied by a direct-light heatmap.

## Grid comparisons

The IES Lab can compare grids such as:

```text
2×4
3×4
3×5
```

using the same:

- room dimensions;
- IES photometry;
- evaluation height;
- maintenance factor;
- sampling grid;
- user-defined target lux band.

The comparison reports brightness and uniformity indicators. It intentionally does not automatically choose the grid solely because it has the highest average lux.

## Provenance

The user can attach:

```text
IES/source URL
source checked timestamp
```

The uploaded file remains the numerical photometric input. A future product adapter should associate the IES file with an exact manufacturer model/SKU and hash so the application can prove that the photometry belongs to the recommended purchasable luminaire.

## Initial benchmark relevance

This module directly strengthens the original 36° COB use case that triggered NitiKube. The simpler beam-diameter equation remains useful as a geometric diagnostic, but when a real manufacturer IES is available, the point-by-point candela calculation should take priority for illumination-field analysis.
