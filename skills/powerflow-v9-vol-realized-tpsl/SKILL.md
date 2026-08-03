---
name: powerflow-v9-vol-realized-tpsl
description: Use when working on Phase 130 L13 (adaptive TP/SL by realized volatility).
trigger: "Phase 130 L13, vol realized TP SL, volatility adaptive, spike calm"
category: powerflow-v9
---

# PowerFlow V9 — L13 Adaptive TP/SL by Realized Volatility (Phase 130)

Filtre additif qui module les TP/SL adaptatifs selon la volatilité réalisée
des 5 dernières bougies M5 vs moyenne 20 bougies. Sprint CEO 03/08/2026.

## Kill switch

- `V9_HEATMAP_L13_VOL_REALIZED_TP_SL_ENABLED=1` (motion CEO 03/08 active)

## Module

`core/v9/v9_vol_realized_tp_sl.py` (NEW Phase 130).

API :
- `vol_realized_tp_sl_enabled() -> bool`
- `compute_realized_vol_ratio(recent_ranges, lookback=20) -> float`
- `compute_tp_sl_multipliers(vol_ratio) -> tuple[float, float]`
- `adapt_tp_sl_by_volatility(tp_base, sl_base, recent_ranges) -> dict`

## Logique

| Régime vol | Ratio | TP mult | SL mult | Levier |
|---|---|---|---|---|
| spike | ratio >= 2.0 | ×1.5 | ×1.5 | `L13_vol_spike_x1.5` |
| calme | ratio <= 0.5 | ×0.7 | ×0.7 | `L13_vol_calm_x0.7` |
| normal | 0.5 < ratio < 2.0 | ×1.0 | ×1.0 | (pass-through) |

Bornes strictes : TP et SL dans [0.7, 1.5].

## Gain projeté

50-100 pips (capture des spikes vol sans casser le RR cible).

## Tests

`tests/test_v9_vol_realized_tp_sl.py` : 14/14 verts (kill switch ON/OFF,
spike/calm/normal, R6 fail-open empty/zero/insufficient, bornes strictes,
compute ratio basique, signature accesseur, arrondi 2 décimales).

## Doctrine

- R2 additif (NEW module, 0 modif core/ partagé)
- R6 fail-open (recent_ranges vide/zero/insufficient → 1.0)
- R7 tests verts (14/14 ajoutes, baseline 103 préservée)
- R14 git vérité (audit SQL réel à venir post-activation)
- R22 sous-unité unique (1 module + 1 test + 1 commit)
- R25' motion CEO explicite (kill switch ON par motion CEO 03/08)
- R28 Hermes git unique