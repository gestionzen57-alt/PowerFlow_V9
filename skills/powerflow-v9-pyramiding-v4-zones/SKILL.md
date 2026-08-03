---
name: powerflow-v9-pyramiding-v4-zones
description: Use when working on Phase 136 V4 (zones_state boost, naissance/2e_jambe/retest/range).
trigger: "Phase 136 V4, zones_state boost, pyramiding V4, Hermes2 H2-1"
category: powerflow-v9
---

# PowerFlow V9 — V4 Pyramiding zones_state boost (Phase 136)

Extension V4 du PyramidingEngine qui ajoute un boost selon l'état de la zone
(naisance/2e_jambe/retest/range). Sprint CEO 03/08+1 (V4, livré Hermes2 H2-1).

## Kill switch

- `V9_PYRAMIDING_V4_ZONES_STATE_ENABLED=1` (motion CEO 03/08 active)

## Module

`core/v9/v9_pyramiding_engine_v4.py` (NEW Phase 136, livré par Hermes2 H2-1, 204 LOC).

API :
- `pyramiding_v4_zones_state_enabled() -> bool`
- `compute_zones_state_multiplier(zone_state) -> float`
- `PyramidingEngineV4(PyramidingEngineV3)` : hérite de V3 (STARS + MTF)
- `e.evaluate_v4(signal, aligned_timeframes, zone_state, context)` : composition V2 × V3 × V4

## Mapping zone_state DB → catégorie V4

| Zone state DB | Catégorie V4 | Multiplicateur |
|---|---|---|
| EARLY_EXTREME | naissance | ×1.2 |
| ACCUMULATING | 2e_jambe | ×1.1 |
| RUPTURE | retest | ×1.0 (pass-through) |
| (range) | range | ×0.8 |
| inconnu | autre | ×1.0 (R6 fail-open) |

## Composition multiplicative

`final = V2_base × V3_MTF × V4_zones_state`

## Gain projeté

50-100 pips (extension V3 + zones_state).

## Tests

`tests/test_v9_pyramiding_engine_v4.py` : 19/19 verts.

## Doctrine

- R2 additif (NEW module, hérite V3 sans le modifier)
- R6 fail-open (zone_state inconnu/None → 1.0)
- R7 tests verts (19/19 ajoutés)
- R14 git vérité (audit SQL réel)
- R22 sous-unité unique
- R25' motion CEO explicite
- R28 Hermes2 git unique (push autorisé)