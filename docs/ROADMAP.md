# NitiKube Roadmap

## v0.1 — Physics-first room engineer

**Status: implemented in the foundation branch.**

- [x] Streamlit application shell
- [x] verification-first floor-plan CV baseline
- [x] geometry engine
- [x] lighting lumen method
- [x] COB beam geometry
- [x] fixture-grid visualisation
- [x] material quantity calculators
- [x] paint calculator
- [x] dew point / condensation check
- [x] simple R/U/Q thermal calculations
- [x] budget scenarios
- [x] product-search adapter and zero-cost fallback links
- [x] evidence-confidence framework
- [x] tests + CI

## v0.2 — Room intelligence

- [ ] automatic scale/dimension extraction with confidence
- [ ] room polygon extraction
- [ ] door/window/column/stair detection
- [ ] manual geometry editor
- [ ] furniture ergonomics and circulation rules
- [ ] TV-viewing and dining-clearance calculators
- [ ] false-ceiling geometry and quantities
- [ ] electrical-point planning
- [ ] richer 2D drawing export

## v0.3 — Material Intelligence

- [ ] sourced material-property database
- [ ] manufacturer datasheet ingestion
- [ ] moisture/UV/heat/chemical/slip/emission fields
- [ ] room-use material constraints
- [ ] alternatives and value-index ranking
- [ ] provenance and freshness on every material fact
- [ ] pack-size aware purchasing quantities

## v0.4 — Geography + building physics

- [ ] long-term climate normals/design conditions
- [ ] elevation and climate-zone context
- [ ] solar orientation and shading
- [ ] surface-temperature model
- [ ] condensation/mould-risk scenarios
- [ ] envelope heat-gain/loss model
- [ ] glazing/SHGC support
- [ ] climate-aware material filters

## v0.5 — Procurement + BOQ audit

- [ ] local live product discovery
- [ ] structured product/spec extraction
- [ ] price/stock timestamp and provenance
- [ ] specification-match scoring
- [ ] BOQ generator
- [ ] quotation PDF/image/Excel extraction
- [ ] quoted vs calculated quantity comparison
- [ ] market-price comparison where lawful/reliable
- [ ] contractor excess-quantity flags

## v0.6 — Optimisation engine

- [ ] constraint programming / OR-Tools
- [ ] multi-objective Pareto optimisation
- [ ] Value / Balanced / Premium-within-budget plans
- [ ] must-not-compromise user priorities
- [ ] substitution engine
- [ ] durability/maintenance/lifecycle cost

## v0.7 — Full-home DesignOS

- [ ] room graph for complete floor plans
- [ ] kitchen planner
- [ ] wardrobes/storage planner
- [ ] bathroom planner
- [ ] bedroom planner
- [ ] drawing/dining planner
- [ ] cross-room budget optimisation
- [ ] project sequencing / dependency graph

## v0.8 — 3D + interactive design

- [ ] floor-plan to 3D extrusion
- [ ] WebGL/Three.js viewer
- [ ] material/colour swapping
- [ ] furniture placement
- [ ] lighting cone visualisation
- [ ] daylight/solar overlays
- [ ] browser-side rendering to avoid image-generation cost

## v0.9 — AI/ML layer

- [ ] local/browser style embedding and inspiration-image matching
- [ ] preference learning
- [ ] product similarity
- [ ] explanation layer grounded only in deterministic outputs/evidence
- [ ] no-LLM fallback explanations
- [ ] hallucination/evidence regression tests

## v1.0 — NitiKube Interior DesignOS

Goal: floor plan + location + budget + lifestyle + taste → verified interior design package containing room layouts, calculations, materials, procurement options, BOQ, execution sequence, evidence and professional-verification flags.

## Permanent product rules

1. No recommendation without reasoning.
2. No invented price, specification, standard or material property.
3. AI does not own engineering arithmetic.
4. Critical CV measurements require verification.
5. Current product/pricing data carries source + timestamp/state.
6. Safety-critical scope gets a professional-verification flag.
7. Zero-cost operation degrades gracefully instead of silently incurring paid API usage.
