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
documentaire canonisée (`docs/v9-governance` fusionnée). 218 tests, tous verts.

## Dernier commit structurant
`c83423e` — fix: make regenerate_chain idempotent and safe for replay
(voir `docs/checkpoints/CHECKPOINT_20260705_V9_REGEN_IDEMPOTENT.md`).

Historique proche : `ffcddbd` (merge gouvernance + mega-checkpoint) → `fe6323e`
(mega-checkpoint clôture Phase 9) → `dc26d8e` (architecture doc + gouvernance) →
`f874560` (Phase 9 — Décision et Principes).

## Phase actuelle
Phase 9 (Décision et Principes) **terminée et canonisée** (2026-07-05).
Aucune phase de code n'est ouverte à ce jour sur `feat/v9-foundation-clean`.
Le chantier immédiat n'est pas une nouvelle phase de code mais le **déploiement live à
l'ouverture du marché** (voir `docs/deployment/V9_DEPLOYMENT_GUIDE.md` et
`assets/MARKET_OPEN_TEMPLATE.md`).

## Blocages
Aucun blocage dur identifié. Deux gaps connus, non bloquants :
- `zone_diagnostics` créée (`core/v9/zone_db.py`) mais **non alimentée** → 9 des 27
  principes se dégradent gracieusement (jamais d'erreur). Chantier distinct estimé 5-8j.
- Marquage replay vs live non posé dans `decisions` (point ouvert depuis Phases 7-8).

## Next actions (voir aussi `ACTIVE_TASKS.md`)
1. Déploiement live à l'ouverture du marché (dimanche 23h Paris / 22h UTC).
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
