# V10 STATE — État du pipeline cognitif V10

**Dernière mise à jour** : 2026-08-05 (~09:00 UTC) — ZCode (mandat CEO)
**Branche active** : `feat/v9-foundation-clean`
**HEAD courant** : Phase 32 Currency Behavior (à committer sur 6255d55)

---

## ✅ Phases livrées

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

---

## 📊 État live (2026-08-05 ~08:00 UTC)

| Élément | État |
|---|---|
| Capture server | ✅ port 31685 LISTENING (PID 18344) |
| DB forces_snapshots | 257 395+ lignes, fraîcheur ~1 min |
| Tests V10 | **774/774 verts** |
| HEAD | 6255d55 + Phase 32 (à committer) |
| Régime marché (calibré) | SAFE_HAVEN — lecture recalibrée |

---

## 🔄 Prochaines étapes (suggérées CEO)

| Phase | Contenu | Statut |
|---|---|---|
| 32.2 | Table stats comportementales par (devise, TF, session, état) → R4 | À valider |
| 32.3 | Branchement `behavior_context` dans signal orchestrator | À valider |
| 32.4 | Watchdog rotation de régime (alerte SAFE_HAVEN↔RISK_ON) | À valider |
| 20++ | Reconstruction forces natives V10 (TA lecture) | À valider |
| 25+ | Validation 100 trades paper (cible Sharpe ≥ 0.5) | À valider |
| 28+ | Promotion RL SHADOW→ACTIVE si 100 trades ≥ 4 gates | À valider |

---

## 🎯 Doctrine V10 respectée

R1-AGIR ✅ · R2 additif pur (0 import core/v9/) ✅ · R3 INVENTER ✅
(fidélité extrême découverte sur données réelles) · R5 CoT ✅ ·
R6 fail-open ✅ · R7 tests verts 774/774 ✅ · R8 auto-calibration ✅ ·
R9 audit honnête (corr ≈ 0 documentée) ✅ · R10 capital protégé ✅

## 🔗 Liens

- Rapport Phase 32 : `docs/V10/V10_PHASE_32_CURRENCY_BEHAVIOR_REPORT.md`
- DECISIONS_LOG : `workspace/perplexity/memory/DECISIONS_LOG.md`
