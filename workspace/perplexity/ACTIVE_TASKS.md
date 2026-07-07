# ACTIVE_TASKS — Workspace Perplexity

Synthèse opérationnelle des tâches. La source de vérité détaillée reste
`docs/CACHE_BOARD.md` §« Chantiers actifs » / §« Prochaines 3 actions » et `docs/STATE.md`
§« Chantiers en file ». Ce fichier ne fait qu'organiser la même information par statut
d'exécution pour une reprise rapide.

## En cours
- **Observation live Hermes** — session Londres ouverte (depuis 07:00 UTC), COALITION_THRESHOLD appliqué = 5.38 (commit `fb5383a`). Seuils ANTAGONISM (31.39) + PLIURE (1.7) maintenus PROVISIONAL (réévaluation n>10 000).
- **Stabilisation live Phase 9** — calibration live continue sur nouveaux seuils, surveillance COALITION_NODE / POWER_ANGLE_BREAK hit rate.
- **Nettoyage documentaire stales** — ✅ **FAIT** (commit `7e56661`). 7 docs alignés sur zone_diagnostics alimentée.
- Attention : session Hermes live concurrente sur branche `feat/v9-foundation-clean`. Toujours vérifier `git log`/`git branch -a`.

## Prochaines actions
1. **Surveillance COALITION_THRESHOLD 5.38** — `python scripts/v9_calibration.py --principles` (toutes les 2h) — hit rate COALITION_NODE / POWER_ANGLE_BREAK / ZONE_RETEST.
2. **ANTAGONISM_THRESHOLD / PLIURE_THRESHOLD** — réévaluation à n>10 000 scènes live (instables actuels).
3. **Checkpoint transition Phase 9 → Phase 10** — `CHECKPOINT_20260707_PHASE9_TO_PHASE10.md` à compléter avec données live actuelles.
4. **Décision DST-aware** `market_calendar.py` (chantier distinct, non bloquant).
5. **Phase 10 OUVERTE** — SI 4 critères bloquants validés (voir `CHECKPOINT_20260707_PHASE9_TO_PHASE10.md`).

## Gelé (ne pas démarrer)
- Phase 10 — Fédération d'agents (GELÉE jusqu'à validation 4 critères).
- Architecture globale agents / routing / mémoire fédérée avancée.
- Génération automatique de skills/agents.
- Voir `docs/ROADMAP.md` §« Chantiers futurs distincts » pour le détail.

## Terminé récemment
- ✅ **COALITION_THRESHOLD 5.0 → 5.38** (2026-07-07 London open) — convergence 3 runs Hermes (5.38/5.67/5.67), médiane conservatrice 5.38. Commit `fb5383a`.
- ✅ **Nettoyage 7 docs stales** (2026-07-07) : zone_diagnostics alimentée alignée partout. Commit `7e56661`.
- ✅ **Inventaire migration V8→V9** (2026-07-06) : audit MIGRATION_POLICY_V9.md complété. P1 identifié.
- ✅ **Session 5 — DORMANT P2 promus PROPAGÉ** (2026-07-06) : 4 champs promus. Commit `f4c3c13`.
- ✅ **Session 4 — YAML news-aware** (2026-07-06) : 4 principes enrichis. Commit `a87d88f`.
- Phase 9 — Décision et Principes canonisée 2026-07-05, 214 tests.
- Phase 9.5 — Outillage ops + mini-checkpoints + runbook. 40 tests.
- 2026-07-06 — ZoneDetector + Grammaire (9/9 node_rule ACTIVE). 283 tests.
- 2026-07-06 — Stabilisation live Phase 9 confirmée (flux EA MT4, n=218 M5+).

## Recommandation pour chantier futur distinct (non démarré)
- Corriger le calendrier canonique (`core/v9/market_calendar.py`) pour qu'il soit
  DST-aware. Nécessite décision explicite — voir `INCIDENTS.md` 2026-07-06.
