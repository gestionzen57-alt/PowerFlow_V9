# Changelog

All notable changes to PowerFlow V9 will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

**Note** : ce CHANGELOG est complémentaire à `workspace/perplexity/memory/DECISIONS_LOG.md`
(journal daté des décisions doctrinales) et `docs/checkpoints/` (jalons de phase).
Pour la traçabilité fine des décisions/opérations, consulter ces 2 sources.
Ce fichier liste les **livraisons** (versions, features, fixes, breaking changes).

## [Unreleased] — 2026-07-14 ~18:45 UTC — Boucle apprentissage + Resync Hermes (P0+P1+P2)

### Added
- **Cron `V9_LearningLoop` installé Ready** (admin PowerShell, 18:43 UTC) — quotidien 23h00 UTC. Commande : `python scripts/v9_ops.py propose 7`. Boucle apprentissage effective (était dormant depuis l'audit 11/07, aucune table considérée comme orpheline — juste non déclenchée).
- **2 propositions PENDING** dans `learning_proposals` :
  - `signal:haussiere:weight_offset` (score=73.52, WR=93% sur n=6228 décisions résolues, écart +43% vs neutre)
  - `signal:baissiere:weight_offset` (score=27.91, WR=65% sur n=1843, écart +15%)
- **7 → 8 crons Windows V9** : tous Ready (AutoRestart, HeartbeatCheck, HeartbeatAlert, ResolveLoop, CalibrationLoop, ArbiterRecal, MetaAgentScan, LearningLoop).

### Changed
- **AGENT.md / workspace/perplexity/BOARD.md / docs/CACHE_BOARD.md / workspace/perplexity/ACTIVE_TASKS.md / workspace/perplexity/COORDINATION_NOTE.md** : resync complet — Fable 5 hors service, P3-CONSUME-EXTEND repris par Hermes (mandat CEO 18:35), boucle apprentissage activée, cron installé.
- **`config/v9_kill_switches.env`** : ajout `V9_SHADOW_MODE_ENABLED=1` (P2 livré 0c0c334, motion CEO), clarification `V9_ADAPTIVE_THRESHOLDS_WIRED_ENABLED=0` (R25' strict, activation = décision Søn distincte).

### Fixed
- **BOARD.md incohérence** : kill switches listés tous ON alors que le fichier n'en déclarait que 2. Aligné sur la doctrine R25' (WIRE = OFF par défaut, Søn décide d'activer).
- **Boucle apprentissage dormante** : module `v9_ops.py propose 7` jamais appelé en cron. Diagnostic : 0 row = pas déclenché, pas orphelin. Cron installé + premier cycle exécuté à 18:43 UTC.

## [Unreleased] — 2026-07-14 ~18:25 UTC — Resync Hermes (P0+P1+P2)

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
