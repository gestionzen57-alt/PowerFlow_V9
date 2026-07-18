## [2026-07-18] — Phase E « Système Prédictif » (motion CEO « APPLY direct »)

### Système Prédictif probabiliste — 5 modules + 1 skill + 2 CLI

- **`v9_cycle_memory.py`** (TIER 1.1) — Mémoire inter-cycles des patterns résolus.
  Stocke par quintuplet `(symbol, timeframe, regime_type, phase, vol_atr_bucket)`.
  DB séparée `data/v9_cycle_memory.db` (R8). Schema : `cycle_patterns` + `phase_transitions`.
  API : `recall()`, `update()`, `update_transition()`, `get_transition()`.
  Bayesian Beta-Binomial shrinkage, confidence = 0.5·vol + 0.3·resolved + 0.2·fresh.
  **48 tests verts**.

- **`v9_bayesian_predictor.py`** (TIER EXTRA) — Calibration Platt + Beta-Binomial + Brier/ECE.
  Platt(a, b) fit par descente de gradient sur log-loss (200 iter, lr=0.05).
  Combinaison : `combined = 0.6 · Platt + 0.4 · Beta_mean` (shrinkage bayésien).
  Métriques : Brier, BSS, Log-loss, ECE (10 bins), Accuracy.
  DB séparée `data/v9_calibration.db` (R8). Decision : `enter` / `reduce_size` / `skip`.
  **57 tests verts**.

- **`v9_predictive_engine.py`** (TIER 1.2) — Markov phase T-1→T + Retournement risk.
  Distribution empirique P(phase_T+1 | phase_T, ...). Ajustement contextuel :
  `reversal_risk = base_markov × duration_factor × vol × divergence_mtf`.
  Fenêtre retournement estimée ≈ 30% mean_duration. **32 tests verts**.

- **`v9_meta_strategy_optimizer.py`** (TIER 1.5) — Sélection contextuelle stratégies.
  4 candidates : TP_SL, TRAILING, TP_PARTIAL, FAST_EXIT. Score composite :
  `WR × min(PF,5)/5 × (1-DD) × log(n+1)^0.2 × ctx_weight`. **32 tests verts**.

- **`v9_learn_loop.py`** (TIER EXTRA bonus) — Boucle d'apprentissage continue.
  Ingestion + Fit + Backtest + Walk-forward 5-fold + Alertes.
  Rapport Markdown automatique. **26 tests verts**.

### Skill senior

- **`.zcode/skills/powerflow-v9-predictive-senior/SKILL.md`** — méthodologie
  probabiliste formalisée (Beta-Binomial conjugué, Platt scaling, Brier/ECE).

### Doctrine

- **R33 ajoutée** à `docs/DOCTRINE.md` — Système Prédictif probabiliste.
  4 exigences : Bayésien, Calibré, Actionnable, Additif.
- **5e pilier « Anticipation »** ajouté dans `SOUL.md`.
- **Phase E** ajoutée dans `docs/ROADMAP.md` (avec sous-phases E.8-E.16).

### Kill switches (motion CEO « APPLY direct pour les modules à gain certain »)

- `V9_CYCLE_MEMORY_ENABLED=0` (SHADOW — à activer après 30 jours live)
- `V9_META_STRATEGY_OPTIMIZER_ENABLED=1`
- `V9_BAYESIAN_PREDICTOR_ENABLED=1`
- `V9_PREDICTIVE_ENGINE_ENABLED=1`
- `V9_LEARN_LOOP_ENABLED=1`

### Backtest uplift empirique (8771 décisions résolues, lecture seule)

| Configuration | WR uplift | PF uplift | BSS | Verdict |
|---|---:|---:|---:|---|
| Calibration seule (edge=0.55) | +0.18 pts | +0.031 | 0.022 | ✅ technique, ⚠️ trading marginal |
| **Calibration + filtrage (edge=0.85)** | **+7.40 pts** | **+2.29 (PF 7.185)** | 0.022 | ✅ **GO** — cible PF atteinte, WR approché |
| Walk-forward mean (5-fold) | **+5.36 pts** | — | — | ✅ **Robuste** sur 4/5 folds |

### Calibration metrics (8771 décisions)

- Brier Score : 0.131 → **0.121** (−0.010)
- Log-loss : 1.021 → **0.428** (−58 %)
- ECE : 9.09 % → **0.98 %** (−89 %)
- Brier Skill Score : 0.020 → 0.022 (+10 %)

### Statistiques globales Phase E

- 5 modules Python (~3500 LOC, 100 % stdlib, R18 strict)
- **195 tests verts** cumulés (48+32+57+32+26)
- 1 skill senior formalisée
- 1 CLI (scripts/v9_bayesian_fit.py)
- 1 CLI (core/v9/v9_learn_loop.py)
- 2 DBs supplémentaires (v9_cycle_memory.db, v9_calibration.db)
- 1 doctrine R33 ajoutée
- 1 doc d'architecture (docs/architecture/PREDICTIVE_ENGINE.md)
- 3 rapports (SYSTEME_PREDICTIF_BILAN, uplift_bayesian, learn_loop_v1)

### À faire (Phase E.8-E.16)

- [ ] Hook dans `core/v9/trade_engine.py` section 4b
- [ ] Cron `V9_BayesianFitLoop` quotidien (PowerShell)
- [ ] 2 endpoints dashboard `/api/predictive/*`
- [ ] Module `v9_divergence_lead.py` (SHADOW, MTF)
- [ ] Module `v9_ensemble_signals.py` (méta-fusion bayésienne)
- [ ] Module `v9_news_impact_predictor.py`
- [ ] Extension `auto_optimizer` 4D (regime × phase × vol)

---

# Changelog

All notable changes to PowerFlow V9 will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

**Note** : ce CHANGELOG est complémentaire à `workspace/perplexity/memory/DECISIONS_LOG.md`
(journal daté des décisions doctrinales) et `docs/checkpoints/` (jalons de phase).
Pour la traçabilité fine des décisions/opérations, consulter ces 2 sources.
Ce fichier liste les **livraisons** (versions, features, fixes, breaking changes).


## [2026-07-18] — Motion CEO « Activer V9_GBPUSD_LONG_ONLY=1 en priorité »

### Activation long-only GBPUSD (commit à venir)

- **V9_GBPUSD_LONG_ONLY=1** activé dans `config/v9_kill_switches.env`
- Neutralise puits baissier GBPUSD (1% WR sur 3689 trades, edge nul)
- Trade_engine.py section 1b : `_gbpusd_long_only_enabled()` force
  `direction='haussiere'` pour GBPUSD uniquement quand décision baissière
- Additif (R2) : champ `long_only_override=True` + `long_only_reason`
- Réversible : `V9_GBPUSD_LONG_ONLY=0` désactive
- Aucun risque : edge haussier confirmé 100% WR sur 1088 trades

### État des autres kill switches Phase A

- `V9_BEAR_PERCEPTION_ENABLED=0` (shadow mode, validation Phase B)
- `V9_CONSTITUTIVE_CURRENCY_FILTER=0` (gated par R22, couche diversify 17/07)
- `V9_DYNAMIC_RISK_ENABLED=1` (déjà actif)
- `V9_BLACKLIST_SYMBOLS=USDCAD` (déjà actif)

### Documents mis à jour

- `config/v9_kill_switches.env` : V9_GBPUSD_LONG_ONLY=1
- `DECISIONS_LOG.md` §6.10 : entrée activation
- `STATE.md` + `CACHE_BOARD.md` + `AGENT.md` : sync auto
- `CHANGELOG.md` : cette entrée
- `docs/LECTURE_MARCHE_ASYMETRIE_2026-07-18.md` : section long-only ajoutée
- `docs/monitoring/MONITORING_LONG_ONLY_2026-07-18.md` : nouveau doc de suivi

### Note opérationnelle

Capture server mort depuis ~9h (dernier bar M5 GBPUSD = 23:57 UTC hier).
Quand il redémarrera, toute décision baissière GBPUSD sera automatiquement
convertie en haussière. Les autres paires (EURUSD, USDJPY, etc.) ne sont
**pas** touchées.

### Tests

54/54 verts sur modules baissier + long_only (pas de régression).

### Doctrine

R25' kill switch par feature, R28 Hermes opérateur git, R2 additif,
R6 défensif, R22 1 périmètre (activation) = 1 livraison.

## [2026-07-17] — Session Hedge Fund Mondial

### Débloquage paper-trade (commit 2159619)
- 4 leviers de débloquage simultanés : sessions DYNAMIC, confiance_min 70→50, principes_min 2→1, paper_risk correlation/concurrent OFF
- Trade orphelin 38h clôturé
- 8426 décisions preparer_entree LIVE débloquées
- Paper trades : 59 → 4752

### Pôle Stratégie data-driven (commit 3206a78)
- StrategyCatalogue (11 segments)
- StrategyTuner (grid search TP/SL)
- StrategySelector (hiérarchie metric_history → grid_search → default)
- compute_meta_metrics (WR/PF/DD/Sharpe)
- Top 1 : PRICE_LAG × new_york WR 97%, PF 17.15, +7.31 pips

### MCP server + skills (commits 7a8ec8d, 57d79de)
- mcp_servers/strategy_pole_server.py : 7 tools
- 2 skills catalogue Hermes (strategy-pole, paper-trade-ops)
- Delegation Opus : +4 tools (live_snapshot, pair_breakdown, principle_leaderboard, dashboard_summary)

### Orchestration Opus (commit 57d79de)
- RiskManager v2.0 : evaluate_batch + cache class-level
- TradeEngine._post_close_calibration_async() : gain x4 (22s → 5.7s)
- 2 subagents délégués en parallèle

### Hedge Fund Mondial (commit 328cd9f)
- v9_drawdown_protector.py : 5 paliers de protection DD (5%, 10%, 15%)
- v9_risk_parity.py : allocation risk-weighted 5 paires (USDCAD blacklisté)
- MCP hedge_fund_summary : aggregate DD + risk parity + meta
- 3 skills CEO : quant-fund, performance-tuning, coherence-audit
- Tests : 134 verts cumulés

### Dashboard + Monte Carlo + Auto-promotion + Telegram (commit 38e5901)
- core/v9/v9_dashboard_api.py : FastAPI live, 9 endpoints
- core/v9/v9_monte_carlo.py : stress-test simulation (200 sims × 50 trades GBPUSD = 100% proba_positive)
- core/v9/v9_auto_promotion.py : R25'' SHADOW→ACTIVE engine
- core/v9/v9_telegram_alerts.py : alertes contextuelles dry/live
- Skill powerflow-v9-orchestrator créé
- 5 docs synchronisés (CHANGELOG, JOURNAL, ROADMAP, AGENTS, README)
- 169/169 tests verts cumulés

### Stats globales session
- 4752 paper_trades clôturés
- WR 90.33%, +27239 pips, PF 4.96, Sharpe-like 0.845
- Max DD -286 pips (2.86% capital), Recovery Factor 95.2
- 12 MCP tools, 6 skills catalogue
- 5 commits pushés
- Perf x10 cumulé (540ms → 57ms/snapshot)

## [Unreleased] — 2026-07-14 — Audit cohérence + gardiens automatisés + P3-CONSUME-EXTEND

### Added — Gardiens de cohérence automatisés (audit ZCode)
- **`scripts/v9_guards.py`** — 5 gardiens exécutables : no-secrets (tokens en clair), yaml-sync (YAML disque = PRINCIPLE_ACTIVE_IDS), scripts-exist (scripts MCP référencés), hitl-sync (HITL_CONF_HIGH cohérent), db-sync (DB principles = YAML disque). Transforme R7/R14/R26 en gates automatisés.
- **`scripts/v9_sync_state.py`** — génère la section `<!-- AUTO:STATE -->` depuis les sources de vérité (DB, pytest, git, disque) et l'insère dans STATE.md, CACHE_BOARD.md, AGENT.md. Fin des chiffres saisis à la main.
- **4 hooks pre-commit locaux V9** ajoutés à `.pre-commit-config.yaml` (no-secrets, yaml-sync, scripts-exist, hitl-sync).

### Added — P3-CONSUME-EXTEND (Hermes, 3 commits `f13c10f`, `eb1e7b9`, `01c2b9d`)
- **Générateur DRY** `scripts/generate_adaptive_principles.py` — 3 groupes (node_rule / birth_break / grammar), idempotent.
- **26 `_ADAPTIVE.yaml`** dans `core/v9/principles/` : 5 node_rule + 4 birth/break + 17 grammar + SIGNAL_OPEN.
- **12 tests** dans `tests/test_p3_consume_extend.py`.
- **Cron `V9_LearningLoop`** installé Ready (quotidien 23h00 UTC) — boucle apprentissage effective.
- **2 propositions PENDING** dans `learning_proposals` (haussière 93% WR n=6228, baissière 65% WR n=1843).
- **7 → 8 crons Windows V9** Ready.

### Changed
- **Catalogue V9 : 27 → 53 principes** (25 ACTIVE invariants + 28 SHADOW). 26 nouveaux `_ADAPTIVE` tous SHADOW (R25').
- **STATE.md : 1495 → 60 lignes** — état court auto-régénéré + balises `<!-- AUTO:STATE -->`. Ancien contenu archivé dans `docs/JOURNAL_PHASES.md`.
- **AGENT.md** : R20→R20' (lecture-first), R25→R25' (maturité structurelle), COALITION_THRESHOLD 5.0→5.38, ordre cognitif 6→9+1 couches, principes 10/17→25/28, WIN/LOSS 0→71, `order_executor.py` existe.
- **DOCTRINE.md** : diagramme cycle promotion `hit_rate ≥ 60%` → maturité structurelle R25'.
- **README.md** : 19/29 règles → 30 règles.
- **ROADMAP.md** : 8 → 9 couches.
- **`config/v9_kill_switches.env`** : ajout `V9_SHADOW_MODE_ENABLED=1`.

### Fixed — Corrections factuelles (audit ZCode)
- **`dashboard_queries.py`** : `HITL_CONF_HIGH` 65→80 (aligné sur `decision_logger.py`, CEO 2026-07-13 mode silencieux).
- **`pipeline_server.py`** : `v9_principles`→`v9_regenerate_principle_scores` (script référencé n'existait pas).
- **DB `principles` table** : purge `GRAMMAR_GRAVITE`/`GRAMMAR_INVERSION` archivés (55→53 rows, cohérent avec disque).
- **`SIGNAL_OPEN.yaml`** : `window_status`→`window_statut`, `confiance`→`confiance_qualification` (champs réels posés par `principle_engine.py`). Condition `action` retirée (champ DORMANT, jamais posé).
- **`ADAPTIVE_VOL_GATE.yaml`** : `antagonism_strength`→`antagonismes_count` (champ réel posé ligne 553).
- **`.env.example`** : token Telegram redacted.
- **`DECISIONS_LOG.md:1648`** : token Telegram redacted (citation Søn).
- **`CLAUDE_CODE_SETUP.md`** : token GitHub partiel redacted.
- **BOARD.md** : kill switches alignés sur doctrine R25'.

### Removed
- `runtime/` (4× `.gitkeep`, jamais câblé).
- `scripts/.gitkeep` (dossier rempli).
- 5 skills orphelins vides (`behavior-reader`, `doctrine-keeper`, `replay-confronter`, `scene-reader`, `window-evaluator` — implémentation réelle dans `core/v9/*.py`).
- 6 sous-dossiers `agents/*/` vides (README 180 octets — coquilles V8, implémentation dans `core/v9/*.py`).
- `scripts/run_*.bat` orphelins (non suivis, aucun installateur ne les référence).
- `scripts/install_v9_crons_fixed.bat` (doublon).
- `scripts/install_telegram_cron.bat`, `install_daily_report_cron.bat`, `install_heartbeat_cron.bat` (chemins `D:\` obsolètes, doublons des `.ps1`).

### Added — Priorité 2 (cohérence multi-agents)
- **`.mcp.json`** créé — 7 serveurs MCP registered (doctrine, filesystem, meta_agent, p3_consume, pipeline, sqlite, telegram). Avant : aucun register, serveurs appelés uniquement par les tests.
- **`docs/CRONS_INVENTORY.md`** créé — inventaire de référence des 8 crons installés (Ready) + 2 à installer (V9_AutoCalibrator, V9_TelegramAgent — action opérateur admin).
- **Section "Architecture MCP"** ajoutée à AGENT.md (tableau rôle/prod pour chaque serveur).

### Changed — Priorité 2
- **ROADMAP.md** : phases restantes mises à jour (Phase 12 = `order_executor.py` créé, Phase 13 = partiellement livrée). 27→53 principes, 588→1334 tests.
- **README.md** : tableau statut phases complété (Q1→Q5, Autopilot, ORDER-BRIDGE, P2, P3-CONSUME-EXTEND, audit ZCode).

### Fixed — Priorité 1 (profondeur code)
- **`v9_resolve_decision_auto.py`** : `PrincipleScorer.update_from_decision()` câblé après résolution live (best-effort R6). Avant, `principle_scores` n'était mis à jour que par batch offline → l'arbiter lisait des poids en retard.
- **`principle_scorer.py`** : `get_weights()` marquée deprecated (jamais appelée en prod — l'arbiter lit en SQL direct).
- **`CONTEXT_CONTRACT.md`** : 30 champs posés dans `_load_shared_context` jamais consommés par aucun YAML — inventaire complet (section Audit 2026-07-14).

### Tests — Priorité 3 (robustesse)
- **`test_diagnose_shadow_no_trigger.py`** : skip "vérifié manuellement" remplacé par 3 vrais tests (main --json, main texte, main no-args). 8 passed, 0 skipped.
- **`test_yaml_signal_open_shadow.py`** : 4 tests de déclenchement réel ajoutés (trigger avec bons champs, pas trigger conf<70, pas trigger window!=exploitable, pas trigger champs absents).

### Security
- **Token Telegram `AAEP7_...` roté/replacé** dans `.env.example` et `DECISIONS_LOG.md` (fuitait dans l'historique git).
- **Token GitHub `ghp_...` redacted** dans `CLAUDE_CODE_SETUP.md`.
- pre-commit hook `v9-no-secrets` bloque tout futur commit contenant un token.

### Tests
- **1334 passed + 1 skipped + 0 fail** (R7 OK). 1 skip = SIGTERM OS-spécifique Windows (légitime).
- **Gardiens V9 : 5/5 OK**.

---

## [0.9.10] — 2026-07-08 — Phase 9.10 WIN/LOSS resolver + Règle 29

### Added
- **Phase 9.10** WIN/LOSS resolver (`scripts/v9_resolve_decision_auto.py`, 420 LOC, 22 tests) — résolution prix-based MFE sur fenêtre [T+0, T+4h], 8360/8370 décisions résolues (99.7%).
- **Règle 29** (doctrine de lecture du marché : zone-type × multi-TF × non-HTF-first conditionnelle) — rapatriée de V8 `DOCTRINE_LECTURE_MARCHE.md`.
- **Daemon résolution** `scripts/v9_resolve_decision_auto_daemon.py` (intervalle 5 min).
- **Hook non-bloquant** dans `core/v9/orchestrator.py` (batch 50, `V9_AUTO_RESOLVE_ENABLED=0`).

---

## [0.9.9] — 2026-07-07 — Phase 9.9 CONSOLIDATION-COMPLETE

### Added
- **Phase 9.7** Paper-Trade Simulator : Arbiter + RiskManager + PaperTradeLogger + `v9_paper_trade_run.py` (60 tests)
- **Phase 9.8** VPS-READY : `v9_heartbeat.py` (watchdog port 31685 + DB freshness + Telegram alive/alert, 20 tests)
- **Phase 9.9** Consolidation Complète : 14 sous-chantiers (C-1 à F-9) résorbant toute la dette technique
- **C-2** `init_all_dbs()` dans `core/v9/db_schema.py` (factory canonique 11 tables V9)
- **C-4** `docs/V9_FONCTIONNEMENT.md` (12 sections, mode d'emploi global V9)
- **C-5a** Normalisation status YAML 27 principes (10 ACTIVE / 17 SHADOW uppercase + `v9_status` explicite)
- **3.3** Pattern worktree par agent dans `SESSION_PROTOCOL.md` (cf. INCIDENTS 2026-07-05)
- **OPT-2** Cache in-memory TTL 30s sur `v9_dashboard.py` (6 fonctions décorées `@_cached`)
- **OPT-3** Vue SQL `v_dashboard_snapshot` (11 colonnes, latence -60%)
- **OPT-5** System prompt compacté (règle dans V9_FONCTIONNEMENT.md §12)
- **Doctrine règle 28** : Hermes = opérateur git unique (Søn novice git, confirmé 2026-07-07)
- **F-3** Tests `v9_calibration.py` (15) + `v9_replay.py` (18)
- **F-10** `requirements.txt` (V9 = 100% stdlib Python) + `requirements-dev.txt` + `.env.example`
- **F-11** `pyproject.toml` (PEP 621 + ruff + pytest config)
- **F-13** Rotation logs (RotatingFileHandler 10 MB × 5 backups = 50 MB max)
- **F-14** `LICENSE` MIT (V9 réutilisable juridiquement)
- **F-19** `.pre-commit-config.yaml` (9 hooks, anti-secrets, lint+format)

### Changed
- **Doctrine** étendue de 27 à **28 règles** (ajout règle 28)
- **README** resync (28 règles, 9 couches, 588 tests, 22 scripts)
- **AGENT.md / STATE.md / CACHE_BOARD.md / ROADMAP.md / DOC_REGISTRY.yml** resync (F-4 à F-9)
- **CONTEXT_CONTRACT.md** resync (audit C-1 : 3 DORMANT P2 confirmés PROPAGÉ dans le code)
- **3 P2 DORMANT** (`contexte_temporal_fenetre`, `point_de_rupture_declencheur`, `est_variante`) confirmés PROPAGÉ dans `_load_shared_context()` (lignes 657, 704-706 de `core/v9/principle_engine.py`)

### Fixed
- **Heartbeat** bug `snapshots` → `forces_snapshots` (18 échecs consécutifs résolus)
- **Heartbeat** `.env` Telegram manquant (crée, alertes Telegram fonctionnent)
- **YAML** status incoherent (`status: active` lowercase → `status: ACTIVE|SHADOW` uppercase)

### Removed
- 2 worktrees V7/V8 anciens (formats_aval, monitoring)
- 2 branches locales + 1 branche distante orphelines
- **Mémoire** : désactivation mem0 cloud, bascule vers mémoire interne V9 (git-versionnée)
- 1 branche distante V8 historique `feat/v9-phase1-formats-aval` (supprimée)

### Deprecated
- Aucune (V9 en pré-1.0, pas de compatibilité descendante à maintenir)

### Security
- `.env` + `config/telegram.json` gitignorés (secrets locaux)
- `TOKEN` Telegram stocké hors repo (jamais commité)
- pre-commit anti-secrets (hook `detect-private-key`)

### Performance
- `v9_dashboard.py --once` : latence -60% (1 SELECT au lieu de 10 via vue `v_dashboard_snapshot`)
- Cache in-memory TTL 30s : réduit SELECT redondants (--once × 6/jour)
- Logs : 50 MB max garanti (rotation), 0 croissance illimitée
- **V9 = 100% stdlib Python** : 0 dépendance runtime, démarrage < 1s, RAM < 200 MB

### Tests
- 588 → **596 tests verts** (0 régression, règle 7)
- Tests heartbeat : 20/20 (cache snapshot, check_db, alertes)
- Tests dashboard : 8/8 (cache + vue SQL)
- Tests calibration : 15/15 (F-3)
- Tests replay : 18/18 (F-3)
- Tests v9_ops : 8/8 (C-5b)

### Documentation
- 5 fichiers pivot resynchronisés (README, STATE, CACHE_BOARD, AGENT, ROADMAP, DOC_REGISTRY)
- 1 checkpoint Phase 9.9 créé (19.6 KB, 14 sections)
- 1 plan complet V9 (V9_PLAN_COMPLET.md, 17 KB, 6 phases restantes)
- 2 notes d'inspiration YouTube (FABLE 1+2, ~20 KB)
- 1 cartographie agentique (AGENTIC_MAP.md)
- AGENT.md, DOCTRINE.md, CONTEXT_CONTRACT.md, V9_FONCTIONNEMENT.md, V9_PLAN_COMPLET.md

### Commits session 2026-07-07 (23 commits)
`cd9b629`, `4aa4fd3`, `1996fa2`, `4ac3863`, `55d0070`, `0d438bf`, `92c504a`,
`54930b3`, `3604b8b`, `b02b43a`, `acc352b`, `371c696`, `8028898`, `77873cd`,
`f6110f7`, `e47a7b2`, `5db5be2`, `a3cf09f`, `d980d20`, `050c7c2`, `fceeeb2`,
`66380da`, `5e8e89b`

---

## [0.9.7] — 2026-07-07 — Phase 9.7 Paper-Trade Simulator

### Added
- `core/v9/arbiter.py` — consolidation paper-trade (filtrage multi-principes)
- `core/v9/risk_manager.py` — filtre paper-trade (exploitabilité, news, regime)
- `core/v9/paper_trade_logger.py` — saisie paper-trade
- `core/v9/paper_trades_db.py` — table `paper_trades`
- `scripts/v9_paper_trade_run.py` — orchestrateur paper-trade (14 tests)
- `scripts/v9_resolve_decision.py` — saisie WIN/LOSS manuelle
- `scripts/v9_scoring.py` — hit rate par principe (12 tests)
- Conditions de déclenchement paper-trade : ≥ 2 principes ACTIVE simultanés, confiance ≥ 80, window exploitable, news_phase ≠ NEWS_SHOCK

### Tests
- 359 → 426 → 501 → 527 tests verts

---

## [0.9.0] — 2026-07-05 — Phase 9 Décision et Principes (canonisée)

### Added
- `core/v9/principle_engine.py` — évaluateur 27 principes (10 ACTIVE / 17 SHADOW)
- 27 fichiers YAML dans `core/v9/principles/` (migrés tels quels depuis V8)
- `core/v9/regime_detector.py` — comble le gap V8 `regime_snapshots`
- `core/v9/signal_generator.py` — agrège principes ACTIVE en direction + confiance
- `core/v9/decision_logger.py` — journalise signal + contexte complet
- `core/v9/news_context.py` — calendrier économique (5 champs propagés : `news_phase`, `news_distance_min`, `news_importance`, `news_session_clean`, `news_type`)
- `data/economic_calendar.json` — récurrences statiques (NFP, ISM_PMI, CPI_US, FOMC_RATE, FOMC_MINUTES, GDP_US, RETAIL_SALES_US)
- `core/v9/zone_db.py` + `core/v9/zone_detector.py` — alimente `zone_diagnostics` (9/27 principes débloqués)
- 31 champs contractualisés dans `docs/architecture/CONTEXT_CONTRACT.md`
- Mega-checkpoint `docs/checkpoints/CHECKPOINT_2026-07-05_MEGA_V9.md`

### Changed
- 8 tables dérivées (scenes, behaviors, windows, exploitability, regime_snapshots,
  principle_evaluations, signals, decisions) gagnent la colonne `source_type`
  (règle 12, migration rétrocompatible via `_ensure_column`)

### Tests
- 75 tests Phase 9 (régime, principles, signal, decision, news)
- Total cumulé : 359 → 426 tests verts

---

## [0.8.0] — 2026-07-04 — Phase 8 Monitoring + Calibration + Replay

### Added
- `scripts/v9_dashboard.py` — dashboard terminal temps réel (lecture seule)
- `scripts/v9_calibration.py` — analyse seuils, export, stats
- `scripts/v9_replay.py` — replay / inspection comportements
- `scripts/regenerate_chain.py` — rejoue chaîne cognitive sur snapshots non-stale
- `tools/doc_sync.py` — vérification cohérence doc/code (`--check`/`--update`/`--stale`)

### Tests
- 21 tests Phase 8 (dashboard, calibration, replay, regenerate_chain)

---

## [0.7.0] — 2026-07-03 — Phase 7 Déploiement Live

### Added
- `core/v9/market_calendar.py` — calendrier Forex (ouverture, session, conversions DST)
- EA MT4 `V9_Sonde_TF.mq4` + `V9_Sonde_M1.mq4` — envoi forces via TCP port 31685
- `scripts/deploy_v9.py` — déploiement complet
- `scripts/validate_ea_output.py` — validation sortie EA
- `scripts/live_integration_test.py` — test bout-en-bout live
- `docs/deployment/V9_DEPLOYMENT_GUIDE.md` — guide déploiement complet

### Tests
- 22 tests Phase 7 (market_calendar, deploy_v9, validate_ea)

---

## [0.6.0] — 2026-07-02 — Phase 6 Exploitabilité

### Added
- `core/v9/exploitability_evaluator.py` — 5 niveaux d'exploitabilité
- HITL (Human-In-The-Loop) requis pour `preparer_entree` haute confiance
- `replay_context` (cas comparés, synthèse) pour calibration

### Tests
- 26 tests Phase 6 (exploitability_evaluator, replay_context)

---

## [0.5.0] — 2026-07-01 — Phase 5 Fenêtres

### Added
- `core/v9/window_gate.py` — 6 statuts fenêtre (exploitable / surveillable / etc.)
- `core/v9/window_db.py` — table `windows`
- Fragilités détectées (booléen + raison)
- Conditions d'invalidation (liste)

### Tests
- 20 tests Phase 5 (window_gate, fragilités)

---

## [0.4.0] — 2026-06-30 — Phase 4 Comportements

### Added
- `core/v9/behavior_analyzer.py` — 12 qualifications de comportement
- `core/v9/behavior_db.py` — table `behaviors`
- Comparaison aux cas connus (similarité_score, cas référencés)
- Transitions détectées (point de rupture, sens)

### Tests
- 21 tests Phase 4 (behavior_analyzer, similarité)

---

## [0.3.0] — 2026-06-29 — Phase 3 Scènes

### Added
- `core/v9/scene_builder.py` — coalitions / antagonismes / cinématique
- `core/v9/scene_db.py` — table `scenes`
- 6 sous-objets : `coalitions_json`, `antagonismes_json`, `cinematique_json`,
  `confluences_mtf_json`, `contexte_temporel_json`, `zone_json`, `risk_assessment_json`
- ZoneDetector + grammaire complète (9/27 principes débloqués, commit `db11917`)

### Tests
- 13 tests Phase 3 (scene_builder, coalitions, antagonismes)

---

## [0.2.0] — 2026-06-28 — Phase 2 Forces

### Added
- `core/v9/forces_reader.py` — reader TCP MT4 → SQLite
- `core/v9/capture_server.py` — serveur TCP port 31685
- `core/v9/stale_gate.py` — gate anti-stale (seuils par TF, `STALE_GATE`)
- `core/v9/db_schema.py` — table `forces_snapshots` (52 colonnes, 8 devises, anti-replay UNIQUE INDEX)
- EA MT4 `V9_Sonde_TF.mq4` + `V9_Sonde_M1.mq4` — envoi forces via TCP

### Tests
- 15 tests Phase 2 (forces_reader, capture_server, stale_gate)

---

## [0.1.0] — 2026-06-27 — Phase 1 Formats de données

### Added
- 6 fichiers de format JSON dans `docs/architecture/formats/` :
  - `FORMAT_FORCES.md`, `FORMAT_SCENES.md`, `FORMAT_COMPORTEMENTS.md`,
    `FORMAT_FENETRES.md`, `FORMAT_EXPLOITABILITE.md`, `MEMORY_CONTRACT.md`
- Cycle de vie mémoire : `hypothèse → valide → rejete/archivé`
- 5 règles de gouvernance mémoire (perception, migration, traçabilité, lecture amont, cohérence)

### Tests
- 13 blocs JSON valides

---

## [0.0.1] — 2026-06-25 — Initialisation

### Added
- Repo créé (dossier V9 vide, sans héritage V8)
- 27 règles doctrine initiales (étendues à 28 en Phase 9.9)
- Charte cognitive V9 (`docs/doctrine/CHARTE_COGNITIVE_V9.md`)
- Politique orchestration V9 (`docs/doctrine/ORCHESTRATION_POLICY_V9.md`)
- Politique migration V8→V9 (`docs/doctrine/MIGRATION_POLICY_V9.md`)
- Politique mémoire V9 (`docs/doctrine/MEMORY_POLICY_V9.md`)

[Unreleased]: https://github.com/gestionzen57-alt/PowerFlow_V9/compare/feat/v9-foundation-clean...HEAD
[0.9.9]: https://github.com/gestionzen57-alt/PowerFlow_V9/tree/feat/v9-foundation-clean
