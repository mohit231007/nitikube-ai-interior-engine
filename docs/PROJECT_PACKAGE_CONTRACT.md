# NitiKube Project Package / Orchestration Contract

NitiKube's room planners intentionally remain modular. A drawing/dining planner, kitchen planner, bedroom planner or bathroom planner can evolve independently as long as each emits a truthful optimizer-compatible room-option artifact.

The **Project Orchestrator** is the layer that combines those artifacts with authoritative verified geometry, runs cross-room budget optimisation, and emits one reproducible design-package manifest.

## Inputs

A project run consumes:

1. one `nitikube_verified_geometry.json` file;
2. one or more room-option JSON artifacts;
3. exact room scope for the run;
4. room policies / must-not-compromise constraints;
5. total budget and protected reserve;
6. explicit quality/durability/aesthetics/comfort/maintainability weights;
7. optional homeowner locks;
8. project-specific professional-verification flags.

The orchestrator does not silently invent a room option for a verified room with no candidate artifact.

## Artifact hashing

Every source artifact is represented by:

```text
name
kind
SHA-256
byte size
```

Each selected room option retains the SHA-256 of the option artifact that supplied it.

The geometry artifact is also hashed. This means a final package can identify the exact bytes of the geometry/options used by the run without embedding the raw floor-plan image or every source document in the final manifest.

## Room identity validation

Room-option artifacts must refer to `room_id` values present in authoritative verified geometry.

An unknown/orphan room ID is rejected. The orchestrator does not fuzzy-match room names such as `Master Bedroom`, `Bedroom 1` or `MBR` because doing so could bind calculations to the wrong geometry.

Room names are display labels; `room_id` is the authoritative join key.

## Coverage

For every verified room, the orchestrator reports:

```text
covered
missing_options
```

The user explicitly chooses `required_room_ids` for the optimisation run.

If not every verified room is included, the resulting artifact is a **partial-home design package**, not a complete-home design package. The package truthfully records that narrower room scope.

## Optimization

The orchestrator delegates room selection to the existing deterministic whole-home optimiser. It therefore inherits the same hard constraints:

- one selected candidate per required room;
- authoritative room geometry constraints;
- room-specific must-not-compromise policies;
- homeowner locks;
- budget;
- protected reserve;
- explicit ranking weights.

An infeasible optimisation result cannot be promoted into an approved design package.

## Professional-verification flags

Project-specific flags can be carried through the package, for example:

```text
structural wall modification requires structural engineer
bathroom waterproofing detail requires site/professional verification
major electrical service upgrade requires licensed verification
```

The orchestrator records these flags. Optimisation never clears or overrides them.

## Design package schema

The current package schema is:

```text
schema = nitikube.design_package
schema_version = 0.17
```

The manifest contains:

```text
project name
created timestamp
geometry artifact hash
room-option artifact hashes
required room IDs
homeowner locks
budget / reserve / spendable budget
selected cost / remaining budget
total utility
ranking weights
selected room options
selected-option source artifact + source SHA
professional-verification flags
package ID
```

## Package ID / integrity

The package ID is SHA-256 over a canonical JSON serialization of the manifest **before** the `package_id` field is added:

```text
package_id = SHA256(canonical_manifest_without_package_id)
```

`verify_design_package_hash()` recomputes that hash and can detect manifest tampering.

This is an **integrity/reproducibility mechanism**, not a truth certificate.

A valid package hash proves only that:

- the manifest has not changed since the hash was computed; and
- the recorded source-artifact hashes are part of the manifest that was hashed.

It does **not** prove that:

- a dimension was measured correctly;
- a retailer price remains current;
- a manufacturer property is accurate;
- a subjective score is appropriate;
- a professional-verification flag has been resolved.

Those truth/evidence questions remain governed by the originating NitiKube modules and evidence contracts.

## Reproducibility

When the same:

- input artifact bytes;
- room scope;
- policies;
- locks;
- budget/reserve;
- ranking weights;
- fixed `created_at` timestamp

are supplied, the canonical package manifest and `package_id` are deterministic.

A normal live run includes the current UTC creation timestamp, so a later re-run gets a new package ID unless the timestamp is fixed intentionally for reproducibility testing.

## Privacy

The final package carries hashes and selected structured results rather than requiring the raw uploaded floor-plan image to be embedded. Users must retain the referenced source artifacts if they want to reproduce/audit the package later.

A future persistent-project layer should provide explicit retention/deletion controls and encrypted/private storage. Hashing does not itself make sensitive data anonymous.

## Current boundary

The Project Orchestrator currently assembles room-option artifacts that have already been created by planners/evidence workflows. It does not yet automatically run every planner from one raw floor plan.

The next full-home workflow should progressively automate:

```text
floor plan
  → verified geometry
  → room classification/function
  → room-specific candidate generation
  → material/climate/product evidence
  → room packages
  → cross-room optimisation
  → BOQ/procurement/execution package
```

Each automated transition must preserve the same verification gates and provenance rather than converting the pipeline into one opaque AI call.
