---
name: powerflow-v9-direction-asymmetry
description: Use when working on Phase 129 L16 (direction WR asymmetry ×1.3 haussier / ×0.7 baissier).
trigger: "Phase 129 L16, direction asymmetry, haussier baissier sizing, ZCode C2"
category: powerflow-v9
---

# PowerFlow V9 — L16 Direction Asymmetry (Phase 129)

Asymétrie WR par direction dans le sizing. Sprint CEO 03/08/2026 (livré ZCode C2).

## Kill switch

- `V9_HEATMAP_L16_ASYMMETRY_DIRECTION_ENABLED=1` (motion CEO 03/08 active)

## Module

`core/v9/v9_direction_asymmetry.py` (NEW Phase 129, livré par ZCode C2).

API :
- `direction_asymmetry_enabled() -> bool`
- `compute_asymmetry_multiplier(direction, regime=None) -> float`
- `apply_direction_asymmetry(sizing_base, direction, regime=None) -> dict`

## Logique

| Direction | Régime | Multiplicateur |
|---|---|---|
| haussière | (tout sauf RETOUR_EQUILIBRE) | ×1.3 |
| haussière | RETOUR_EQUILIBRE | ×1.0 |
| baissière | (tout sauf CASSURE) | ×0.7 |
| baissière | CASSURE | ×1.0 (edge baissier confirmé) |
| autre | — | ×1.0 |

Si kill switch OFF → multiplier = 1.0 systématique.

## Gain projeté

100-250 pips (amplification edge haussier dominant, atténuation edge
baissier structurellement plus faible).

## Tests

`tests/test_v9_direction_asymmetry.py` : 16/16 verts (kill switch ON/OFF,
×1.3/×0.7, exceptions régime RETOUR_EQUILIBRE/CASSURE, R6 fail-open).

## Doctrine

- R2 additif (NEW module, 0 modif core/ partagé)
- R6 fail-open (direction inconnue → 1.0)
- R7 tests verts (16/16 ajoutés)
- R14 git vérité (audit SQL réel)
- R22 sous-unité unique
- R25' motion CEO explicite
- R28 Hermes git unique (ZCode livraison C2)