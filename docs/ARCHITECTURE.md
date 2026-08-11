# Architecture

## Design rule

NitiKube separates **measurement/evidence**, **deterministic engineering**, **optimisation**, and **AI explanation**. A language model must never be the source of record for numeric engineering outputs.

## Logical layers

```text
INPUTS
floor plan • room dimensions • budget • location • style • lifestyle • product specs
   │
   ▼
VERIFICATION GATE
user confirms dimensions / scale / detected geometry
   │
   ├───────────────┬──────────────────┬─────────────────┐
   ▼               ▼                  ▼                 ▼
GEOMETRY        SCIENCE            EVIDENCE          CV/ML
areas           lighting           climate           line detection
polygons        thermal            product specs     room detection
clearances      moisture           prices            style extraction
coordinates     materials          standards         preference models
   │               │                  │                 │
   └───────────────┴─────────┬────────┴─────────────────┘
                             ▼
                    CONSTRAINT ENGINE
                 feasible / unsafe / unknown
                             │
                             ▼
                     OPTIMISATION ENGINE
          cost × durability × comfort × maintainability × aesthetics
                             │
                             ▼
                       DESIGN PACKAGE
             layouts • BOQ • products • explanations
                             │
                             ▼
                       AI EXPLANATION
                 never invents the arithmetic
```

## Deterministic core

### Geometry

- feet/inches ↔ decimal feet
- ft² ↔ m²
- rectangle area
- arbitrary polygon area via shoelace formula
- grid coordinates and offsets

### Lighting

Lumen method:

```text
Phi_installed = E × A / (CU × MF)
```

Beam diameter:

```text
D = 2h tan(theta/2)
```

Maintained lux:

```text
E = N × Phi_fixture × CU × MF / A
```

Beam spacing and lumen adequacy are evaluated separately.

### Thermal / moisture

Layer resistance:

```text
R = d / k
```

Assembly U-value:

```text
U = 1 / (Rsi + ΣRlayer + Rse)
```

Conductive heat flow:

```text
Q = U A ΔT
```

Dew point uses the Magnus approximation. Material-property values must come from sourced product/technical data, not from the LLM.

### Quantity estimation

Material quantities keep the net area, waste factor, gross area and purchasable-unit rounding visible. Paint quantities are based on the selected product's stated coverage, coat count and explicit allowance.

## Computer vision policy

CV is a proposal engine, not a silent source of truth. Floor-plan detections must expose confidence and route critical geometry through a correction/verification interface before downstream calculations run.

V0.1 implements line detection using Canny + probabilistic Hough transform. Planned stages are:

1. scale and dimension extraction
2. room polygons
3. doors/windows/columns/stairs
4. room labels
5. wall topology graph
6. plan-to-3D extrusion

## Product/search policy

Search adapters return source, URL and verification state. NitiKube must not display stale or inferred prices as current prices. A product can be recommended by specification even when a live price is unavailable.

## Geography

Location informs climate context rather than triggering simplistic city-based rules. Climate features may include temperature, humidity, dew point, solar radiation, rainfall, wind, elevation and eventually long-term design-day statistics.

## Confidence

Confidence is an evidence-quality score built from factors such as source reliability, measurement confidence, data freshness and constraint completeness. It must not be described as a probability that a subjective design choice is objectively correct.

## Professional verification boundary

The application should set a `professional_verification_required` state for structural/load-bearing changes, statutory approvals, fire-code certification, gas systems, major electrical-service changes, structural seismic work and other regulated/safety-critical scopes.
