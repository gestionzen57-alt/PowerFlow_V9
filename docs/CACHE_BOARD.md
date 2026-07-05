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
- État : Phase 6 TERMINÉE (exploitability evaluator) — Couche Exploitabilité (`ExploitabilityEvaluator`, table `exploitability`) implémentée sur `feat/v9-phase6-exploitabilite`, 26 tests verts. Phase 5 (Fenêtres) existe sur `feat/v9-phase5-fenetres`, non fusionnée : Phase 6 consomme donc `FORMAT_FENETRES.md` via une table `windows` shim alignée sur le schéma réel de `window_db.py`. Prochaine étape : fusion Phase 5 + Phase 6 sur `feat/v9-foundation-clean`, réconciliation des tables shim.

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
- [O] Phase 4 — Couche Comportements (BehaviorAnalyzer, behavior_db, 21 tests) ✅ (2026-07-05, branche `feat/v9-phase4-comportements`, fusionnée sur `feat/v9-foundation-clean` en cours de session)
- [P] Phase 5 — Couche Fenêtres (WindowGate, window_db) ✅ (2026-07-05, branche `feat/v9-phase5-fenetres`, non fusionnée)
- [Q] Phase 6 — Couche Exploitabilité (ExploitabilityEvaluator, exploitability_db, 26 tests) ✅ (2026-07-05, branche `feat/v9-phase6-exploitabilite`, non fusionnée)

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
1. Fusionner `feat/v9-phase5-fenetres` puis `feat/v9-phase6-exploitabilite` sur `feat/v9-foundation-clean`, réconcilier les tables shim (`windows`, `behaviors`) avec `window_db.py`/`behavior_db.py` officiels
2. Statuer sur le périmètre de la Phase 7 — Exécution éventuelle, puis brancher la chaîne complète (Scènes → Comportements → Fenêtres → Exploitabilité) en temps réel en aval de capture_server.py
3. Valider la chaîne EA MT4 réelle (ea/V9_Sonde_TF.mq4) → capture_server.py → v9_forces.db + calibrer les seuils sur données réelles

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
- core/v9/ — implémentation Python des couches Forces (capture, STALE_GATE, reader), Scènes (scene_builder, scene_db), Comportements (behavior_analyzer, behavior_db) et Exploitabilité (exploitability_evaluator, exploitability_db) ; Fenêtres (window_gate, window_db) disponible sur `feat/v9-phase5-fenetres`, non encore fusionnée ici
