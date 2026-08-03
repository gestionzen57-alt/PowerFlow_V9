---
name: powerflow-v9-regime-live-detector
description: Use when working on Phase 138 Regime Live Detector (DOW × regime × vol).
trigger: "Phase 138 regime live detector, DOW regime vol prediction, Hermes2 H2-3"
category: powerflow-v9
---

# PowerFlow V9 — Regime Live Detector (Phase 138)

Détecteur régime live combinant DOW + regime + volatilité pour prédire le
régime de la prochaine heure. Sprint CEO 03/08+1 (V4, livré Hermes2 H2-3).

## Kill switch

- `V9_REGIME_LIVE_DETECTOR_ENABLED=1` (motion CEO 03/08 active)

## Module

`core/v9/v9_regime_live_detector.py` (NEW Phase 138, livré par Hermes2 H2-3).

API :
- `regime_live_detector_enabled() -> bool`
- `predict_next_regime(current_regime, utc_hour, utc_dow, vol_ratio, symbol) -> dict`

## Logique

- **DOW** : mardi GBPUSD baissier, mercredi GBPUSD haussier (L11 DOW pattern)
- **Vol spike** → EXTENSION probable
- **Vol calme** → RETOUR_EQUILIBRE probable

## Gain projeté

40-80 pips (pré-décision adaptative).

## Doctrine

- R2 additif (NEW module, 0 modif core/ partagé)
- R6 fail-open (kill switch OFF, données absentes → 1.0)
- R7 tests verts
- R14 git vérité
- R22 sous-unité unique
- R25' motion CEO explicite
- R28 Hermes2 git unique