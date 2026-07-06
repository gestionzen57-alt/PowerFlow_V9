# BOARD — Workspace Perplexity (continuité V9)

## Rôle de ce document
Tableau de bord de très haut niveau, à relire en moins d'une minute. Ne remplace pas
`docs/CACHE_BOARD.md` (source de vérité pour l'état du chantier) ni `docs/STATE.md`
(source de vérité vivante, détail complet par phase) — ce document en est une synthèse
orientée reprise rapide côté Perplexity/multi-provider. En cas de divergence, `docs/STATE.md`
et `docs/CACHE_BOARD.md` font foi.

## Statut global V9
Chaîne cognitive à 8 couches complète et fusionnée sur `feat/v9-foundation-clean` :
Forces → Scènes → Comportements → Fenêtres → Exploitabilité → Régime → Principes → Signal
→ Décision. Orchestrateur live (`core/v9/orchestrator.py`) opérationnel. Gouvernance
documentaire canonisée (`docs/v9-governance` fusionnée). Outillage opérationnel
(reboot/ouverture marché/reprise de session, « Phase 9.5 ») livré, aucune modification de
`core/v9/*`. Correctif d'observabilité du statut marché (2026-07-06, anomalie DST US,
voir `INCIDENTS.md`) ajouté au même outillage, toujours sans modification de `core/v9/*`.
**269 tests au total** : 269 verts, zéro échec (les 8 tests `test_behavior_analyzer.py` précédemment en échec ont été corrigés le 2026-07-06, voir `INCIDENTS.md`). Purge de la duplication DB exécutée (262 812 lignes dérivées supprimées, 1 296 snapshots régénérés).

## Dernier commit structurant
Ce commit (voir son message : outillage d'automatisation reboot/ouverture marché/reprise
de session — `scripts/v9_supervisor.py`/`v9_bootstrap.py`/`v9_market_open.py`/
`v9_session_resume.py` + `docs/deployment/V9_AUTOMATION_RUNBOOK.md`, 40 tests).

Historique proche : `c83423e` (fix idempotence regenerate_chain) →
`ffcddbd` (merge gouvernance + mega-checkpoint) → `fe6323e`
(mega-checkpoint clôture Phase 9) → `dc26d8e` (architecture doc + gouvernance) →
`f874560` (Phase 9 — Décision et Principes).

## Phase actuelle
Phase 9 (Décision et Principes) **terminée et canonisée** (2026-07-05). Aucune phase de
code n'est ouverte à ce jour sur `feat/v9-foundation-clean` — le travail livré ce jour
(outillage d'automatisation) est volontairement qualifié de **« Phase 9.5 »** : pas une
phase de code métier, pas une ouverture de la Phase 10. Le chantier immédiat reste le
**déploiement live à l'ouverture du marché** (voir `docs/deployment/V9_DEPLOYMENT_GUIDE.md`,
`docs/deployment/V9_AUTOMATION_RUNBOOK.md` et `assets/MARKET_OPEN_TEMPLATE.md`).

## Blocages
Aucun blocage dur identifié. Gaps/anomalies connus, non bloquants :
- `zone_diagnostics` créée (`core/v9/zone_db.py`) mais **non alimentée** → 9 des 27
  principes se dégradent gracieusement (jamais d'erreur). Chantier distinct estimé 5-8j.
- Marquage replay vs live posé dans les 8 tables dérivées (colonne `source_type`, 2026-07-06).
- 8 tests `test_behavior_analyzer.py` en échec, pré-existants, sans rapport avec
  l'outillage livré ce jour (voir `INCIDENTS.md` 2026-07-05) — à investiguer par une
  session future, hors périmètre ops.
- Calendrier canonique (`core/v9/market_calendar.py`) ancré sur 22h UTC fixe, incorrect
  ~8 mois/an pendant la DST US (marché réel ouvre/ferme à 21h UTC) → peut afficher
  « Marché : FERMÉ » pendant que le live tourne. **Corrigé côté observabilité** le
  2026-07-06 (avertissement explicite dans dashboard/health/mini-checkpoints quand une
  activité live récente contredit le calendrier), calendrier canonique lui-même non
  modifié par décision explicite — chantier DST-aware dédié recommandé, hors Phase 9.5.
  Voir `INCIDENTS.md` 2026-07-06.

## Next actions (voir aussi `ACTIVE_TASKS.md`)
1. Déploiement live à l'ouverture du marché (dimanche 23h Paris / 22h UTC) — utiliser
   `scripts/v9_bootstrap.py --boot` puis `scripts/v9_market_open.py --market-open`
   (voir `docs/deployment/V9_AUTOMATION_RUNBOOK.md`) en complément des étapes manuelles
   de `V9_DEPLOYMENT_GUIDE.md`.
2. Calibration des seuils (Scènes/Comportements/Fenêtres/Exploitabilité/Régime/Principes)
   sur données réelles via `scripts/v9_calibration.py --analyze`/`--principes`.
3. Décision de périmètre pour l'alimentation de `zone_diagnostics`.

## Ce qui est gelé
- **Phase 10 (fédération d'agents)** : planifiée (P1) mais ne démarre pas avant
  stabilisation live de la Phase 9.
- **Architecture globale agents / routing / mémoire avancée** : hors périmètre actuel,
  non scopée, ne sera abordée qu'après amorçage de la Phase 10.
- **Skills/agents auto-générés** : dépend d'un socle Phases 9-10 stable en live.
- Voir `docs/ROADMAP.md` §« Chantiers futurs distincts — ne pas mélanger maintenant » et
  `docs/checkpoints/CHECKPOINT_2026-07-05_MEGA_V9.md`.

## Références pivots (ne pas dupliquer, toujours relire en premier)
- `docs/STATE.md` — détail vivant par phase
- `docs/CACHE_BOARD.md` — tableau de reprise complet
- `docs/ROADMAP.md` — phases restantes et chantiers gelés
- `docs/PERPLEXITY.md` — rôle et responsabilités de Perplexity dans V9
- `docs/DOCTRINE.md` — index doctrine (19 règles immuables)
- `docs/deployment/V9_AUTOMATION_RUNBOOK.md` — outillage reboot/ouverture marché/reprise
