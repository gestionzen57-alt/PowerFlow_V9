---
name: powerflow-v9-correlation-l12
description: Use when working on Phase 128 L12 (inter-pair correlation × regime filter).
trigger: "Phase 128 L12, correlation filter, inter-pair, regime correlation"
category: powerflow-v9
---

# PowerFlow V9 — L12 Correlation Filter (Phase 128)

Filtre corrélation inter-paires × régime. Sprint CEO 03/08/2026 (livré ZCode C1).

## Kill switch

- `V9_HEATMAP_L12_CORRELATION_REGIME_ENABLED=0` (motion CEO à valider)
- `V9_L12_CORR_THRESHOLD=0.7` (seuil corrélation)

## Module

`core/v9/v9_correlation_filter.py` (NEW Phase 128, livré par ZCode).

API :
- `correlation_filter_enabled() -> bool`
- `correlation_threshold() -> float`
- `get_correlation(sym1, sym2, correlation_matrix=None) -> float`
- `evaluate_correlation_filter(symbol, regime, open_positions, correlation_matrix=None) -> dict`

## Logique

- Si `correlation(symbol, open_pos.symbol) > V9_L12_CORR_THRESHOLD`
  ET `regime(open_pos) == regime(symbol)` → `sizing_multiplier = 0.5`
- Si 2+ positions déjà ouvertes sur paires corrélées (même régime) → `go = False`
- Sinon pass-through (sizing = 1.0).

## Audit SQL live (Phase 128, n=337 post-DROP)

- NEUTRE + 4 paires simultanées : n=218, WR=13.8%, PNL=-1163.8p (surexposition)
- EXTENSION + 2 paires simultanées : n=28, WR=32.1%, PNL=-118.0p
- RETOUR_EQUILIBRE + 2 paires simultanées : n=7, WR=0%, PNL=-53.4p

## Gain projeté

80-150 pips (réduction exposition sur fenêtres corrélées, ~50% sizing sur 5-10% trades).

## Tests

`tests/test_v9_correlation_filter.py` : 13/13 verts (kill switch OFF, no open
positions, 1 corrélée, 2+ corrélées, régimes différents, matrix None fail-open,
GBPUSD vs GBPUSD ignore, get_correlation miroir/same/unknown, threshold,
bad input).

## Doctrine

- R2 additif (0 modif core/ partagé)
- R6 fail-open (correlation_matrix=None → pass-through)
- R7 tests verts (13/13 ajoutes)
- R14 git vérité (audit SQL réel)
- R22 sous-unité unique
- R25' motion CEO explicite (kill switch défaut OFF, activation CEO)
- R28 Hermes git unique (ZCode livrée C1)