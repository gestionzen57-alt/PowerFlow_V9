---
name: powerflow-v9-correlation-filter
description: Use when working on Phase 128 L12 (inter-pair correlation × regime filter).
trigger: "Phase 128 L12, correlation filter, inter-pair, regime correlation"
category: powerflow-v9
---

# PowerFlow V9 — L12 Correlation Filter (Phase 128)

Filtre corrélation inter-paires × régime. Sprint CEO 03/08/2026.

## Kill switch

- `V9_HEATMAP_L12_CORRELATION_REGIME_ENABLED=0` (défaut OFF, R25' strict)

## Module

`core/v9/v9_correlation_filter.py` (NEW Phase 128).

API :
- `correlation_filter_enabled() -> bool`
- `evaluate_correlation_filter(symbol, regime, open_positions, correlation_matrix) -> dict`

## Logique

- Si `correlation(symbol, open_pos.symbol) > V9_L12_CORR_THRESHOLD` (défaut 0.7)
  ET `regime(open_pos) == regime(symbol)` → `sizing_multiplier = 0.5`
- Si 2+ positions déjà ouvertes sur paires corrélées (même régime) → `go = False`
- Sinon pass-through (sizing = 1.0).

## Gain projeté

80-150 pips (réduction exposition sur fenêtres corrélées).

## Tests

`tests/test_v9_correlation_filter.py` : 5+ tests (corrélation haute/basse,
régime matching/non-matching, kill switch ON/OFF, R6 fail-open).

## Doctrine

- R2 additif (0 modif core/ partagé)
- R6 fail-open (correlation_matrix=None → pass-through)
- R7 tests verts (5+ verts obligatoires)
- R14 git vérité (audit SQL réel)
- R22 sous-unité unique
- R25' motion CEO explicite
- R28 Hermes git unique

## Statut

🚧 **À LIVRER** par ZCode (chantier git-indépendant C1 du ROADMAP V3).