# NitiKube AI — Current Build Status

**Product:** NitiKube AI / Interior DesignOS  
**Core rule:** **No recommendation without reasoning.**  
**Current capability milestone:** **v0.30 — verified-network whole-home planning + routed drainage/electrical engineering layers**.

This file is deliberately conservative. **Implemented** means deterministic code, evidence contracts and tests exist in this repository. It does **not** mean every module is production-certified or that NitiKube can replace licensed architects, structural engineers, MEP engineers, electricians, plumbers or other regulated professionals.

---

# 1. Current architecture

```text
floor plan / verified dimensions / homeowner brief / location / budget
                                  │
                                  ▼
                          VERIFICATION GATE
                                  │
                                  ▼
                         VERIFIED GEOMETRY
                                  │
          ┌───────────────────────┼────────────────────────┐
          ▼                       ▼                        ▼
  room candidate generation   openings/keepouts     service evidence
          │                       │                        │
          └───────────────┬───────┴───────────────┬────────┘
                          ▼                       ▼
                    GEOMETRY GATE        VERIFIED SERVICE NETWORK
                          │               walls / shafts / risers
                          │                       │
                          └──────────────┬────────┘
                                         ▼
                           CANDIDATE SERVICE GATE
                                         │
                 ┌───────────────────────┼───────────────────────┐
                 ▼                       ▼                       ▼
          drainage profile        electrical route        other future MEP
          fall / slope            voltage drop/loss       discipline checks
                 │                       │                       │
                 └───────────────────────┼───────────────────────┘
                                         ▼
                             EXPLICIT COST + SCORES
                                         │
                                         ▼
                            WHOLE-HOME OPTIMISATION
                                         │
                 ┌───────────────────────┼───────────────────────┐
                 ▼                       ▼                       ▼
               BOQ                  PROCUREMENT                 3D
                 │                       │                       │
                 └───────────────────────┼───────────────────────┘
                                         ▼
                              HASHED DESIGN PACKAGE
                                         │
                                         ▼
                                FINAL DESIGN REPORT
```

The system increasingly separates five different questions that conventional AI interior tools often mix together:

1. **What geometry is actually verified?**
2. **Which layouts physically fit?**
3. **Can required services actually reach the proposed fixture/appliance through verified building routes?**
4. **Do discipline-specific calculations pass the explicit sourced engineering inputs?**
5. **Which surviving design is preferable under budget and homeowner priorities?**

---

# 2. Verified floor-plan / geometry foundation

Implemented:

- OpenCV floor-plan line/region proposal baseline;
- verification-first CV semantics;
- pixel → physical scale calibration;
- multi-reference scale disagreement checks;
- verified room polygons;
- verified openings;
- room-region proposals;
- room adjacency / topology primitives;
- polygon area / centroid maths;
- SVG verified-geometry export;
- rectangle-support checks that refuse unsupported irregular geometry rather than silently replacing it with a bounding box;
- opening-to-room boundary linkage.

Still not production-complete:

- robust dimension OCR with source bounding boxes/confidence;
- wall centreline/thickness extraction;
- door/window/column/stair detection at production accuracy;
- perspective correction for photographed plans;
- interactive drag-handle correction workflow;
- large real-world regression set across CAD, builder plans, scans and camera photos.

---

# 3. Lighting / photometry

Implemented:

- lumen method;
- maintained lux calculations;
- COB beam-diameter geometry;
- 36° COB analysis;
- fixture-grid generation;
- constrained fixture optimisation;
- Type-C IES point-by-point subset;
- point-grid illuminance metrics;
- heatmap-ready illuminance data;
- fail-closed unsupported photometric cases.

Important boundary:

A beam angle or lumen number is not treated as sufficient evidence for a complete photometric design when the fixture distribution/IES data required by the selected model are absent.

---

# 4. Deterministic room planners

## Drawing / dining

Implemented:

- deterministic furniture geometry;
- living/dining zoning;
- sofa / TV-console arrangements;
- coffee-table placement;
- dining-table orientation alternatives;
- collision checks;
- keepouts;
- pair gaps;
- circulation grid metrics;
- geometry-only score.

## Kitchen

Implemented:

- one-wall families;
- galley families;
- L-shape families;
- U-shape families;
- counter-run geometry;
- sink / hob / fridge work centres;
- explicit work-triangle calculations;
- opening / keepout collision checks;
- passage connectivity;
- countertop union area;
- cabinet/countertop quantity envelopes;
- deterministic SVG output.

Still needed:

- arbitrary-polygon kitchen planning;
- manufacturer appliance clearances;
- corner-module libraries;
- detailed cabinetry modules;
- slab nesting / seam optimisation;
- discipline-specific kitchen plumbing/gas/electrical/ventilation rules.

## Bedroom / wardrobe

Implemented:

- bed wall alternatives;
- wardrobe wall alternatives;
- optional desk alternatives;
- side / foot clearance zones;
- wardrobe-front access zone;
- furniture collisions;
- opening keepouts;
- circulation connectivity;
- wardrobe front area / volume quantities;
- deterministic geometry scoring.

Still needed:

- bedside-table systems;
- internal wardrobe compartment optimisation;
- storage-demand modelling;
- TV sightline integration;
- HVAC/radiator/socket/switch constraints;
- sliding/hinged wardrobe-door kinematics.

## Bathroom

Implemented:

- shower corner alternatives;
- WC and basin wall alternatives;
- fixture-front clearance zones;
- collision/keepout checks;
- circulation metrics;
- floor/wall tile quantities;
- waterproofing quantity envelopes;
- ACH → CFM arithmetic;
- simple drainage run → fall arithmetic;
- deterministic SVG output.

Still needed:

- arbitrary-polygon bathroom planning;
- shower-screen / door-swing geometry;
- detailed wet-zone electrical rules;
- manufacturer fixture clearances;
- waterproofing system details;
- plumbing stack and route-aware fixture generation.

---

# 5. Geometry / circulation / ergonomics primitives

Implemented:

- axis-aligned rectangle maths;
- polygon shoelace area;
- rectangle containment;
- overlap/collision checks;
- shortest rectangle gap;
- opening keepouts;
- rasterised passage-width connectivity;
- obstacle inflation / Minkowski-style passage approximation;
- furniture-fit reasoning;
- drawing/dining and room-specific geometry metrics.

These metrics are geometry diagnostics. They are not silently labelled as building-code compliance.

---

# 6. Climate / geography / building physics

Implemented foundation includes:

- climate adapter architecture;
- historical/current climate variable interfaces;
- dew-point / condensation checks;
- R-value / U-value arithmetic;
- conductive heat-flow maths;
- solar geometry / shadow diagnostics;
- first-order acoustics / RT60;
- electrical resistance / load / energy / voltage-drop arithmetic primitives;
- explicit safety/model-boundary warnings.

The system does not ship fake geography-specific standards simply because a city name is known.

---

# 7. Materials / product / procurement evidence

Implemented:

- material evidence states;
- material provenance model;
- material suitability/conflict primitives;
- specification-first product query building;
- deterministic specification matching;
- required-but-unknown specifications are not treated as matches;
- verified price state requires source + timestamp;
- optional search-adapter / retailer-search architecture;
- locality-aware product lookup architecture;
- quantity-driven procurement linkage foundation.

Still needed at production scale:

- manufacturer datasheet ingestion;
- normalized material property corpus;
- water absorption / density / thermal / VOC / UV / abrasion / slip / fire fields where applicable;
- source conflict resolution;
- pack/slab/module constraints;
- live lawful retailer/provider adapters;
- current stock and local delivery state;
- warranty extraction;
- product variant deduplication;
- public-scale quota accounting.

---

# 8. Quantity / BOQ / quotation audit

Implemented:

- tile quantities;
- board/panel quantities;
- paint quantities;
- explicit wastage;
- BOQ primitives;
- CSV/XLSX quotation import;
- semantic column mapping;
- quantity × rate arithmetic audit;
- discrepancy states;
- insufficient-data states;
- downloadable audit outputs.

---

# 9. Budget / optimisation

Implemented:

- budget envelopes;
- protected reserve;
- weighted option utility;
- Pareto pruning;
- cross-room whole-home optimiser;
- one option per required room;
- room policies;
- must-not-compromise constraints;
- homeowner locks;
- required-room coverage checks;
- infeasible combination detection;
- deterministic scenario optimisation.

Critical invariant:

```text
geometry/service infeasible option
        cannot become feasible
        because its preference score is high
```

---

# 10. v0.23 — Whole-Home Candidate Factory

Implemented bridge from verified geometry to the full deterministic room-planning stack:

- parses authoritative `nitikube.verified_geometry`;
- deterministic room-role inference from explicit room names;
- explicit role override in brief;
- ambiguous/anonymous rooms remain unresolved;
- dispatches supported rooms to drawing/dining, kitchen, bedroom and bathroom planners;
- exact rectangle support checks;
- no hidden bounding-box substitution for unsupported polygons;
- verified opening keepouts;
- room candidate audits;
- globally unique option IDs;
- explicit cost models;
- explicit five-score promotion contract;
- required-room scope;
- direct whole-home optimisation;
- provenance-preserving design package;
- geometry + option artifact SHA-256.

Streamlit:

- **Page 24 — Whole-Home Candidate Factory**.

---

# 11. v0.24 — Verified Service Points + Straight-Line Routing

Implemented explicit service evidence for:

- cold water;
- hot water;
- drain;
- electrical;
- gas;
- exhaust;
- data;
- HVAC condensate;
- other service kinds.

Capabilities:

- room-linked XY and optional Z coordinates;
- verified state + source/note;
- service-point validation against verified room geometry;
- explicit service targets;
- allowed service kinds;
- required vs optional service requirements;
- plan / 3D distances;
- optional explicit maximum route distance;
- exact minimum-total-distance assignment when points cannot be shared;
- explicit shared-point mode;
- target adapters for kitchen, bathroom, bedroom and generic layouts.

This layer is retained as a simple lower-bound model but is no longer the strongest available routing model.

Streamlit:

- **Page 25 — Verified Service Points + Routing Lab**.

---

# 12. v0.25 — Service-Aware Candidate Feasibility

Implemented permanent hard-gate semantics:

```text
overall_feasible = geometry_feasible AND service_feasible
```

Capabilities:

- candidate-specific service rules;
- required/optional missing-target semantics;
- actual candidate target coordinates;
- service feasibility before preference ranking;
- service failures cannot be rescued by geometry score;
- geometry failures cannot be rescued by service success;
- route distance used only as transparent tie-break evidence, not hidden aesthetics/quality scoring.

Streamlit:

- **Page 26 — Service-Aware Candidate Lab**.

---

# 13. v0.26 — Service-Aware Whole-Home Factory

Implemented integration of service feasibility into the whole-home optimisation pipeline:

```text
verified geometry
+ explicit brief
+ verified service points
→ room candidates
→ geometry gate
→ service gate
→ optimizer options
→ whole-home optimisation
→ hashed design package
```

Capabilities:

- room service states: evaluated / not configured / blocked / base-room blocked;
- exact raw-candidate ID reconciliation before target recovery;
- service-filtered optimizer options;
- required-room viability gate;
- service-point SHA-256 provenance;
- service-aware brief SHA-256 provenance;
- v0.26 package re-hash.

Streamlit:

- **Page 27 — Service-Aware Whole-Home Candidate Factory**.

---

# 14. v0.27 — Verified Wall / Shaft / Riser Service Network

This replaces the strongest remaining weakness in v0.24–v0.26: conceptual straight-line routes through building fabric.

Implemented `nitikube.service_network` with:

- explicit network nodes;
- XY + optional Z coordinates;
- optional room linkage;
- route classes;
- target-access eligibility;
- verified/source/note provenance;
- service-kind-specific edges;
- directed or bidirectional edges;
- explicit surveyed edge-length override;
- explicit service-point → network-node attachment;
- graph validation;
- service-kind-compatible Dijkstra shortest path;
- plan / 3D routing;
- fail-closed missing-Z geometry-derived 3D paths;
- verified-only default;
- same-room target-access default;
- bounded target → access-node connector;
- exact multi-requirement assignment;
- downloadable network-routing evaluation.

Critical invariant:

```text
proximity does NOT create a route edge
```

A route can cross a wall, shaft, riser, sleeve or corridor only when an explicit verified graph edge represents that path.

Streamlit:

- **Page 28 — Verified Service Network**.

---

# 15. v0.28 — Verified-Network Whole-Home Factory

The v0.27 graph is now part of real candidate feasibility and whole-home optimisation.

Implemented:

- project-level network routing policy;
- room-level routing-policy overrides;
- explicit `max_target_access_ft` requirement for configured service rooms;
- default verified-network-only routing;
- default same-room target access;
- candidate-specific graph routing;
- `service_network_total_route_ft`;
- `service_network_max_route_ft`;
- `service_network_evaluated` feature;
- `service_network:` failure/warning provenance;
- required-room viability after routed-service filtering;
- optimisation only after graph-feasible options survive;
- service-network artifact SHA-256 in final package;
- network-aware brief SHA-256;
- package re-hash to v0.28.

Permanent rule:

```text
overall candidate feasible
    = geometry feasible
      AND configured verified-network service feasible
```

Streamlit:

- **Page 29 — Verified-Network Whole-Home Candidate Factory**.

---

# 16. v0.29 — Drainage Route Elevation + Slope Engineering

First discipline-specific engineering layer on top of the routed service graph.

Implemented:

- drainage profile brief;
- required numeric slope source provenance;
- target elevation checks;
- route-node elevation checks;
- segment plan run;
- segment fall in inches;
- segment slope percentage;
- total plan run;
- total end-to-end fall;
- average slope;
- minimum required fall from caller-supplied slope;
- fall margin;
- optional maximum slope;
- monotonic-fall checking;
- local-rise detection;
- vertical-drop semantics;
- PASS / FAIL / UNKNOWN / NOT APPLICABLE;
- artifact-level evaluation and export.

Math:

```text
fall_in = (z_start - z_end) × 12
slope_% = fall_in / (plan_run_ft × 12) × 100
required_fall_in = plan_run_ft × 12 × required_slope_% / 100
```

Evidence invariant:

```text
unsourced numeric drainage slope → rejected
missing elevation evidence → UNKNOWN, never PASS
```

Streamlit:

- **Page 30 — Drainage Route Elevation + Slope Lab**.

Not yet included:

- fixture-unit loading;
- pipe sizing;
- hydraulic capacity;
- traps/vents;
- cleanouts;
- stacks;
- plumbing-code certification.

---

# 17. v0.30 — Routed Electrical Voltage Drop + Conductor Loss

Second discipline-specific engineering layer on top of the verified routing graph.

Implemented circuit models:

### DC two-wire

```text
ΔV = 2 I L R
```

### Single-phase AC

```text
ΔV = 2 I L (R cosφ + X sinφ)
```

### Balanced three-phase AC

```text
ΔV = √3 I L (R cosφ + X sinφ)
```

Implemented:

- verified routed cable length;
- explicit slack fraction;
- sourced conductor resistance Ω/km;
- optional conductor reactance Ω/km;
- explicit AC power factor;
- optional resistance temperature adjustment;
- explicit parallel conductors per phase;
- voltage drop V;
- voltage drop %;
- receiving voltage;
- routed I²R copper loss;
- optional operating-hours energy loss;
- optional sourced maximum voltage-drop limit;
- PASS / FAIL / CALCULATED / UNKNOWN / NOT APPLICABLE.

Evidence invariants:

```text
conductor resistance without conductor_source_ref → rejected
voltage-drop limit without limit source → rejected
AC limit + missing reactance → UNKNOWN, not fake PASS/FAIL
```

Streamlit:

- **Page 31 — Routed Electrical Voltage Drop + Conductor Loss Lab**.

Not yet included:

- ampacity;
- conductor derating;
- protective-device selection;
- fault current;
- earth-fault loop impedance;
- earthing/bonding;
- short-circuit withstand;
- discrimination/selectivity;
- electrical-code certification.

---

# 18. Standards / guidance evidence framework

Implemented:

- sourced numeric rule schema;
- authority;
- jurisdiction;
- version;
- source URL;
- checked timestamp;
- clause/page/table locator;
- min / max / range / equality rules;
- deterministic unit normalization;
- PASS / FAIL / UNKNOWN / NOT APPLICABLE;
- room/tag/jurisdiction applicability;
- same-scope disjoint-rule conflict detection.

The repository deliberately does **not** ship a fake production standards corpus.

Still needed:

- lawful source acquisition;
- jurisdiction/version tracking;
- licensing review;
- professional validation;
- rule binding to planner outputs at scale.

---

# 19. Lifecycle material value

Implemented:

- installed material + labour cost;
- explicit wastage;
- maintenance cash flows;
- service-life replacements;
- disposal cost;
- escalation;
- discounting;
- residual service-value credit;
- NPV;
- equivalent annual cost;
- NPV per area;
- cost/performance Pareto comparison;
- deterministic sensitivity;
- optional verified-evidence requirement;
- missing lifecycle evidence stays unknown/non-feasible.

---

# 20. Privacy / zero-paid-cost guardrails

Implemented:

- provider-call cap;
- declared estimated cost/call;
- paid-use disable switch;
- positive-cost call blocked before execution when paid usage disabled;
- session usage ledger;
- floor plans / home photos / quotations / verified geometry treated as sensitive;
- external sensitive transfer disabled by default;
- explicit consent gate;
- metadata-only telemetry helper;
- raw-content telemetry fields rejected.

Important truth:

Application-side session limits alone cannot guarantee ₹0 account-wide usage for a public service. Provider-side hard spending/free-tier limits or a shared quota layer are still needed for a truthful public-scale zero-cost guarantee.

---

# 21. 3D / final handoff

## Verified-geometry 3D

Implemented:

- polygon triangulation;
- verified room floor meshes;
- wall extrusion from explicit height;
- optional ceilings;
- parametric object boxes;
- verified opening line overlays;
- Plotly 3D;
- scene JSON export;
- self-contained HTML export.

Still needed:

- wall thickness/shared-wall deduplication;
- actual door/window voids;
- door swings;
- planner-native furniture meshes;
- cabinetry/sanitaryware parametric models;
- verified product dimensions;
- material textures;
- IES lighting overlays;
- daylight overlays.

## Final report

Implemented:

- design-package hash validation;
- optional standards/lifecycle attachments;
- executive evidence audit;
- open professional flags;
- source SHA provenance;
- safe HTML escaping;
- deterministic report SHA-256;
- print-friendly HTML;
- browser Print → Save as PDF route.

---

# 22. QA / engineering discipline

Implemented across the project:

- deterministic pytest coverage;
- compile-all checks;
- Python 3.11 / 3.12 core CI where configured;
- dedicated page/workflow smoke tests for newer subsystems;
- fail-closed integration tests;
- regression tests for discovered bugs;
- explicit evidence/model-boundary contracts;
- source/provenance hashing for key artifacts.

The project has repeatedly caught integration regressions in CI before merge; fixes are made on the feature branch and the dedicated workflow rerun before merge.

---

# 23. Current Streamlit engineering pages added in the newer pipeline

```text
24  Whole-Home Candidate Factory
25  Verified Service Points + Routing
26  Service-Aware Candidate Lab
27  Service-Aware Whole-Home Candidate Factory
28  Verified Service Network
29  Verified-Network Whole-Home Candidate Factory
30  Drainage Route Elevation + Slope Lab
31  Routed Electrical Voltage Drop + Conductor Loss Lab
```

These sit alongside the earlier geometry, CV, lighting, materials, climate/physics, quotation, optimisation, guardrail, 3D and reporting pages.

---

# 24. Highest-priority unfinished engineering

## A. Production-grade floor-plan understanding

- robust OCR/dimension semantics;
- walls/thicknesses;
- doors/windows/columns/stairs;
- scan/perspective correction;
- interactive geometry editor;
- real-world regression corpus.

## B. Arbitrary-polygon room planning

Current room planners remain strongest for exact rectangular rooms. The next geometry frontier is native planning in verified irregular polygons without bounding-box substitution.

## C. Richer routing network

- automatic proposals from verified wall/shaft geometry, still requiring user verification;
- explicit penetrations/sleeves;
- wall thickness;
- shared shafts/risers;
- route capacity/occupancy;
- bend geometry;
- cross-floor routing;
- route cost/constructability.

## D. Drainage engineering beyond slope

- fixture load/units;
- branch/stack sizing;
- hydraulic capacity;
- traps/vents;
- cleanouts;
- sourced plumbing rules.

## E. Electrical engineering beyond voltage drop

- conductor ampacity;
- installation/ambient/grouping derating;
- protective-device coordination;
- fault current;
- earthing;
- thermal short-circuit checks;
- sourced jurisdiction rules.

## F. Ventilation / exhaust routing

- routed duct geometry;
- duct cross-section;
- velocity;
- equivalent length;
- bend/fitting losses;
- fan static-pressure requirement;
- noise constraints;
- sourced ventilation requirements.

## G. Sourced standards + material science

- lawful corpus acquisition;
- licensing;
- version/jurisdiction tracking;
- source conflict resolution;
- manufacturer data normalization;
- professional validation.

## H. Live product inventory / public-scale deployment

- lawful live providers;
- stock/delivery locality;
- warranty;
- price freshness;
- quotas;
- persistence/auth;
- deletion/retention policy;
- security/performance/accessibility/mobile review.

## I. Grounded AI / ML convenience layer

Still intentionally downstream of deterministic engineering:

- style/inspiration embeddings;
- preference learning;
- grounded explanation layer;
- local/browser model evaluation;
- no-LLM fallback;
- hallucination/evidence regression tests.

---

# 25. Current product truth

NitiKube is now a substantial deterministic **Interior DesignOS / residential decision-engineering foundation**.

It can already reason across:

```text
verified geometry
→ deterministic room candidates
→ opening/circulation constraints
→ verified service evidence
→ verified wall/shaft/riser routing
→ candidate service feasibility
→ routed drainage slope engineering
→ routed electrical voltage-drop/loss engineering
→ cost / preference / lifecycle constraints
→ whole-home optimisation
→ provenance package
→ BOQ / 3D / final report
```

The strongest truthful product claim remains:

> **NitiKube can automate and audit a growing portion of residential interior planning and engineering decision support while keeping missing evidence, unsupported geometry and regulated/safety-critical work explicitly visible instead of hallucinating certainty.**

It is not yet a production-certified replacement for licensed professionals on regulated scopes.

---

# 26. Strategic direction

The priority is not to turn NitiKube into an image generator.

The target is:

```text
floor plan + location + budget + household requirements + verified product/material evidence
                                    │
                                    ▼
                         evidence-backed candidate factory
                                    │
                                    ▼
                     geometry + physics + service engineering
                                    │
                                    ▼
                       whole-home constrained optimisation
                                    │
                                    ▼
                  procurement-ready, auditable design package
```

AI/ML/CV should accelerate input understanding, style preference learning, retrieval and explanation **without being allowed to overwrite the deterministic evidence gates**.
