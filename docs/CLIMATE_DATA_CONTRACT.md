# NitiKube Climate / Geography Data Contract

NitiKube must make geography change design calculations through **measured/modelled climate variables**, not through hardcoded rules such as `if city == "Shimla": use wood`.

## Current data path

The live historical adapter uses Open-Meteo's Historical Weather API:

- Documentation: `https://open-meteo.com/en/docs/historical-weather-api`
- Endpoint: `https://archive-api.open-meteo.com/v1/archive`
- Default dataset requested by NitiKube: `era5_land`
- Alternative exposed in the current UI: `era5`

Open-Meteo documents the Historical Weather API as a reanalysis source intended for long-term consistency. ERA5-Land is available from 1950 at roughly 0.1° spatial resolution; ERA5 is available from 1940 at roughly 0.25° resolution. Reanalysis is **not the same as a weather-station measurement at the user's exact building**.

The current daily variables requested are:

```text
temperature_2m_mean
temperature_2m_max
temperature_2m_min
precipitation_sum
shortwave_radiation_sum
wind_speed_10m_max
```

Long-term relative humidity is deliberately not fabricated. The historical comparison leaves that part of the profile empty until a suitably efficient daily humidity source/aggregation path is connected.

## Provider metadata retained

Every live historical dataset carries:

```text
provider
dataset/model
latitude
longitude
provider elevation
timezone
start date
end date
checked timestamp
source documentation URL
```

This allows any downstream recommendation to explain exactly which climate dataset was used.

## Thresholds are explicit design inputs

The climate engine counts exposure only against visible thresholds supplied in the design scenario, for example:

```text
hot day: daily maximum >= threshold °C
cold day: daily minimum <= threshold °C
heavy-rain day: precipitation >= threshold mm
high-solar day: shortwave radiation >= threshold MJ/m²
```

These thresholds are **not hidden NitiKube building standards**. The UI exposes them and labels them as scenario inputs. A later standards engine may supply sourced thresholds, but it must carry provenance and jurisdiction/version metadata.

## Degree days

Heating and cooling degree-day bases are also explicit inputs.

For each day with mean temperature `T`:

```text
HDD = max(0, heating_base - T)
CDD = max(0, T - cooling_base)
```

The time-series totals are annualized to allow periods of different lengths to be compared. NitiKube does not pretend that a degree-day result is itself a complete HVAC load calculation.

## Geography comparison

Two locations are compared using the same:

- historical period,
- climate dataset,
- user/design thresholds,
- heating/cooling degree-day bases.

That means a Delhi/Shimla comparison is produced from the retrieved time series rather than a city-name lookup table. If the retrieved data does not differ, NitiKube must not force a difference merely because the city names are different.

## From climate metrics to design

The current engine generates **design pressures**, not direct material prescriptions.

Examples:

- repeated high-heat exposure -> check solar control, glazing, shading, ventilation and cooling load;
- repeated cold exposure -> check insulation, thermal bridging, glazing and heating load;
- heavy-rain exposure -> check waterproofing, drainage, exterior finishes and opening protection;
- high solar exposure -> check orientation-specific shading, solar heat gain and UV resistance.

The next material engine must then evaluate candidate products against sourced material properties. It may not jump directly from `rainy location` to an unsourced material recommendation.

## Site-level limitations

A gridded climate model cannot capture every building-specific effect. NitiKube must keep visible that local conditions can differ because of:

- elevation mismatch;
- slope/aspect;
- dense urban heat-island effects;
- neighbouring buildings and shade;
- trees/vegetation;
- local drainage and flooding;
- wind shielding/channelling;
- construction quality and existing moisture paths.

These become additional site inputs as the product matures.

## Zero-cost/provider rule

Open-Meteo is an external adapter, not a permanent dependency contract. Provider availability, free-tier/licensing terms and endpoints can change. NitiKube's science layer therefore consumes normalized climate records and can be fed by:

1. a replaceable live adapter;
2. a user-provided climate CSV;
3. a future self-hosted/open dataset pipeline.

If an external provider fails or exceeds the configured free-use policy, NitiKube must degrade gracefully rather than generating synthetic climate facts or silently incurring a paid API bill.
