# NitiKube v0.23 — Whole-Home Candidate Factory

This milestone connects verified geometry directly to the existing deterministic room planners and whole-home optimizer.

## Shipped

- room-aware brief template generated from verified geometry
- deterministic room-role inference with explicit override and ambiguous-name fail-closed behavior
- exact rectangular-room validation; no bounding-box substitution for unsupported polygons
- verified door/opening → explicit inward keepout conversion
- automatic dispatch to drawing/dining, kitchen, bedroom/wardrobe and bathroom planners
- unified candidate audit across rooms
- globally unique room option IDs
- explicit cost model based only on fixed cost + produced geometry metrics × supplied rates
- explicit decision-score requirement before optimizer promotion
- opt-in geometry-score blending with provenance in `score_source`
- direct whole-home optimization when every required room is optimizer-ready
- direct generation of the existing hashed `nitikube.design_package`
- room option / factory audit / design package downloads
- Streamlit page 24
- deterministic tests and dedicated CI smoke workflow

## Deliberately not invented

The factory does not invent furniture dimensions, prices, scores, budgets, opening clearances or professional standards. The generated room-aware template leaves unknown values null.

## Next

The strongest next engineering target is arbitrary-polygon + service-point-aware planning so the same candidate-factory contract can operate on more realistic homes without falling back to rectangular approximations.
