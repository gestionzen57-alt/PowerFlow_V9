# ACTIVE_TASKS — Workspace Perplexity

Synthèse opérationnelle des tâches. La source de vérité détaillée reste
`docs/CACHE_BOARD.md` §« Chantiers actifs » / §« Prochaines 3 actions » et `docs/STATE.md`
§« Chantiers en file ». Ce fichier ne fait qu'organiser la même information par statut
d'exécution pour une reprise rapide.

## En cours
- Rien en cours côté code sur `feat/v9-foundation-clean` au moment de la rédaction
  (Phase 9 clôturée, pas de Phase 10 ouverte).
- Attention : une session concurrente peut travailler sur une branche de phase séparée
  (cf. `[[memory/LESSONS_LEARNED]]` — plusieurs sessions Claude Code peuvent tourner en
  parallèle sur ce dépôt). Toujours vérifier `git log`/`git branch -a` avant de supposer
  qu'un chantier est libre.

## À faire après market open (dimanche 23h Paris / 22h UTC)
1. Déploiement live : compilation EA (`ServerPort=31690`), `scripts/deploy_v9.py --start`,
   `scripts/validate_ea_output.py`, `scripts/live_integration_test.py`.
2. Observation dashboard : `scripts/v9_dashboard.py --watch signals` /
   `--watch decisions`.
3. Calibration à partir des observations live : `scripts/v9_calibration.py --analyze` /
   `--principes`.
4. Purge opérateur de la duplication historique (`--replace-derived` sur
   `scripts/regenerate_chain.py`) si pas déjà faite — ~245k lignes dérivées dupliquées à
   nettoyer (voir `docs/checkpoints/CHECKPOINT_20260705_V9_REGEN_IDEMPOTENT.md`).
5. Décision de périmètre pour l'alimentation de `zone_diagnostics` (non bloquant).

## Gelé (ne pas démarrer)
- Phase 10 — Fédération d'agents.
- Architecture globale agents / routing / mémoire fédérée avancée.
- Génération automatique de skills/agents.
- Voir `docs/ROADMAP.md` §« Chantiers futurs distincts » pour le détail des dépendances
  de séquencement.

## Terminé récemment
- Phase 9 — Décision et Principes (Régime/Principes/Signal/Décision), canonisée
  2026-07-05, 214 tests.
- Correctif idempotence `regenerate_chain.py` (commit `c83423e`), 218 tests.
- Gouvernance documentaire (`docs/v9-governance` fusionnée, commit `ffcddbd`).
