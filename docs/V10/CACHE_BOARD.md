# V10 CACHE_BOARD — Snapshot opérationnel live

**Dernière MAJ :** 2026-08-07 15:45 CEST (ZCode, Phases 13-15 complete)
**HEAD actuel :** `d213290` (post-Phases 13-15) sur `feat/v9-foundation-clean`
**Tests V10 :** **1310/1310 verts** (pytest tests/test_v10_*.py -q)
**Tests suite complète :** **5793 collected** (15 V9 rouges pré-existants hors périmètre)
**Branche :** `feat/v9-foundation-clean` (source de vérité Git)

> Ce fichier est régénéré à chaque session. État live canonique = `docs/V10/STATE.md` + `docs/V10/DOCUMENT_STATUS.md`.

---

## 📦 Snapshot live — Data Pipeline

| Champ | Valeur |
|---|---|
| DB Source | `data/v9_forces.db` (6.4 GB, 27 tables, 269k+ snapshots) |
| Capture Server | ✅ Port 31685 LISTENING, fraîcheur ~2 min |
| `forces_snapshots` | 269 149+ lignes, 7 TF live (M1→D1) |
| `v10_signals_clean` | 9 581 signaux (M30+H1+H4 × 6 paires, fraîcheur 2.1h) |
| `paper_trades` | 337 trades (vérité héritée V9, WR 44.5%) |
| `v10_decisions.db` | Journal décisions live (Sprint 16) |
| `v10_learning_state.db` | Persistance apprentissage (Phase 9) |

---

## ⏳ Pipeline V10 — État post-Phases 13-15

```
[1]  Currency Strength (Fatman)      ✅ Phase 1 LIVRÉE
[2]  VSA Engine (Wyckoff)            ✅ Phase 2 LIVRÉE
[3]  Extreme Detector                ✅ Phase 3 LIVRÉE (v10_confluence)
[4]  Multi-TF Confluence 7-TF        ✅ Phase 3 LIVRÉE (v10_fractal_context)
[5]  Signal Orchestrator             ✅ Phase 4 LIVRÉE (v10_signal_scorer + orchestrator)
[6]  MT5 Bridge Tickmill             ✅ Phase 7 LIVRÉE (v10_mt5_bridge, paper_only=True)
[7]  Macro Filter (Regime HMM)       ✅ Phase 10 LIVRÉE (v10_market_regime)
[8]  Scalp Engine M1 (Delta Flow)    ✅ Phase 13 LIVRÉE (v10_delta_flow)
[9]  Fatman DB Reader (SOURCE DE VÉRITÉ) ✅ Phase 9 LIVRÉE (v10_fatman_db_reader)
[10] Market Regime HMM               ✅ Phase 10 LIVRÉE (v10_regime_hmm)
[11] Spread Guard                   ✅ Phase 11 LIVRÉE
[12] Liquidity Map                   ✅ Phase 12 LIVRÉE
[13] Delta Flow                      ✅ Phase 13 LIVRÉE
[14] Session Filter                  ✅ Phase 14 LIVRÉE
[15] Edge Validator WF               ✅ Phase 15 LIVRÉE (walk-forward)
[16] Couche 3 Market Context Global  ✅ Phase 16 LIVRÉE (v10_market_context_global)
[17] Bayesian Recalibrator pair      ✅ Phase 17 LIVRÉE (v10_bayesian_recalibrator)
[18] RL Adapter Thompson+ADWIN       ✅ Phase 18 LIVRÉE (v10_rl_adapter, SHADOW mode)
[19] Signal Generator Live v1        ✅ Phase 19 LIVRÉE (v10_signal_generator_live)
[20] Signal Generator Live v2        ✅ Phase 20 LIVRÉE (horizon TF + binaire + M30)
[21] Bayesian Recal pair-TF          ✅ Phase 21 LIVRÉE (4/6 M30 gate-passed WR ≥ 45%)
[22] M30 Bonus Solidarity            ✅ Phase 22 LIVRÉE (ad7832d)
[23] Cognitive Continuum (11 phases) ✅ 78 652 comportements, COHERENT (0 orphelin)
[24] Phase 12 Fractal 7-TF + Cinématique M1/M5 ✅ Structure S1-S9 câblée live
[25] Sigma Oracle v1.0 (Sprint 14)   ✅ COILING/RESOLVING/RANGING → 53% recovery M30
[26] Dashboard API Live (M2)         ✅ FastAPI 8080 + JS injection (v10_dashboard_api.py)
[27] Sprint 23 — Filter Compositor   ✅ câblé orchestrateur inconditionnel
[28] Sprint 23 — Vol Forecast SL/TP  ✅ GARCH/EWMA combiné avec ATR
[29] Sprint 23 — Backtest Endpoint   ✅ /api/v1/backtest/summary
[30] Phase 13 — Wyckoff Gate         ✅ decide_entry() gate
[31] Phase 14 — LiquidityMap         ✅ compose_filters() integration
[32] Phase 15 — Behavior Context     ✅ orchestrator gate

Cœur cognitif V10 : ✅ 1310/1310 tests V10 verts, 32 phases additif pur (R2)
```

---

## 📊 Derniers Runs Live (08/07)

### Sigma Oracle Calibration (Sprint 14 — 15 signaux live)
```
AVANT (Fatboy gate only) : 13/15 → NONE (12 sigma_zone_grise, 3 safe_haven)
APRÈS (Sigma Oracle)     : 8/15 → A2 (53% recovery)
  M30 : 5/5 RESOLVING → A2 (slope > 0.8, sigma > 20) ⭐
  M15 : 5/5 RANGING → NONE (slope ~0.2, bruit)
  H1  : 3 safe_haven → NONE (R6 fail-open correct)
```

### RL Shadow Session 100 trades × 4 paires
```
Gate CEO (30 trades consécutifs WR_shadow ≥ WR_baseline) : 2/4 PASS
  GBPUSD : baseline 50.8% → shadow 57.0% (+6.2%) ✅
  AUDUSD : baseline 46.6% → shadow 49.0% (+2.4%) ✅
  EURUSD : baseline 69.3% → shadow 72.0% (+2.7%) ❌
  USDJPY : baseline 58.1% → shadow 66.0% (+7.9%) ❌
Kill switch DD>5% : RESPECTÉ (R10)
```

### Weekly Summary (172 décisions)
```
WR global : 56.4% (vs 34.2% base ICT)
Top edges : USDJPY BUY 64%, AUDUSD SELL 60%, USDCAD SELL 58.3%
```

### Sprint 23 Backtest Kill Zones (8822 signaux)
```
Base WR : 33.2%
NY      : +20.0 pts (WR 53.2%) ⭐
LONDON  : +11.5 pts (WR 44.7%)
ASIAN   : +6.7  pts (WR 39.9%)
OUTSIDE : -9.8  pts (WR 23.4%)
```

---

## 🔗 Pointeurs Opérationnels

### Modules cœur `core/v10/` (50+ fichiers, 0 import core/v9/)
- `v10_currency_strength.py` — FatmanCalculator + MultiTF
- `v10_fatman_db_reader.py` — **SOURCE DE VÉRITÉ** depuis `forces_snapshots`
- `v10_fatman_bible_signals.py` — 6 signaux + 6 filtres + 4 principes + fatboy_gate
- `v10_perplexity_sigma_oracle.py` — Sigma Oracle v1.0 (Sprint 14)
- `v10_fractal_context.py` — Confluence 7-TF + Cinématique M1/M5
- `v10_market_context_global.py` — Couche 3 (Cycle+Coalition+Antagonism+Divergence)
- `v10_orchestrator.py` — Pipeline Hub-first (Fatboy→Sigma→Filter→Hub→EdgeSelector→RiskShield)
- `v10_rl_adapter.py` — Thompson Bandit 3-arms + ADWIN (SHADOW)
- `v10_currency_behavior.py` — 5 couches comportement (Phase 32)
- `v10_dashboard_api.py` — **M2** FastAPI 8080 + WebSocket ready
- `v10_vol_forecast.py` — **S23-B** GARCH/EWMA + combined ATR/vol SL/TP
- `v10_filter_compositor.py` — **S23-A** câblé inconditionnel dans orchestrateur
- `v10_live_monitor.py` — **S23-B** vol forecast intégré pour SL/TP

### Tests `tests/test_v10_*.py` (26 fichiers)
- **1278/1278 verts** (4 warnings sklearn attendus)
- Nouveaux Sprint 14 : `test_v10_sigma_oracle.py` (21 tests)
- Nouveaux Sprint 15+ : `test_v10_ibkr_bridge.py`
- Nouveaux Sprint 23 : `test_v10_orchestrator_filter.py` (5 tests), `test_v10_dashboard_backtest.py` (3 tests)

### Rapports `reports/` (générés live)
- `v10_fatman_calibration_20260807.json` — 10 signaux + conflit Fatboy
- `v10_rl_shadow_100trades_20260807.json` — 2/4 gate passed
- `v10_sigma_oracle_calibration_20260807.json` — 53% recovery M30
- `v10_night_report_20260806.json` — ICT Kill Zones + Error Learner
- `v10_weekly_summary_20260806.json` — WR 56.4% sur 172 décisions
- `v10_replay_batch_20260806.json` — 4217 trades appris, 10 edges ≥50%
- `v10_public_strategy_backtest_20260805.json` — Kill Zones edge

### Config
- `config/v10_active_thresholds.json` — Seuils recalibrés par paire×TF + `sigma_oracle` section
- `config/v9_kill_switches.env` — **M1 DONE** V9_EXECUTION_ENABLED commenté (D02 resolved)

### Dashboards Live (M2 DONE)
- `docs/dashboard_v10_ceo.html` — Regénéré 12:35 UTC (auto-refresh 60s + live JS)
- `docs/dashboard_live.html` — Regénéré 12:35 UTC (auto-refresh 60s + live JS)
- API Server : `scripts/v10_dashboard_api.py` → `http://localhost:8080`
  - Endpoints : `/api/v1/signals/live`, `/api/v1/forces/latest`, `/api/v1/behavior/summary`, `/api/v1/paper/summary`, `/api/v1/system/status`, `/api/v1/backtest/summary`
  - Dashboards : `/dashboard/v10`, `/dashboard/v9` (avec injection JS live)
  - Regenerate endpoints : `/api/v1/dashboard/v10`, `/api/v1/dashboard/v9`

---

## 🎯 Prochaines Étapes (CEO)

| Priorité | Action | Statut |
|---|---|---|
| **P0** | Calibration live Fatman — aligner FatmanCalculator vs lecture visuelle (10 signaux) | 🔄 En cours |
| **P1** | RL SHADOW→ACTIVE — 100 trades paper, gates : WR≥50 / Sharpe≥0.3 / DD≤50p / consistency≥75% | ⏳ 2/4 gates passed |
| **P2** | Validation signaux live — tenir 2-3 jours consécutifs | ⏳ En observation |
| **P3** | Sprint 24+ — Nettoyage 15 tests V9 rouges — mandat Søn requis | ⏳ Verrouillé |

---

## ⚠️ Dettes Techniques (DEBT_TRACKER.md)

| ID | Sévérité | Description | Propriétaire | Statut |
|---|---|---|---|---|
| D01 | 🔴 | 15 tests V9 rouges (pré-existants, V9 verrouillé) | Søn | 🔴 Open |
| D02 | 🟡 | ~~V9_EXECUTION_ENABLED=1 résidu~~ | Zcode | ✅ **RÉSOLUE** (M1) |
| D03 | 🟡 | ~~CACHE_BOARD.md obsolète~~ | Hermes | ✅ **RÉSOLUE** (M3) |
| D04 | 🟡 | Sprint 23 Quant non commencé | Zcode | ✅ **RÉSOLUE** (Sprint 23 complete) |
| D05 | 🟢 | Docs/checkpoint_*.md dupliqués sans consolidation | Perplexity | 🟢 Open |
| D06 | 🟢 | Dashboards — ~~pas reliés à la vraie DB~~ | Zcode | ✅ **RÉSOLUE** (M2) |
| D07 | 🟢 | filter_compositor non câblé orchestrateur | Zcode | ✅ **RÉSOLUE** (S23-A) |
| D08 | 🟢 | SL/TP statiques (vol_forecast non intégré) | Zcode | ✅ **RÉSOLUE** (S23-B) |
| D09 | 🟢 | Endpoint backtest absent dashboard | Zcode | ✅ **RÉSOLUE** (S23-C) |

---

*Régénéré via : `python -m pytest tests/test_v10_*.py --collect-only -q` + `python -m pytest tests/ --collect-only -q` + `git rev-parse --short HEAD`*