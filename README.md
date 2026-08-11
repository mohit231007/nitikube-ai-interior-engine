# NitiKube AI — Interior DesignOS

**Measured interiors. Verified decisions.**

NitiKube AI is a physics-first, evidence-grounded interior engineering system for homeowners who want to understand what a room/home actually needs before spending money on interiors.

The permanent product rule is:

> **No recommendation without reasoning.**

A recommendation must be backed by a calculation, a verified measurement, a rule/standard, a sourced material/product specification, geographic/climate evidence, or be explicitly labelled as subjective/aesthetic.

## Current build status

NitiKube is already a working multi-page Streamlit application, not a placeholder. The current `main` branch now spans verified floor-plan geometry, deterministic room-layout generation, manufacturer photometry, material evidence, climate analysis, procurement, cross-room budget optimisation, BOQ audit and execution planning.

### Geometry + floor plans

- feet/inches and ft²/m² conversion
- rectangle and arbitrary-polygon area (shoelace formula)
- OpenCV line-detection baseline
- user-verified pixel → physical scale calibration
- multi-reference calibration disagreement/spread reporting
- pixel-polygon → physical area conversion
- heuristic enclosed/free-space region proposals from uploaded floor plans
- explicit user verification before CV proposals become trusted geometry
- polygon-backed `VerifiedRoom` schema
- verified door/window/opening segments
- room/opening boundary validation
- shared-boundary room adjacency + opening-aware topology
- table-based Verified Geometry Editor
- authoritative geometry JSON / SVG / adjacency CSV export
- verified geometry persisted inside project snapshots

### Lighting engineering

- lumen method: `Phi = E × A / (CU × MF)`
- maintained-lux estimate
- COB beam diameter: `D = 2h tan(theta/2)`
- beam-spacing / overlap diagnostics
- constrained fixture/grid/lumen search
- deterministic downloadable SVG lighting plans
- Type-C IES LM-63 parser for the supported `TILT=NONE` subset
- candela interpolation
- point-by-point direct horizontal illuminance: `E = I(γ,C) cos(γ) / r²`
- multi-fixture superposition
- explicit maintenance factor
- direct-light minimum / average / maximum lux
- min/average and min/max uniformity ratios
- user-defined target-band coverage
- fixture-grid comparisons such as `2×4` vs `3×4` vs `3×5`
- Plotly IES illuminance heatmap + point-grid CSV
- initial benchmark remains the 10′7″ × 22′9″ drawing/dining room with a 9 ft false ceiling and 36° COB question

### Room planning + ergonomics

- rectangular furniture fit
- dining table/chair/movement envelope
- TV/screen geometry from chosen field of view
- deterministic drawing/dining candidate generator
- living-first / dining-first zone alternatives
- sofa left/right-wall alternatives
- dining-table 0°/90° alternatives
- furniture collision checks
- explicit pair-gap and reserved-clearance checks
- verified-opening keepout rectangles
- rasterized passage-width / walkable-connectivity diagnostic
- deterministic furniture-layout SVG
- feasible generated layout → whole-home optimizer package bridge

### Materials + quantities

- tile/board/panel quantities with explicit waste allowance
- paint quantities using user/manufacturer coverage input
- provenance-aware material-property model
- numeric verified facts require source + verification timestamp
- unverified material values cannot silently drive verified recommendations
- structured JSON/CSV datasheet evidence ingestion
- canonical material-property names + aliases
- deterministic supported-unit normalization
- cross-source conflict detection
- no silent averaging of conflicting values
- explicit preferred-source resolution
- material suitability constraints with PASS / FAIL / UNKNOWN
- missing required material evidence remains non-feasible
- empty production material registry rather than invented starter facts

### Geography + building physics

- geocoding adapter
- current climate snapshot adapter
- historical reanalysis daily-data adapter
- provider/model/location/date/timestamp climate provenance
- long-period climate profiles + monthly summaries
- explicit hot/cold/heavy-rain/high-solar scenario thresholds
- heating/cooling degree-day arithmetic with explicit bases
- location-to-location climate comparison
- climate design-pressure diagnostics without city-name material rules
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

### Product + procurement intelligence

- specification-first search-query builder
- optional Brave discovery adapter
- zero-cost retailer-search fallbacks
- product discovery explicitly separated from verification
- retailer-specific structured product offers
- price verification requires price + source + timestamp
- price-age/freshness arithmetic
- explicit in-stock / out-of-stock / preorder / unknown states
- warranty and delivery-location evidence constraints
- conservative brand+model / brand+SKU product grouping
- required-but-unknown specs/evidence remain non-feasible
- transparent procurement ranking
- user-uploaded schema.org `Product` / `Offer` JSON-LD extraction
- no arbitrary server-side product-URL fetching in the public workflow
- small per-session optional live-search call cap

### Whole-home optimisation

- weighted feasible-option ranking
- Pareto-front primitives
- constrained lighting-layout optimisation
- one design package per required room
- global cross-room budget coupling
- protected reserve
- must-not-compromise room policies
- homeowner locks before re-optimisation
- verified-geometry area/width/height constraints
- exact additive dynamic programming with cost/utility Pareto-state pruning
- editable Value / Balanced / Full-budget scenario envelopes
- selected whole-home package JSON export

### BOQ + quotation audit + execution

- BOQ line/quantity primitives
- calculated-vs-quoted quantity diagnostics
- CSV/XLSX quotation ingestion
- explicit quotation column mapping
- `quantity × rate` arithmetic validation
- insufficient-data state rather than invented values
- downloadable quote-audit CSV
- dependency-graph execution scheduling
- cycle detection
- earliest start/finish
- deterministic critical path
- simple cumulative task-cost timing

### Quality + safety

- deterministic Python core kept separate from AI explanation
- unsupported cases fail closed instead of being silently treated as verified
- Python 3.11 + 3.12 GitHub Actions CI
- compile checks
- pytest deterministic test suite
- Streamlit app/page smoke tests
- no mandatory paid AI API
- professional-verification guardrails for structural/regulatory scopes

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
9. Verified Geometry Editor
10. Material Datasheet Evidence Lab
11. Geography → Climate → Design Pressure
12. Procurement Intelligence
13. Whole-Home Design Optimizer
14. Deterministic Drawing / Dining Layout Generator
15. IES Point-by-Point Lighting Lab

The numbered filenames under `pages/` currently run from `01` through `14`; the main `app.py` is the first application experience listed above.

## Architecture contract

```text
floor plan / user inputs / product specs / location / budget / IES
                              │
                              ▼
                      VERIFICATION GATE
                              │
       ┌──────────────────────┼───────────────────────┐
       ▼                      ▼                       ▼
    GEOMETRY               SCIENCE                 EVIDENCE
       │                      │                       │
       ├──────────────────────┼───────────────────────┤
       ▼                      ▼                       ▼
      CV/ML              CONSTRAINTS            LIVE ADAPTERS
       │                      │                       │
       └──────────────────────┼───────────────────────┘
                              ▼
                     FEASIBLE ROOM OPTIONS
                              │
                              ▼
                  WHOLE-HOME OPTIMISATION
                              │
                              ▼
                   AI EXPLANATION / DESIGN UX
```

**AI does not own engineering arithmetic.** AI/ML/CV may propose, classify, rank and explain. Deterministic tested code owns geometry, quantities, physics and hard-constraint calculations.

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
- optional climate/geocoding adapters for prototyping
- optional search adapter only when a key/quota is available
- direct retailer-search links as a zero-cost fallback
- SVG/Plotly rendering instead of paid image generation
- user-uploaded product HTML instead of arbitrary server-side scraping
- provider adapters isolated from the deterministic science core

External providers remain replaceable. If a free quota disappears, NitiKube should degrade gracefully instead of silently generating a bill.

## What is *not* claimed complete yet

The repository has moved substantially beyond the original room-lighting prototype, but a production-grade whole-home Interior DesignOS still needs:

- robust automatic walls/doors/windows/columns/stairs + dimension/label OCR
- drag-handle polygon geometry editing
- sourced manufacturer/material datasets at useful scale
- PDF/image datasheet extraction with page-level evidence
- higher-fidelity solar/daylight/surface-temperature/moisture models
- sourced climate-zone and room/task standards libraries
- kitchen, wardrobes, bathroom, bedroom and home-office planners
- arbitrary polygon furniture optimisation and exact door swings
- broader trusted local retailer/manufacturer inventory integrations
- PDF/photo quotation OCR with verification
- lifecycle-cost/material substitution optimisation
- 3D/WebGL room/house visualisation
- browser-side/local AI style and preference models
- production deployment, privacy/retention controls and provider-wide zero-paid-overage enforcement
- larger real-world regression datasets with permission

See [`docs/ROADMAP.md`](docs/ROADMAP.md).

## Safety boundary

NitiKube can assist with interior planning, quantities, layouts, material selection, lighting, procurement and project sequencing. It must flag professional verification for load-bearing/structural work, seismic design, major electrical-service design, gas systems, fire-code certification, statutory approvals and other regulated/safety-critical scopes.

## License

MIT. See [`LICENSE`](LICENSE).
