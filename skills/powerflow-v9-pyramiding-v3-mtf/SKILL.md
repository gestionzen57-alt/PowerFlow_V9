---
name: powerflow-v9-pyramiding-v3-mtf
description: Use when working on Phase 133 L17 (multi-timeframe boost PyramidingEngine V3).
trigger: "Phase 133 L17, pyramiding V3, MTF boost, multi-timeframe"
category: powerflow-v9
---

# PowerFlow V9 — L17 Pyramiding Engine V3 (Phase 133)

Extension V3 du PyramidingEngine qui ajoute un boost multi-timeframe (MTF)
lorsque ≥3 timeframes sont alignés.

## Kill switch

- `V9_PYRAMIDING_V3_MTF_BOOST_ENABLED=0` (motion CEO à valider)

## Module

`core/v9/v9_pyramiding_engine_v3.py` (NEW Phase 133).

API :
- `pyramiding_v3_mtf_boost_enabled() -> bool`
- `evaluate_mtf_boost(aligned_timeframes, min_timeframes=3) -> dict`
- `PyramidingEngineV3(PyramidingEngineV2)` : hérite de V2
- `e.evaluate_v3(signal, aligned_timeframes, context)` : composition V2 × MTF

## Logique

Composition multiplicative : `final = V2_multiplier × MTF_multiplier`

| V2 stars_level | MTF boost | final | Leviers |
|---|---|---|---|
| base | pass-through | ×1.0 | (aucun) |
| stars (×1.3) | ×1.2 (3+ TF) | ×1.56 | STARS + L17 MTF |
| super_stars (×1.5) | ×1.2 (3+ TF) | ×1.80 | SUPER_STARS + L17 MTF |

## Gain projeté

30-60 pips (extension V2 stars/super_stars × MTF).

## Tests

`tests/test_v9_pyramiding_engine_v3.py` : 13/13 verts (version, constants,
3/5/2/empty TF, dédup, inherit V2, no MTF, with MTF boost, composition
cumulative, combo label, kill switch accessor).

## Doctrine

- R2 additif (NEW module, hérite de V2 sans le modifier)
- R6 fail-open (aligned_timeframes=None/empty → multiplier 1.0)
- R7 tests verts (13/13 ajoutés)
- R14 git vérité (audit SQL à venir post-activation)
- R22 sous-unité unique
- R25' motion CEO explicite
- R28 Hermes git unique