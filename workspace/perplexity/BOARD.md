# BOARD — Workspace Perplexity (continuité V9)

## Rôle de ce document
Tableau de bord de très haut niveau, à relire en moins d'une minute. Ne remplace pas
`docs/CACHE_BOARD.md` (source de vérité pour l'état du chantier) ni `docs/STATE.md`
(source de vérité vivante, détail complet par phase) — ce document en est une synthèse
orientée reprise rapide côté Perplexity/multi-provider. **Resync 2026-07-14 — activation
générale Phase 13**.

## Statut global V9 (2026-07-14 ~14:00 UTC)
Chaîne cognitive à 9 couches complète. **Phase 13 activée** (A1+A2+P2+P3-WIRE ON).
Kill switches : V9_TRADER_MINI_ENABLED=1, V9_AUTO_CALIBRATOR_ENABLED=1,
V9_SHADOW_MODE_ENABLED=1, V9_ADAPTIVE_THRESHOLDS_WIRED_ENABLED=1.
V9_EXECUTION_ENABLED=0 (E refusé par CEO, interdit fondateur).

**Décisions résolues** : 9516/9516 (100%). DYNAMIC=8217 (7272W/945L, 88.5% WR tradé),
SKIPPED=1298 (new_york/after). P1-RESOLVE actif : `resolve_one()` lit désormais
`signals.exit_strategy_recommended` en priorité sur la constante DYNAMIC.

**Tests** : **1263 verts + 2 skipped + 0 fail** (baseline 5049d48 = 1258, +5 Hermes).

**Sessions parallèles actives** :
- **ZCode** : P1-RESOLVE ✅, SHADOW-EXPAND ✅, docs à jour
- **Hermes** : P3-CONSUME (6-10h) en cours, vérification pipeline live

## Dernier commit structurant
`2ab07f3` (Hermes) — restoration DB + wrapper kill switches
`5049d48` (ZCode) — activation générale Phase 13 + P1-RESOLVE + SHADOW-EXPAND

## Phase actuelle
**Phase 13 activée** — A1 (trader_mini weighter) + A2 (auto_calibrator propose-only)
tournent. P2 shadow mode évalue P3-WIRE + A1 + A2 en parallèle du live.
P1-RESOLVE branché : les résolveurs WIN/LOSS lisent la recommandation du signal.

## Blocages
Aucun blocage dur. **P3-CONSUME** (consommation réelle adaptive thresholds dans
evaluate_condition/YAML) est le dernier gros chantier code avant la stabilisation.

## Prochaines actions
1. **P3-CONSUME** (Hermes) — consommer `adaptive_*_threshold` dans evaluate_condition/YAML
2. **Vérifier pipeline live** après Asian open 22h UTC — filtres O4 + signaux DYNAMIC
3. **Token Telegram** — le `.env` a le vrai token, mais `v9_shadow_divergence_report.py --send`
   n'a pas été testé avec
4. **Arbitrage comptage tests** — 1 `pytest -q` à HEAD sur machine canonique, puis resync
   STATE/BOARD/ACTIVE_TASKS sur le chiffre unique (fissure tracée 14/07, session Fable — cf. DECISIONS_LOG)

## Ce qui est gelé
- **Phase 10** (fédération d'agents) — gelée par doctrine R19
- **Phase 12** (exécution d'ordres réelle) — interdit fondateur, E refusé
- **Entraînement V9-trader-mini** — dataset prêt, GO séparé requis
- **Distillation LLM Phase 13** — pas d'infra locale

## Références pivots
- `docs/STATE.md` — détail vivant par phase (source de vérité)
- `workspace/perplexity/memory/DECISIONS_LOG.md` — historique décisionnel complet
- `workspace/perplexity/COORDINATION_NOTE.md` — coordination ZCode ↔ Hermes
- `docs/ROADMAP.md` — phases restantes et chantiers gelés
