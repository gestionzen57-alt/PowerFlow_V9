# CHANGELOG — PowerFlow V10

Format: `[CycleN] YYYY-MM-DD — titre`

---

## [C10] 2026-08-09 — Walk-Forward + BayesUpdate + MetaOpt + RL Promotion + LiveGate

### Ajouts (C10-OPT)
- **C10-OPT1** : Walk-Forward → `BayesianRecalibrator.update()` par outcome `(pair, tf, signal_level, reward)`
- **C10-OPT2** : `MetaOptimizer.run_cycle()` déclenché automatiquement si `global_wr < 0.45`
- **C10-OPT3** : `RLPromotion.promote()` gate double — `rl_score ≥ 0.70`, `n_trades ≥ 20`, `wr ≥ 0.40`
- **C10-OPT4** : `LiveGate` compute-only (R10) — flag `live_ready` si `WR ≥ 0.48` ET `PnL ≥ 0`
- **C10-OPT5** : Deltas baseline C9-FINAL — `wr_delta_vs_c9`, `pnl_delta_vs_c9` dans `ReplayReport`
- **C10-OPT6** : `summary["cycle"] = "10"` + liste `c10_features`

### Fixes (C10-FIX)
- **C10-FIX1** : `run_all()` expose 7 champs C10 dans `ReplayReport` : `walk_forward_outcomes`, `bayes_updated`, `meta_opt_triggered`, `rl_promoted`, `live_ready`, `live_ready_reason`, `c10_result`
- **C10-FIX2** : `v10_cycle10_optimizer.py` autonome — `run_cycle10_postprocess()` + `C10PostprocessResult.as_dict()` + fail-open R6

### Merge
- PR #1 squash-mergée : `feat/replay-fullstack-v10` → `feat/v9-foundation-clean`
- Commit merge : `0d575e2`

---

## [C9] 2026-08-07 — Walk-Forward Validator + AutoRecalibrator + ReplayReport baseline

- `v10_walk_forward_validator.py` : validation WF sur 3+ fenêtres glissantes
- `v10_auto_recalibrator.py` : recalibration automatique des seuils VSA/Force
- `ReplayReport` : champs `c9_wr`, `c9_pnl`, `c9_sharpe` comme baseline

---

## [C8] 2026-08-05 — MetaOptimizer + RLPromotion

- `v10_meta_optimizer.py` : optimisation multi-objectifs TP/SL/SessionGate
- `v10_rl_promotion.py` : promotion RL des configs performantes
- `v10_rl_adapter.py` : bridge récompense ↔ signal scorer

---

## [C7] 2026-08-03 — BayesianRecalibrator

- `v10_bayesian_recalibrator.py` : mise à jour bayésienne des priors par `(pair, tf, signal_level)`
- Intégration dans `v10_replay_engine.py`

---

## [C4] 2026-07-28 — Fondation Replay Engine

- `v10_replay_engine.py` : moteur de replay complet
- `v10_backtest_engine.py`, `v10_signal_engine.py`, `v10_decision_pipeline.py`
- Doctrine R2/R6/R9/R10 établie

---

## [C3] 2026-07-20 — Bootstrap V10

- Migration V9 → V10 : zéro import `core/v9/`
- Modules fondamentaux : `v10_confluence.py`, `v10_currency_strength.py`, `v10_vsa.py`, `v10_smc.py`
