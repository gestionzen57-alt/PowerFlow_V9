# V10 CACHE_BOARD — Cache opérationnel live

**Dernière mise à jour** : 2026-08-05 06:30 UTC (post run nocturne)
**HEAD courant** : `e08223c` sur `feat/v9-foundation-clean`
**Tests V10 cumulés** : **545/545 verts**

---

## 📦 Snapshot live — Currency Strength Engine (Phase 1)

| Champ | Valeur |
|---|---|
| Source | DB v9_forces.db / forces_snapshots |
| TF | H1 (extensible M1/M5/M15/M30/H4/D1) |
| Paires trackées | 6/6 (EURUSD, GBPUSD, USDJPY, USDCHF, AUDUSD, USDCAD) |
| Devises trackées | 7/7 + NZD disponible (8 colonnes force_*) |
| Last timestamp | 2026-08-05 (à re-check via `freshness_check`) |
| n_bars used | 600 (100 par pair × 6 paires) |
| Insufficient | 0 |
| Spread Fatman | recalcul live |

### Top / Bottom (dernier snapshot H1)
- **Strongest** : à recalculer via `v10_fatman_db_reader.get_fatman_live()`
- **Weakest** : à recalculer via `v10_fatman_db_reader.get_fatman_live()`

---

## ⏳ Pipeline V10 — état post-run nocturne (22 phases)

```
[1]  Currency Strength           ✅ Phase 1 LIVRÉE
[2]  VSA Engine                  ✅ Phase 2 LIVRÉE
[3]  Extreme Detector            ✅ Phase 3 LIVRÉE (v10_confluence)
[4]  Multi-TF Confluence         ✅ Phase 3 LIVRÉE
[5]  Signal Orchestrator         ✅ Phase 4 LIVRÉE (v10_signal_scorer + orchestrator)
[6]  MT5 Bridge Tickmill         ✅ Phase 7 LIVRÉE (v10_mt5_bridge, paper_only=True)
[7]  Macro Filter                ✅ Phase 10 LIVRÉE (v10_market_regime)
[8]  Scalp Engine M1             ✅ Phase 13 LIVRÉE (v10_delta_flow)
[9]  Fatman DB Reader            ✅ Phase 9 LIVRÉE (v10_fatman_db_reader, SOURCE DE VÉRITÉ)
[10] Market Regime               ✅ Phase 10 LIVRÉE
[11] Spread Guard                ✅ Phase 11 LIVRÉE
[12] Liquidity Map               ✅ Phase 12 LIVRÉE
[13] Delta Flow                  ✅ Phase 13 LIVRÉE
[14] Session Filter              ✅ Phase 14 LIVRÉE
[15] Edge Validator WF           ✅ Phase 15 LIVRÉE (walk-forward 60j train + 20j test)
[16] Couche 3 Market Context     ✅ Phase 16 LIVRÉE (v10_market_context_global)
[17] Bayesian Recalibrator pair  ✅ Phase 17 LIVRÉE (v10_bayesian_recalibrator)
[18] RL Adapter Thompson+ADWIN   ✅ Phase 18 LIVRÉE (v10_rl_adapter, SHADOW mode)
[19] Signal Generator Live v1    ✅ Phase 19 LIVRÉE (v10_signal_generator_live)
[20] Signal Generator Live v2    ✅ Phase 20 LIVRÉE (5A patches: horizon TF + binaire + M30)
[21] Bayesian Recal pair-TF      ✅ Phase 21 LIVRÉE (4/6 M30 gate-passed WR ≥ 45%)
[22] M30 Bonus Solidarity        ✅ Phase 22 LIVRÉE (ad7832d)

Cœur cognitif V10 : ✅ 545/545 verts, 22 phases additif
DB v9_forces.db : ✅ 6.40 GB, 28 tables, 254 226 forces_snapshots, 8669 v10_signals_clean
capture_server : ✅ PID live (port 31685)
```

---

## 📈 Dernier test live (run nocturne 2026-08-05)

### Étape 5B — dataset V10 propre v2
```
n_snapshots_loaded : 8843 (M30+H1+H4 × 6 paires)
n_filtered_binary  : 138 (1.56%, < seuil 80% R6 fail-open)
n_signals_generated: 8669
n_signals_persisted: 8669 dans v10_signals_clean
WR global          : 32.82%
WR M30             : 38.45% (top vs 32.53% H1, 17.71% H4)
```

### Étape 6 — recalibration par (paire, TF) Phase 21
```
GATE WR ≥ 45% : 4/6 paires × M30 gate-passed
  AUDUSD_M30 : 50.30% (169/724) PnL=+2.0p ✅
  GBPUSD_M30 : 48.11% (212/1057) PnL=+2.2p ✅
  USDCAD_M30 : 50.00% (58/646) PnL=-0.1p ✅
  USDCHF_M30 : 45.28% (53/737) PnL=+0.5p ✅
  EURUSD_M30 : 41.43% (177/419) — proche mais < 45%
  USDJPY_M30 : 39.80% (188/755) — outlier (proxy pnl bruité)

Comparaison V9 vs V10 A1 (ΔWR) :
  USDCHF : +28.5pts ⭐ (V9 10.5% → V10 39.0%)
  USDCAD : +29.7pts ⭐ (V9 0.0% → V10 29.65%)
  GBPUSD : -30.0pts (V9 64% artefact, V10 34% réel)
```

### Étape 7 — M30 bonus solidarity
```
SANS M30 bonus : context_score=91.43 solidarity=0.96 m30_included=False
AVEC M30 bonus : context_score=92.50 solidarity=1.00 m30_included=True
                 m30_bonus=+0.043 (cap à 1.0)
Gain context_score: +1.07
```

---

## 🔗 Pointeurs

### Modules cœur `core/v10/`
- `v10_currency_strength.py` (Phase 1) — moteur Fatman Hawkeye par devise
- `v10_vsa.py` (Phase 2) — Wyckoff 4 états
- `v10_confluence.py` (Phase 3) — Multi-TF pondéré
- `v10_signal_scorer.py` (Phase 4) — 5 critères pondérés
- `v10_mt5_bridge.py` (Phase 7) — Bridge MT5 compte démo
- `v10_fatman_db_reader.py` (Phase 9) — **SOURCE DE VÉRITÉ** depuis `forces_snapshots`
- `v10_market_regime.py` (Phase 10)
- `v10_spread_guard.py` (Phase 11)
- `v10_liquidity_map.py` (Phase 12)
- `v10_delta_flow.py` (Phase 13)
- `v10_session_filter.py` (Phase 14)
- `v10_edge_validator.py` (Phase 15) — Walk-forward gates
- `v10_market_context_global.py` (Phase 16+22) — Couche 3 + M30 bonus
- `v10_bayesian_recalibrator.py` (Phase 17+21) — Pair + (pair, TF) grid search
- `v10_rl_adapter.py` (Phase 18) — Thompson Bandit + ADWIN + SHADOW
- `v10_signal_generator_live.py` (Phase 19+20) — Dataset V10 propre
- `v10_orchestrator.py` — Compose + wiring M30 + thresholds

### Tests `tests/test_v10_*.py`
- 25 fichiers tests V10, **545/545 verts** au HEAD `e08223c`

### Rapports `reports/`
- `v10_dataset_v2_20260805.json` (14 KB)
- `v10_recalibration_v2_20260805.json` (14 KB)
- `v10_night_report_20260805.json` (4.5 KB)

### Config
- `config/v10_bayesian_thresholds.json` (Phase 17 par paire)
- `config/v10_bayesian_thresholds_pair_tf_v2.json` (Phase 21 par paire × TF)

### Plans & docs
- `docs/V10/V10_PLAN_EDGE_FUND_QUANTIQUE.md`
- `docs/V10/V10_PLAN_REPARALETTRAGE.md`
- `docs/V10/V10_PHASE_EDGE_FUND_PHASE{1,2,3}_REPORT.md`
- `docs/V10/V10_PHASE_EF_COGNITIVE_REPORT.md`

### Skills catalogue Hermes
- `powerflow-v10-edge-fund` — haut-niveau V10 (22 phases)
- `powerflow-v10-microstructure-edge-fund` — Couche 2
- `powerflow-v10-market-context-filter` — Couche 3
- `powerflow-v10-system-canon` — canon V10 + 16 pitfalls R9/R10
- `powerflow-v9-edge-fund` — V9 historique (patché HEAD e08223c)
- `powerflow-v9-quant` — quantique V9 (patché HEAD e08223c)

---

## ⛔ Étape 9 CEO gate matin — 3 décisions requises

1. **Phase 20++ recalcul forces V10 natif** (vs proxy pnl bruité)
2. **RL SHADOW launch** sur 4 paires gate-passed M30 (30 trades consécutifs)
3. **Priorité chantier adjacent** Doctrine R6

Voir `reports/v10_night_report_20260805.json` + `workspace/perplexity/memory/DECISIONS_LOG.md` (entrée DECISION-2026-08-05-001).
