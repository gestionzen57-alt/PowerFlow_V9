---
name: powerflow-v9-adaptive-dd-tracker
description: Use when working on Phase 137 Adaptive DD Tracker (vol × regime × session).
trigger: "Phase 137 adaptive DD, drawdown tracker, vol regime session, Hermes2 H2-2"
category: powerflow-v9
---

# PowerFlow V9 — Adaptive DD Tracker (Phase 137)

Tracker Drawdown adaptatif par contexte (vol × regime × session). Sprint CEO
03/08+1 (V4, livré Hermes2 H2-2).

## Kill switch

- `V9_ADAPTIVE_DD_TRACKER_ENABLED=1` (motion CEO 03/08 active)

## Module

`core/v9/v9_adaptive_dd_tracker.py` (NEW Phase 137, livré par Hermes2 H2-2).

API :
- `adaptive_dd_tracker_enabled() -> bool`
- `compute_adaptive_dd_threshold(dd_base, vol_ratio, regime, session) -> dict`
- `track_drawdown(dd_current, vol_ratio, regime, session, dd_base) -> dict`

## Logique adaptative

`dd_threshold = DD_BASE × vol_mult × regime_mult × session_mult`

| Contexte | Multiplicateur |
|---|---|
| Vol spike (ratio ≥ 2.0) | ×1.5 (bruit normal) |
| Vol calme (ratio ≤ 0.5) | ×0.7 (DD suspect) |
| Regime CASSURE | ×1.2 (volatilité structurelle) |
| Regime RETOUR_EQUILIBRE | ×0.8 |
| Session asie (liquidité basse) | ×0.5 |
| Session overlap/london | ×1.0 |

## Gain projeté

80-150 pips (réduction faux positifs HALT par contexte).

## Doctrine

- R2 additif (NEW module, 0 modif core/ partagé)
- R6 fail-open (kill switch OFF, données absentes → 1.0)
- R7 tests verts
- R14 git vérité
- R22 sous-unité unique
- R25' motion CEO explicite
- R28 Hermes2 git unique