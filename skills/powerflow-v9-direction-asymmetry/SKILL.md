---
name: powerflow-v9-direction-asymmetry
description: Use when working on Phase 129 L16 (direction WR asymmetry ×1.3/×0.7).
trigger: "Phase 129 L16, direction asymmetry, haussier baissier sizing"
category: powerflow-v9
---

# PowerFlow V9 — L16 Direction Asymmetry (Phase 129)

Asymétrie WR par direction dans le sizing. Sprint CEO 03/08/2026.

## Kill switch

- `V9_HEATMAP_L16_ASYMMETRY_DIRECTION_ENABLED=0` (défaut OFF, R25' strict)

## Module

`core/v9/v9_direction_asymmetry.py` (NEW Phase 129).

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

`tests/test_v9_direction_asymmetry.py` : 5+ tests (kill switch ON/OFF,
×1.3/×0.7, exceptions régime RETOUR_EQUILIBRE/CASSURE, R6 fail-open).

## Doctrine

- R2 additif (0 modif core/ partagé)
- R6 fail-open (direction inconnue → 1.0)
- R7 tests verts (5+ verts obligatoires)
- R14 git vérité (audit SQL réel)
- R22 sous-unité unique
- R25' motion CEO explicite
- R28 Hermes git unique

## Statut

🚧 **À LIVRER** par ZCode (chantier git-indépendant C2 du ROADMAP V3).