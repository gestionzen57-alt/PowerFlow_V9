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
**283 tests au total** : 283 verts, zéro échec. Purge de la duplication DB exécutée (262 812 lignes dérivées supprimées, 1 296 snapshots régénérés).

## Dernier commit structurant
`59dea22` — stabilisation live Phase 9 confirmée (flux EA MT4 live réel, calibration live exécutée sur n≥200 snapshots M5+ purement live). Poussé sur `origin/feat/v9-foundation-clean` le 2026-07-06.

HEAD confirmé ce jour : `59dea22`
Upstream : `origin/feat/v9-foundation-clean` — à jour, working tree clean.

Historique proche : `baaad6b` (BOARD/ACTIVE_TASKS/DECISIONS_LOG grammaire 9/9) →
`a596f37` (feat: grammaire complétée) → `2f39c4a` (STATE.md zone_diagnostics) →
`923ab1d` (mini-checkpoint zone_detector) → `db11917` (feat: zone_detector) →
`6a5d603` (source_type live/replay) → `9a9233c` (docs port 31685) → `2669a7e` (validate-ea fallback DB).

## Phase actuelle
Phase 9 (Décision et Principes) **terminée, canonisée et stabilisée en live** (2026-07-05 → 2026-07-06). Aucune phase de
code n'est ouverte à ce jour sur `feat/v9-foundation-clean`. Le chantier immédiat est l'**observation live continue et la calibration sur données réelles** puis la décision d'ouverture de la Phase 10 (voir `docs/ROADMAP.md`).

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
- Calendrier canonique (`core/v9/market_calendar.py`) ancré sur 22h UTC fixe, incorrect ~8 mois/an pendant la DST US → corrigé côté observabilité uniquement. Chantier DST-aware dédié recommandé hors Phase 9.5.
- 7 documents stales mentionnent encore "zone_diagnostics non alimentée" → chantier documentaire distinct borné, non bloquant. Voir checkpoint `docs/checkpoints/CHECKPOINT_20260706_DOC_CLEANUP.md`.
- Seuils `config.py` encore `PROVISIONAL` (portés de V8) — à recalibrer après session live complète.

## Next actions (voir aussi `ACTIVE_TASKS.md`)
1. Observation live continue via `python scripts\v9_ops.py watch` et `python scripts\v9_ops.py signals` / `decisions`.
2. Nettoyage documentaire borné : aligner les 7 documents stales sur la réalité live (zone_diagnostics alimenté, ANTAGONIST_NODE comportement normal, Phase 9 stabilisée live).
3. Décision structurante : appliquer ou non les seuils suggérés à `config.py` après une session live plus longue.
4. Décision structurante : ouvrir ou non le chantier DST-aware pour `market_calendar.py`.
5. Déclenchement Phase 10 — fédération d'agents — après confirmation de stabilisation live suffisante.

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
6. ⏳ Nettoyage documentaire stales
7. ⏳ Checkpoint officiel de transition Phase 9 → Phase 10

## Références pivots (ne pas dupliquer, toujours relire en premier)
- `docs/STATE.md` — détail vivant par phase
- `docs/CACHE_BOARD.md` — tableau de reprise complet
- `docs/ROADMAP.md` — phases restantes et chantiers gelés
- `docs/PERPLEXITY.md` — rôle et responsabilités de Perplexity dans V9
- `docs/DOCTRINE.md` — index doctrine (19 règles immuables)
- `docs/deployment/V9_AUTOMATION_RUNBOOK.md` — outillage reboot/ouverture marché/reprise
- `workspace/perplexity/mini_checkpoints/20260706_084600_live_stabilise.md` — checkpoint live Phase 9
