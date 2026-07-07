# BOARD — Workspace Perplexity (continuité V9)

## Rôle de ce document
Tableau de bord de très haut niveau, à relire en moins d'une minute. Ne remplace pas
`docs/CACHE_BOARD.md` (source de vérité pour l'état du chantier) ni `docs/STATE.md`
(source de vérité vivante, détail complet par phase) — ce document en est une synthèse
orientée reprise rapide côté Perplexity/multi-provider. En cas de divergence, `docs/STATE.md`
et `docs/CACHE_BOARD.md` font foi.

## Statut global V9
Chaîne cognitive à 9 couches complète et fusionnée sur `feat/v9-foundation-clean` :
Forces → Scènes → Comportements → Fenêtres → Exploitabilité → Régime → Principes → Signal
→ Décision. Orchestrateur live (`core/v9/orchestrator.py`) opérationnel. Gouvernance
documentaire canonisée (`docs/v9-governance` fusionnée). Outillage opérationnel
(reboot/ouverture marché/reprise de session, « Phase 9.5 ») livré, aucune modification de
`core/v9/*`. Correctif d'observabilité du statut marché (2026-07-06, anomalie DST US,
voir `INCIDENTS.md`) ajouté au même outillage, toujours sans modification de `core/v9/*`.
**359 tests au total** : 359 verts, zéro échec (état au 2026-07-06 fin de session Phase 9.5 — voir `docs/checkpoints/CHECKPOINT_20260706_SESSION_FINALE.md`). Purge de la duplication DB exécutée (262 812 lignes dérivées supprimées, 1 296 snapshots régénérées, DB 1393→582 MB, 3 UNIQUE constraints idempotence).

## Dernier commit structurant
HEAD = `a303057` — feat(ops): validate-coherence.py — 7 checks cohérence DB live.
Session 2026-07-07 commits : `8697d84` (fix signal currency) → `4fde966` (telegram notifier) → `b6b722e` (is_win/résolution) → `a303057` (validate-coherence) → `5fc39c5` (GAP-001) → `52ee778` (checkpoint Phase 9→10).

**Tests** : **426 verts, 0 échec** (était 359 au 2026-07-06, 391 → 394 → 406 → 426 sur les chantiers 2026-07-07).
**DB live** : dernier snapshot `v9-GBPUSD-M15-1783422465-048964` (2026-07-07T08:07:45 UTC).
**Telegram** : 2 messages envoyés à 10:07:49 CEST (preuve `logs/telegram_notifier.log`).

Upstream : `origin/feat/v9-foundation-clean` — working tree clean au 2026-07-07 10h08 CEST.

## Phase actuelle
**Phase 9 terminée et stable live. Phase 10 autorisée le 2026-07-07.
Chantier Phase 10 ouvert — arbiter + risk_manager + paper_trades.**

- HEAD : `a303057`
- Tests : **426 verts**, 0 échec
- DB live : 7 signaux directionnels GBPUSD 2026-07-07, confiance 80–100, 2 messages Telegram 10:07:49 CEST
- Critères objectifs WIN/LOSS ≥ 20 (règle 25) : **non remplis** — période de grâce autorisée par l'opérateur, WIN/LOSS collectés via `scripts/v9_resolve_decision.py` en parallèle
- Périmètre Phase 10 : `core/v9/arbiter.py` + `core/v9/risk_manager.py` + table `paper_trades` (simulation uniquement, zéro ordre réel avant Phase 12)

Voir [`docs/checkpoints/CHECKPOINT_20260707_PHASE9_TO_PHASE10.md`](../../docs/checkpoints/CHECKPOINT_20260707_PHASE9_TO_PHASE10.md) pour le détail (signature opérateur).

## Acquis stabilisation live (2026-07-06)
- Flux EA MT4 live réel confirmé : 7 TF connectés, timestamps qui avancent en temps réel, `is_closed_bar=0`, `validate-ea = VALIDE`.
- `calibrate` et `principles` exécutés sur n≥218 snapshots M5+ purement live.
- `zone_diagnostics` alimenté en live (2 008 lignes, états NEUTRAL/EARLY_EXTREME/ACCUMULATING visibles).
- 9/9 principes `node_rule` ACTIVE désormais déclenchables. `ANTAGONIST_NODE = 0` est un comportement normal de marché (H1 et M5 alignés, pas de divergence).
- Stale M5+ : ~0.6% — excellent.
- Seuils suggérés calibration live : `COALITION_THRESHOLD → 3.73`, `ANTAGONISM_THRESHOLD → 31.31`, `PLIURE_THRESHOLD → 0.0`. **Non appliqués à `config.py`** en attente d'une session live plus longue.
- Le message résiduel "gap zone_diagnostics" dans `v9_calibration.py` est un résidu de code obsolète (non mis à jour après commits `db11917` + `a596f37`). Corrigé en session. Verdict : `ANTAGONIST_NODE` dépend du contexte cross-TF de `forces_snapshots`, pas de `zone_diagnostics`.

## Blocages
Aucun blocage dur identifié. Gaps/anomalies connus, non bloquants :
- ~~`zone_diagnostics` créée mais **non alimentée**~~ → **RÉSOLU** le 2026-07-06 (commits `db11917`, `a596f37`). 9/9 principes `node_rule` ACTIVE déclenchables.
- Marquage replay vs live posé dans les 8 tables dérivées (colonne `source_type`, 2026-07-06). ✅ Résolu.
- ~~Calendrier canonique (`core/v9/market_calendar.py`) ancré sur 22h UTC fixe, incorrect ~8 mois/an pendant la DST US~~ → **RÉSOLU** par commit `e42d81b` (DST-aware via `America/New_York` + `zoneinfo`, 2026-07-07).
- ~~7 documents stales mentionnent encore "zone_diagnostics non alimentée"~~ → **RÉSOLU** par commit `7e56661` (nettoyage 7 docs stales alignés sur la réalité live, 2026-07-07).
- Seuils `config.py` encore `PROVISIONAL` (portés de V8) — gelés jusqu'au run calibration 08h CEST London open (Phase 9.7, commit `539a62e`).

## Next actions (voir aussi `ACTIVE_TASKS.md`)
1. Observation live continue via `python scripts\v9_ops.py watch` et `python scripts\v9_ops.py signals` / `decisions` (session Asie en cours, n>5 000 scènes).
2. ✅ ~~Nettoyage documentaire borné : aligner les 7 documents stales sur la réalité live~~ → FAIT (commit `7e56661`).
3. Décision structurante au matin 08h CEST : appliquer ou non les seuils suggérés (COALITION 5.38, ANTAGONISM 30.53, PLIURE 0.86) — règle de convergence : 3 runs Hermes stables + n>5 000 + WIN/LOSS ≥ 20.
4. Compléter le draft checkpoint Phase 9 → Phase 10 (`docs/checkpoints/CHECKPOINT_20260707_PHASE9_TO_PHASE10.md`) avec les résultats du run calibration London open.
5. Déclenchement Phase 10 — fédération d'agents — sous condition des 4 critères bloquants (règle doctrine 16/17/19).

## Ce qui est gelé
- **Phase 10 (fédération d'agents)** : planifiée (P1) mais ne démarre pas avant
  stabilisation live confirmée et checkpoint de transition.
- **Architecture globale agents / routing / mémoire avancée** : hors périmètre actuel.
- **Skills/agents auto-générés** : dépend d'un socle Phases 9-10 stable en live.
- Voir `docs/ROADMAP.md` §« Chantiers futurs distincts — ne pas mélanger maintenant ».

## Ce qui reste avant Phase 10
1. ✅ Flux live confirmé
2. ✅ `validate-ea` valide
3. ✅ `calibrate` + `principles` sur live pur
4. ✅ `zone_diagnostics` alimenté et cohérent
5. ⏳ Seuils `config.py` applicables (après session live plus longue)
6. ✅ Nettoyage documentaire stales (commit `7e56661` + corrections BOARD.md 2026-07-07)
7. ⏳ Checkpoint officiel de transition Phase 9 → Phase 10

## Références pivots (ne pas dupliquer, toujours relire en premier)
- `docs/STATE.md` — détail vivant par phase
- `docs/CACHE_BOARD.md` — tableau de reprise complet
- `docs/ROADMAP.md` — phases restantes et chantiers gelés
- `docs/PERPLEXITY.md` — rôle et responsabilités de Perplexity dans V9
- `docs/DOCTRINE.md` — index doctrine (27 règles immuables au 2026-07-06)
- `docs/deployment/V9_AUTOMATION_RUNBOOK.md` — outillage reboot/ouverture marché/reprise
- `workspace/perplexity/mini_checkpoints/20260706_084600_live_stabilise.md` — checkpoint live Phase 9
