# ACTIVE_TASKS — Workspace Perplexity

Synthèse opérationnelle des tâches. La source de vérité détaillée reste
`docs/CACHE_BOARD.md` §« Chantiers actifs » / §« Prochaines 3 actions » et `docs/STATE.md`
§« Chantiers en file ». Ce fichier ne fait qu'organiser la même information par statut
d'exécution pour une reprise rapide.

## En cours
- **Observation live Hermes** — session Asie en cours (depuis ~22h UTC 2026-07-06), accumulation n>5 000 scènes sur seuils PROVISIONAL. **ZCode en attente** — AUCUNE modification config.py avant run calibration 08h CEST (London open).
- **Stabilisation live Phase 9** — calibration exécutée sur n=218 M5+ live faite, seuils suggérés non appliqués (attente n>5 000 + WIN/LOSS + règle de convergence 3 runs).
- **Nettoyage documentaire stales** — ✅ **FAIT** (commit `7e56661`). 7 docs alignés sur zone_diagnostics alimentée.
- Attention : session Hermes live concurrente sur branche `feat/v9-foundation-clean`. Toujours vérifier `git log`/`git branch -a`.

## Prochaines actions
1. **Run calibration 08h CEST** (London open) — `python scripts/v9_calibration.py --analyze && python scripts/v9_calibration.py --principes` — **DÉCISION SEUILS FINALE**.
2. Application seuils validés dans `config.py` (si règle de convergence atteinte : 3 runs Hermes stables + n>5 000 + WIN/LOSS ≥ 20).
3. Checkpoint transition Phase 9 → Phase 10 (`CHECKPOINT_20260707_PHASE9_TO_PHASE10.md` — draft créé, à compléter).
4. Décision DST-aware `market_calendar.py` (chantier distinct, non bloquant).
5. Phase 10 OUVERTE **SI ET SEULEMENT SI** les 4 critères bloquants validés.

## Gelé (ne pas démarrer)
- Phase 10 — Fédération d'agents (GELÉE jusqu'à validation 4 critères).
- Architecture globale agents / routing / mémoire fédérée avancée.
- Génération automatique de skills/agents.
- Voir `docs/ROADMAP.md` §« Chantiers futurs distincts » pour le détail.

## Terminé récemment
- ✅ **Nettoyage 7 docs stales** (2026-07-07) : zone_diagnostics alimentée alignée partout. Commit `7e56661`.
- ✅ **COALITION_THRESHOLD audit + calibration** (2026-07-06) : n=3957 scènes live, suggéré 5.33. Seuil 5.0 PROVISIONAL.
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
