# NitiKube AI — Interior DesignOS

**Measured interiors. Verified decisions.**

NitiKube AI is a physics-first, evidence-grounded interior engineering system for homeowners who want to understand what a room/home actually needs before spending money on interiors.

The permanent product rule is:

> **No recommendation without reasoning.**

A recommendation must be backed by a calculation, a verified measurement, a rule/standard, a sourced material/product specification, geographic/climate evidence, or be explicitly labelled as subjective/aesthetic.

## Current build status

NitiKube is already a working multi-page Streamlit application, not a placeholder. The repository currently includes:

### Geometry + floor plans

- feet/inches and ft²/m² conversion
- rectangle and arbitrary-polygon area (shoelace formula)
- deterministic fixture-grid coordinates and spacing
- OpenCV line-detection baseline
- user-verified pixel → physical scale calibration
- multi-reference calibration disagreement/spread reporting
- pixel-polygon → physical area conversion
- heuristic enclosed/free-space region proposals from uploaded floor plans
- explicit user verification before CV proposals become trusted geometry
- downloadable verified-region CSV

### Lighting engineering

- lumen method: `Phi = E × A / (CU × MF)`
- maintained-lux estimate
- COB beam diameter: `D = 2h tan(theta/2)`
- beam-spacing / overlap diagnostics
- constrained search across fixture count, grid geometry and available lumen outputs
- deterministic downloadable SVG lighting plans with nominal beam circles
- initial benchmark: 10′7″ × 22′9″ drawing/dining room, 9 ft false ceiling, 36° COBs

### Materials + quantities

- tile/board/panel quantities with explicit waste allowance
- paint quantities using user/manufacturer coverage input
- provenance-aware material-property model
- numeric verified facts require source + verification timestamp
- unverified material values cannot silently drive verified recommendations
- empty production material registry rather than invented starter facts
- deterministic product-specification matching with matched / failed / unknown fields

### Building physics

- dew point and simple condensation-risk check
- thermal layer `R = d/k`
- assembly U-value
- conductive heat flow `Q = UAΔT`
- latitude/day/solar-time solar geometry
- first-pass shadow geometry
- first-order Sabine RT60 room-acoustics model
- free-field distance/SPL-change diagnostic
- connected/diversified electrical load arithmetic
- single-phase current equation
- energy calculations
- generic conductor resistance + voltage-drop math using explicit resistivity input

### Ergonomics + optimisation

- rectangular furniture fit
- dining table/chair/movement envelope
- TV/screen geometry from chosen field of view
- budget envelopes
- weighted feasible-option ranking
- Pareto-front calculation
- constrained lighting-layout optimiser
- professional-verification guardrails for structural/regulatory scopes

### Procurement + execution

- specification-first search-query builder
- optional Brave search adapter
- zero-cost retailer-search fallbacks
- price verification state (price + source + timestamp)
- BOQ line/quantity audit primitives
- CSV/XLSX quotation ingestion
- explicit quotation column mapping
- `quantity × rate` arithmetic validation
- downloadable quote-audit CSV
- dependency-graph execution scheduling
- cycle detection
- earliest start/finish and critical path
- simple cumulative task-cost timing

### Quality

- deterministic Python core kept separate from AI explanation
- Python 3.11 + 3.12 GitHub Actions CI
- compile checks
- pytest test suite
- Streamlit app/page smoke tests
- no mandatory paid AI API

## Application pages

Run `streamlit run app.py` and use the Streamlit navigation:

1. Main app — floor-plan CV baseline, room/lighting, quantities, climate/thermal, budget, products, evidence
2. Ergonomics + BOQ
3. Optimizers
4. Materials + Products
5. Plan Calibration + SVG Export
6. Building Physics
7. Quotation + Execution
8. Floor-plan Region Proposals

## Architecture contract

```text
floor plan / user inputs / product specs / location / budget
                         │
                         ▼
                 VERIFICATION GATE
                         │
       ┌─────────────────┼──────────────────┐
       ▼                 ▼                  ▼
    GEOMETRY          SCIENCE            EVIDENCE
       │                 │                  │
       ├─────────────────┼──────────────────┤
       ▼                 ▼                  ▼
      CV/ML         CONSTRAINTS       LIVE ADAPTERS
       │                 │                  │
       └─────────────────┼──────────────────┘
                         ▼
                 FEASIBLE OPTIONS
                         │
                         ▼
               OPTIMISATION / RANKING
                         │
                         ▼
             AI EXPLANATION / DESIGN UX
```

**AI does not own engineering arithmetic.** AI/ML/CV may propose, classify, rank and explain. Deterministic tested code owns geometry, quantities, physics and constraint calculations.

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

Run tests:

```bash
pytest -q
```

## Zero-cost philosophy

The MVP is deliberately designed without mandatory paid model APIs:

- deterministic Python for engineering
- OpenCV for CV baselines
- Streamlit-compatible hosting
- optional no-key climate/geocoding adapters for prototyping
- optional search adapter only when a key/quota is available
- direct retailer-search links as a zero-cost fallback
- SVG/Plotly rendering instead of paid image generation

External providers remain replaceable. If a free quota disappears, NitiKube should degrade gracefully instead of silently generating a bill.

## What is *not* claimed complete yet

The repository has a substantial engineering foundation, but a production-grade whole-home Interior DesignOS still needs:

- robust room polygons + doors/windows/columns/stairs + dimension OCR
- an interactive geometry correction editor
- sourced manufacturer/material datasets at useful scale
- long-term climate/design-day/daylight data and higher-fidelity solar modelling
- richer room-specific planners (kitchen, wardrobes, bathroom, bedroom, full-home graph)
- broader local live product inventory/price integrations
- PDF/photo quotation OCR with verification
- lifecycle-cost/material substitution optimisation
- 3D/WebGL room/house visualisation
- browser-side/local AI style and preference models
- production deployment, telemetry/privacy controls and larger real-world regression datasets

See [`docs/ROADMAP.md`](docs/ROADMAP.md).

## Safety boundary

NitiKube can assist with interior planning, quantities, layouts, material selection, lighting, procurement and project sequencing. It must flag professional verification for load-bearing/structural work, seismic design, major electrical-service design, gas systems, fire-code certification, statutory approvals and other regulated/safety-critical scopes.

## License

MIT. See [`LICENSE`](LICENSE).
