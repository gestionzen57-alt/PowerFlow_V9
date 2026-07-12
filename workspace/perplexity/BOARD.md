# BOARD — Workspace Perplexity (continuité V9)

## Rôle de ce document
Tableau de bord de très haut niveau, à relire en moins d'une minute. Ne remplace pas
`docs/CACHE_BOARD.md` (source de vérité pour l'état du chantier) ni `docs/STATE.md`
(source de vérité vivante, détail complet par phase) — ce document en est une synthèse
orientée reprise rapide côté Perplexity/multi-provider. En cas de divergence, `docs/STATE.md`
et `docs/CACHE_BOARD.md` font foi. **Resync 2026-07-12 (Brief R)** — les sections
historiques détaillées (sprints 2026-07-06/07) ont été retirées d'ici car dupliquées et
en meilleur état dans `docs/STATE.md`/`workspace/perplexity/memory/DECISIONS_LOG.md`.

## Statut global V9 (2026-07-12)
Chaîne cognitive à 9 couches complète sur `feat/v9-foundation-clean`. Phases **9.7 → 13.2
livrées**. Catalogue principes : **25 ACTIVE + 1 SHADOW** (SIGNAL_OPEN). Doctrine :
**30 règles immuables** (règle 28 = Hermes opérateur git unique).

**Décisions résolues** : 9516/9516 (100%). Répartition `preparer_entree` post-Brief O1
(2026-07-12) : DYNAMIC=8217 (7272W/945L, 88.5% WR tradé), SKIPPED=1298 (new_york/after,
pas de résolution directionnelle), 0 en TP_SL. `principle_scores` peuplée (125 lignes,
1ère fois en prod). `Arbiter` pondéré par le score historique des principes (Brief O2).
Branching HITL confiance 40-65 informatif (Brief O3). Dataset V9-trader-mini exporté,
entraînement non ouvert (Brief O5). Analyse biais NY/After livrée, recommandation SKIP
statu quo (Brief O4).

**Tests** : **1018 verts**, 0 régression (règle 7). 2 skips documentés et stables
(intégration complexe vérifiée manuellement ; SIGTERM non-fonctionnel sous Windows).

**Découverte pipeline notable** : `core/v9/arbiter.py` (Arbiter, pondération PrincipleScorer)
n'est consommé QUE par `scripts/v9_paper_trade_run.py` — le chemin d'écriture live
(`orchestrator.run_chain()` → `decision_logger.log()`) n'y passe jamais. Le branching HITL
(Brief O3) a donc été implémenté dans `decision_logger.py`, confirmé comme le seul point
d'écriture live.

## Dernier commit structurant
Voir `git log --oneline -1` (Hermes opérateur git unique, règle 28). Série de briefs
O1→O5 + R (2026-07-12) préparée par une session Claude Code, commits en attente de
validation/push par Hermes — cf. `workspace/perplexity/memory/DECISIONS_LOG.md`
§2026-07-12 pour le détail complet de chaque livraison.

## Phase actuelle
**Phase 13.3 en cours** (post re-résolution DYNAMIC/SKIPPED complète). Prochaine étape
côté doctrine : décisions en attente pour Søn — recommandation O4 (SKIP maintenu),
dérogation HITL éventuelle (aucune actée, O3 reste informatif), GO entraînement
V9-trader-mini (O5, non demandé).

## Blocages
Aucun blocage dur. Le bloqueur historique (timeout du batch de résolution DYNAMIC,
2026-07-11) est résolu — root cause : absence d'index sur `decisions.decision_id` en
production malgré la déclaration `UNIQUE` dans le code (schéma jamais migré). Corrigé
Brief O1 (`idx_decisions_decision_id`).

## Next actions
Voir `workspace/perplexity/ACTIVE_TASKS.md` pour le détail. En résumé (checklist série
O1-O5 du 2026-07-12) :
1. Hermes : commit/push des livraisons O1 → O5 (staged, pas commit — R28).
2. Post-open marché (dimanche 23h Paris = 21h UTC heure d'été) : vérifier que le
   résolveur live tourne en DYNAMIC + skip New York/After (corrigé Brief O1).
3. Décisions Søn en attente : cf. §Phase actuelle ci-dessus.
4. Brief R (ce document + ACTIVE_TASKS.md + MEMORY_CANON.md + DOC_REGISTRY.yml) —
   en cours de clôture.

## Ce qui est gelé
- **Phase 10 (fédération d'agents)** et **Phase 12 (exécution d'ordres réelle)** —
  aucune modification, aucune date planifiée.
- **Skills/agents auto-générés**.
- **Entraînement V9-trader-mini** (dataset préparé Brief O5, GO séparé requis).
- Voir `docs/ROADMAP.md` §« Chantiers futurs distincts — ne pas mélanger maintenant ».

## Références pivots (ne pas dupliquer, toujours relire en premier)
- `docs/STATE.md` — détail vivant par phase (source de vérité)
- `docs/CACHE_BOARD.md` — tableau de reprise complet
- `workspace/perplexity/memory/DECISIONS_LOG.md` — historique décisionnel complet
- `docs/ROADMAP.md` — phases restantes et chantiers gelés
- `docs/PERPLEXITY.md` — rôle et responsabilités de Perplexity dans V9
- `docs/DOCTRINE.md` — index doctrine (30 règles immuables)
- `docs/deployment/V9_AUTOMATION_RUNBOOK.md` — outillage reboot/ouverture marché/reprise
