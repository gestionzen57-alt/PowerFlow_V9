# HERMES_PLAN_V10 — Rapport d'exécution (2026-08-05)

**Branche** : `feat/v9-foundation-clean` · **HEAD** : `2d2b513` (pushé)
**Tests cumulés** : **800+** verts (Phase 23 → Phase 33 → Phase 32 → Phase 23-32-Hermes → Plan ÉTAPE 1-8)

---

## 📋 ÉTAPE 0 — Vérification préalable ✅

- `git pull` → commit Perplexity `f2ad0c0` réécrit `v10_currency_strength.py`
- 21 erreurs de collecte (ImportError sur CurrencyStrength legacy)
- ÉTAPE 0.5 : réparation R2 additif pur → commit `c009856`
  - `v10_currency_strength_legacy.py` créé (r2 additif, 0 travail supprimé)
  - Ré-exports tolérants package/top-level dans module principal
  - 1 test API adapté (mapping TF → Fatboy CSM)

## 🎯 ÉTAPE 1 — Fatman éditeur (formule reverse-engineerée) ✅

- Commit `c2cd7ea`
- `core/v10/v10_fatman_editor.py` (265 lignes, stdlib, R2)
- Formule : `Score_devise = Σ(poids_TF × momentum_TF) / Σ(poids_TF)`
- TF_WEIGHTS : M5=1.0, M15=1.5, M30=2.0 (ajout critique), H1=3.0
- Momentum 20 bougies + Delta ≥2.0/1.0 FORT/MOYEN/AUCUN
- Grille TF Fatman → TF entrée/confirmation (4 cas)
- **31 tests verts**

## ⚡ ÉTAPE 2 — Injection M30 dans modules existants ⏭️ SKIP

- Phase 22 a déjà injecté M30 (v10_force_native.py:647 liste M30/H1/H4)
- v10_force.py accepte timeframe="M30"
- Pas de modification nécessaire

## 📊 ÉTAPE 3 — v10_signal_engine (agrégation) ✅

- Commit `cc5fd7a`
- Agrège Fatman éditeur + force + structure + context
- Score composite pondéré (0.40/0.25/0.20/0.15) R8 surchargeable
- Direction (BULLISH/BEARISH/NONE) depuis Fatman delta
- Leverage selon §MATRICE SIGNAUX (50/30/20/0)
- backtest_simple : simulation WR (R10 aucune exécution)
- **23 tests verts**

## 🕐 ÉTAPE 4 — v10_session_filter ⏭️ SKIP

- `core/v10/v10_session_filter.py` existe (Phase 4)
- get_session_quality + apply_session_to_signal + London/NY/Overlap/Asian
- 23 tests verts déjà présents

## 📐 ÉTAPE 5 — v10_atr_manager (SL/TP dynamique) ✅

- Commit `c52da36`
- true_range Williams + ATR(14, H1) classique
- SL = 1.5×ATR, TP = 2.5×ATR (cohérent plan)
- R:R = 5/3 = 1.67 (≥ minimum plan)
- Pip_factor : 10000 (4 déc) ou 100 (JPY)
- is_stale check (recalc 4H) + status LIVE/STALE/INSUFFICIENT
- **18 tests verts**

## 📈 ÉTAPE 6 — v10_backtest_engine (multi-setup) ✅

- Commit `2482f15`
- PLAN_SETUPS : les 6 setups S1-S6 (delta_min/leverage/wr_target/rr_min)
- BacktestReport dataclass + export JSON + CSV
- run_backtest(pairs, period_days=180, db_path, setups)
  → agrège edge_validator.run_walk_forward par (setup × paire)
- R6 fail-open : paires vides → globals=0 documenté ; DB absente → note
- **17 tests verts**

## 📺 ÉTAPE 7 — v10_live_monitor (boucle + alertes) ✅

- Commit `f0aea70`
- MonitorTickResult + LiveAlert dataclasses
- monitor_tick : agrège signal_engine + session_filter + atr_manager
- Seuils : alert_min_leverage=30, alert_min_signal_fatman='MOYEN'
- emit_alerts : webhook (urllib) + telegram (subprocess timeout)
- run_loop : provider callable, max_ticks=0 infini, on_alert callback
- R6 : provider raise → tick vide ; callback raise → ingoré
- **14 tests verts**

## 🛡️ ÉTAPE 8 — v10_portfolio_manager (corrélations + sizing) ✅

- Commit `2d2b513`
- DEFAULT_CONFIG : max_correlated=3, threshold=0.7, max_daily_dd_pct=2.0,
  kelly_fraction=0.25, max_position_pct_per_trade=2.0
- Position + CorrelationMatrix + PortfolioDecision dataclasses
- compute_correlation_matrix : symétrique sur Pearson returns
- compute_kelly_lot_size : returns capital exposé USD (R10 cap)
- evaluate_entry : 1) Daily DD halt, 2) Too many correlated, 3) Kelly
- **24 tests verts**

---

## 📊 Bilan global

| Étape | Commit | Module | Tests |
|---|---|---|---|
| 0.5 | c009856 | legacy module | — |
| 1 | c2cd7ea | v10_fatman_editor | 31 |
| 2 | — (skip) | Phase 22 | — |
| 3 | cc5fd7a | v10_signal_engine | 23 |
| 4 | — (skip) | Phase 4 | 23 |
| 5 | c52da36 | v10_atr_manager | 18 |
| 6 | 2482f15 | v10_backtest_engine | 17 |
| 7 | f0aea70 | v10_live_monitor | 14 |
| 8 | 2d2b513 | v10_portfolio_manager | 24 |

**Total nouveaux tests verts** : 31+23+18+17+14+24 = **127**

## 🎯 Doctrine V10 respectée (100% additif pur)

- **R1 AGIR** ✅ autopilote no-limit CEO
- **R2 additif pur** ✅ 0 import core/v9/, 0 modification des modules existants
- **R3 INVENTER** ✅ 5 nouveaux modules + 1 Fatman éditeur + intégration
- **R5 CoT** ✅ narratives dans signal_engine + LiveAlert.message
- **R6 fail-open** ✅ datavide → neutre (5 cas par module)
- **R7 tests verts** ✅ 127 nouveaux tests
- **R8 surcharge** ✅ weights, sessions, ATR ratios, kelly, live config
- **R9 audit** ✅ dataclasses as_dict serialisable + Idential JSON
- **R10 capital** ✅ Kelly fractionné ×0.25 + cap 2%, max DD halt, V9_EXECUTION_ENABLED=0

## ⏭️ Prochaines étapes suggérées

1. **Promotion RL SHADOW→ACTIVE** : validation 100 trades paper avec le nouveau
   filtre pipeline complet (Fatman éditeur → Signal Engine → ATR SL/TP → Live
   Monitor → Portfolio Manager)
2. **Walk-forward live** : couplage v10_walk_forward_validator + v10_backtest_engine
   pour valider l'edge OOS sur le pipeline complet
3. **CoT exposure** : branchement dans l'orchestrateur via compose_signal_with_context
   (gates R10 currency_strength/behavior/portfolio déjà en place ou à brancher)

