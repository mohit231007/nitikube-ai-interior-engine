# NitiKube v0.30 — Routed Electrical Voltage Drop + Losses

v0.30 adds the second discipline-specific engineering layer on top of the verified routing graph.

## New core

`nitikube/electrical_route.py` adds:

- DC two-wire voltage-drop arithmetic;
- single-phase AC R/X + power-factor voltage drop;
- balanced three-phase AC voltage drop;
- routed cable-length + explicit slack;
- optional resistance temperature adjustment;
- parallel-conductor adjustment;
- receiving voltage;
- routed I²R copper loss;
- optional energy-loss calculation;
- sourced voltage-drop limit evaluation;
- PASS / FAIL / CALCULATED / UNKNOWN / NOT APPLICABLE.

## Evidence rules

- conductor resistance requires `conductor_source_ref`;
- voltage-drop limit requires `voltage_drop_limit_source_ref`;
- AC limit evaluation remains UNKNOWN when reactance evidence is absent;
- no voltage/current/resistance/limit is prefilled in the template.

## UI

Page 31 — **Routed Electrical Voltage Drop + Conductor Loss Lab** — consumes the verified service network, network routing evaluation and electrical circuit/conductor brief, then exports an auditable evaluation artifact.

## Boundary

This is not ampacity, protection, earthing, fault-current or code-compliance engineering. Those remain future evidence-grounded layers.
