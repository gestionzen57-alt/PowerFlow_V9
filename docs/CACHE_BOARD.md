# CACHE_BOARD — PowerFlow V9

## Rôle
Ce fichier est le tableau de bord compact de reprise.
Il doit pouvoir être relu en 2 minutes maximum au début de chaque session.

## État système — généré automatiquement

<!-- AUTO:STATE -->
<!-- Généré automatiquement par scripts/v9_sync_state.py — 2026-07-21 07:27 UTC -->
<!-- Ne pas éditer manuellement. Pour forcer : python scripts/v9_sync_state.py -->

| Métrique | Valeur | Source |
|---|---|---|
| HEAD | `3ecc3ce feat(v9): Axe 1.3 J3 Walk-Forward — kill switch + cron + doc + tests (4/4 verts)` | `git log --oneline -1` |
| Tests collectés | 2629 | `pytest --collect-only` |
| Tables DB | 28 | `sqlite3 data/v9_forces.db` |
| Index DB | 62 | `sqlite3` |
| Taille DB | 4.22 GB | `du -h` |
| Décisions | 83860 | `SELECT count(*) FROM decisions` |
| Forces snapshots | 146317 | DB |
| Scènes | 84183 | DB |
| Principle evals | 3095516 | DB |
| Régime snapshots | 671864 | DB |
| Paper trades | 193 | DB |
| Principle scores | 413 | DB |
| Principes YAML | 55 (46 ACTIVE + 9 SHADOW) | `ls core/v9/principles/*.yaml` |
| Serveurs MCP | 9 | `ls mcp_servers/*.py` |
| Crons Ready | 26 | `Get-ScheduledTask (PowerShell)` |
| V9_TRADER_MINI_ENABLED | 1 | `config/v9_kill_switches.env` |
| V9_AUTO_CALIBRATOR_ENABLED | 1 | env |
| V9_SHADOW_MODE_ENABLED | 0 | env |
| V9_ADAPTIVE_THRESHOLDS_WIRED_ENABLED | 1 | env |
| V9_EXECUTION_ENABLED | 0 | env |
| V9_LEARNING_OFFSET_ENABLED | 1 | env |
| V9_DYNAMIC_RISK_ENABLED | 1 | env |
| V9_BLACKLIST_SYMBOLS | USDCAD | env |
| V9_GBPUSD_LONG_ONLY | 1 | env (activé 2026-07-18 §6.10) |
| V9_BEAR_PERCEPTION_ENABLED | 0 | env (shadow) |
| V9_CONSTITUTIVE_CURRENCY_FILTER | 0 (défaut OFF, R22) | env (shadow) |
| V9_CYCLE_MEMORY_ENABLED | 0 | env (Phase E, R33) |
| V9_META_STRATEGY_OPTIMIZER_ENABLED | 1 | env (Phase E) |
| V9_BAYESIAN_PREDICTOR_ENABLED | 0 | env (Phase E) |
| V9_PREDICTIVE_ENGINE_ENABLED | 1 | env (Phase E) |
| V9_LEARN_LOOP_ENABLED | 1 | env (Phase E) |

<!-- /AUTO:STATE -->

## Resync 2026-07-21 08h15 UTC (ZCode — Correction roadmap + audit edgefund)

⚠️ **Correction d'erreur roadmap précédente** : l'audit edgefund Opus a été **CLOS
le 2026-07-19** sous motion CEO « oui go full audit 8 axes » (Søn). Verdict
**MARGINAL → GO conditionnel** (605/700 ≈ 86%). 5 actions critiques dérivées
(A1-A5). Roadmap opérationnelle V2 : `docs/ROADMAP.md`.

**Statut actions audit edgefund A1-A5** (CLOS livré 19/07) :
- **A1** Révoquer 4 tokens Telegram + `git rm --cached` `.bak` → ⚠️ **EN ATTENTE CEO**
- **A2** Activer `V9_LOOP_BREAKER_ENABLED=1` → ✅ Actif (rejeu OK post-DROP)
- **A3** Réouverture long-only GBPUSD + collecte OOS T+7j → 🔄 En cours
- **A4** Capture continue 5 autres paires → 🔄 CVD 6/6 OK
- **A5** Watchdog live + tuning TP/SL → ✅ LIVRÉ 19/07

**Roadmap V2 — 6 axes / 24 jours** :
- Axe 1 (J1-J4) : Fondations quantiques (Bayésien + Kelly + Walk-forward + Brier)
- Axe 2 (J5-J9) : Architecture multi-agent (Strategy Pole + Meta + Bayesian)
- Axe 3 (J10-J13) : Robustesse risque (CVaR + DD protector + Risk parity + Stress)
- Axe 4 (J14-J18) : Phase E meta-strategy (V2 + Apprentissage + Cycle memory + Cross-pair)
- Axe 5 (J19-J21) : Audit & observabilité (edgefund CLOS + Cohérence + Telegram)
- Axe 6 (J22-J24) : Hardening (Sécurité + Push canonique + Phase 10)

## Resync 2026-07-17 ~10:15 UTC (ZCode — Activation DynamicRiskManager + Clôture semaine)
- **HEAD** : `c6afebb` — DynamicRiskManager ACTIF (V9_DYNAMIC_RISK_ENABLED=1)
- **6 paires live** : GBPUSD, USDJPY, USDCAD, USDCHF, EURUSD, **AUDUSD** — toutes fraîches < 1 min
- **Charge** : 96.1ms / 6 paires ✅
- **Tests** : 1557 passed / 1 skipped, 0 fail
- **Crons** : 12 Ready + V9CaptureWatchdog Running
- **DynamicRiskManager** : ✅ **ACTIF** (motion CEO Søn). RR planifié 0.53→1.63. Cycles/phases SL/TP adaptatifs.
- **4 SHADOW** : ⏳ Promotion reportée (critère WR>50% n≥10 non atteint). Ré-évaluer lundi/mardi.
- **PRICE_LAG part aujourd'hui** : **2.7%** (2237/82122) — diversification réussie ✅
- **Distribution currency** : **12.5% par devise** — vote-devise NZD corrigé ✅
- **30 commits cette semaine** (ZCode + Opus + Hermes), 11 bugs corrigés
- **Risque weekend** : Aucun. Pas de MT4 (SDI est MT4-only). Watchdog + heartbeat fiables. Le système tient tout seul.
  strict) ; (3) observation 24h en parallèle SHADOW pour cross-validate ; (4) revue
  mardi si WR climat Ok.
- **🎯 Activation lundi 4 SHADOW → ACTIVE** : VOL_GATE n=24 WR 33 % (KO critère
  WR>50 %), ANTAGONIST n=1 (KO n≥10), LOCK/RESPIRATION WR 66.7 % mais n=9 (KO
  n≥10) — wait, actualiser les seuils d'observation avant promotion.

## Resync 2026-07-17 (Opus — Risk Manager Dynamique SHADOW, Phase 13.3)
- **Livré** : gestion du risque adaptative aux cycles/phases (accumulation,
  cassure, trend, distribution, climax, retour). **SHADOW** (évalue, n'applique
  pas). Doctrine **R32**.
- **Modules** : `core/v9/market_cycle_detector.py`, `phase_classifier.py`,
  `dynamic_risk_manager.py` ; hook `trade_engine` étape 4b
  (`result["dynamic_risk"]`) ; kill switch `V9_DYNAMIC_RISK_ENABLED`.
- **Tests** : +54 (1503→1557), suite complète **1556 passed / 1 skipped**.
- **Empirique** : replay 2000 décisions → climax WR 20 % / −6.3 pips (garde-fou
  no-position), trend +1.97 / accumulation +2.46 pips.
- **À décider (CEO)** : activation mode APPLY + réconciliation bornes
  SHADOW [6,25]/[4,40] vs R30 APPLY [5,20].
- **Doc** : `docs/architecture/DYNAMIC_RISK_MANAGER.md`.

## Resync 2026-07-17 ~09:15 UTC (Opus — Validation DRM + look-ahead disculpé)
- **Validation DynamicRiskManager (SHADOW)** : rejeu 2000 décisions → **100 %
  `dynamic`, 0 fallback, 0 crash**. Garde-fou climax OK (WR 20 %). **NON promu
  APPLY** : restructure l'économie (RR 0.53→1.21) et WR = métrique trompeuse.
- **4 SHADOW NON promus** : critère (WR>50 % ET n≥10) non atteint — VOL_GATE
  33 % (n=24), ANTAGONIST n=1, LOCK/RESPIRATION 66.7 % mais n=9.
- **🔬 Look-ahead ExitSimulator DISCULPÉ** : fenêtre résolveur propre
  (`timestamp > start` strict) ; re-résolution intrabar (800, high/low,
  pessimiste) = **89.2 % vs 89.8 % mid-only (Δ+0.5 pt), 0 barre ambiguë**. WR
  haut = géométrie TP 8/SL 15 (RR 0.53), **pas un bug**. Chantier réorienté →
  pilotage espérance/RR.
- **⚠️ Biais distribution** : 85 % des phases classées `distribution` → à
  investiguer avant tout APPLY.
- **Reprise lundi vérifiée** : capture live + heartbeat OK ; **MT4 = seul
  risque** (ni `v9_market_open.py` ni `v9_bootstrap.py` ne le relancent).
- **Rapport** : `docs/reports/dynamic_risk_validation_20260717.md`. Lecture
  seule — aucun `core/v9/*` modifié.

## Resync 2026-07-17 ~08:50 UTC (Opus — Audit clôture semaine)
- **HEAD** : `c601c0c` (commit clôture à suivre)
- **Tests** : **1557 collectés, verts** (suite complète relancée post-fixes)
- **5 paires** : EURUSD, GBPUSD, USDJPY, USDCAD, USDCHF — pipeline actif (snapshot < 2 min)
- **Marché** : OUVERT, ferme 21h UTC (23h Paris). Rouvre dimanche 22h UTC.
- **Fiabilité sim** : `paper_trades` 48.3 % **non fiable** (pips fixes, batch instantané).
  Vrai forward-sim = résolveur `decisions` ; **batch frais 169 → 56.8 % WR / +0.1 pip**
  (≈ breakeven). Cumulé 85.5 % gonflé par l'historique. **Ne pas citer un WR sans caveat.**
- **4 angles morts corrigés** : heartbeat tz (−180 min → `timestamp` UTC), `apply_resolutions`
  code mort (NameError), `V9_ResolveLoop` dry-run → `--apply`, 8 crons `python` nu → `.venv` absolu.
- **12 crons** : tous en `.venv\python.exe -X utf8` + `WorkingDirectory` (fini 0x80070002).
  11 en **S4U** (tournent session fermée) ; `V9CaptureWatchdog` en Interactive (MT4).
- **Boucle fermée** : `V9_ResolveLoop` écrit désormais (`--apply --backup backups/resolve_loop`).
- **⚠️ Reprise lundi** : `--autorestart` relance le capture_server headless mais **PAS MT4**.
  Vérifier que MT4 tourne à la réouverture (sinon pipeline muet → heartbeat alertera).

## Resync 2026-07-16 ~17:12 UTC (ZCode + Opus — DIVERSIFY complet)
- **HEAD** : `b799997` — DIVERSIFY A+B+C livrés (6 commits)
- **Tests** : **1481 passed, 1 skipped, 0 failed**
- **Guards** : 6/6 verts
- **Crons Windows** : **11/11 installés et Ready**
- **Telegram** : ✅ Testé et fonctionnel. Notifications auto-calibrateur + auto-optimizer actives.
- **Dashboard web HITL** : ✅ https://localhost:9090 (son/v9-dashboard-2026)
- **Marché** : OUVERT (Londres). Pipeline actif. Boucle fermée opérationnelle.
- **Doctrine** : R25'' (auto-promotion), R30 (boucle fermée), R31 (vérification vocabulaire/échelle). SOUL.md révisé.
- **Principes** : 44 ACTIVE + 9 SHADOW (dont 4 en observation DIVERSIFY). 6 principes à 0% → réanimés.
- **SignalFusionEngine** : ✅ Branché dans SignalGenerator. Fusionne les principes faibles concordants.
- **Phase 13** : ✅ TERMINÉE.
- **Bug latent corrigé** : auto-promotion R30 était silencieusement plantée (`.get()` sur `sqlite3.Row`) — corrigé.
- **Kill switches** : tous à 1. `V9_EXECUTION_ENABLED=1` (simulation).
- **Problème ouvert** : stale M1/M5 = artefact historique (burst 07-07/08), flux live sain.
- **Problème ouvert** : edge decay PRICE_LAG -18.9% — surveillé par auto-optimizer.
- **Problème ouvert** : token Telegram `AAEP7_...` non purgé de l'historique git.
- **Prochaine étape** : J+2 — vérifier WR des 4 SHADOW (ANTAGONIST_NODE, GRAMMAR_LOCK, GRAMMAR_RESPIRATION, ADAPTIVE_VOL_GATE) → les retirer de `AUTO_PROMOTION_EXCLUDE` + passer ACTIVE si sains.

## Statut global
- Projet : PowerFlow V9
- Nature : refondation cognitive + architecture propre
- Base : dossier V9 vide
- Source de vérité : GitHub
- Doctrine : architecture-first
- État : Chaîne cognitive V9 étendue à 9 couches, TOUTES TERMINÉES — Forces → Scènes →
  Comportements → Fenêtres → Exploitabilité (Phases 1-6) → Régime → Principes → Signal →
  Décision (Phase 9). Phase 7 (déploiement live), Phase 8 (monitoring/calibration/replay),
  Phase 9 (Décision et Principes) **canonisée 2026-07-05**, Phase 9.7 (Paper-Trade Simulator)
  **livrée 2026-07-07**, Phase 9.8 (VPS-READY) **livrée 2026-07-07**, Phase 9.9 (Consolidation
  Complète) **livrée 2026-07-07**, **Phase 9.10 (WIN/LOSS resolver)** **livrée 2026-07-08**,
	  **Phase 13 (recalibrage arbiter)** **livrée 2026-07-10**. **Ménage Phase 13 CEO (2026-07-11)** :
	  71 paper trades clôturés, 102 décisions résiduelles résolues, **0 décision non résolue**.
	  Zone_diagnostics alimentée (ZoneDetector + grammaire complète).
	  **Brief O1 (2026-07-12)** : les 9516 décisions `preparer_entree` sont TOUTES
	  résolues en DYNAMIC (8217) ou SKIPPED (1298, new_york/after), 0 en TP_SL —
	  root cause du blocage précédent = index manquant sur `decisions.decision_id`
	  (corrigé). WR global preparer_entree (tradé, hors SKIP) : 45.5% → **88.5%**
	  (changement de stratégie de résolution, pas du marché). `principle_scores`
	  peuplée pour la 1ère fois en prod (125 lignes). **981 tests verts**
	  (vérifiés 2026-07-12, +51 vs 930 — cf. docs/STATE.md §2026-07-12).
- **Mémoire** : interne V9 (workspace/perplexity/memory/*.md + JOURNAL.md), 0 dépendance mem0
  (archivé 2026-07-07).
- **Doctrine** : 30 règles immuables (règle 28 = Hermes opérateur git unique, ajoutée 2026-07-07 ; **R7/R22/R25'/R28 assouplies 2026-07-14** — motion CEO, cf. DOCTRINE.md + DECISIONS_LOG §2026-07-14).
  - **Série Autopilot CEO 2026-07-13 livrée** (4 commits sur `feat/v9-foundation-clean`) :
    - P6 — `core/v9/vol_regime.py` module pur (197 LOC), ATR-30 → LOW/NORMAL/HIGH/EXTREME,
      calibration empirique 9970 fenêtres M15 GBPUSD (P25=2.13 / P50=3.20 / P75=5.50 /
      P95=11.34 pips), intégration `principle_engine._load_shared_context()` (3 clés
      `vol_regime` / `vol_atr_pips` / `vol_regime_level`).
    - P1 — 3 colonnes `signals.(exit_strategy_recommended, tp_pips_recommended,
      sl_pips_recommended)` peuplées par `session_marche` via DYNAMIC_PROFILES
      (`exit_simulator`). Migration rétrocompatible `_ensure_column` (R8 additif).
      INEFFET j/Q activation Brief O4.
    - Fix HITL — `tests/test_decision_logger_hitl_branching.py` adapté au seuil CEO
      `HITL_CONF_HIGH=80` (1 test obsolète `conf > 65` remplacé par 2 tests cohérents).
- **Brief O4 résolu** — Søn tranchée 13/07 ~01:50 UTC : politique conservatrice
  **exclusion structurelle NY/After** (DYNAMIC_BLACKLIST_SESSIONS +
  DYNAMIC_TRADABLE_SESSIONS dans `core/v9/exit_simulator.py`).
  `signal_generator` retourne `strategy=None` pour ces sessions,
  `decision_logger` defense-in-depth force `aucune_action`. P1 sert
  désormais **asie/london/overlap** uniquement.
  - **HITL_CONF_HIGH 65 → 80** (CEO 13/07 mode silencieux) acté dans
    `decision_logger.py`. Tests `tests/test_brief_o4_blacklist.py`
    (18 verts) + ajustements `tests/test_decision_logger.py`. Commit `bd1ca6f`.
  - **Tests** : **1132 verts + 2 skipped + 0 fail** post O4 (1114 → 1132, +18).
  - **Suite Autopilot reportée** (chantiers CEO distincts, prochaine session) :
    P3 (Adaptive Thresholds 8-12h) > P4 (Event Calendar 6-8h) > P5 (Long-term memory
    4-6h) > P2 (Shadow mode 16-24h, J+2). Documenté `workspace/perplexity/ACTIVE_TASKS.md`
    + `workspace/perplexity/ROADMAP_CLAUDE_CODE.md` (chantiers délégables pour
    sessions Claude Code parallèles).
  - **Décision Brief O4 « biais New York/After »** ✅ résolu 13/07 ~01:50
    UTC (politique conservatrice : NY/After blacklistées structurellement,
    P1 sert désormais asie/london/overlap). Tranchée par CEO autopilot
    (Søn no-answer 60s, R6). Commit `bd1ca6f`. Voir
    `DECISIONS_LOG.md` §2026-07-13 « Brief O4 ».
- **6 décisions §5 VPS** actées 2026-07-07 : A (orchestrateur central), 2a (Telegram HITL),
  3a (SQLite WAL), 4a (EA Phase 7 réutilisé), 5b (watchdog livré), 6a (DNS swap rollback).
- **Série Q1→Q5 « saut quantique » clôturée 2026-07-13** (session Claude Code, parallèle à
  la série Autopilot CEO ci-dessus) : Q1 trader-mini (investigation val + baseline logistique
  stdlib + intégration gated `V9_TRADER_MINI_ENABLED=0`), Q2 auto-calibrateur (propose-only,
  `V9_AUTO_CALIBRATOR_ENABLED=0`), Q3 dashboard web HITL (lecture seule, table `hitl_reviews`
  dédiée), Q4 multi-paires EURUSD/USDJPY/GBPJPY (GBPUSD non-régression prouvée), Q5 volet
  déploiement VPS (exécution réelle exclue). **1191 verts + 2 skipped**, 15 fails pré-existants
  `test_telegram_notifier.py` inchangés (hors périmètre). `core/v9/order_executor.py`
  **jamais écrit** — reste gelé sous `AGENT.md` §Périmètre GELÉ, confirmation explicite et
  distincte requise. Checkpoint : `docs/checkpoints/CHECKPOINT_20260713_QUANTUM_LEAP.md`.
  Détail : `workspace/perplexity/memory/DECISIONS_LOG.md` §"2026-07-12 — Série Q1→Q5".

  **Session 2026-07-06 — Calibration seuils + enrichissement cinématique :**
  - ANTAGONISM_THRESHOLD : 10.0 → 31.39 ✅ (calibration live n=218 M5+, commit `460716f`)
  - COALITION_THRESHOLD : maintenu 5.0 (gain marginal, 89.8% scènes déjà couvertes)
  - PLIURE_THRESHOLD : 3.0 → 1.7 ✅ (proxy corrigé vitesse→pente, P90 sur n=1454 M5+, commit `e9bd9b1`)
  - Cinématique enrichie : `velocite_moyenne`, `acceleration_vraie`, `dispersion_velocite`
    ajoutés dans `_compute_cinematics()` (commit `e2ea619`)
  - 7 champs cinématiques injectés dans `principle_engine._load_shared_context()`
    (`velocite_moyenne`, `acceleration_vraie`, `dispersion_velocite`, `pente`,
    `courbure`, `pliure_detectee`, `pliure_severite`) — données désormais
    évaluables par les principes YAML (commit `db7bb6d`)

  **Gaps résiduels identifiés (audit 2026-07-06, non bloquants) :**
  - `vitesse` dans forces_snapshots = devise de base du symbole uniquement (pas par devise)
    → `velocite_moyenne` reste un proxy d'une seule devise. Levier P3 : enrichir EA MT4.
  - `REGIME_LOOKBACK_BARS = 20` identique pour tous TF (portage V8, non recalibré).
  - `SIMILARITY_THRESHOLD = 0.65` non recalibré sur données live V9.
  - `REPLAY_MIN_CAS = 3` → malus systématique en live naissant (P3, non urgent).
  - Cross-TF direction (h1_dir/m5_dir) calculée sur max(forces) — approximation connue.

## Décision fondatrice
V9 part de zéro.
Aucune mémoire, aucun skill, aucune convention, aucun workflow ancien n'est repris implicitement depuis V8/Hermes.

## Mission produit
Construire un système qui comprend les forces dans leur lecture :
- globale
- temporelle
- zonale
- multi-devises
- fenêtrée
- orchestrée
- fractale
- comportementale

## Ordre cognitif officiel
1. Forces
2. Scènes
3. Comportements
4. Fenêtres
5. Exploitabilité
6. Exécution éventuelle

## Ce que le projet n'est pas
- pas une simple migration technique
- pas un bot de signal prioritaire
- pas un projet RAG en premier
- pas une accumulation de modules
- pas une extension sale de V8

## Ce que le projet doit devenir
- une base saine
- une mémoire fiable
- une doctrine stable
- un squelette agentique propre
- une machine de confrontation / replay / apprentissage continu

## Chantiers actifs
- [A] Doctrine fondatrice V9 ✅
- [B] Structure repo propre ✅
- [C] Politique mémoire V9 ✅
- [D] Inventaire de migration V8 → V9
- [E] AGENT.md racine V9
- [F] Lexique natif V9 ✅
- [G] Formats couche Forces ✅
- [H] Formats couche Scènes ✅
- [I] Formats couches Comportements / Fenêtres / Exploitabilité ✅
- [J] Corrections post-review ✅
- [K] Phase 2A — EA MT4 ✅
- [L] Phase 2B — capture Python + STALE_GATE + forces_reader ✅
- [M] Fusion Phase 2 + harmonisation STALE_GATE ✅
- [N] Phase 3 — Couche Scènes ✅
- [O] Phase 4 — Couche Comportements ✅
- [P] Phase 5 — Couche Fenêtres ✅
- [Q] Phase 6 — Couche Exploitabilité ✅
- [R] Smoke test chaîne complète ✅
- [S] Phase 7 — Déploiement live ✅
- [T] Phase 8 — Monitoring + calibration + replay ✅
- [U] Phase 9 — Décision et Principes ✅ (9/9 node_rule ACTIVE déclenchables)
- [V] Gouvernance documentaire ✅
- [W] Outillage opérationnel Phase 9.5 ✅
- [X] Correctif DST observabilité ✅ (calendrier canonique non modifié — décision explicite)
- [Y] ZoneDetector + grammaire complète ✅ (zone_diagnostics alimentée, 283 tests)
- [Z] Calibration seuils live + cinématique enrichie ✅ (289 tests, 2026-07-06)
  - ANTAGONISM_THRESHOLD 31.39, PLIURE_THRESHOLD 1.7
  - velocite_moyenne / acceleration_vraie / dispersion_velocite dans _compute_cinematics
  - 7 champs cinématiques dans principle_engine._load_shared_context
- [AA] Phase 9.7 — Paper-Trade Simulator ✅ (60 tests, livrée 2026-07-07, commit `aa5c365`)
  - Arbiter, RiskManager, PaperTradeLogger, paper_trades_db, v9_paper_trade_run.py
  - Hit rate par principe (v9_scoring.py) — WIN/LOSS = 0 (attente London/NY)
- [AB] Phase 9.8 — VPS-READY ✅ (20 tests, livrée 2026-07-07, commit `4aa4fd3`)
  - scripts/v9_heartbeat.py (port 31685 + DB freshness + Telegram alive/alert)
  - install_heartbeat_cron.bat (2 schtasks Windows)
  - 6 décisions §5 actées dans DECISIONS_LOG.md
- [AC] Phase 9.9 — Consolidation Complète ✅ (livrée 2026-07-07, voir CHECKPOINT_20260707_PHASE9_9.md)
  - C-1/C-2/C-3 : CONTEXT_CONTRACT.md resync + init_all_dbs() + .gitignore runtime
  - C-4 : docs/V9_FONCTIONNEMENT.md (12 sections, mode d'emploi global)
  - C-5a : 27 YAML principes status uppercase + v9_status (10 ACTIVE / 17 SHADOW)
  - C-5b : tests/test_v9_ops.py (8 tests routing)
  - F-3 : tests v9_calibration (15) + v9_replay (18)
  - F-4 : README.md resync (28 règles, 9 couches, 588 tests, 22 scripts)
  - F-5 : docs/STATE.md resync (Phase 9.7+9.8, 588 tests)
  - F-6/F-7/F-8 : CACHE_BOARD, AGENT.md, DOC_REGISTRY.yml resync
  - Règle 28 ajoutée : Hermes = opérateur git unique
  - Total session 2026-07-07 : 14 commits, 588/588 tests verts

## Risques ouverts
- dérive vers des solutions techniques prématurées
- contamination par anciennes mémoires Hermes
- confusion V8 / V9
- multiplicité des docs sans synchronisation
- perte de fil due aux limites de contexte

## Garde-fous
- Git = source de vérité
- STATE.md tenu à jour
- checkpoint à chaque jalon important
- cache board relu à chaque session
- migration par audit, jamais par héritage implicite

## Pré-réouverture 19/07 §23h UTC — point rapide reprise

- **HEAD** : `289fa93` (origin et local alignés, push `dcd2fed..289fa93` fait 12:18 UTC).
- **Cron watchdog** : `V9_LiveWatchdogLoop` installé ✅, prochaine exec 12:58 UTC.
- **Cron paper trade** : `V9_PaperTradeLoop` ⚠️ KO depuis 12:50 UTC (code
  `-2147024894` = FILE_NOT_FOUND, superviseur ne charge PAS le `.env` kill
  switches) → **refit 23h UTC en CMD admin** :
  `cd /d C:\projet\V9 && scripts\install_v9_paper_trade_loop_wrapper.bat`.
- **Capture server** : ✅ vivant depuis 18/07 23h45 (fix daemon-mort). Le
  watchdog 5 min alerte si DB se vide.
- **Sécurité Telegram** : 4 tokens à rotation BotFather avant 22h UTC
  (8656… 8790… 8932… 8948…).
- **Verdict semaine** : OK si refit 23h + capture_server tient. Sinon lundi
  reproduit la catastrophe du 17/07.
- **Risques** : Phase E = DRAFT (motion CEO, pas livraison), CVaR sizing
  NO-GO walk-forward (OFF), CVD tick-level attend migration DB + EA MT4.
- **Détail** : `docs/STATE.md` §19/07 12h15 + `docs/security/PRE_REOUVERTURE_CHECKLIST_20260719.md`.

## Prochaines actions (post-session 2026-07-06)
1. **Observation live** — ouvrir le marché avec `scripts/v9_market_open.py --market-open`,
   surveiller `--watch signals`/`--watch decisions` sur les nouveaux seuils calibrés.
2. **Recalibration P2** (après n≥50 sessions live) :
   - `REGIME_LOOKBACK_BARS` par TF (dict M5/H1/H4/D1)
   - `SIMILARITY_THRESHOLD` sur données live V9
3. **Levier P3** (non urgent) : `REPLAY_MIN_CAS = 1` temporaire pendant montée en charge live.
4. **Phase 10** : GELÉE — ne pas ouvrir tant que stabilisation live Phase 9 non confirmée.

## HEAD actuel
- Branche : `feat/v9-foundation-clean`
- Dernier commit : voir `git log --oneline -1` (R28 assouplie 14/07 : push délégable sur instruction directe de Søn)
- Tests : **divergence à arbitrer** — 1285 (STATE §2026-07-14, post `0c0c334`) vs 1263 (BOARD 14/07, « baseline 5049d48 = 1258 »). Arbitrage : 1 `pytest tests/ -q` à HEAD sur la machine canonique, puis resync STATE/BOARD/ACTIVE_TASKS sur ce chiffre unique (cf. DECISIONS_LOG §2026-07-14 « Session Fable »).
- Dernier resync de cette section : 2026-07-14 (session Fable).

## Références pivots
- docs/STATE.md
- docs/CACHE_BOARD.md (ce fichier)
- workspace/perplexity/ACTIVE_TASKS.md
- workspace/perplexity/memory/DECISIONS_LOG.md
- docs/checkpoints/CHECKPOINT_2026-07-05_MEGA_V9.md
- docs/deployment/V9_AUTOMATION_RUNBOOK.md
- core/v9/config.py — seuils calibrés
- core/v9/scene_builder.py — _compute_cinematics enrichie
- core/v9/principle_engine.py — _load_shared_context enrichi
- scripts/v9_calibration.py — proxy PLIURE corrigé
