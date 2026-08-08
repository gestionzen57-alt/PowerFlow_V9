# Sprint 24 — Addendum scripts exécutables

## Scripts ajoutés le 2026-08-08

- `scripts/v10_rl_shadow_rerun.py` : re-run ciblé RL SHADOW sur `EURUSD` et `USDJPY`, 100 trades, calcul baseline/shadow WR, delta et gate 30 consécutifs.
- `scripts/v10_walkforward_30d.py` : validation walk-forward 30 jours sur `EURUSD M30`, calcul WR, n trades, avg pnl, proxy Sharpe, verdict GO/NO-GO.

## Rapports générés

- `reports/v10_rl_shadow_rerun_YYYYMMDD_HHMMSS.json`
- `reports/v10_walkforward_30d_EURUSD_M30_YYYYMMDD_HHMMSS.json`
