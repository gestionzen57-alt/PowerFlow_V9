# PowerFlow V9

## Nature du projet

PowerFlow V9 est une refondation cognitive propre de PowerFlow.
Ce n'est pas une extension de V8. C'est un nouveau socle, construit sur une doctrine explicite,
posé dans un dossier vide, sans héritage implicite de mémoire, de skills ou de conventions passées.

V8 reste une source de migration curée : chaque élément repris doit être audité et classé
(voir `docs/doctrine/MIGRATION_POLICY_V9.md`). V8 n'est jamais la base de travail directe de V9.

## Mission

PowerFlow V9 est un système de lecture comportementale des forces de marché.
Sa mission première n'est pas de produire un trade, mais de reconnaître fidèlement
la dynamique réelle des forces telle qu'elle est perçue par l'opérateur.

Phrase directrice : **ne jamais demander au système de trader ce qu'il ne sait pas encore décrire.**

## Ordre cognitif officiel

## Status (2026-07-17 18:30+ UTC — Session Hedge Fund Mondial)

**HEAD** : `328cd9f + 38e5901 (dashboard/MC/promo/telegram)` sur `feat/v9-foundation-clean` — 5 commits pushés dans la session, R6/R18/R23 respectées.

- **Paper trades clôturés** : 4752 (vs 59 baseline) — WR 90.33%, +27239 pips
- **Profit Factor** : 4.96 — **Sharpe-like** : 0.845 — **Recovery Factor** : 95.2
- **Max Drawdown** : -286 pips (2.86% capital, sous la cible hedge fund 15%)
- **Performance** : 540ms → 57ms par snapshot (gain x10) ; async calibration 22s → 5.7s (gain x4)
- **Tests** : 134+ verts cumulés session, 0 fail
- **MCP** : 12 tools (strategy_pole 7 + hedge_fund_summary 4 + live 1)
- **Skills catalogue** : 6 (strategy-pole, paper-trade-ops, quant-fund, performance-tuning, coherence-audit, market-report)
- **Modules hedge fund livrés** : `core/v9/v9_drawdown_protector.py` (5 paliers DD), `core/v9/v9_risk_parity.py` (5 paires, USDCAD blacklist), `core/v9/v9_strategy_pole.py` (StrategyCatalogue + Tuner + Selector)
- **Pôle stratégie** : StrategySelector a élu `PRICE_LAG × new_york` top 1 (WR 97%, PF 17.15, +7.31 pips/trade, n=3293)
- **Doctrine respectée** : simulation uniquement, Phase 12 exécution réelle non ouverte

5 commits chainés : `2159619` débloquage → `3206a78` pôle stratégie → `7a8ec8d` MCP+skills → `57d79de` orchestration Opus → `328cd9f + 38e5901 (dashboard/MC/promo/telegram)` hedge fund mondial.

---

1. Forces
2. Scènes
3. Comportements
4. Fenêtres
5. Exploitabilité
6. Régime (Phase 9)
7. Principes (Phase 9, 53 YAML : 25 ACTIVE + 28 SHADOW)
8. Signal (Phase 9)
9. Décision (Phase 9)
10. **Phase 9.7 — Paper-Trade Simulator (Arbiter + RiskManager + PaperTradeLogger, gelé)**
11. **Phase 9.10 — Règle 29 LIVRÉE (zone_type + naissance_isolee + HITL + pondération arbiter, doctrine §3bis import V8)**
12. Phase 10 — Fédération d'agents (gelée par règle 19, doctrine : stabilisation live)
13. Phase 11 — Layer MT4 ticks (gelée par décision Søn 2026-07-07 14h58)
14. Phase 12 — Exécution d'ordres (interdit fondateur)
15. Phase 13 — Apprentissage + recalibrage pondérations RULE29 (conditionnelle WIN/LOSS ≥ 50)

Aucune couche aval ne peut court-circuiter une couche amont.

## Reprise rapide de session (nouvelle conversation Hermes ou Perplexity)

Pour reconstruire le contexte sans mémoire implicite de conversation antérieure,
copier **le bloc ` ``` ` de l'un des templates** en **premier message** d'une nouvelle
session du provider cible :

- **Perplexity** (rôle doctrinal/orchestrateur) :
  `workspace/perplexity/REPRISE_TEMPLATE.md` (~80 lignes + bloc ` ``` ` à copier-coller).
- **Hermes** (rôle git + observateur live) :
  `workspace/perplexity/REPRISE_TEMPLATE_HERMES.md` (~100 lignes + bloc ` ``` ` à copier-coller).

Chaque template donne :
1. L'ordre de lecture obligatoire (10-11 fichiers dans un ordre précis).
2. La liste des modules `core/v9/` critiques vs gelés (périmètre Phase 9.7 strict).
3. Les règles opérationnelles strictes (règle 6/14/22/25/28 — arrêt à 3 échecs, Git=vérité,
   pas d'invention de seuils, Søn CEO).
4. Les crons Windows actifs et le statut pipeline live.
5. La procédure de backup+revert MD5 en cas de régression (`workspace/perplexity/memory/backups_<date>/`).

**Note** : ce `README.md` est lui-même un résumé. Pour la doctrine technique complète
(orchestration, migration V8, charte cognitive), voir `docs/PERPLEXITY.md` et
`docs/doctrine/CHARTE_COGNITIVE_V9.md`.

## Arborescence

```
PowerFlow_V9/
├── README.md                  — ce fichier
├── AGENT.md                   — document racine, rôle et routing du système
├── docs/
│   ├── PERPLEXITY.md          — rôle Perplexity dans l'orchestration
│   ├── STATE.md               — état exécutif du chantier
│   ├── CACHE_BOARD.md         — tableau de bord compact de reprise
│   ├── ARCHITECTURE.md        — vue d'ensemble technique (renvoie vers architecture/)
│   ├── DOCTRINE.md            — index des 30 règles immuables (renvoie vers doctrine/, règle 28 Hermes git unique, règle 29 lecture multi-TF §3bis ajoutée 2026-07-07, règle 30 apprentissage WIN/LOSS progressif)
│   ├── LEXIQUE.md             — index alphabétique du vocabulaire (renvoie vers lexicon/)
│   ├── NOMENCLATURE.md        — conventions de nommage, vérifiées contre le code
│   ├── V9_FONCTIONNEMENT.md   — mode d'emploi global du système (12 sections)
│   ├── ROADMAP.md             — phases 9-13, leviers, risques connus
│   ├── DOC_GOVERNANCE.md      — règles de gouvernance documentaire
│   ├── DOC_REGISTRY.yml       — registre de tous les documents (statut, fraîcheur)
│   ├── phases/                — un document par phase (PHASE1_FORMATS.md … PHASE9_DECISION.md)
│   ├── reports/                — rapports générés (calibration, fraîcheur doc)
|   ├── checkpoints/           — jalons structurants
│   │   └── CHECKPOINT_TEMPLATE.md — gabarit pour tout nouveau checkpoint
│   │   └── CHECKPOINT_20260707_RULE29.md — checkpoint règle 29 (12 sections, 11 KB)
├── workspace/perplexity/       — workspace interne Hermes/Perplexity (sources résumées, non canoniques pour doctrine)
│   ├── BOARD.md / STATE.md / CACHE_BOARD.md — sources résumées (cf. mêmes docs dans docs/)
│   ├── REPRISE_TEMPLATE.md — template 1er message session **Perplexity** (rôle doctrinal)
│   ├── REPRISE_TEMPLATE_HERMES.md — template 1er message session **Hermes** (rôle git + ops)
│   ├── doctrine/
│   │   ├── CHARTE_COGNITIVE_V9.md
│   │   ├── ORCHESTRATION_POLICY_V9.md
│   │   ├── MIGRATION_POLICY_V9.md
│   │   └── MEMORY_POLICY_V9.md
│   ├── architecture/
│   │   ├── IMPLEMENTATION_ROADMAP_V9.md
│   │   ├── CHAINE_COGNITIVE.md — détail des 9 couches cognitives
│   │   ├── DB_SCHEMA.md        — schéma SQLite complet
│   │   ├── CONTEXT_CONTRACT.md — contrat vivant de propagation des métriques (PROPAGÉ/DORMANT)
│   │   ├── PIPELINE_LIVE.md    — flux EA → TCP → Python → DB → chaîne
│   │   ├── audit_v8_v9_migration.md
│   │   └── formats/
│   │       ├── FORMAT_FORCES.md
│   │       ├── FORMAT_SCENES.md
│   │       ├── MEMORY_CONTRACT.md
│   │       ├── FORMAT_COMPORTEMENTS.md
│   │       ├── FORMAT_FENETRES.md
│   │       └── FORMAT_EXPLOITABILITE.md
│   ├── deployment/
│   │   └── V9_DEPLOYMENT_GUIDE.md
│   └── lexicon/
│       └── LEXICON_V9.md
├── core/
│   └── v9/
│       ├── __init__.py
│       ├── config.py
│       ├── market_calendar.py
│       ├── stale_gate.py
│       ├── forces_reader.py
│       ├── capture_server.py
│       ├── db_schema.py
│       ├── scene_builder.py
│       ├── scene_db.py
│       ├── behavior_analyzer.py
│       ├── behavior_db.py
│       ├── window_gate.py
│       ├── window_db.py
│       ├── exploitability_evaluator.py
│       ├── exploitability_db.py
│       ├── regime_detector.py
│       ├── regime_db.py
│       ├── principle_engine.py
│       ├── principle_db.py
│       ├── principles/            — 53 YAML (25 ACTIVE + 28 SHADOW, cf. core/v9/config.py::PRINCIPLE_ACTIVE_IDS)
│       ├── signal_generator.py
│       ├── signal_db.py
│       ├── decision_logger.py
│       ├── decision_db.py
│       ├── zone_db.py             — table zone_diagnostics, alimentée par ZoneDetector (commit db11917)
│       ├── orchestrator.py        — run_chain, chaîne cognitive complète (9 couches)
│       ├── arbiter.py             — consolidation paper-trade (Phase 9.7)
│       ├── risk_manager.py        — filtre paper-trade (Phase 9.7)
│       ├── paper_trade_logger.py  — saisie paper-trade (Phase 9.7)
│       ├── paper_trades_db.py     — table paper_trades (Phase 9.7)
│       ├── news_context.py        — calendrier économique (5 champs propagés)
├── ea/
│   ├── V9_Sonde_TF.mq4
│   ├── V9_Sonde_M1.mq4
│   └── V9_Sonde_README.md
├── tests/                    — 35 fichiers test_*.py, 588 tests verts (cf. tests/test_context_propagation.py gardien)
├── memory/                    — memory.md / memory_temp.md / exchange.md
├── workspace/perplexity/      — memory interne V9 (BOARD, ACTIVE_TASKS, JOURNAL, EXCHANGE, DECISIONS_LOG, LESSONS_LEARNED, inspiration)
├── assets/                    — loop / reading / windows / scenes / behaviors
├── skills/                    — scene-reader, behavior-reader, window-evaluator, replay-confronter, doctrine-keeper
├── agents/                    — 6 squelettes README-only (orchestrator, force-reader, scene-builder, behavior-analyst, window-gate, reviewer) + agents/AGENTIC_MAP.md
├── .hermes/                   — c5a_normalize_yaml_status.py, c5b_run_claude_code.py, c5b_prompt.txt (helpers)
├── runtime/                   — state / reports / logs / snapshots
├── scripts/                   — 22 scripts v9_*.py + deploy_v9.py + heartbeat/telegram/daily_report crons
├── tools/
│   └── doc_sync.py            — vérification/maintenance cohérence doc/code (--check/--update/--stale)
├── .github/workflows/
│   └── doc-freshness.yml      — CI : docstrings, DOC_REGISTRY.yml, fraîcheur STATE.md
└── archive/
```

## Reprise de session

En début de session, lire dans l'ordre :
1. `docs/CACHE_BOARD.md`
2. `docs/STATE.md`
3. le dernier fichier de `docs/checkpoints/`
4. uniquement les documents de doctrine utiles à la tâche en cours

## Rituel de lecture — Toute IA

Toute IA (Claude Code, Hermes, Perplexity, ou autre) qui intervient sur V9
DOIT lire ces documents dans cet ordre exact avant toute action. Aucune exception.

### Rituel de démarrage — Obligatoire pour toute IA

#### Niveau 1 — Reprise de contexte (2 min)
1. `docs/CACHE_BOARD.md` — tableau de bord compact, état global
2. `docs/STATE.md` — état exécutif détaillé, livrables, décisions
3. Le dernier fichier dans `docs/checkpoints/` — jalon le plus récent

#### Niveau 2 — Doctrine (5 min)
4. `docs/DOCTRINE.md` — index des 30 règles immuables (renvoie vers `docs/doctrine/*.md`)
5. `docs/doctrine/CHARTE_COGNITIVE_V9.md` — charte cognitive, ordre des couches
6. `docs/LEXIQUE.md` / `docs/lexicon/LEXICON_V9.md` — vocabulaire natif V9
7. `docs/doctrine/ORCHESTRATION_POLICY_V9.md` — politique d'orchestration
8. `docs/doctrine/MIGRATION_POLICY_V9.md` — politique de migration V8→V9
9. `docs/ARCHITECTURE.md` — vue d'ensemble technique, modules et flux de données
10. `docs/NOMENCLATURE.md` — conventions de nommage à respecter dans tout nouveau code

#### Niveau 3 — Formats de la tâche (selon la couche concernée)
11. `docs/architecture/formats/FORMAT_FORCES.md` — si tâche touche la couche Forces
12. `docs/architecture/formats/FORMAT_SCENES.md` — si tâche touche la couche Scènes
13. `docs/architecture/formats/MEMORY_CONTRACT.md` — si tâche touche la mémoire
14. `docs/architecture/formats/FORMAT_COMPORTEMENTS.md` — si tâche touche Comportements
15. `docs/architecture/formats/FORMAT_FENETRES.md` — si tâche touche Fenêtres
16. `docs/architecture/formats/FORMAT_EXPLOITABILITE.md` — si tâche touche Exploitabilité
17. `docs/architecture/DB_SCHEMA.md` / `docs/architecture/CHAINE_COGNITIVE.md` / `docs/architecture/PIPELINE_LIVE.md` — détail technique complémentaire aux formats

#### Niveau 4 — Code existant (selon la couche concernée)
18. `core/v9/config.py` — configuration centrale (toujours)
19. `core/v9/db_schema.py` — schéma DB Forces (si couche Forces)
20. `core/v9/forces_reader.py` — reader Forces (si couche Forces)
21. `core/v9/capture_server.py` — serveur TCP (si couche Forces)
22. `core/v9/scene_builder.py` — builder Scènes (si couche Scènes)
23. `core/v9/scene_db.py` — schéma DB Scènes (si couche Scènes)
24. `core/v9/behavior_analyzer.py` — analyzer Comportements (si couche Comportements)
25. `core/v9/behavior_db.py` — schéma DB Comportements (si couche Comportements)
26. `core/v9/window_gate.py` — gate Fenêtres (si couche Fenêtres)
27. `core/v9/window_db.py` — schéma DB Fenêtres (si couche Fenêtres)
28. `core/v9/exploitability_evaluator.py` — évaluateur Exploitabilité (si couche Exploitabilité)
29. `core/v9/exploitability_db.py` — schéma DB Exploitabilité (si couche Exploitabilité)
30. `core/v9/regime_detector.py` / `principle_engine.py` / `signal_generator.py` / `decision_logger.py` (+ `*_db.py` associés, `core/v9/principles/*.yaml`) — si couche Régime/Principes/Signal/Décision (Phase 9)

#### Règles du rituel
- Le Niveau 1 est obligatoire pour TOUTE session, sans exception.
- Le Niveau 2 est obligatoire pour toute session qui implémente ou modifie du code.
- Le Niveau 3 est obligatoire pour la couche concernée par la tâche.
- Le Niveau 4 est obligatoire si la tâche touche du code existant.
- Si un document du Niveau 1 est absent ou incohérent, la session est considérée
  comme DÉGRADÉE et doit le signaler avant de poursuivre.
- Aucune IA ne doit s'appuyer sur une mémoire implicite de conversation précédente.
  La source de vérité est GitHub + les fichiers ci-dessus.

## Index des documents pivots

| Document | Rôle | Fréquence de lecture |
|---|---|---|
| docs/CACHE_BOARD.md | Tableau de bord compact, reprise rapide | Chaque session |
| docs/STATE.md | État exécutif, livrables, décisions actées | Chaque session |
| docs/checkpoints/ | Jalons structurants (chronologique) | Dernier uniquement |
| docs/PERPLEXITY.md | Rôle Perplexity dans l'orchestration | Si rôle orchestration |
| docs/DOCTRINE.md | Index des 30 règles immuables (renvoie vers doctrine/) | Toute session de code |
| docs/ARCHITECTURE.md | Vue d'ensemble technique, modules, flux de données | Toute session de code |
| docs/LEXIQUE.md | Index alphabétique du vocabulaire (renvoie vers lexicon/) | Toute session de code |
| docs/NOMENCLATURE.md | Conventions de nommage vérifiées contre le code | Tout nouveau code |
| docs/ROADMAP.md | Phases 9-13, leviers, risques connus | Si planification |
| docs/DOC_GOVERNANCE.md | Règles de gouvernance documentaire | Si création/modif de doc |
| docs/doctrine/CHARTE_COGNITIVE_V9.md | Charte cognitive, ordre des couches | Toute session de code |
| docs/lexicon/LEXICON_V9.md | Vocabulaire natif V9 | Toute session de code |
| docs/doctrine/ORCHESTRATION_POLICY_V9.md | Politique d'orchestration multi-IA | Si multi-session |
| docs/doctrine/MIGRATION_POLICY_V9.md | Politique de migration V8→V9 | Si reprise de V8 |
| docs/architecture/DB_SCHEMA.md | Schéma SQLite complet de toutes les tables | Si travail DB |
| docs/architecture/CHAINE_COGNITIVE.md | Détail des 5+1 couches cognitives | Toute session de code |
| docs/architecture/PIPELINE_LIVE.md | Flux EA → TCP → Python → DB → chaîne | Si déploiement live |
| docs/architecture/formats/FORMAT_FORCES.md | Format JSON couche Forces | Si couche Forces |
| docs/architecture/formats/FORMAT_SCENES.md | Format JSON couche Scènes | Si couche Scènes |
| docs/architecture/formats/MEMORY_CONTRACT.md | Contrat mémoire inter-couches | Si mémoire |
| docs/architecture/formats/FORMAT_COMPORTEMENTS.md | Format JSON couche Comportements | Si couche Comportements |
| docs/architecture/formats/FORMAT_FENETRES.md | Format JSON couche Fenêtres | Si couche Fenêtres |
| docs/architecture/formats/FORMAT_EXPLOITABILITE.md | Format JSON couche Exploitabilité | Si couche Exploitabilité |
| core/v9/config.py | Configuration centrale V9 | Toute session de code |
| core/v9/exploitability_evaluator.py | Évaluateur couche Exploitabilité | Si couche Exploitabilité |
| core/v9/exploitability_db.py | Schéma DB couche Exploitabilité | Si couche Exploitabilité |
| core/v9/market_calendar.py | Calendrier de marché (ouverture, session, conversions temporelles) | Si déploiement live |
| ea/V9_Sonde_README.md | Déploiement EA MT4 | Si travail sur EA |
| docs/deployment/V9_DEPLOYMENT_GUIDE.md | Guide de déploiement live complet | Si déploiement live |
| scripts/v9_dashboard.py | Dashboard terminal temps réel (lecture seule) | Si monitoring/observation live |
| scripts/v9_calibration.py | Analyse, export, statistiques (lecture seule) | Si calibration des seuils |
| scripts/v9_replay.py | Replay / inspection des comportements (lecture seule) | Si analyse rétrospective |
| docs/phases/ | Un document par phase, détail des livrables | Si reprise d'une phase spécifique |
| docs/DOC_REGISTRY.yml | Registre de tous les documents (statut, fraîcheur) | Si création/modif de doc |
| tools/doc_sync.py | Vérification cohérence doc/code (`--check`/`--update`/`--stale`) | Avant tout commit de doc |

## Statut du projet (2026-07-14)

| Phase | Couche | Statut | Tests |
|---|---|---|---|
| Phase 1 | Formats (6 fichiers) | ✅ Terminée | 13 blocs JSON valides |
| Phase 2 | Forces (EA MT4 + Python) | ✅ Terminée | 15 tests |
| Phase 3 | Scènes (SceneBuilder) | ✅ Terminée | 13 tests |
| Phase 4 | Comportements (BehaviorAnalyzer) | ✅ Terminée | 21 tests |
| Phase 5 | Fenêtres (WindowGate) | ✅ Terminée | 20 tests |
| Phase 6 | Exploitabilité (ExploitabilityEvaluator) | ✅ Terminée | 26 tests |
| Phase 7 | Déploiement live (market_calendar + scripts) | ✅ Terminée | 22 tests |
| Phase 8 | Monitoring + calibration + replay | ✅ Terminée | 21 tests |
| Phase 9 | Décision et Principes (Régime → Principes → Signal → Décision) | ✅ Canonisée 2026-07-05 | 75 tests |
| Phase 9.7 | Paper-Trade Simulator (Arbiter + RiskManager + PaperTradeLogger) | ✅ Livrée 2026-07-07 | 60 tests |
| Phase 9.8 | VPS-READY (heartbeat + cron + rollback DNS swap) | ✅ Livrée 2026-07-07 | 20 tests |
| Phase 9.9 | CONSOLIDATION-COMPLETE (14 sous-chantiers C-1→F-9, dette = 0) | ✅ Livrée 2026-07-07 | (compté dans 596 verts) |
| Phase 9.10 | RULE29 + WIN/LOSS resolver + Règle 30 | ✅ Livrée 2026-07-08 | +33 tests |
| Phase 10 | Fédération d'agents | ⏸️ Gelée par règle 19 (doctrine : stabilisation live) | — |
| Phase 11 | Layer MT4 ticks | ⏸️ Gelée par décision Søn | — |
| Phase 12 | Exécution d'ordres | ⏸️ Interdit fondateur (HITL) — `order_executor.py` créé (double-verrou, exécution réelle OFF) | — |
| Phase 13 | Apprentissage + recalibrage + auto-calibration | ✅ Phase 13 CEO livrée 2026-07-10 (CONFIANCE_MIN 80→70). Phase 13.2 simulation pro (4 modules). **Série Q1→Q5** (2026-07-12/13) : trader-mini, auto-calibrateur, dashboard HITL, multi-paires, order_executor. **Autopilot CEO** (2026-07-13) : P1 DYNAMIC, P3 adaptive thresholds, P5 long-term memory, P6 vol_regime. **ORDER-BRIDGE + P2 shadow** (2026-07-14). **P3-CONSUME-EXTEND** (2026-07-14, Hermes) : 26 YAML `_ADAPTIVE`. | 1334 tests |
| — | Audit cohérence + gardiens automatisés | ✅ Livré 2026-07-14 (ZCode) | `v9_guards.py` + `v9_sync_state.py` |

**Total : 1334 tests verts, 0 échec.** CHAÎNE COGNITIVE V9 ÉTENDUE À 9+1 COUCHES
— Forces → Scènes → Comportements → Fenêtres → Exploitabilité → Régime → Principes →
Signal → Décision → Arbiter/RiskManager → PaperTrade/Heartbeat. **Doctrine 30 règles immuables**
(règle 28 = Hermes opérateur git unique, **règle 29 = lecture scène-complète multi-TF**,
**règle 30 = apprentissage conditionnel WIN/LOSS**).

Phase 13 CEO livrée 2026-07-10 : CONFIANCE_MIN 80→70, arbiter neutre recalibré,
SIGNAL_OPEN.yaml SHADOW (1er YAML généré par meta-agent). Ménage 2026-07-11 :
71 paper trades clôturés, 102 décisions résiduelles résolues, **0 décision non résolue**.
**9516 décisions résolues (97.9% WR), 0 non résolue, 71 paper trades clôturés.**

Phase 9.10 = Règle 29 LIVRÉE : `zone_type` (naissance/2e_jambe/continuation/respiration)
calculé et persisté dans `principle_evaluations.context_json`, statut `naissance_isolee`
whitelisté dans `WindowGate.WINDOW_STATUTS` + promotion conditionnelle (bascule/rupture/
extension + point_de_rupture_detecte), HITL renforcé dans `exploitability_evaluator`,
pondération zone-type×session dans `arbiter.consolidate` (±15 max, indications Phase 13).

Pipeline live GBPUSD M5/M15/H1/H4/D1 : port 31685 actif, MT4 redémarré (17h00 CEST
2026-07-07 par Søn, capture flux rétablie), 130K+ forces / 69K scènes / 1.5M+ principle_evaluations.
**71 paper trades clôturés** (66W/5L, ménage 2026-07-11). **0 décision non résolue** (9516/9516).
Prochain driver macro US HIGH = **NFP vendredi 7 août 2026** (NFP juillet est sorti vendredi 3 juillet 2026,
1er vendredi du mois récurrent — cf. `data/economic_calendar.json`).

Mémoire interne = `workspace/perplexity/memory/*.md` (0 dépendance mem0).
Templates de reprise rapide :
- `workspace/perplexity/REPRISE_TEMPLATE.md` (Perplexity, rôle doctrinal)
- `workspace/perplexity/REPRISE_TEMPLATE_HERMES.md` (Hermes, rôle git + ops)

Voir `docs/V9_FONCTIONNEMENT.md` pour le mode d'emploi global, `docs/checkpoints/CHECKPOINT_20260707_RULE29.md`
pour la règle 29, `docs/checkpoints/CHECKPOINT_20260707_PHASE9_9.md` pour Phase 9.9.

## Interdits fondateurs

- Ne pas hériter implicitement de V8, de Hermes legacy, ou de workflows non audités.
- Ne pas introduire d'outillage (RAG, scoring, agentisation, multi-IA) avant d'avoir localisé
  sa place exacte dans la chaîne cognitive.
- Ne pas confondre lecture et décision, comportement et signal, scène et trade.

Voir `AGENT.md` et `docs/doctrine/CHARTE_COGNITIVE_V9.md` pour le détail complet.
