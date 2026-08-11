# NitiKube Roadmap

This roadmap separates **shipped deterministic capability** from **production-grade capability still required**. A checked box means code exists in `main`; it does not imply every real-world edge case is solved.

## Foundation — shipped

- [x] Streamlit multi-page application shell
- [x] deterministic geometry engine
- [x] lighting lumen method + COB beam geometry
- [x] material/paint quantity calculators
- [x] thermal/dew-point basics
- [x] budget scenarios + weighted/Pareto optimisation primitives
- [x] evidence-confidence and provenance contracts
- [x] product-search abstraction + zero-cost fallbacks
- [x] professional-verification scope guardrails
- [x] tests + Python 3.11/3.12 CI + Streamlit smoke tests

## Floor-plan intelligence

- [x] OpenCV line-detection baseline
- [x] user-verified pixel/physical scale calibration
- [x] multi-reference scale-disagreement metric
- [x] calibrated polygon-area calculation
- [x] enclosed/free-space candidate-region proposals
- [x] user verification selection + exported verified-region table
- [ ] robust wall topology graph
- [ ] automatic dimension OCR with confidence
- [ ] doors/windows/columns/stairs detection
- [ ] room-label detection
- [ ] perspective/scan correction
- [ ] interactive geometry correction editor
- [ ] complete room polygon extraction across open doorways
- [ ] full-home room adjacency graph

## Lighting

- [x] maintained-lux lumen method
- [x] beam footprint geometry
- [x] spacing/beam diagnostics
- [x] constrained fixture/grid/lumen search
- [x] SVG top-view lighting-plan export
- [ ] IES/LDT photometric-file parser
- [ ] point-by-point illuminance grid
- [ ] uniformity/glare metrics from photometric data
- [ ] daylight + electric-light combined model
- [ ] room-task-specific sourced target library

## Ergonomics + room planning

- [x] generic rectangular fit engine
- [x] dining envelope
- [x] TV/viewing geometry
- [ ] sourced accessibility/circulation rule library
- [ ] sofa/living-room planner
- [ ] kitchen work-triangle/work-zone planner
- [ ] wardrobe/storage planner
- [ ] bedroom planner
- [ ] bathroom fixture planner
- [ ] home-office planner
- [ ] door-swing/collision solver
- [ ] cross-room furniture/layout optimisation

## Material Intelligence

- [x] provenance-aware material record schema
- [x] verified/unverified/user-provided/subjective evidence states
- [x] verified numeric fact requires source + timestamp
- [x] unverified facts blocked from verified recommendations
- [x] deterministic product specification matcher
- [ ] sourced manufacturer/material property corpus
- [ ] datasheet ingestion pipeline
- [ ] water absorption / moisture data
- [ ] thermal conductivity / specific heat data
- [ ] UV/weathering data
- [ ] VOC/emission data
- [ ] slip/fire/chemical/abrasion properties where applicable
- [ ] room/environment suitability constraints
- [ ] pack-size aware procurement
- [ ] service-life/lifecycle maintenance model
- [ ] equivalent-material substitution engine

## Geography + building physics

- [x] geocoding adapter
- [x] current climate snapshot adapter
- [x] dew point / simple condensation check
- [x] R-value / U-value / conductive heat flow
- [x] latitude/day/solar-time geometry
- [x] first-pass shadow geometry
- [x] first-order Sabine RT60 acoustics
- [x] free-field sound-distance diagnostic
- [x] simple electrical load/current/energy/voltage-drop math
- [ ] long-term climate normals/design conditions
- [ ] climate-zone classification with sourced rules
- [ ] civil clock ↔ solar time conversion
- [ ] wall/window azimuth + incidence angle
- [ ] local obstruction/horizon modelling
- [ ] surface-temperature network
- [ ] mould-risk model
- [ ] transient thermal model
- [ ] glazing SHGC/U-value model
- [ ] daylight model
- [ ] more advanced room acoustics
- [ ] standards-aware electrical design engine (with professional boundary)

## Procurement + BOQ + audit

- [x] BOQ item/quantity primitives
- [x] quantity difference audit
- [x] price verification state
- [x] CSV/XLSX structured quote ingestion
- [x] explicit quote column mapping
- [x] line arithmetic validation
- [x] downloadable quote-audit CSV
- [ ] PDF text quote ingestion
- [ ] scanned PDF/photo OCR with verification
- [ ] calculated-BOQ ↔ quoted-line mapping workflow
- [ ] pack/waste/scope reconciliation
- [ ] broader live local product integrations
- [ ] seller/location availability
- [ ] price freshness/history
- [ ] warranty/specification extraction
- [ ] market-price comparison with licensing/compliance review

## Optimisation

- [x] feasible weighted ranking
- [x] Pareto-front primitives
- [x] lighting-specific constrained enumerator
- [x] Value/Balanced/Premium planning envelopes
- [ ] OR-Tools constraint solver
- [ ] cross-room budget optimisation
- [ ] must-not-compromise priorities
- [ ] lifecycle cost
- [ ] material substitution optimisation
- [ ] labour/sequence/resource constraints
- [ ] Monte Carlo / sensitivity analysis for uncertain prices and durations

## Execution planning

- [x] dependency DAG
- [x] cycle detection
- [x] earliest-start / earliest-finish
- [x] deterministic critical path
- [x] simple cumulative task-cost curve
- [ ] calendar dates + working-day calendars
- [ ] contractor/resource constraints
- [ ] lead times / procurement dependencies
- [ ] wet-work/dry-work rules with provenance
- [ ] milestones / payment stages
- [ ] schedule-risk simulation
- [ ] snagging / handover checklist

## 2D / 3D visualisation

- [x] deterministic SVG room/lighting export
- [x] Plotly plan/timeline visualisation
- [ ] interactive geometry editor
- [ ] floor-plan → 3D extrusion
- [ ] Three.js/WebGL viewer
- [ ] material/colour swapping
- [ ] parametric furniture models
- [ ] lighting cones
- [ ] daylight/solar overlay
- [ ] browser-side rendering

## AI / ML

- [x] CV proposal architecture with verification gate
- [x] deterministic-core / AI-explanation separation
- [ ] room/object segmentation model evaluation
- [ ] dimension/label OCR pipeline
- [ ] style embeddings from inspiration images
- [ ] preference learning
- [ ] product/material similarity
- [ ] grounded natural-language explanation layer
- [ ] local/browser model option
- [ ] no-LLM explanation fallback
- [ ] hallucination/evidence regression suite

## Production / privacy / scale

- [ ] public Streamlit deployment
- [ ] documented secrets/quota configuration
- [ ] privacy policy and uploaded-plan retention policy
- [ ] provider quota hard-stops
- [ ] observability without sensitive floor-plan logging
- [ ] accessibility QA
- [ ] browser/mobile QA
- [ ] real-home benchmark dataset with permission
- [ ] performance profiling
- [ ] security review

## v1.0 goal

`floor plan + verified dimensions + location + budget + lifestyle + taste`

→ a **traceable interior design package** containing feasible room layouts, calculations, materials, product options, BOQ, quotation audit, execution sequence, evidence, confidence and professional-verification flags.

## Permanent product rules

1. No recommendation without reasoning.
2. No invented price, specification, standard or material property.
3. AI does not own engineering arithmetic.
4. Critical CV measurements require verification.
5. Current product/pricing data carries source + timestamp/state.
6. Safety-critical scope gets a professional-verification flag.
7. Unknown required product/material facts are not treated as matches.
8. Heuristic CV scores are never presented as calibrated probabilities.
9. Zero-cost operation degrades gracefully instead of silently incurring paid API usage.
10. A difference in a contractor quote is an audit finding to reconcile—not an accusation.
