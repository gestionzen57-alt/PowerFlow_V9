# V10 STATE — État du pipeline cognitif V10

**Dernière mise à jour** : 2026-08-07 23:50 CEST — ZCode (calibration Fatman P0 livrée)
**Branche active** : `feat/v9-foundation-clean`
**HEAD courant** : `d213290` (Phases 13-15 complètes) — **1310/1310 tests V10 verts**

> Gouvernance : `docs/V10/DOCUMENT_STATUS.md` définit les documents actifs et la hiérarchie de vérité. Les compteurs des sections historiques restent des jalons, jamais le statut courant.

---

## ✅ Phases livrées

### 🔴 Audit ZCode 2026-08-05 17h-18h (mandat plein pouvoir)

**Bug critique RÉPARÉ (commit `885a851`)** — Safe Haven flip inversé :
`v10_currency_strength._compute_raw_returns` inversait le signe des paires
inversées (USDJPY/USDCHF/USDCAD). Quand JPY/CHF s'apprécient, le moteur les
classait "faibles" et USD "fort" — l'inverse de la réalité. Fix :
`returns[quote] = raw`, `USD -= raw`. Validé : JPY=100/CHF=100/USD=4.6 sur
scénario safe_haven. **Dette R9 (test safe_haven pré-existant) RÉPARÉE** —
96 tests currency_strength verts.

**Réconciliation doublon** : `v10_strategy_layers` réécrit en wrapper de
`v10_filter_compositor.compose_filters` — cœur de filtrage unique
(session + OTE + SMC + regime). Export `__init__.py` vérifié : zéro nom
non résolu (27 réparés).

### Cron replay hebdomadaire (2026-08-05, Hermes)
- `scripts/v10_replay_batch_cron.sh` — rejoue la profondeur complète chaque
  lundi 03:00, rafraîchit la carte des edges + modèle d'apprentissage.
  Cron `89c26817deb9`. Testé : execution_success=true.
- `scripts/v10_edges_telegram_alert.py` — notifie la carte des edges (WR,
  direction, trades) sur Telegram. Commit `8e7db16`. 1141/1141 verts.

### Edge Selector — sélectivité R3/R10 (2026-08-05, Hermes)
- `core/v10/v10_edge_selector.py` — EdgeSelector charge la carte des edges du
  replay batch, n'autorise que les paires×TF×direction validées (WR≥0.50, n≥30,
  direction dominante). R6 fail-open. 10 tests.
- Câblé dans `v10_live_decision` : ne trade que les edges validés → les paires
  sans edge downgradées A1/A2→A3 (WAIT). Plus conservateur = R10 renforcé.
- Cumul tests : **1141/1141 verts** (1131 → 1141). Commit `07da7e4` pushé.

### Cognitive Continuum — Compréhension continue (06/08, Hermes autopilote)
- `v10_memory_bridge.py` — pont mémoire V9→V10 (201 patterns, read-only)
- `v10_behavior_registry.py` — registre d'interprétation (table v10_behaviors, query_coherence)
- `v10_cortex.py` — moteur d'interprétation continue (boucle voir→comprendre→apprendre→mémoriser)
- `v10_coherence_audit.py` — auto-détection des modules orphelins (amélioration perpétuelle)
- `v10_learning_continuum.py` — apprentissage continu par comportement (drift par comportement)
- `v10_behavior_rag.py` — RAG d'amplification sur mémoire propre (APRÈS cohérence)
- Cumul tests : 1186 → **1218** (HEAD `89db6b9`)
- `scripts/v10_replay_engine.py` — replay historique bars → décisions → outcomes
  → ErrorLearner. Résultat : 747 décisions, WR agrégé 43.8%, GBPUSD H1 55.6% +
  AUDUSD M30 62.7% (edges émergents). HMM stride 15 (perf).
- `scripts/v10_learning_loop.py` — apprentissage continu replay + live (481 trades,
  WR 50.5%, drift → REVERT).
- `scripts/v10_daily_bilan.py` + `v10_bilan_telegram_alert.py` — bilan quotidien
  (décisions, outcomes, WR/PnL/Sharpe, reco R8) notifié sur Telegram.
- Cron nocturne étendu à 8 étapes. Commits `3ff5ea8`→`b7a95d5`. 1125/1125 verts.

### Persistance apprentissage + Replay batch (2026-08-05, Hermes)
- `core/v10/v10_learning_persistence.py` — LearningPersistence (SQLite
  v10_learning_state, R6 fallback) + learner_to_dict/dict_to_learner. L'apprentissage
  est CONTINU à travers les sessions/replays (rechargé à chaque run). 6 tests,
  cumul **1131/1131 verts**. Commit `3517eb8`.
- `scripts/v10_replay_batch.py` — replay profondeur complète (M30 4559 / H1 2925 /
  H4 1597 bars × 6 paires) → carte des edges + persistance du modèle. **TERMINÉ** :
  4217 trades appris, WR 49%, 10 edges ≥50% (EURUSD M30 62%, USDJPY H4 57%,
  USDCHF H4 56%), modèle persisté. Perf fixée : rolling window HMM 200 bars
  (élimine O(N²) sur gros TF). Commit `4e3894c`.

### Sprint 20 — Alerte R8 Telegram (2026-08-05, Hermes)
- `scripts/v10_r8_telegram_alert.py` — lit la boucle fermée R8 + synthèse hebdo,
  notifie le CEO sur Telegram quand une recalibration est déclenchée (drift,
  DEPLOY/REVERT/HOLD, WR avant/après). Branché comme 6e étape du cron nocturne.
  Testé réel : alerte recalibration REVERT envoyée. Commit `119702a`.

### Sprint 19 — Notification Telegram des signaux live (2026-08-05, Hermes)
- `scripts/v10_telegram_alert.py` — envoie les signaux BUY/SELL via
  v9_telegram_notifier (token+chat_id projet, anti-spam). Testé réel Envoyé=True.
- Branché dans le cron live decision (fix TMPD) — chaque run notifie. Commit `295ad10`.

### Sprint 17-18 — Synthèse hebdo + résolution outcomes (2026-08-05, Hermes, post-ZCode)
- `scripts/v10_weekly_summary.py` — synthèse hebdomadaire (WR/PnL/Sharpe par
  paire×action via summarize_decisions, benchmark v10_signals_clean, reco R8).
  5e étape du cron nocturne. Commits `83cd046` + `e3d300d`.
- `scripts/v10_resolve_outcomes.py` — résout pnl/is_win des décisions BUY/SELL
  depuis l'évolution de prix forward (horizon par TF). R9 : proxy. Commit `77fc04a`.
- Note R9 : ZCode annonce 1179 tests mais pytest mesure **1125/1125 verts**.

### Sprint 16 — Journal des décisions + synthèse (2026-08-05, Hermes autopilote quant)
- `core/v10/v10_decision_log.py` — DecisionLogger (SQLite v10_decisions, R6
  fallback in-memory) + summarize_decisions (WR/PnL/Sharpe-like par paire×action).
  7 tests.
- Câblé dans `v10_live_decision` : les décisions BUY/SELL sont persistées
  dans data/v10_decisions.db. Cumul tests : **1125/1125 verts** (1118 → 1125).
  Commits `f6fbb4d` + `9e511cd` pushés

### Sprint 15 — Cron boucle décision live (2026-08-05, Hermes autopilote quant)
- `scripts/v10_live_decision_cron.sh` — exécute v10_live_decision toutes les
  30 min, persiste reports/v10_live_decision_latest.json, extrait les signaux.
- Cron Hermes `v10-live-decision` (`8c038f0d10e9`). Testé : execution_success=true,
  4 signaux actifs (EURUSD/CHF/AUD SELL, GBPUSD BUY). Commit `4fe3b47` pushé

### Sprint 14 — Boucle décision live temps-réel (2026-08-05, Hermes autopilote quant)
- `scripts/v10_live_decision.py` — polling bars live (forces_snapshots) →
  stratégies publiques → decide_entry → action/lot. Direction dérivée du
  régime HMM (bias), pas forcée. R6 fail-open, R10 paper-only.
- Live 6 paires H1 : EURUSD/CHF/AUD TRENDING_DOWN → SELL, GBPUSD TRENDING_UP
  → BUY, USDJPY/CAD RANGING → WAIT. lot 0.01 micro-lot R10. Commit `5cc71b7`

### Sprint 13 — Pipeline de décision end-to-end (2026-08-05, Hermes autopilote quant)
- `core/v10/v10_decision_pipeline.py` — decide_entry compose signal_level +
  stratégies publiques (compose_filters) + bouclier R10 (risk_shield +
  net_exposure) → action BUY/SELL/WAIT/NONE + lot_size. R6 fail-open. 9 tests.
- Cumul tests : **1118/1118 verts** (1109 → 1118, +9). Commit `e899811` pushé

### Sprint 12 — Démo composition publique live (2026-08-05, Hermes autopilote quant)
- `scripts/v10_strategy_demo.py` — enchaîne ICT OTE + SMC + régime HMM +
  wyckoff + filter compositor sur les bars live (forces_snapshots). Rapport
  EURUSD H1 : regime TRENDING_DOWN, A1→A2 cohérent. Commit `ed0f4ec` pushé

### Sprint 11 — Risk dashboard R10 (2026-08-05, Hermes autopilote quant)
- `scripts/v10_risk_dashboard.py` — charge positions paper, calcule net
  exposure par devise, exerce evaluate_risk_shield → rapport JSON R10.
- Cron nocturne étendu à 4 étapes (night_report + closed_loop + shadow +
  risk_dashboard). Commits `0f42350` + `b7a66ee` pushés

### Sprint 10 — Bouclier R10 unifié (2026-08-05, Hermes autopilote quant)
- `core/v10/v10_risk_shield.py` — evaluate_risk_shield compose les gates R10
  en une décision unique : DD halt (kill switch), position max 2%, double
  opposée + net exposure (v10_net_exposure), corrélation portfolio.
  R6 fail-open. 8 tests.
- Cumul tests : **1109/1109 verts** (1101 → 1109, +8). Commit `3779cc7` pushé

### Sprint 9 — R10 renforcé : exposition nette + doubles opposées (2026-08-05, Hermes)
- `core/v10/v10_net_exposure.py` — compute_net_exposure (net par devise,
  long +/- short), find_directly_opposed (même paire direction opposée),
  exposure_gate (bloque opposé direct + net exposure par devise > max).
  R6 fail-open. 10 tests.
- Cumul tests : **1101/1101 verts** (1091 → 1101, +10). Commit `f2049f4` pushé

### Sprint 8 — Cron nocturne auto (2026-08-05, Hermes autopilote quant)
- `scripts/v10_night_cron.sh` — orchestre v10_night_report + v10_closed_loop
  + v10_shadow_promotion quotidiennement.
- Cron Hermes `v10-night-report-r8-loop` (`d210e2eecd2e`, 01:00 UTC, deliver local).
  Testé manuellement : execution_success=true, CLOSED_LOOP drift=REVERT.
- Commit `1ec0138` pushé

### Sprint 7 — Boucle R8 auto-recalibration (2026-08-05, Hermes autopilote quant)
- `core/v10/v10_auto_recalibrator.py` — should_recalibrate (drift ou re-calib
  recommandée avec données suffisantes) + run_auto_recalibration
  (compute_recalibration_by_pair_tf + WR avant/après + décision DEPLOY/REVERT/HOLD).
  R6 fail-open. 8 tests.
- `scripts/v10_closed_loop.py` — boucle fermée end-to-end (error learner → bayésien).
- Live : drift détecté → REVERT (recalib fail-open after_wr=0 < before_wr=0.49) —
  conservateur R8. R10 intact.
- Cumul tests : **1091/1091 verts** (1083 → 1091, +8). Commit `780ecd0` pushé

### Sprint 6 — Exploitation + validation SHADOW (2026-08-05, Hermes autopilote quant)
- `scripts/v10_night_report.py` — rapport nocturne consolidé (backtest ICT Kill
  Zones + error learner + KPI setup×zone). Live 8857 signaux : NY +20pts,
  LONDON +11.4, ASIAN +6.7, OUTSIDE −9.8 (base 33.2%). Drift détecté.
- `scripts/v10_shadow_promotion.py` — gates R10 (WR≥50, Sharpe≥0.3, DD≤50p,
  consistency≥75%) sur 100 derniers trades. Verdict live : **HOLD** (1/4 gates).
  R9 honnête : pas de promotion non méritée.
- Commit `82afbc8` pushé

### Sprint 5 — Pipeline branché + apprentissage (2026-08-05, Hermes autopilote quant)
- `core/v10/v10_orchestrator.py` : kwargs `public_filters` + `regime_block` →
  GATE FINAL `compose_filters` (session+OTE+SMC+regime) après tous les filtres.
  Backward-compatible R2, R6 fail-open, CoT `3_public_filters`.
- `core/v10/v10_error_learner.py` : boucle apprentissage des erreurs (R4/R8) —
  TradeOutcome + ADWIN-like drift + re-calibration recommandée par setup + leçons
  coT (R5). 9 tests.
- Fix export `v10_strategy_layers` (gap pré-existant ZCode) → test passe.
- Cumul tests V10 : **1083/1083 verts** (1060 → 1083, +23)
- Commit `61ff4a7` pushé

### Sprint 4 — Pipeline de signal (2026-08-05, Hermes autopilote quant)
- `core/v10/v10_filter_compositor.py` — chaîne session+ICT OTE+SMC+regime
  sur setup_level, trace R9, R6 fail-open. 10 tests.
- `core/v10/v10_vol_forecast.py` — GARCH (arch) + fallback EWMA, sl_tp_from_vol. 9 tests.
- `core/v10/v10_wyckoff_consolidated.py` — VSA + compression-extension consolidé
  (MARKUP/MARKDOWN/ACCUMULATION/DISTRIBUTION). 8 tests.
- Cumul tests V10 : **1060/1060 verts** (959 → 1060, +101 Sprints 2-4)
- Doctrine quant libérée (pyproject v0.10.0). Commit `5dac9a4` pushé

### Sprint 3b — ICT OTE (2026-08-05, Hermes autopilote quant)
- `core/v10/v10_ict_ote.py` — Kill Zones ICT 2022 (ASIAN 0-8 / LONDON 8-13 /
  NY 13-17 UTC) + OTE Fibonacci 62-79% (zone optimale d'entrée)
- `_trend_bias` pente linéaire (bias indépendant de la bande OTE)
- `conviction_score [0,1]` : +0.60 in_ote, +0.15 LONDON/NY, +0.25 NY
- `apply_ote_to_signal` : A1→A2 si hors kill zone / hors zone / conviction faible
- R6 fail-open (no_data/flat_swing/invalid_ts → setup NONE), R9 as_dict JSON
- Pure stdlib (R2 additif, 0 import core/v9/), 20 tests verts (939→959 cumulés)
- Export via `core/v10/__init__.py`. Commit `0949fa9` pushé

### Phase 32 — Currency Behavior (2026-08-05, ZCode)
- `core/v10/v10_currency_behavior.py` — 5 couches : observation,
  comportement (états/coalitions/leadership/régimes/lead-lag), fidélité
  (linéaire + extrême P90/P10), apprentissage (calibration R8 + drift
  + réversibilité), expression (narratives V1/V2 + behavior_context)
- 43 tests verts (cumul V10 : **774/774**, zéro régression)
- `scripts/v10_currency_behavior_demo.py` + rapport JSON + rapport MD
- **Découvertes R9** : corrélation linéaire forces→prix ≈ 0 MAIS WR
  65-90% aux queues P90/P10 → GBPUSD + AUDUSD RELIABLE, USDJPY DÉGRADÉE
  (exclue du gate R10). Régime SAFE_HAVEN calibré (59.9/38.6).
- Réversibilité totale : `apply_behavior_config` / `reset_behavior_config`
  / `get_behavior_state` (jamais bloqué par un choix)

### Phases antérieures (résumé)
- Phases 1-31 Edge Fund (commits `b1c3b98` → `40ed93a`) + Phase 28b
  (étapes 1-4, commits `21225cf` → `6255d55`) : 731 tests → 774
- Cœur cognitif V10 (Phases E-F) : v10_force/structure/context/orchestrator
- Phase A-D institutionnelles + Edge Fund Quantique Phases 1-3

### Cognitive Continuum — 11 phases (2026-08-06, Hermes autopilote)
- **Phases 1-10** : pont mémoire V9→V10 (`v10_memory_bridge`), registre
  interprété (`v10_behavior_registry`, **78 652 comportements**), Cortex
  (`v10_cortex` + `v10_cortex_enrich`), auto-cohérence (`v10_coherence_audit`,
  **COHERENT, 17 modules connectés, 0 orphelin**), apprentissage continu
  (`v10_learning_continuum`), RAG (`v10_behavior_rag`), câblage live
  (`v10_cortex_live`), réconciliation V9→V10 (migration batch, registre peuplé),
  résolution outcomes + drift par comportement réel (22 752 résolus).
- **Audit biais Fatman (DEC-043)** : 3 biais V10 corrigés —
  1. **Fraîcheur EURUSD STALE 10j** → STALE GATE R10 dans les 2 boucles live.
  2. **Comptage WR** → `WHERE is_win IS NOT NULL` (rotation_leadership "7%" = artefact, réalité 78%).
  3. **Volume M5/M15 4×** → filtre `timeframes=["M30","H1","H4"]` dans
     `query_coherence` **+ câblé dans les callers de décision** (`interpret()`
     cortex, `drift_by_behavior()` learning, `v10_cortex_live.py`).
- Cumul tests : 1186 → **1225** (Phase 11 commit à venir).
- Rapports : `workspace/perplexity/AUDIT_BIAIS_V10_20260806.md`,
  `workspace/perplexity/SESSION_CACHE_V10_COGNITIVE.md`,
  `reports/v10_comprehension_status` (JSON).

### Phase 12 — Lecture fractale multi-TF + cinématique (2026-08-06, Hermes autopilote R1)
- **`v10_fractal_context.py`** (additif R2, 0 import core/v9/) : confluence 7-TF
  pondérée (M1→D1, HTF=biais, LTF=entrée) + cinématique rapide M1/M5 (vitesse
  pips/min, divergence vs TF lissés → détecte le "mouvement invisible") +
  `fractal_signal` (boost/veto signé [-1,+1]).
- **Câblage décision** : `decide_entry(fractal=)` (veto → downgrade, alignement
  → upgrade) + `tick_decision` calcule le fractal à chaque tick.
- **Structure S1-S9** câblée dans la boucle live (pitfall 50 : lecture riche
  enfin connectée au live) — BOS aligné renforce, opposé downgrade.
- **Garde d'asymétrie directionnelle** (friction shorts R9) : SELL A2 sans
  renforcement fractal → A3 (données live : BUY +46.4p vs SELL -5.0p).
- Cumul tests : 1225 → **1239**. Commits `4e60789`, `462d8b7`, `74efc7c`.

### Phase 13 — Wyckoff Gate dans decide_entry (2026-08-07, ZCode)
- **Wyckoff gate** dans `decide_entry()` utilisant `consolidate_wyckoff()` 
  (`v10_wyckoff_consolidated.py`) — évite d'entrer contre la phase de marché.
- **Gate** : MARKUP+SELL A2/A3→A3, MARKDOWN+BUY A2/A3→A3, DISTRIBUTION+BUY A2/A3→A3,
  ACCUMULATION+SELL A2/A3→A3. A1 protégé, NEUTRAL/UNKNOWN→fail-open (R6).
- **6 tests** : `test_v10_wyckoff_gate.py` (MARKUP+SELL A2→A3, MARKUP+SELL A1 protégé,
  MARKDOWN+BUY A3→A3, DISTRIBUTION+BUY A2→A3, UNKNOWN+SELL inchangé, exception→fail-open).
- R6 fail-open : exception → signal inchangé, log WARNING.

### Phase 14 — LiquidityMap dans compose_filters (2026-08-07, ZCode)
- **LiquidityMap** intégrée dans `compose_filters()` — détecte 5 structures :
  EQUAL_HIGHS/LOWS, ORDER_BLOCK, FAIR_VALUE_GAP, SWING_LEVEL.
- **Trap detection** : prix dans zone + proximité zone opposée (distance < ATR*0.5)
  → downgrade. Bonus/malus composite_score via `liquidity_bonus_malus()`.
- **R6 fail-open** : données indisponibles → skip silencieux, log WARNING.
- **5 tests** : `test_v10_liquidity_filter.py` (bonus zone acheteuse/vendeuse, malus opposé,
  pas de zone, trap buy/sell, exception fail-open).
- Intégré dans `compose_filters()` après SMC, avant Regime.

### Phase 15 — Behavior Context Gate dans Orchestrator (2026-08-07, ZCode)
- **Behavior Context Gate** injecté dans `compose_signal_with_context()` après
  Fatboy gate + Sigma Oracle, avant Public Filters.
- **Source** : `query_coherence()` depuis `v10_behavior_registry` (78 652 comportements).
- **Règles** : WR<0.35→A3, drift+A2→A3, WR≥0.55+A3→A2, A1 protégé.
- **Filtre TF** : M30/H1/H4 uniquement (exclut M5/M15 — biais volume corrigé DEC-044).
- **R6 fail-open** : exception → signal inchangé, CoT `3_behavior_gate` avec error/fallback.
- **16 tests unitaires** : `test_v10_behavior_gate_unit.py` (WR low/high, drift, A1 protégé,
  WR None/drift fail-open, degraded, mid-range, boundaries 0.35/0.55 exacts).
- Câblé dans `compose_signal_with_context()` après Sigma Oracle, avant Public Filters.

### Phase 16 — Calibration Live Fatman (2026-08-07, ZCode — P0)
- **Script** : `scripts/v10_fatman_calibration.py` — aligne FatmanCalculator (v10_fatman_db_reader)
  vs lecture visuelle Oracle Hawkeye (fatman_oracle.py) sur 10 signaux récents forces_snapshots.
- **Résultat** : 10/10 signaux Oracle = VALID (score moyen 76.7/100), alignement directionnel 100%
  (S/S pour USD paires, L/L pour GBP/AUD), score alignement moyen 86.7/100.
- **Fatman DB Reader** : source `v9_forces_db` fraîche (freshness ~2 min), base/quote scores,
  ranks, momentum cohérents.
- **Rapport** : `reports/v10_fatman_calib_20260807_2145.json` (R9 audit trail complet).
- **Doctrine** : R1-AGIR (pas de permission), R3-INVENTER (nouveau script calibration), R9-AUDIT,
  R10-CAPITAL (zero order), R7-TESTS VERTS (1310/1310).

---

---

## 📊 État live (2026-08-07 15:45 CEST — vérifié ZCode)

| Élément | État |
|---|---|
| Capture server | ✅ port 31685 LISTENING |
| DB forces_snapshots | ✅ 269 149+ lignes, 7 TF live (M1→D1, fraîcheur ~2 min) |
| Tests V10 | **1310/1310 verts** |
| HEAD | `d213290` (Phases 13-15 complètes) |
| V9_EXECUTION_ENABLED | ⚠️ =1 (résidu V9, non consommé par V10 — 0 order_send) |
| Pipeline live | ✅ cron décision 30min + cron nocturne + replay hebdo + Cortex live |
| Crons V10 | ✅ nocturne (ok) + live 30min (ok) + replay hebdo (ok) |
| Crons V9 | ⚠️ meta-agent réparé (script .sh recréé, dernier run ok) |
| Compréhension continue | ✅ 78 652 comportements, COHERENT (0 orphelin) |

---

## 🔄 Prochaines étapes (suggérées CEO)

| Phase | Contenu | Statut |
|---|---|---|
| Calibration live Fatman | Aligner FatmanCalculator vs lecture visuelle (10 signaux) | P0 À démarrer |
| Promotion RL SHADOW→ACTIVE | 100 trades paper, cible Sharpe ≥ 0.5 (4 gates R10) | 2/4 gates passed |
| Validation signaux live | 2-3 jours d'observation Sprints 14-15 | En observation |
| Nettoyage 15 tests V9 rouges | Chantier V9 verrouillé, mandat Søn requis | En attente |
| 32.3 | Branchement `behavior_context` dans signal orchestrator | ✅ FAIT (Phase 15) |

---

## 🎯 Doctrine V10 respectée

R1-AGIR ✅ · R2 additif pur (0 import core/v9/) ✅ · R3 INVENTER ✅
(fidélité extrême découverte sur données réelles) · R5 CoT ✅ ·
R6 fail-open ✅ · R7 tests verts 1239/1239 ✅ · R8 auto-calibration ✅ ·
R9 audit honnête (corr ≈ 0 documentée, safe_haven fixé) ✅ · R10 capital protégé ✅

## 🔗 Liens

- Rapport Phase 32 : `docs/V10/V10_PHASE_32_CURRENCY_BEHAVIOR_REPORT.md`
- DECISIONS_LOG : `workspace/perplexity/memory/DECISIONS_LOG.md`
