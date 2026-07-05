# CACHE_BOARD — PowerFlow V9

## Rôle
Ce fichier est le tableau de bord compact de reprise.
Il doit pouvoir être relu en 2 minutes maximum au début de chaque session.

## Statut global
- Projet : PowerFlow V9
- Nature : refondation cognitive + architecture propre
- Base : dossier V9 vide
- Source de vérité : GitHub
- Doctrine : architecture-first
- État : Chaîne cognitive V9 étendue à 8 couches, TOUTES TERMINÉES — Forces → Scènes →
  Comportements → Fenêtres → Exploitabilité (Phases 1-6) → Régime → Principes → Signal →
  Décision (Phase 9). Phase 7 (déploiement live) et Phase 8 (monitoring/calibration/replay)
  également terminées. Phase 9 (branche `feat/v9-foundation-clean`) a comblé le gap V8
  `regime_snapshots`, migré 27 principes YAML (10 ACTIVE/17 SHADOW) et ajouté le journal de
  décisions qualitatives (`decision_logger.py`) — **gap non résolu, non bloquant** :
  `zone_diagnostics` créée mais non alimentée (voir `docs/phases/PHASE9_DECISION.md`).
  **214 tests au total, tous verts** (vérifiés indépendamment le 2026-07-05). Gouvernance
  documentaire canonisée en parallèle (`docs/v9-governance`) : voir
  `docs/checkpoints/CHECKPOINT_2026-07-05_MEGA_V9.md` pour la synthèse consolidée. Prochaine
  étape : déploiement live à l'ouverture du marché, avec dashboard en observation
  (`--watch signals`/`--watch decisions`).

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
- [C] Politique mémoire V9 — contrat Forces ↔ Scènes posé (MEMORY_CONTRACT.md) ✅, reste à étendre aux couches aval
- [D] Inventaire de migration V8 → V9
- [E] AGENT.md racine V9
- [F] Lexique natif V9 ✅
- [G] Formats couche Forces ✅ (FORMAT_FORCES.md)
- [H] Formats couche Scènes ✅ (FORMAT_SCENES.md)
- [I] Formats couches Comportements / Fenêtres / Exploitabilité ✅ (livrés 2026-07-05, branche `feat/v9-phase1-formats-aval`)
- [J] Corrections post-review (scene_source, schema_version, contrat mémoire aval) ✅
- [K] Phase 2A — EA MT4 (V9_Sonde_TF, V9_Sonde_M1) ✅ (livrés 2026-07-05, branche `feat/v9-phase2-ea-mt4`)
- [L] Phase 2B — capture Python + STALE_GATE + forces_reader ✅ (livrés 2026-07-05, branche `feat/v9-phase2-python-capture`)
- [M] Fusion Phase 2 + harmonisation STALE_GATE ✅ (2026-07-05, sur `feat/v9-foundation-clean`)
- [N] Phase 3 — Couche Scènes (SceneBuilder, scene_db, 13 tests) ✅ fusionnée sur `feat/v9-foundation-clean` (2026-07-05)
- [O] Phase 4 — Couche Comportements (BehaviorAnalyzer, behavior_db, 21 tests) ✅ fusionnée sur `feat/v9-foundation-clean` (2026-07-05)
- [P] Phase 5 — Couche Fenêtres (window_gate.py, window_db.py, 20 tests) ✅ fusionnée sur `feat/v9-foundation-clean` (2026-07-05) — `_load_behavior`/`_load_behavior_history` revalidés contre le schéma réel de `behavior_db.py`
- [Q] Phase 6 — Couche Exploitabilité (exploitability_evaluator.py, exploitability_db.py, 26 tests) ✅ fusionnée sur `feat/v9-foundation-clean` (2026-07-05) — `_load_window`/`insert_window` revalidés contre le schéma réel de `window_db.py` (schéma identique, aucune divergence)
- [R] Smoke test chaîne complète Forces → Scènes → Comportements → Fenêtres → Exploitabilité (tests/test_full_chain.py) ✅ (2026-07-05) — 96 tests au total
- [S] Phase 7 — Déploiement live + test d'intégration ✅ (livrés 2026-07-05, branche `feat/v9-phase7-live-deployment`) : référentiel temporel (`market_calendar.py`, 22 tests), scripts `deploy_v9.py`/`validate_ea_output.py`/`live_integration_test.py`, EA avec `ServerPort` configurable, guide de déploiement — 118 tests au total
- [T] Phase 8 — Monitoring + calibration + replay ✅ (livrés 2026-07-05, branche `feat/v9-phase8-monitoring`) : `scripts/v9_dashboard.py` (dashboard terminal temps réel), `scripts/v9_calibration.py` (`--stats`/`--export csv|json`/`--analyze` avec suggestions de seuils), `scripts/v9_replay.py` (`--list`/`--show`/`--compare`/`--search`), `tests/test_dashboard.py` (21 tests) — 139 tests au total, tous en lecture seule stricte sur `data/v9_forces.db`
- [U] Phase 9 — Décision et Principes ✅ (livrés/canonisés 2026-07-05, branche `feat/v9-foundation-clean`) : `regime_detector.py`/`regime_db.py` (gap V8 `regime_snapshots` comblé), `principle_engine.py`/`principle_db.py` (27 principes YAML migrés, 10 ACTIVE/17 SHADOW), `signal_generator.py`/`signal_db.py`, `decision_logger.py`/`decision_db.py`, `zone_db.py` (créée, non alimentée — gap connu), `orchestrator.py` étendu — 75 nouveaux tests, 214 au total. Voir `docs/phases/PHASE9_DECISION.md` et `docs/checkpoints/CHECKPOINT_2026-07-05_MEGA_V9.md`
- [V] Gouvernance documentaire ✅ (2026-07-05, branche `docs/v9-governance`) : arborescence canonique `docs/` (ARCHITECTURE/DOCTRINE/LEXIQUE/NOMENCLATURE/ROADMAP/DOC_GOVERNANCE/DOC_REGISTRY), `docs/phases/`, `docs/checkpoints/`, `tools/doc_sync.py`, `.github/workflows/doc-freshness.yml`. Mega-checkpoint de clôture Phase 9 : `docs/checkpoints/CHECKPOINT_2026-07-05_MEGA_V9.md`

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

## Prochaines 3 actions
1. Déploiement live à l'ouverture du marché (dimanche 23h Paris / 22h UTC) — suivre docs/deployment/V9_DEPLOYMENT_GUIDE.md (compilation EA avec ServerPort, scripts/deploy_v9.py --start, scripts/validate_ea_output.py, scripts/live_integration_test.py, scripts/v9_dashboard.py --watch signals/--watch decisions en observation)
2. Calibrer les seuils Scènes/Comportements/Fenêtres/Exploitabilité/Régime/Principes sur données réelles, via scripts/v9_calibration.py --analyze/--principes à partir des observations live
3. Décider et planifier l'alimentation de `zone_diagnostics` (gap Priorité 2 de l'audit, ~5-8j) — non bloquant pour le market open ; ne pas démarrer la Phase 10 (fédération d'agents) ni tout chantier d'architecture agentique avant stabilisation live de la Phase 9 (voir docs/ROADMAP.md §Chantiers futurs distincts)

## Références pivots
- docs/doctrine/CHARTE_COGNITIVE_V9.md
- docs/STATE.md
- docs/checkpoints/CHECKPOINT_2026_07_05_V9_INIT.md
- docs/checkpoints/CHECKPOINT_2026_07_05_V9_PHASE1A.md
- docs/checkpoints/CHECKPOINT_2026_07_05_V9_PHASE1B.md
- docs/checkpoints/CHECKPOINT_20260705_V9_PHASE1_COMPLETE.md
- docs/checkpoints/CHECKPOINT_20260705_V9_PHASE2A.md
- ea/V9_Sonde_README.md
- docs/checkpoints/CHECKPOINT_20260705_V9_PHASE2B.md
- docs/checkpoints/CHECKPOINT_20260705_V9_PHASE2_COMPLETE.md
- docs/checkpoints/CHECKPOINT_20260705_V9_PHASE3.md
- docs/checkpoints/CHECKPOINT_20260705_V9_PHASE3_COMPLETE.md
- docs/checkpoints/CHECKPOINT_20260705_V9_PHASE4.md
- docs/checkpoints/CHECKPOINT_20260705_V9_PHASE6.md
- docs/architecture/formats/FORMAT_FORCES.md
- docs/architecture/formats/FORMAT_SCENES.md
- docs/architecture/formats/MEMORY_CONTRACT.md
- docs/architecture/formats/FORMAT_COMPORTEMENTS.md
- docs/architecture/formats/FORMAT_FENETRES.md
- docs/architecture/formats/FORMAT_EXPLOITABILITE.md
- core/v9/ — implémentation Python des 6 couches : Forces (capture, STALE_GATE, reader), Scènes (scene_builder, scene_db), Comportements (behavior_analyzer, behavior_db), Fenêtres (window_gate, window_db), Exploitabilité (exploitability_evaluator, exploitability_db)
- docs/checkpoints/CHECKPOINT_20260705_V9_PHASE5.md
- docs/checkpoints/CHECKPOINT_20260705_V9_PHASE4_5_COMPLETE.md
- docs/checkpoints/CHECKPOINT_20260705_V9_CHAIN_COMPLETE.md
- docs/deployment/V9_DEPLOYMENT_GUIDE.md
- core/v9/market_calendar.py
- docs/checkpoints/CHECKPOINT_20260705_V9_PHASE7.md
- docs/checkpoints/CHECKPOINT_20260705_V9_PHASE8.md
- scripts/v9_dashboard.py, scripts/v9_calibration.py, scripts/v9_replay.py
- docs/phases/PHASE9_DECISION.md
- docs/checkpoints/CHECKPOINT_2026-07-05_MEGA_V9.md
- docs/architecture/audit_v8_v9_migration.md
- core/v9/regime_detector.py, principle_engine.py, signal_generator.py, decision_logger.py, zone_db.py
