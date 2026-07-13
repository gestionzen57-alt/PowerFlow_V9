# BOARD — Workspace Perplexity (continuité V9)

## Rôle de ce document
Tableau de bord de très haut niveau, à relire en moins d'une minute. Ne remplace pas
`docs/CACHE_BOARD.md` (source de vérité pour l'état du chantier) ni `docs/STATE.md`
(source de vérité vivante, détail complet par phase) — ce document en est une synthèse
orientée reprise rapide côté Perplexity/multi-provider. En cas de divergence, `docs/STATE.md`
et `docs/CACHE_BOARD.md` font foi. **Resync 2026-07-12 (Brief R)** — les sections
historiques détaillées (sprints 2026-07-06/07) ont été retirées d'ici car dupliquées et
en meilleur état dans `docs/STATE.md`/`workspace/perplexity/memory/DECISIONS_LOG.md`.

## Statut global V9 (2026-07-13 ~01:15 UTC)
Chaîne cognitive à 9 couches complète sur `feat/v9-foundation-clean`. Phases **1→13.2 livrées + Autopilot série (P1+P6) 2026-07-13**. Catalogue principes : **25 ACTIVE + 1 SHADOW** (SIGNAL_OPEN). Doctrine : **30 règles immuables** (règle 28 = Hermes opérateur git unique).

**Décisions résolues** : 9516/9516 (100%) Brief O1 + 71 paper_trades (résolveur). Répartition `preparer_entree` post-Brief O1 (2026-07-12) : DYNAMIC=8217 (7272W/945L, 88.5% WR tradé), SKIPPED=1298 (new_york/after, pas de résolution directionnelle), 0 en TP_SL. `principle_scores` peuplée (125 lignes, 1ère fois en prod). `Arbiter` pondéré par le score historique des principes (Brief O2). Branching HITL confiance 40-80 informatif (Brief O3, CEO a porté HITL_CONF_HIGH 65→80 le 13/07). Dataset V9-trader-mini exporté, entraînement non ouvert (Brief Q1). Analyse biais NY/After livrée mais décision O4 toujours en attente (P1 a ajouté la recommandation DYNAMIC dans le signal, INEFFET j/Q activation).

**Série Autopilot 2026-07-13 livrée** (CEO autopilot « go fait tout ») :
- **P6** `core/v9/vol_regime.py` — module pur, ATR-30 → LOW/NORMAL/HIGH/EXTREME, calibration empirique 9970 fenêtres M15 GBPUSD, intégration `principle_engine._load_shared_context()`. Commit `9592ce3`.
- **P1** 3 colonnes `signals.(exit_strategy_recommended, tp_pips_recommended, sl_pips_recommended)` peuplées par `session_marche` via DYNAMIC_PROFILES. INEFFET j/Q activation O4. Commit `331382f`.
- **Fix HITL** `tests/test_decision_logger_hitl_branching.py` adapté au seuil CEO 2026-07-13 `HITL_CONF_HIGH=80` (résolution de la dernière régression pré-existante). Commit `ade60e1`.

**Tests** : **1114 verts + 2 skipped + 0 fail**. 0 régression.

**Suite Autopilot reportée** (chantiers distincts, prochaine session) :
- P3 — Adaptive Thresholds (seuils f(vol_regime, news_proximity))
- P4 — Event Calendar dynamique
- P5 — Long-term memory (lookback 50→500)
- P2 — Shadow mode parallèle (infra lourd, J+2)
- Décision Brief O4 « biais New York/After » → trancher formellement pour activer P1

## Dernier commit structurant
Voir `git log --oneline -1`. 4 commits Autopilot CEO 2026-07-13 : `9592ce3` P6, `331382f` P1, `6cf75d4` autopilot status doc, `ade60e1` fix HITL test.

## Phase actuelle
**Phase 13.3 + Autopilot P1+P6 livrés. O4 résolu 13/07 ~02:00 (politique
conservatrice : NY/After blacklistés structurellement, trades asie/london/overlap uniquement).
Prochaine étape côté doctrine : décisions en attente pour Søn — dérogation
HITL éventuelle (aucune actée, O3 reste informatif jusqu'à 80).

## Blocages
Aucun blocage dur. **Telegram status runtime cassé** (placeholder sanitisé dans `config/telegram.json`, vrai token ailleurs, getMe → 404). Status de l'autopilot déposé dans `logs/autopilot_status.md` conformément R6 (pas de simulation de faux succès).

## Next actions
Voir `workspace/perplexity/ACTIVE_TASKS.md` pour le détail. En résumé (série Autopilot CEO 2026-07-13) :
1. Décision Brief O4 « biais New York/After » → trancher pour activer P1 (`signals.exit_strategy_recommended` populated, INEFFET tant que les résolveurs WIN/LOSS ne le consomment pas).
2. Lancer P3 (Adaptive Thresholds) en prochaine session — chantier structurant le plus impactant.
3. Fixer les 15 fails pré-existants de `tests/test_telegram_notifier.py` (refactoring Telegram post-bug 2026-07-11, indépendant P1/P6).
4. Post-open marché (lundi Asian session 22h UTC = 23h Paris heure d'été) — vérifier que le pipeline live capte les nouveaux snapshots et les nouvelles colonnes `vol_regime` + `exit_strategy_recommended`.

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
