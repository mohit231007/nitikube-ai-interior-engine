# NitiKube AI — Interior DesignOS

**Measured interiors. Verified decisions.**

NitiKube AI is a physics-first, evidence-grounded interior engineering system that combines deterministic maths/physics/geometry, computer vision, optimisation, material intelligence, climate context and live product discovery.

The product was conceived around a simple rule:

> **No recommendation without reasoning.**

A recommendation must be backed by at least one of the following: a calculation, verified measurement, rule/standard, material/product specification, geographic/climate input, or an explicit label that the choice is subjective/aesthetic.

## What is already implemented in v0.1

- Verification-first floor-plan CV baseline using OpenCV line detection
- Feet/inches conversion, rectangular geometry and arbitrary polygon area via the shoelace formula
- Even fixture-grid generation and layout dimensions
- Lighting lumen method: `Phi = E × A / (CU × MF)`
- COB beam geometry: `D = 2h tan(theta/2)`
- Maintained-lux estimation and beam-spacing warnings
- 12-COB 3×4 layout evaluation for the initial drawing/dining-room case
- Tile/board/panel quantity calculation with explicit wastage
- Paint quantity calculation from manufacturer coverage assumptions
- Dew-point/condensation check using the Magnus approximation
- Simple thermal-resistance/U-value/heat-flow calculations
- Budget envelopes and weighted feasible-option scoring
- Evidence-confidence scoring
- Product-search abstraction: optional Brave live search plus zero-cost retailer search fallbacks
- Streamlit UI covering floor-plan CV, lighting, materials, climate/thermal, budget, products and evidence
- Pytest deterministic-core tests
- GitHub Actions CI on Python 3.11 and 3.12

## Why NitiKube is different

NitiKube does **not** ask a language model to do engineering arithmetic. The architecture is deliberately split:

```text
floor plan / user inputs / product specs
                 │
                 ▼
         verification gate
                 │
      ┌──────────┼───────────┐
      ▼          ▼           ▼
  geometry    science    live evidence
   engine      engine       adapters
      │          │           │
      └──────────┼───────────┘
                 ▼
       feasible design options
                 │
                 ▼
        optimisation / ranking
                 │
                 ▼
       AI explanation / UX
```

AI/ML/CV may extract, classify, rank and explain. The deterministic science core owns the numbers.

## Quick start

```bash
python -m venv .venv

# Windows
.venv\Scripts\activate

# macOS / Linux
source .venv/bin/activate

pip install -r requirements.txt
streamlit run app.py
```

Run the deterministic tests:

```bash
pytest -q
```

## Initial real-world benchmark

The first benchmark reproduces the room that triggered the project:

- Drawing/dining room: `10′7″ × 22′9″`
- False ceiling: `9 ft`
- Example COB beam: `36°`
- Default work/evaluation plane: `2.5 ft`
- User can evaluate 12 COBs as a `3 × 4` grid and compare spacing to the nominal beam footprint

For a beam angle `theta` and vertical distance `h` from fixture to the evaluation plane:

```text
D = 2h tan(theta / 2)
```

For a 36° COB mounted at 9 ft and evaluated at 2.5 ft:

```text
h = 6.5 ft
D ≈ 4.22 ft
```

The UI therefore evaluates both lumens **and** spatial beam coverage rather than assuming that total wattage alone makes a room comfortable.

## Zero-cost philosophy

The initial public version is designed to run without mandatory paid AI APIs:

- deterministic Python for science/geometry/optimisation
- OpenCV for local CV baseline
- Streamlit Community Cloud compatible
- optional no-key climate adapter for prototyping
- optional search adapter when a free quota/key is available
- direct retailer search links when live search is unavailable

External providers are isolated behind adapters so the core is not locked to a vendor or a free-tier policy.

## Repository structure

```text
.
├── app.py
├── nitikube/
│   ├── __init__.py
│   ├── budget.py
│   ├── climate.py
│   ├── confidence.py
│   ├── floorplan_cv.py
│   ├── geometry.py
│   ├── lighting.py
│   ├── materials.py
│   └── product_search.py
├── tests/
│   ├── test_geometry.py
│   ├── test_lighting.py
│   ├── test_materials.py
│   └── test_systems.py
├── docs/
│   ├── ARCHITECTURE.md
│   └── ROADMAP.md
├── .github/workflows/ci.yml
├── .streamlit/config.toml
├── requirements.txt
└── LICENSE
```

## Safety boundary

NitiKube can support residential interior planning, layout, estimation, material selection, lighting, procurement and design auditing. It must **not** present itself as a substitute for licensed verification where law/safety requires it. The application should flag professional verification for load-bearing or structural changes, seismic/structural engineering, major electrical-service design, gas systems, fire-code certification, waterproofing guarantees and statutory approvals.

## Roadmap

See [`docs/ROADMAP.md`](docs/ROADMAP.md). The direction is a full Interior DesignOS: floor-plan understanding, climate-aware material recommendations, geometry/ergonomics, lighting, thermal/moisture/acoustic modelling, product search, BOQ generation, quotation auditing, project sequencing and eventually interactive 2D/3D visualisation.

## License

MIT. See [`LICENSE`](LICENSE).
