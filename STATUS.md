# NitiKube AI — Current Build Status

**Product:** NitiKube AI / Interior DesignOS  
**Core rule:** **No recommendation without reasoning.**  
**Current capability milestone:** v0.22 foundation + room planners + orchestration + evidence/report layers.

This file is deliberately conservative: **implemented** means code exists in the repository with deterministic tests/guardrails; it does not mean every module is production-certified or that NitiKube can yet replace licensed professionals for regulated work.

## Implemented

### Verified floor-plan / geometry foundation
- OpenCV floor-plan line/region proposal baseline
- verification-first CV semantics
- pixel → physical scale calibration
- multi-reference scale disagreement checks
- verified room polygons/openings
- room-region proposals
- room adjacency / topology primitives
- SVG plan export
- geometry never silently replaced by a guessed bounding box in planners that do not support arbitrary polygons

### Lighting / photometry
- lumen method
- maintained lux
- COB beam-diameter geometry
- fixture grid generation / optimisation
- 36° COB analysis
- Type-C IES point-by-point photometry subset
- point-grid illuminance metrics / heatmap data
- fail-closed unsupported photometric cases

### Room-specific deterministic planners
- drawing / dining planner
- kitchen planner
  - one-wall / galley / L / U candidates
  - sink / hob / fridge work-centre geometry
  - explicit work-triangle constraints
  - opening / circulation constraints
  - countertop/cabinet quantity envelopes
- bedroom / wardrobe planner
  - bed / wardrobe / optional desk alternatives
  - directional bed-side / foot clearance
  - wardrobe-front access zone
  - wardrobe geometric quantities
- bathroom planner
  - shower / WC / basin alternatives
  - fixture-front clearance
  - tile / waterproofing quantities
  - explicit ACH → CFM airflow calculation
  - explicit drainage slope → fall calculation

### Geometry / ergonomics / circulation
- rectangle and polygon maths
- shoelace areas
- collision checks
- wall/opening keepouts
- raster passage-width connectivity
- dining-envelope calculations
- TV-viewing geometry primitives
- deterministic furniture-fit reasoning

### Material / evidence / geography
- material evidence states and provenance model
- material suitability / conflict primitives
- climate adapter architecture
- historical/current climate variables
- dew point / condensation checks
- R-value / U-value / conductive heat-flow maths
- solar geometry / shadow diagnostics
- material/standards framework does not ship invented production values

### Building physics
- thermal resistance / heat flow
- dew point / condensation diagnostics
- solar geometry
- first-order acoustics / RT60
- electrical load / energy / conductor resistance / voltage drop arithmetic
- explicit safety/model-boundary warnings

### Product / procurement evidence
- specification-first product query building
- deterministic specification matcher
- required-but-unknown specifications are not treated as matches
- verified price state requires source + timestamp
- optional search adapter + retailer-search fallback design
- local/geographic lookup adapter architecture

### Quantity / BOQ / contractor audit
- tile / board / panel / paint quantities
- explicit wastage
- BOQ primitives
- CSV/XLSX quotation import
- explicit semantic column mapping
- quantity × rate arithmetic audit
- discrepancy / insufficient-data states
- downloadable audit results

### Budget / optimisation
- budget envelopes
- weighted feasible-option scoring
- Pareto optimisation primitives
- constrained lighting optimisation
- cross-room whole-home optimiser
- one option per required room
- protected reserve
- room policies / must-not-compromise constraints
- homeowner locks
- optimisation cannot make a geometrically invalid option feasible

### Project orchestration / provenance
- multiple room-planner option artifacts can be merged
- global option-ID uniqueness
- strict room-ID linkage to verified geometry
- room coverage / missing-options inventory
- exact partial-home vs complete-home scope
- source artifact SHA-256 on selected room packages
- reproducible design-package manifest
- package SHA-256 self-check / tamper detection
- open professional-verification flags are carried through optimisation

### Standards / guidance evidence framework
- sourced numeric rule schema
- authority / jurisdiction / version / URL / checked timestamp / locator
- min / max / range / equality rules
- deterministic unit normalization
- PASS / FAIL / UNKNOWN / NOT APPLICABLE
- room/tag/jurisdiction applicability
- same-scope disjoint-rule conflict detection
- no bundled fake production standards corpus

### Lifecycle material value
- installed material + labour cost
- explicit material wastage
- maintenance cash flows
- service-life replacements
- disposal cost
- cost escalation
- NPV / equivalent annual cost
- residual service-value credit
- cost × performance Pareto comparison
- deterministic low/base/high sensitivity
- optional VERIFIED-evidence requirement
- missing lifecycle data remains unknown/non-feasible

### Privacy / zero-paid-cost guardrails
- explicit provider call cap
- declared estimated cost per call
- paid-use disable switch
- positive-cost calls blocked before execution when paid usage is disabled
- session usage ledger
- floor plan / home photo / quotation / verified geometry treated as sensitive
- external sensitive-artifact transfer disabled by default
- explicit consent gate
- metadata-only telemetry helper
- raw-content telemetry fields rejected
- explicit warning that app-side session limits do not replace provider-side account spending caps

### Zero-paid-rendering 3D
- polygon triangulation
- verified room floor meshes
- wall extrusion from explicit height
- optional ceilings
- parametric object boxes
- verified opening line overlays
- interactive Plotly 3D
- scene JSON export
- self-contained interactive HTML export
- visual material appearance clearly separated from physical/product evidence

### Final homeowner / contractor handoff
- hashed design-package validation
- optional standards/lifecycle attachments
- executive evidence audit
- open professional flags
- room-package/source SHA provenance
- safe HTML escaping
- deterministic report SHA-256
- print-friendly HTML
- browser Print → Save as PDF path

### QA / engineering discipline
- pytest deterministic-core coverage
- compile-all CI
- Python 3.11 / 3.12 core CI
- dedicated newer-page smoke workflows
- contracts documenting evidence/model boundaries

---

# Important unfinished work

## 1. Production-grade automatic floor-plan understanding
Still needed:
- robust dimension OCR with source bounding boxes/confidence
- stronger wall centerline/thickness extraction
- door/window/column/stair detection
- perspective/scan correction
- interactive drag-handle geometry editor
- real-world regression dataset across builder/CAD/scanned/photographed plans

## 2. Sourced standards corpus
The rule engine exists, but the project deliberately does **not** bundle unverified building/interior standards. Still needed:
- lawful source acquisition
- India/Norway/etc. version/jurisdiction tracking
- licensing review
- professional validation
- planner binding that retains rule IDs/source provenance

## 3. Sourced material-science corpus at scale
Still needed:
- manufacturer datasheet ingestion
- water absorption / density / thermal / UV / VOC / abrasion / chemical / fire / slip fields where applicable
- unit normalization
- source conflicts
- lifecycle/service-life evidence
- pack/module/slab constraints

## 4. Higher-fidelity kitchens
Still needed:
- plumbing/drain/gas/electrical service points
- appliance manufacturer clearances
- hood/duct/ventilation requirements
- corner-cabinet/module libraries
- slab nesting/seams
- arbitrary-polygon kitchen geometry

## 5. Higher-fidelity bedrooms / wardrobes
Still needed:
- bedside tables
- electrical/switch/socket/HVAC/window/radiator constraints
- TV sightline integration
- sliding/hinged wardrobe-door access
- internal wardrobe compartment optimisation
- storage-demand modelling

## 6. Higher-fidelity bathrooms
Still needed:
- plumbing stack/drain coordinates
- exact floor-drain position
- 2D slope field rather than one run
- shower-screen/door arcs
- wet-zone electrical rules
- manufacturer fixture clearances
- waterproofing system details

## 7. Live product inventory at public scale
Still needed:
- provider/retailer adapters with current lawful access
- stock state
- seller/delivery locality
- warranty extraction
- variant deduplication
- provider-wide quota accounting
- provider-side hard billing caps

## 8. 3D fidelity
Still needed:
- wall thickness / deduplicated shared walls
- actual door/window voids + heights
- planner-native furniture meshes
- cabinetry/sanitaryware parametric models
- verified product dimensions
- material textures
- IES lighting overlays
- daylight/solar overlays

## 9. Grounded AI / ML convenience layer
Still needed:
- inspiration-image/style embeddings
- preference learning
- grounded explanation layer driven only by deterministic/evidence outputs
- browser/local model evaluation
- no-LLM fallback explanations
- hallucination/evidence regression tests

## 10. Production deployment / privacy
Still needed:
- documented retention/deletion behavior for hosting
- provider/account hard quota controls
- shared public-scale quota ledger if needed
- security/performance/mobile/accessibility review
- privacy policy
- production monitoring that excludes raw home content

---

# Current product truth

NitiKube is now a **substantial deterministic Interior DesignOS engineering foundation**, not merely an AI room-rendering prototype.

It can already reason across:

```text
verified geometry
→ room candidate generation
→ lighting / physics / quantities
→ material / product evidence
→ budget / lifecycle / constraints
→ cross-room optimisation
→ provenance package
→ 3D visualization
→ final evidence report
```

But a truthful production claim is still:

> NitiKube can automate and audit a large portion of residential interior planning and decision engineering, while regulated/safety-critical work and incomplete evidence remain explicitly flagged for professional or source verification.

The remaining roadmap is about turning this foundation into a robust one-click whole-home product without sacrificing that evidence contract.
