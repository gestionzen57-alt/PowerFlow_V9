# BOARD — Workspace Perplexity (continuité V9)

## Rôle de ce document
Tableau de bord de très haut niveau, à relire en moins d'une minute. Ne remplace pas
`docs/CACHE_BOARD.md` (source de vérité pour l'état du chantier) ni `docs/STATE.md`
(source de vérité vivante, détail complet par phase) — ce document en est une synthèse
orientée reprise rapide côté Perplexity/multi-provider. **Resync 2026-07-14 ~15:30 UTC**.

## Statut global V9 (2026-07-14 ~15:30 UTC)
Chaîne cognitive à 9 couches complète. **Pipeline LIVE actif** — 37 décisions produites
en 30 min après `deploy_v9.py --start`. Dernier snapshot : 2026-07-14T15:29 (GBPUSD M1).
**Telegram testé ✅**. **7 crons Windows réparés et fonctionnels**.

Kill switches : V9_TRADER_MINI_ENABLED=1, V9_AUTO_CALIBRATOR_ENABLED=1,
V9_SHADOW_MODE_ENABLED=1, V9_ADAPTIVE_THRESHOLDS_WIRED_ENABLED=1.
V9_EXECUTION_ENABLED=0 (E refusé par CEO, interdit fondateur).

**Décisions résolues** : 8423 (100%). DYNAMIC=8131 (7208W/923L, 88.6% WR),
SKIPPED=292 (new_york/after). P1-RESOLVE actif. P3-CONSUME livré (ADAPTIVE_VOL_GATE).

**Tests** : **1277 verts + 2 skipped + 0 fail**.

## Dernier commit structurant
`6051277` (ZCode) — 3 actions immédiates + requête Fable 5
`080fb3f` (Hermes) — F = A+B+C+D

## Phase actuelle
**Phase 13 activée** — pipeline LIVE, 7 crons, AutoRestart toutes les 5 min.
Prochaine échéance : Asian open dimanche 22h UTC.

## Blocages
Aucun blocage dur. Pipeline live actif. Telegram fonctionnel.

## Prochaines actions
1. Vérifier pipeline live Asian open (dimanche 22h UTC)
2. Étendre P3-CONSUME aux 26 autres principes
3. Démarrer boucle d'apprentissage

## Ce qui est gelé
- **Phase 10** (fédération d'agents) — gelée par doctrine R19
- **Phase 12** (exécution d'ordres réelle) — interdit fondateur, E refusé
- **Distillation LLM Phase 13** — pas d'infra locale

## Références pivots
- `docs/STATE.md` — détail vivant par phase (source de vérité)
- `workspace/perplexity/memory/DECISIONS_LOG.md` — historique décisionnel complet
- `workspace/perplexity/BILAN_SESSION_FABLE5.md` — bilan complet pour Fable
- `workspace/perplexity/FABLE5_QUANTUM_LEAP_REQUEST.md` — requête Fable 5
