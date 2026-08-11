# NitiKube v0.30 — Routed Electrical Engineering Contract

## Purpose

v0.30 uses the verified service-network route length as the physical basis for transparent voltage-drop and conductor-loss arithmetic.

It does not select a cable automatically and it does not bundle hidden electrical-code thresholds.

## Input evidence

Each electrical route requirement identifies:

- routed electrical service requirement ID;
- circuit topology;
- nominal voltage;
- design current;
- conductor resistance per kilometre;
- conductor evidence source;
- optional conductor reactance per kilometre;
- power factor for AC calculations;
- parallel conductors per phase;
- explicit cable-length slack fraction;
- optional resistance temperature-adjustment evidence;
- optional voltage-drop limit plus its source;
- optional operating hours for energy-loss arithmetic.

## Route length

The one-way cable route length comes from `nitikube.network_routing_evaluation`:

```text
candidate electrical target
  → bounded access connector
  → compatible verified routing edges
  → attached electrical service point
```

Design cable length is:

\[
L_{design}=L_{route}(1+s)
\]

where `s` is an explicit slack fraction.

## Resistance temperature adjustment

When reference temperature, design conductor temperature and temperature coefficient are all supplied:

\[
R_T=R_{ref}[1+\alpha(T-T_{ref})]
\]

No temperature adjustment is silently invented when those inputs are absent.

Parallel conductors per phase reduce effective R and X by the supplied parallel count.

## Voltage drop

### Two-wire DC

\[
\Delta V=2ILR
\]

### Single-phase two-wire AC

\[
\Delta V=2IL(R\cos\phi+X\sin\phi)
\]

### Balanced three-phase AC

\[
\Delta V=\sqrt{3}IL(R\cos\phi+X\sin\phi)
\]

with `L` in kilometres and R/X in ohms per kilometre.

Percentage drop:

\[
\Delta V_{\%}=100\frac{\Delta V}{V_{nom}}
\]

## Copper loss

For the routed conductor resistance `R_line`:

Two-wire circuit:

\[
P_{loss}=2I^2R_{line}
\]

Balanced three-phase circuit:

\[
P_{loss}=3I^2R_{line}
\]

If operating hours are supplied:

\[
E_{loss,kWh}=\frac{P_{loss}\times h}{1000}
\]

## Evidence states

### CALCULATED

The arithmetic is available, but no voltage-drop limit was supplied.

### PASS / FAIL

Only produced when an explicit `max_voltage_drop_percent` and non-empty `voltage_drop_limit_source_ref` are supplied and the selected electrical model has the evidence required to make that comparison.

### UNKNOWN

Examples include:

- no routed assignment;
- routed assignment references edges/nodes absent from the supplied network;
- AC voltage-drop limit is supplied but conductor reactance evidence is absent.

For the last case NitiKube may display the resistive-only estimate, but it will not promote that estimate to PASS/FAIL.

### NOT APPLICABLE

The routed assignment is not electrical.

## No hidden conductor selection

A conductor resistance value must carry `conductor_source_ref`.

NitiKube does not infer a conductor cross-section, material, insulation system or permitted current from the design current in this layer.

## Model boundary

A voltage-drop PASS does **not** establish:

- conductor ampacity;
- ambient/grouping/installation derating;
- protective-device selection;
- overload/short-circuit protection;
- prospective fault current;
- earth-fault loop impedance;
- earthing/bonding adequacy;
- short-circuit thermal withstand;
- discrimination/selectivity;
- fire performance;
- local code compliance.

Those remain separate sourced electrical-engineering layers.
