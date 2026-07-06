# ACTIVE_TASKS — Workspace Perplexity

Synthèse opérationnelle des tâches. La source de vérité détaillée reste
`docs/CACHE_BOARD.md` §« Chantiers actifs » / §« Prochaines 3 actions » et `docs/STATE.md`
§« Chantiers en file ». Ce fichier ne fait qu'organiser la même information par statut
d'exécution pour une reprise rapide.

## En cours
- **Observation live continue** — flux EA MT4 confirmé, pipeline stable, 359 tests verts.
- **Stabilisation live Phase 9** — calibration exécutée sur n=218 M5+ purement live.
  Seuils suggérés non encore appliqués à `config.py` (attente session live plus longue).
- **Nettoyage documentaire stales** — 7 documents mentionnent encore "zone_diagnostics
  non alimentée" (information périmée depuis 2026-07-06). Chantier borné, non bloquant.
  Voir `docs/checkpoints/CHECKPOINT_20260706_DOC_CLEANUP.md`.
- Attention : une session concurrente peut travailler sur une branche de phase séparée
  (cf. `[[memory/LESSONS_LEARNED]]`). Toujours vérifier `git log`/`git branch -a` avant
  de supposer qu'un chantier est libre.

## Prochaines actions
1. Observation live continue : `python scripts\v9_ops.py watch` + `signals` + `decisions`.
2. Nettoyage documentaire stales : aligner README.md, CACHE_BOARD.md, ARCHITECTURE.md,
   ROADMAP.md, DB_SCHEMA.md, CHAINE_COGNITIVE.md, PHASE9_DECISION.md,
   CHECKPOINT_2026-07-05_MEGA_V9.md sur la réalité live actuelle.
3. **COALITION_THRESHOLD** — réévaluer à n>5000 scènes + WIN/LOSS (actuel 5.0, suggéré 5.33 par calibration live, 3.96 suggéré précedent).
4. Décision : ouvrir ou non le chantier DST-aware pour `market_calendar.py`.
5. Checkpoint officiel Phase 9 → Phase 10 une fois la stabilisation confirmée.

## Gelé (ne pas démarrer)
- Phase 10 — Fédération d'agents.
- Architecture globale agents / routing / mémoire fédérée avancée.
- Génération automatique de skills/agents.
- Voir `docs/ROADMAP.md` §« Chantiers futurs distincts » pour le détail.

## Terminé récemment
- ✅ **COALITION_THRESHOLD audit + calibration** (2026-07-06) : n=3957 scènes live, 3 décisions directionnelles (3 preparer_entree haussiere conf 80-100), suggéré 5.33 par calibration --analyze (P20 des écarts de force). Seuil 5.0 maintenu PROVISIONAL en attendant n>5000 + WIN/LOSS. Commit à venir.
- ✅ **Inventaire migration V8→V9** (2026-07-06) : audit selon `MIGRATION_POLICY_V9.md` complété. 4 catégories A/B/C/D appliquées. Priorités P1 (principes YAML, agent_registry, règles GOLDEN, ShiftIndex EA) identifiées. Commit à venir.
- ✅ **Session 5 — DORMANT P2 promus PROPAGÉ** (2026-07-06) : 4 champs promus (contexte_temporel_fenetre, point_de_rupture_declencheur, est_variante, comportement_reference), 359 tests verts. Commit `f4c3c13`.
- ✅ **Session 4 — YAML news-aware** (2026-07-06) : 4 principes enrichis (POWER_ANGLE_BREAK, NODE_BIRTH_FAST, RAW_NODE_BIRTH, COALITION_NODE, ANTAGONIST_NODE note), 359 tests verts. Commit `a87d88f`.
- Phase 9 — Décision et Principes (Régime/Principes/Signal/Décision), canonisée 2026-07-05, 214 tests.
- Correctif idempotence `regenerate_chain.py` (commit `c83423e`), 218 tests.
- Gouvernance documentaire (`docs/v9-governance` fusionnée, commit `ffcddbd`).
- Outillage d'automatisation reboot machine / ouverture marché / reprise de session (scripts `v9_ops.py`, `docs/deployment/V9_AUTOMATION_RUNBOOK.md`, 40 tests).
- 2026-07-06 — Correctif observabilité statut marché + correction 8 tests `test_behavior_analyzer.py` (commit `eec353c`). 269 tests, tous verts.
- 2026-07-06 — Purge DB duplication exécutée (commit `0c3d719`). DB saine.
- 2026-07-06 — Marquage `source_type` live/replay (commit `6a5d603`). ✅
- 2026-07-06 — **ZoneDetector** (commit `db11917`) + **Grammaire complétée** (commit `a596f37`) : 9/9 principes `node_rule` ACTIVE déclenchables. 283 tests, tous verts.
- 2026-07-06 — Alignement port 31685 dans tous les docs EA et déploiement (commit `9a9233c`).
- 2026-07-06 — Correctif `validate-ea` fallback DB si port occupé (commit `2669a7e`).
- 2026-07-06 — **Stabilisation live Phase 9 confirmée** : flux EA MT4 live réel, n=218 snapshots M5+ purement live, `calibrate` + `principles` exécutés, `zone_diagnostics` alimenté, ANTAGONIST_NODE comportement normal (marché aligné H1/M5).

## Recommandation pour chantier futur distinct (non démarré)
- Corriger le calendrier canonique (`core/v9/market_calendar.py`) pour qu'il soit
  DST-aware. Nécessite décision explicite — voir `INCIDENTS.md` 2026-07-06.
