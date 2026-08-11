# NitiKube AI — Current Build Status

**Product:** NitiKube AI / Interior DesignOS  
**Core rule:** **No recommendation without reasoning.**  
**Current capability milestone:** **v0.26 — service-aware whole-home candidate factory**.

This file is deliberately conservative. **Implemented** means code exists in this repository with deterministic tests/guardrails; it does **not** mean every module is production-certified or that NitiKube can replace licensed professionals for regulated work.

---

## 1. Product architecture now implemented

```text
floor plan / verified dimensions / homeowner brief / product & material evidence
                                  │
                                  ▼
                          VERIFICATION GATE
                                  │
                 ┌────────────────┼────────────────┐
                 ▼                ▼                ▼
             GEOMETRY         SERVICES         EVIDENCE
                 │                │                │
                 ├───────────────┬┴───────────────┤
                 ▼               ▼                ▼
          ROOM CANDIDATES   HARD FEASIBILITY   STANDARDS /
          + QUANTITIES        FILTERS          MATERIALS
                 │               │                │
                 └───────────────┼────────────────┘
                                 ▼
                       OPTIMIZER-READY OPTIONS
                                 │
                                 ▼
                       WHOLE-HOME OPTIMIZATION
                                 │
                                 ▼
                       HASHED DESIGN PACKAGE
                                 │
                ┌────────────────┼────────────────┐
                ▼                ▼                ▼
               3D          PROCUREMENT/BOQ     FINAL REPORT
```

**AI does not own engineering arithmetic.** AI/ML/CV may propose, classify, rank or explain. Deterministic tested code owns geometry, quantities, physics, evidence-state logic, hard constraints and optimization arithmetic.

---

# 2. Verified geometry + floor-plan foundation

## Implemented

- feet/inches and ft²/m² conversion
- rectangle and arbitrary-polygon area
- polygon centroid and validation
- self-intersection / zero-edge checks
- verified room and verified opening schemas
- opening-on-boundary validation
- shared-boundary / room adjacency graph
- deterministic fixture-grid coordinates
- user-verified pixel → physical scale calibration
- multi-reference calibration disagreement/spread reporting
- pixel polygon → physical area conversion
- OpenCV line-detection baseline
- heuristic enclosed/free-space region proposals
- explicit verification gate before CV proposals become trusted geometry
- verified-region CSV/JSON exports
- deterministic geometry editor workflow
- exact-rectangle validation for rectangle-only room planners
- explicit refusal to replace unsupported non-rectangular verified rooms with bounding boxes

## Not yet production-complete

- robust room/wall/door/window/column/stair extraction from arbitrary real plans
- production dimension OCR
- perspective/skew correction for photographed plans
- wall-thickness reconstruction
- automatic door-swing interpretation
- exact opening sill/head heights
- large real-world floor-plan regression corpus
- arbitrary-polygon furniture/cabinet planners across all room types

---

# 3. Lighting engineering

## Implemented

- lumen-method arithmetic
- maintained-lux estimate
- COB beam diameter
- beam-spacing / overlap diagnostics
- constrained fixture-count/grid search
- deterministic SVG lighting layouts
- IES LM-63 numeric parser for supported Type-C photometry
- fail-closed unsupported tilt / Type A/B / partial-symmetry handling
- candela interpolation
- point-by-point direct horizontal illuminance
- multi-fixture superposition
- maintenance factor
- point-grid min/average/max lux
- uniformity ratios
- explicit target-band coverage
- IES Photometry Lab

## Important boundary

Current IES calculation is direct illuminance only. It does not yet claim full interreflection, UGR/glare certification, daylight integration or lighting-code compliance.

---

# 4. Room-specific deterministic planners

## Drawing / dining

Implemented:

- deterministic living/dining zone variants
- sofa-wall alternatives
- dining-table rotation alternatives
- collisions
- pair gaps
- wall margins
- clearance envelopes
- verified-opening keepouts
- circulation raster metrics
- SVG output
- whole-home optimizer package bridge

## Kitchen

Implemented:

- one-wall layouts
- galley layouts
- L-shape layouts
- U-shape layouts
- sink / hob / fridge work-centre placement
- module-fit checks
- work-triangle leg/perimeter/area arithmetic
- optional explicit triangle constraints
- opening collisions
- passage-width connectivity
- gross counter run
- non-double-counted countertop union area
- base/wall cabinet quantity envelopes
- explicit countertop waste factor
- optimizer package bridge

Not yet production-complete:

- exact plumbing/drain/electrical/gas/ventilation routing
- manufacturer appliance-clearance rules at useful scale
- cabinet-module libraries
- corner hardware / shutter / drawer manufacturing logic
- arbitrary-polygon kitchen generation

## Bedroom + wardrobe

Implemented:

- bed-wall alternatives
- wardrobe-wall alternatives
- optional desk alternatives
- directional side/foot bed clearances
- wardrobe-front access zones
- collisions / opening keepouts / circulation
- wardrobe run / front area / geometric volume
- optimizer package bridge

Not yet production-complete:

- bedside-table generation
- window/radiator/electrical constraints at full fidelity
- TV sightline integration
- wardrobe compartment/internal-storage optimization
- arbitrary-polygon bedroom generation

## Bathroom

Implemented:

- shower-corner variants
- WC-wall variants
- basin-wall variants
- fixture collisions
- directional fixture-front clearances
- opening keepouts
- circulation
- floor/wall tile quantities
- opening deductions
- waterproofing quantities
- ACH → exhaust-CFM arithmetic
- drainage-run slope/fall arithmetic
- optimizer package bridge

Not yet production-complete:

- exact drain coordinates + routed slope networks
- floor slope-field modeling
- plumbing fixture connection libraries
- wet-zone electrical rules at jurisdiction scale
- exact shower/door swing geometry
- arbitrary-polygon bathroom generation

---

# 5. Whole-home candidate generation — v0.23

## Implemented

The Whole-Home Candidate Factory connects verified geometry directly to the deterministic room planners.

It now supports:

- room-aware design-brief template from verified geometry
- deterministic room-role inference from explicit room names
- explicit role override
- ambiguous/anonymous room fail-closed behavior
- dispatch to drawing/dining, kitchen, bedroom/wardrobe and bathroom planners
- unified room/candidate audit
- hard geometry rejection
- globally unique option IDs:

```text
<room_id>::<role>::<planner_layout_id>
```

- explicit required-room scope
- no silent dropping of incomplete required rooms
- optimizer promotion only after explicit cost + five decision scores exist
- optional explicit geometry-score blending
- direct whole-home optimization
- direct hashed design-package generation

## Permanent score boundary

A planner `geometry_score` is **not** silently re-labelled as aesthetics, comfort, quality, durability or maintainability.

If a caller wants deterministic geometry blended into a decision score, the brief must explicitly define that mapping.

---

# 6. Verified service-point evidence — v0.24

## Implemented

NitiKube now has a dedicated service-location evidence layer.

Supported service kinds include:

- cold water
- hot water
- drain
- electrical
- gas
- exhaust
- data
- HVAC condensate
- other

Capabilities:

- `nitikube.service_points` artifact
- verified point coordinates tied to authoritative `room_id`
- XY + optional Z coordinates
- validation that service points lie within the declared verified room
- empty room-aware service-point template — **no service location is invented from room type**
- explicit service targets
- explicit allowed service kinds
- optional maximum route distance
- required vs optional requirements
- plan and 3D distance modes
- fail-closed unknown Z in required 3D links
- same-room matching
- verified-only matching
- exact minimum-total-distance unique assignment when sharing is disabled
- explicit shared-point mode when sharing is intentionally allowed
- kitchen target adapters: sink / hob / fridge
- bathroom target adapters: shower / WC / basin
- bedroom target adapters: bed / wardrobe / desk
- generic layout target adapters
- downloadable routing-evaluation JSON

## Current routing boundary

Current route distance is a **straight-line lower bound**.

It is not yet:

- wall/shaft-aware routed pipe length
- routed cable length
- routed duct length
- pressure-drop calculation
- drainage hydraulics
- pipe sizing
- voltage-drop calculation
- electrical circuit/load sizing
- ventilation pressure-loss calculation
- gas-system safety design
- code certification

---

# 7. Service-aware candidate feasibility — v0.25

## Implemented

Verified services can now reject otherwise valid room candidates.

Permanent rule:

```text
overall_feasible = geometry_feasible AND service_feasible
```

Capabilities:

- `nitikube.candidate_service_rules`
- candidate-specific target-coordinate evaluation
- missing required target → failure
- missing optional target → warning
- kitchen service-aware candidate wrappers
- bathroom service-aware candidate wrappers
- bedroom/wardrobe service-aware candidate wrappers
- drawing/dining service-aware candidate wrappers
- service feasibility does not rewrite geometry score
- service route distance is only a transparent tie-breaker after hard feasibility + geometry score
- downloadable combined candidate evaluation

This means, for example, two geometrically valid kitchen layouts can receive different feasibility outcomes because their actual sink locations have different relationships to the verified water/drain evidence.

---

# 8. Service-aware whole-home optimization — v0.26

## Implemented

The v0.24/v0.25 service evidence layer is now wired into the v0.23 Whole-Home Candidate Factory.

Pipeline:

```text
verified geometry
+ room/design brief
+ verified service points
→ deterministic room candidates
→ geometry gate
→ candidate-specific service gate
→ feasible optimizer options
→ whole-home optimization
→ hashed design package
```

Room service states are explicit:

- `evaluated`
- `not_configured`
- `blocked`
- `not_evaluated_base_room_blocked`

A room without service rules is **not** reported as a fake PASS.

Additional v0.26 guarantees:

- raw candidate regeneration must reproduce the exact v0.23 candidate IDs before service evidence is bound to them
- service failures/warnings remain separately identified
- service route metrics appear only after service evaluation
- service-blocked candidates are marked infeasible before optimization
- each required room must retain at least one feasible optimizer option
- service-blocked required rooms are never silently removed
- final package hash covers:
  - geometry artifact
  - generated option artifact
  - verified service-point artifact
  - service-aware whole-home brief
- existing package hash verification remains valid

---

# 9. Materials + product evidence

## Implemented

- tile / board / panel quantities with explicit waste
- paint quantities using explicit coverage inputs
- provenance-aware material-property model
- verified numeric facts require source + timestamp
- unverified values cannot silently drive verified recommendations
- empty production material registry rather than invented facts
- deterministic product-spec matching
- matched / failed / unknown product criteria
- datasheet ingestion/extraction workflow
- product source/verification state

## Not yet production-complete

- large legally sourced manufacturer material corpus
- automated product-spec ingestion at market scale
- verified pack/slab/board size catalog coverage
- broad regional availability/inventory

---

# 10. Standards / guidance evidence — v0.18+

## Implemented

- provenance-first rule registry
- rule ID / subject / metric / operator / value / unit
- room/applicability tags
- mandatory state
- authority / jurisdiction / document version
- source URL / checked timestamp / locator
- deterministic compatible-unit comparison
- PASS / FAIL / UNKNOWN / NOT_APPLICABLE states
- applicability context
- conflict detection for disjoint same-scope numeric intervals
- JSON/CSV ingestion
- no production numeric standard corpus bundled by default

## Important boundary

The engine is a standards-evidence framework, not a legal interpretation service and not a redistribution mechanism for copyrighted/paywalled standards.

A useful production corpus still needs lawful sourcing and jurisdiction-specific professional review.

---

# 11. Building physics

## Implemented

- dew point
- first-order condensation-risk check
- thermal-layer resistance
- assembly U-value
- conductive heat flow
- latitude/day/solar-time solar geometry
- first-pass shadow geometry
- Sabine RT60 acoustics
- free-field SPL-distance diagnostic
- connected/diversified electrical-load arithmetic
- single-phase current equation
- energy arithmetic
- conductor resistance + voltage-drop math using explicit resistivity

## Not yet production-complete

- whole-building dynamic simulation
- validated design-day climate datasets at production scale
- detailed daylight simulation
- CFD
- professional electrical design automation
- structural/seismic engineering

---

# 12. Climate + geography

## Implemented

- geocoding/climate adapter framework
- historical climate comparison workflow
- solar-geometry inputs tied to location
- explicit provenance/freshness concepts

## Not yet production-complete

- long-horizon production design-weather corpus
- climate-zone regulatory mapping at jurisdiction scale
- detailed daylight/solar obstruction model

---

# 13. Lifecycle material value

## Implemented

- material + labour installed cost
- explicit material waste
- annual maintenance cash flows
- service-life replacements
- disposal/replacement costs
- explicit escalation
- present-value discounting
- optional residual service-value credit
- equivalent annual cost
- NPV per area
- verified / user-provided / unverified evidence states
- feature-based substitution filters
- separate performance score
- cost × performance Pareto frontier
- deterministic low/base/high sensitivity multipliers

## Important boundary

Sensitivity bands are what-if scenarios, not statistical confidence intervals.

Missing service life/cost evidence remains unavailable rather than being filled with zero.

---

# 14. Procurement + quotation + execution

## Implemented

- specification-first search-query builder
- optional search adapter + zero-cost fallbacks
- price verification state with source/timestamp
- BOQ quantity audit primitives
- CSV/XLSX quotation ingestion
- explicit quotation column mapping
- `quantity × rate` arithmetic validation
- quotation audit export
- dependency-graph execution scheduling
- cycle detection
- earliest start/finish
- critical path
- simple cumulative task-cost timing

## Not yet production-complete

- broad live inventory integrations
- PDF/photo quotation OCR at production quality
- automated vendor normalization
- procurement order/payment integrations
- site-progress telemetry

---

# 15. Whole-home optimizer + project orchestration

## Implemented

- one design package per required room
- additive utility across explicit decision dimensions
- normalized user weights
- global budget coupling
- protected reserve
- exact dynamic-programming Pareto-state pruning
- homeowner locks
- hard room policies before scoring
- verified-geometry fit constraints
- explicit infeasible states
- Value/Balanced/Full-budget scenario support
- multi-artifact room-option merge
- global option-ID uniqueness
- strict room-ID linkage to verified geometry
- complete vs partial project scope
- SHA-256 artifact fingerprints
- selected-option source provenance
- deterministic design-package manifest/hash
- tamper/hash verification
- professional-verification flags preserved into the package

---

# 16. Privacy + zero-paid-cost guardrails

## Implemented

- provider/operation policy
- per-session call cap
- declared estimated cost/call
- paid-usage enabled/disabled switch
- explicit paid-cost cap
- positive-cost call blocked before execution when paid usage is disabled
- authorized usage ledger
- sensitivity classes for floor plans / home photos / quotations / verified geometry
- raw sensitive artifact retention disabled by default
- external sensitive transfer disabled by default
- optional explicit user-consent requirement
- metadata-only telemetry primitives
- hashes / byte size / MIME / sensitivity without raw content

## Important limitation

Application-session caps alone cannot truthfully guarantee ₹0 account-wide public usage. Production zero-cost guarantees still require provider-side spending/overage caps and/or shared persistent quota accounting.

---

# 17. 3D visualization

## Implemented

- simple-polygon ear-clipping triangulation
- clockwise/counter-clockwise polygon support
- concave polygon support
- deterministic room floor meshes
- wall-edge extrusion
- optional ceiling meshes
- parametric object boxes
- verified opening overlays
- `nitikube.scene3d` export
- interactive Plotly 3D
- self-contained HTML export
- no mandatory paid rendering/image-generation API

## Not yet production-complete

- wall-thickness solids
- Boolean door/window openings
- planner-native object transfer across every room planner
- parametric cabinetry/sanitaryware libraries
- material/product textures
- photorealistic rendering
- IES/daylight overlay in 3D

---

# 18. Final report + handoff

## Implemented

- requires `nitikube.design_package`
- package SHA verification by default
- explicit forensic override for invalid hash
- optional standards/lifecycle attachments
- selected vs required room audit
- open professional-verification flags
- standards PASS/FAIL/UNKNOWN/N/A summary
- lifecycle feasible/non-feasible summary
- provenance display
- escaped untrusted strings
- deterministic report ID
- self-contained print-friendly HTML
- browser Print → Save as PDF path
- structured audit JSON

The final report is a coordination/decision artifact, not a stamped architectural/structural/electrical/plumbing approval.

---

# 19. Streamlit application pages

Current application pages now extend through:

1. Main app
2. Ergonomics + BOQ
3. Optimizers
4. Materials + Products
5. Plan Calibration + Export
6. Building Physics
7. Quotation + Execution
8. Floor-plan Regions
9. Verified Geometry Editor
10. Material Datasheet Lab
11. Climate Comparison
12. Procurement Intelligence
13. Whole-Home Optimizer
14. Drawing / Dining Layout Generator
15. IES Photometry Lab
16. Kitchen Planner
17. Bedroom + Wardrobe Planner
18. Bathroom Planner
19. Project Orchestrator
20. Standards / Guidance Evidence Lab
21. Lifecycle Material Value
22. Privacy + Zero-Paid-Cost Guardrails
23. Verified-Geometry 3D Scene Viewer
24. Final Design Package Report
25. Whole-Home Candidate Factory
26. Verified Service Points + Routing Lab
27. Service-Aware Candidate Lab
28. Service-Aware Whole-Home Candidate Factory

> File numbering currently reflects repository page filenames rather than this conceptual list; the newest repository pages are `24_Whole_Home_Candidate_Factory.py`, `25_Service_Points_and_Routing.py`, `26_Service_Aware_Candidate_Lab.py`, and `27_Service_Aware_Whole_Home_Factory.py`.

---

# 20. Test / CI posture

## Implemented

- Python 3.11 + 3.12 core CI
- compile-all checks
- deterministic pytest suite
- Streamlit import/smoke checks
- page-specific smoke workflows for newer capability layers
- fail-closed tests for unsupported/unknown states
- reproducibility/hash tests
- optimizer exactness tests
- planner geometry/quantity tests
- IES tests
- standards/lifecycle/privacy tests
- service-routing tests
- service-aware candidate tests
- service-aware whole-home factory tests

The suite is meaningful but does not replace real-home validation and professional domain review.

---

# 21. Major remaining production gaps

The largest remaining gaps are now clearer.

## A. Floor-plan intelligence

- reliable OCR/dimension understanding
- robust CV room/wall/opening semantics
- arbitrary-polygon room planning
- larger regression datasets

## B. Service-network engineering

- wall/shaft/riser-aware routed paths
- cross-room service networks
- drainage slope-network routing
- plumbing hydraulics / sizing
- electrical load/circuit/voltage-drop integration
- ventilation pressure-loss / duct routing
- manufacturer/service-point clearance integration

## C. Evidence scale

- lawful jurisdiction-specific standards corpus
- manufacturer/material/product corpus
- broad regional live pricing and inventory
- verified labour-rate evidence

## D. Design depth

- kitchen cabinet-module optimization
- wardrobe internal-compartment optimization
- bathroom slope/drain planning
- richer room types
- full planner-native 3D objects

## E. AI / ML layer

- grounded explanation/search over verified NitiKube artifacts
- preference/style learning
- local/browser-friendly AI options where practical
- stronger CV/ML plan interpretation
- explicit privacy/budget gates around every external AI/search call

## F. Production platform

- authentication/projects/storage
- persistent audit trail
- shared quota/billing protection
- telemetry/privacy controls
- deployment hardening
- end-to-end regression tests on real homes

---

# 22. Current product truth

NitiKube is **no longer just a room calculator or AI interior mock-up**.

The repository now contains a deterministic, evidence-first chain from verified geometry through room candidate generation, service-aware feasibility, whole-home optimization, artifact provenance, 3D visualization and final reporting.

The strongest current differentiator is not photorealism. It is the ability to say:

> **Why is this option being recommended, what evidence/calculation supports it, what remains unknown, what failed, and which professional checks are still open?**

The next major engineering frontier is:

```text
arbitrary real floor plan
→ verified semantic geometry
→ wall/shaft-aware service network
→ fully service-aware room generation
→ sourced standards/material/product evidence
→ whole-home optimization
→ buildable handoff
```

That is the path from a strong engineering prototype to a production Interior DesignOS.
