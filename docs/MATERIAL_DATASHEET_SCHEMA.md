# NitiKube Material Datasheet Evidence Contract

NitiKube's material database is deliberately **evidence-first**. A material property is not accepted as a verified fact merely because it appears in a model response, retailer description, spreadsheet or user note.

## Core rule

> **No production material value without an evidence state. No verified numeric value without provenance.**

The supported evidence states are:

- `verified` — the observation has a source URL/document reference and a checked timestamp.
- `user_provided` — the homeowner/designer explicitly supplied the value. It may be used as an input, but must not be presented as an independently verified external fact.
- `unverified` — stored for review, but cannot drive a verified recommendation.
- `subjective` — aesthetic/descriptive information rather than an engineering fact.

## Structured JSON bundle

```json
{
  "material_id": "manufacturer-product-id",
  "material_name": "Product name",
  "category": "flooring",
  "aliases": ["optional alias"],
  "sources": [
    {
      "document_id": "manufacturer-datasheet-v3",
      "title": "Technical Datasheet",
      "manufacturer": "Manufacturer",
      "product_name": "Product name",
      "source_url": "https://manufacturer.example/datasheet.pdf",
      "document_version": "v3 / date",
      "checked_at": "2026-08-11T12:00:00+00:00"
    }
  ],
  "observations": [
    {
      "property_name": "water absorption",
      "value": 0.5,
      "unit": "%",
      "source_document_id": "manufacturer-datasheet-v3",
      "state": "verified",
      "note": "Optional source-page/section note"
    }
  ],
  "notes": []
}
```

Observation-level `source_url` and `checked_at` may override/inherit source-document metadata. Every observation must identify its `source_document_id`.

## CSV ingestion

The zero-cost CSV importer intentionally performs **no semantic column guessing**.

Required columns:

```text
property_name,value,unit,source_document_id
```

Optional columns:

```text
state,source_url,checked_at,note
```

## Canonical property vocabulary

The first supported normalized properties are:

| Property | Canonical unit | Examples of aliases |
|---|---|---|
| `thermal_conductivity` | `W/(m·K)` | thermal conductivity, k-value, lambda |
| `density` | `kg/m³` | bulk density, mass density |
| `specific_heat` | `J/(kg·K)` | specific heat capacity |
| `water_absorption` | `%` | water absorption percent |
| `voc` | `g/L` | VOC content |
| `thickness` | `mm` | nominal thickness |
| `service_life` | `year` | design life, expected life |
| `slip_resistance` | source classification/unit | slip rating, COF |
| `fire_rating` | source classification | reaction to fire |
| `uv_resistance` | source classification | ultraviolet resistance |
| `chemical_resistance` | source classification | chemical resistant |
| `abrasion_resistance` | source classification | wear resistance |

Unknown property names are preserved using a normalized snake-case name rather than discarded.

## Deterministic unit normalization

Where a canonical numeric unit exists, NitiKube converts only through explicit arithmetic rules. Examples:

```text
1.2 g/cm³       -> 1200 kg/m³
0.84 kJ/(kg·K)  -> 840 J/(kg·K)
0.05 fraction   -> 5 %
300 mg/L        -> 0.3 g/L
0.5 in          -> 12.7 mm
18 months       -> 1.5 year
```

An unsupported unit raises an error. NitiKube does **not** guess what the supplier meant.

## Multiple sources and conflicts

Observations for the same canonical property remain separate source observations. NitiKube does not silently average values.

If values agree within configured numerical tolerance, one observation can be selected using evidence-state priority. If values disagree beyond tolerance, the property is marked as a conflict and is omitted from the resolved material record until a source is explicitly chosen.

Example:

```text
Source A: water absorption = 0.5 %
Source B: water absorption = 3.0 %

Result: CONFLICT — no averaged value such as 1.75 % is created.
```

## Material suitability constraints

NitiKube's suitability engine can compare verified material properties against explicit design requirements such as:

```text
water_absorption <= user/sourced threshold
VOC <= user/sourced threshold
thermal_conductivity <= user/sourced threshold
```

The engine itself does not contain hidden regulatory thresholds. A threshold is either:

1. sourced, with URL + checked timestamp; or
2. explicitly a user/design-brief input.

Missing properties produce `unknown`, and a required `unknown` does **not** count as feasible.

## What this does not yet do

This ingestion layer does not yet automatically parse arbitrary PDFs/images or crawl manufacturer websites. That later extraction layer must preserve source-document location, page/section evidence and confidence, and extracted values must remain proposals until validated. This design prevents OCR/LLM extraction errors from silently becoming engineering facts.
