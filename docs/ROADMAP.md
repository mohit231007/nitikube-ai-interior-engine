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
- [x] verified polygon-backed room geometry schema
- [x] verified door/window/opening segment schema
- [x] shared-boundary room adjacency graph
- [x] opening-aware room topology
- [x] table-based authoritative geometry correction editor
- [x] verified geometry JSON/SVG/CSV export + project persistence
- [ ] robust automatic wall topology extraction from CV
- [ ] automatic dimension OCR with confidence/source bounding boxes
- [ ] automatic doors/windows/columns/stairs detection
- [ ] room-label detection
- [ ] perspective/scan correction
- [ ] drag-handle polygon editor
- [ ] complete room polygon extraction across open doorways
- [ ] real-plan regression corpus with permission

## Lighting

- [x] maintained-lux lumen method
- [x] beam footprint geometry
- [x] spacing/beam diagnostics
- [x] constrained fixture/grid/lumen search
- [x] SVG top-view lighting-plan export
- [x] fail-closed Type-C IES LM-63 parser (`TILT=NONE` subset)
- [x] candela interpolation
- [x] point-by-point direct horizontal illuminance grid
- [x] multi-fixture inverse-square/cosine superposition
- [x] minimum/average/maximum + direct-light uniformity ratios
- [x] IES fixture-grid comparison against explicit target bands
- [ ] IES partial-symmetry plane interpreter
- [ ] LDT parser
- [ ] fixture aiming / tilt
- [ ] glare metrics such as UGR
- [ ] interreflection/radiosity model
- [ ] daylight + electric-light combined model
- [ ] room-task-specific sourced target library

## Ergonomics + room planning

- [x] generic rectangular fit engine
- [x] dining envelope
- [x] TV/viewing geometry
- [x] drawing/dining deterministic candidate generator
- [x] sofa/TV/coffee/dining furniture collision checks
- [x] verified-opening rectangular keepouts
- [x] explicit pair-gap and reserved-clearance checks
- [x] rasterized passage-width / walkable-connectivity diagnostic
- [x] feasible drawing/dining layout → whole-home package bridge
- [ ] sourced accessibility/circulation rule library
- [ ] arbitrary polygon room planner
- [ ] exact door-swing arc solver
- [ ] kitchen work-triangle/work-zone planner
- [ ] wardrobe/storage planner
- [ ] bedroom planner
- [ ] bathroom fixture planner
- [ ] home-office planner
- [ ] individual dining-chair placement
- [ ] continuous/nonlinear furniture placement optimisation

## Material Intelligence

- [x] provenance-aware material record schema
- [x] verified/unverified/user-provided/subjective evidence states
- [x] verified numeric fact requires source + timestamp
- [x] unverified facts blocked from verified recommendations
- [x] structured JSON/CSV datasheet evidence ingestion
- [x] canonical material-property vocabulary + aliases
- [x] deterministic supported-unit normalization
- [x] explicit cross-source conflict detection
- [x] no silent averaging of conflicting material facts
- [x] explicit preferred-source conflict resolution
- [x] deterministic material suitability constraints
- [x] required missing property = UNKNOWN/non-feasible
- [x] deterministic product specification matcher
- [ ] sourced manufacturer/material property corpus at useful scale
- [ ] manufacturer PDF/datasheet extraction with page/section evidence
- [ ] water absorption / moisture corpus
- [ ] thermal conductivity / density / specific-heat corpus
- [ ] UV/weathering corpus
- [ ] VOC/emission corpus
- [ ] slip/fire/chemical/abrasion corpus where applicable
- [ ] pack-size aware procurement
- [ ] service-life/lifecycle maintenance model
- [ ] equivalent-material substitution graph/engine

## Geography + building physics

- [x] geocoding adapter
- [x] current climate snapshot adapter
- [x] historical reanalysis daily-data adapter
- [x] provider/model/location/date/checked-at climate provenance
- [x] historical climate profile + monthly summaries
- [x] explicit hot/cold/rain/solar exposure thresholds
- [x] heating/cooling degree-day arithmetic with explicit bases
- [x] location-to-location climate comparison
- [x] climate → design-pressure diagnostics without city-name material rules
- [x] dew point / simple condensation check
- [x] R-value / U-value / conductive heat flow
- [x] latitude/day/solar-time geometry
- [x] first-pass shadow geometry
- [x] first-order Sabine RT60 acoustics
- [x] free-field sound-distance diagnostic
- [x] simple electrical load/current/energy/voltage-drop math
- [ ] sourced climate-zone classification
- [ ] civil clock ↔ solar-time conversion
- [ ] wall/window azimuth + solar incidence
- [ ] local obstruction/horizon modelling
- [ ] surface-temperature network
- [ ] mould-risk model
- [ ] transient thermal model
- [ ] glazing SHGC/U-value model
- [ ] daylight model
- [ ] more advanced room acoustics
- [ ] standards-aware electrical design engine with professional boundary

## Procurement + BOQ + audit

- [x] BOQ item/quantity primitives
- [x] quantity difference audit
- [x] structured price/source/timestamp verification state
- [x] price-age/freshness calculation
- [x] explicit in-stock/out-of-stock/preorder/unknown states
- [x] warranty and delivery-location evidence constraints
- [x] conservative brand+model / brand+SKU variant grouping
- [x] unknown required procurement evidence remains non-feasible
- [x] transparent procurement ranking
- [x] structured product-offer JSON ingestion
- [x] user-uploaded schema.org Product/Offer JSON-LD extraction
- [x] optional live search with zero-cost retailer fallbacks
- [x] per-session live-search call cap
- [x] CSV/XLSX structured quote ingestion
- [x] explicit quote column mapping
- [x] line arithmetic validation
- [x] downloadable quote-audit CSV
- [ ] PDF text quote ingestion
- [ ] scanned PDF/photo OCR with verification
- [ ] calculated-BOQ ↔ quoted-line mapping workflow
- [ ] pack/waste/scope reconciliation
- [ ] trusted retailer/manufacturer adapters
- [ ] real location-aware stock/delivery integrations
- [ ] provider-wide quota hard-stop accounting
- [ ] persisted price history
- [ ] broader warranty/specification normalization
- [ ] market-price comparison with licensing/compliance review

## Optimisation

- [x] feasible weighted ranking
- [x] Pareto-front primitives
- [x] lighting-specific constrained enumerator
- [x] explicit Value/Balanced/Full-budget planning envelopes
- [x] exact additive cross-room budget optimisation
- [x] protected reserve
- [x] must-not-compromise room policies
- [x] homeowner option locks
- [x] verified-geometry fit constraints in whole-home selection
- [x] dynamic-programming cost/utility Pareto-state pruning
- [ ] OR-Tools/CP-SAT path for richer discrete constraints
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
- [ ] product lead times / procurement dependencies
- [ ] wet-work/dry-work rules with provenance
- [ ] milestones / payment stages
- [ ] schedule-risk simulation
- [ ] snagging / handover checklist

## 2D / 3D visualisation

- [x] deterministic SVG room/lighting export
- [x] verified geometry SVG export
- [x] deterministic furniture-layout SVG export
- [x] Plotly plan/timeline visualisation
- [x] Plotly IES illuminance heatmap
- [x] table-based geometry editor
- [ ] drag-handle interactive geometry editor
- [ ] floor-plan → 3D extrusion
- [ ] Three.js/WebGL viewer
- [ ] material/colour swapping
- [ ] parametric 3D furniture models
- [ ] lighting cones / photometric overlay in 3D
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
- [ ] documented secrets/quota configuration enforced in deployment
- [ ] privacy policy and uploaded-plan retention policy
- [ ] provider-wide quota hard-stops
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
8. Heuristic CV/layout scores are never presented as calibrated scientific probabilities or aesthetic truth.
9. Zero-cost operation degrades gracefully instead of silently incurring paid API usage.
10. A difference in a contractor quote is an audit finding to reconcile—not an accusation.
11. Search discovery is not product verification.
12. Climate/location labels do not directly prescribe materials; measured/modelled variables drive explicit constraints.
13. Unsupported photometric/geometry cases fail closed rather than being silently approximated as verified.
