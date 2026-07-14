# BOARD — Workspace Perplexity (continuité V9)

## Rôle de ce document
Tableau de bord de très haut niveau, à relire en moins d'une minute. Ne remplace pas
`docs/CACHE_BOARD.md` (source de vérité pour l'état du chantier) ni `docs/STATE.md`
(source de vérité vivante, détail complet par phase) — ce document en est une synthèse
orientée reprise rapide côté Perplexity/multi-provider. **Resync 2026-07-14 ~18:25 UTC**.

## Statut global V9 (2026-07-14 ~18:25 UTC — resync Hermes)

Pipeline live **silencieux depuis 16:37 UTC** — normal, marché forex fermé (London ferme 17h UTC, US 22h UTC). Reprise Asian dimanche 22h UTC. **AutoRestart OK** (2 capture_server relancés à 18:35 par le cron, PIDs 10584/12088, port 31685 OCCUPÉ). Aucune action requise — le superviseur fait son travail, EA reprendra dimanche.

Chaîne cognitive à 9 couches complète. Kill switches réels (vérifiés `config/v9_kill_switches.env` + conftest) :
- `V9_TRADER_MINI_ENABLED=1` (A1, Brief Q1)
- `V9_AUTO_CALIBRATOR_ENABLED=1` (A2, Brief Q2)
- `V9_SHADOW_MODE_ENABLED=1` (P2, commit 0c0c334)
- `V9_ADAPTIVE_THRESHOLDS_WIRED_ENABLED=0` (P3-WIRE, R25' descriptif, OFF par défaut — activation = décision Søn distincte)
- `V9_EXECUTION_ENABLED=0` (E refusé par CEO, interdit fondateur)

**Tests** : **1290 verts + 2 skipped + 0 fail** (2:41).
**DB** : **1.42 GB, 19 tables**. Décisions: 8131 DYNAMIC (88.6% WR), 292 SKIPPED (NY/After blacklistés O4), 55511 NULL (jamais résolues).

## Dernier commit structurant
`149f3b0` (Hermes) — feat(mcp): 7e serveur MCP (sqlite etendu + doctrine + p3-consume) — R25

## Phase actuelle
**Phase 13 active** — pipeline LIVE **silencieux depuis 16:37 UTC** (marché fermé,
reprise Asian dimanche 22h UTC). 7 crons Windows Ready. AutoRestart opérationnel.
Prochaine échéance : Asian open dimanche 2026-07-19 22h UTC.

## Blocages
Aucun blocage dur. Pipeline en attente d'ouverture marché. Pas de décision CEO
requise — le superviseur fait son travail.

## Prochaines actions
1. Étendre P3-CONSUME aux 26 autres principes (claim Fable 5, 6-10h)
2. Activer boucle apprentissage cognitive_journal (Hermes, 4-6h)
3. Vérifier Asian open dimanche 22h UTC (snapshot frais attendu)

## Ce qui est gelé
- **Phase 10** (fédération d'agents) — gelée par doctrine R19
- **Phase 12** (exécution d'ordres réelle) — interdit fondateur, E refusé
- **Distillation LLM Phase 13** — pas d'infra locale

## Références pivots
- `docs/STATE.md` — détail vivant par phase (source de vérité)
- `workspace/perplexity/memory/DECISIONS_LOG.md` — historique décisionnel complet
- `workspace/perplexity/BILAN_SESSION_FABLE5.md` — bilan complet pour Fable
- `workspace/perplexity/FABLE5_QUANTUM_LEAP_REQUEST.md` — requête Fable 5
