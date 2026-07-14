# ACTIVE_TASKS — Workspace Perplexity

Synthèse opérationnelle des tâches. La source de vérité détaillée reste
`docs/STATE.md` (dernière mise à jour **2026-07-14 — activation générale Phase 13**).
Ce fichier ne fait qu'organiser la même information par statut d'exécution
pour une reprise rapide.

## Terminé — Activation générale Phase 13 (2026-07-14, ZCode + Hermes parallèle)

Motion CEO Søn « go activer tous pour le prochain level go go ». Travail en
parallèle ZCode + Hermes sur `feat/v9-foundation-clean`.

### ZCode (commit `5049d48`)
- **A1** ✅ `V9_TRADER_MINI_ENABLED=1` — weighter baseline Brief Q1 actif
- **A2** ✅ `V9_AUTO_CALIBRATOR_ENABLED=1` — recalibrage propose-only Brief Q2 actif
- **P2** ✅ `V9_SHADOW_MODE_ENABLED=1` — shadow mode actif pour évaluation gated
- **P3-WIRE** ✅ `V9_ADAPTIVE_THRESHOLDS_WIRED_ENABLED=1` — descriptif actif
- **B+C+D** ✅ Audits DB live, Phase 13 gate, Phase 12 double verrou
- **6 tests adaptés** ✅ au nouvel état ON des kill switches
- **P1-RESOLVE** ✅ `resolve_one()` lit `signals.exit_strategy_recommended` en priorité
  sur `DEFAULT_EXIT_STRATEGY`. 3 nouveaux tests, 36/36 verts.
- **SHADOW-EXPAND** ✅ `SHADOW_ENV_OVERRIDES` étendu à trader_mini_weigher + auto_calibrator

### Hermes (commit `2ab07f3`)
- **DB restoration** ✅ DB live restaurée (1.45GB, 510k snapshots, md5 vérifié)
- **Wrapper kill switches** ✅ `config/v9_kill_switches.env` + loader .py + .bat + conftest.py
- **5 tests** ✅ `test_v9_load_kill_switches.py`

### Tests finaux
- **1263 verts + 2 skipped + 0 fail** (baseline 5049d48 = 1258, +5 nets Hermes)

## En cours / restant

| Chantier | Priorité | Effort | Scope | Qui |
|----------|----------|--------|-------|-----|
| **P3-CONSUME** | HAUTE | 6-10h | Consommer `adaptive_*_threshold` dans evaluate_condition/YAML | Hermes |
| Vérification pipeline live | HAUTE | — | Asian open 22h UTC, filtres O4 + signaux DYNAMIC | Hermes |
| **Arbitrage comptage tests** | MOYENNE | 15min | 1 `pytest -q` à HEAD canonique + resync STATE/BOARD/ACTIVE_TASKS (fissure 14/07, session Fable) | Hermes |

## Clôturé — série Autopilot CEO 2026-07-13

- **P6** ✅ `core/v9/vol_regime.py` — ATR-30 → LOW/NORMAL/HIGH/EXTREME
- **P1** ✅ 3 colonnes `signals.(exit_strategy_recommended, tp_pips_recommended, sl_pips_recommended)`
- **Brief O4** ✅ Exclusion NY/After (politique conservatrice Søn)
- **P3** ✅ Module `adaptive_thresholds_at_runtime.py` pur (~200 LOC)
- **P5** ✅ `BEHAVIOR_HISTORY_LOOKBACK 10→50`
- **P3-WIRE** ✅ Câblé dans `_load_shared_context` (kill switch OFF→ON 14/07)
- **P2** ✅ `shadow_evaluator.py` + hook orchestrator (kill switch OFF→ON 14/07)
- **ORDER-BRIDGE** ✅ `order_queue_watcher.py` + CLI

## Clôturé — série Q1→Q5 « saut quantique » (2026-07-13)

Q1 (trader-mini, gated OFF→ON 14/07), Q2 (auto-calibrateur, gated OFF→ON 14/07),
Q3 (dashboard HITL), Q4 (multi-paires), Q5 volet VPS (exécution réelle exclue).

## Clôturé — série de briefs O1-O5 (2026-07-12)

25 ACTIVE + 1 SHADOW. Résolveur live : DYNAMIC. Dataset V9-trader-mini exporté.

## Gelé (ne pas démarrer)
- **Phase 10** (fédération d'agents) — gelée par doctrine R19
- **Phase 12 — exécution d'ordres réelle** — interdit fondateur, E refusé par CEO
- **Entraînement V9-trader-mini** — dataset prêt, GO séparé requis
- **Distillation LLM Phase 13** — pas d'infra locale
