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
1. Déploiement live : compilation EA (`ServerPort=31690`), puis
   `scripts/v9_bootstrap.py --boot` et `scripts/v9_market_open.py --market-open`
   (voir `docs/deployment/V9_AUTOMATION_RUNBOOK.md`) pour automatiser checks/port
   stale/démarrage serveur/plausibilité AUD, en complément de
   `scripts/validate_ea_output.py` et `scripts/live_integration_test.py`.
2. Observation dashboard : `scripts/v9_dashboard.py --watch signals` /
   `--watch decisions`.
3. Calibration à partir des observations live : `scripts/v9_calibration.py --analyze` /
   `--principes`.
4. Purge opérateur de la duplication historique (`--replace-derived` sur
   `scripts/regenerate_chain.py`) si pas déjà faite — ~245k lignes dérivées dupliquées à
   nettoyer (voir `docs/checkpoints/CHECKPOINT_20260705_V9_REGEN_IDEMPOTENT.md`).
5. Décision de périmètre pour l'alimentation de `zone_diagnostics` (non bloquant).
6. Reprise de session : `scripts/v9_session_resume.py --resume` pour vérifier
   mécaniquement la continuité documentaire avant de relire `BOARD.md`/`STATE.md` en
   détail.

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
- Outillage d'automatisation reboot machine / ouverture marché / reprise de session
  (`scripts/v9_supervisor.py`, `v9_bootstrap.py`, `v9_market_open.py`,
  `v9_session_resume.py`, `docs/deployment/V9_AUTOMATION_RUNBOOK.md`, 40 tests) — voir
  `docs/STATE.md` §« Outillage post-Phase 9 ». Aucune modification de `core/v9/*`.
- 2026-07-06 (Phase 9.5) — Correctif observabilité statut marché : diagnostic de
  l'anomalie « Marché : FERMÉ pendant que le live tourne » (bug DST US, calendrier
  canonique 22h UTC fixe) et avertissement explicite ajouté dans
  `scripts/v9_supervisor.py` (`market_status_warning`), `scripts/v9_dashboard.py`,
  `scripts/v9_market_open.py`. Aucune modification de `core/v9/*`, calendrier canonique
  inchangé par décision explicite. 11 nouveaux tests (269 au total, 261 verts). Voir
  `INCIDENTS.md` 2026-07-06 et `memory/DECISIONS_LOG.md` 2026-07-06.

## Recommandation pour chantier futur distinct (non démarré)
- Corriger le calendrier canonique (`core/v9/market_calendar.py`) pour qu'il soit
  DST-aware (ancrer `is_market_open`/`next_open` sur 17h heure de New York via
  `zoneinfo`, comme `paris_to_utc`, au lieu de 22h UTC fixe). Nécessite de rouvrir la
  décision Phase 7 canonisée et de réécrire 7 tests de `tests/test_market_calendar.py`.
  Estimé non chiffré, décision explicite requise avant de démarrer (voir `INCIDENTS.md`
  2026-07-06).
