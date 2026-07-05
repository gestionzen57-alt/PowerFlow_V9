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

1. Forces
2. Scènes
3. Comportements
4. Fenêtres
5. Exploitabilité
6. Exécution éventuelle

Aucune couche aval ne peut court-circuiter une couche amont.

## Arborescence

```
PowerFlow_V9/
├── README.md                  — ce fichier
├── AGENT.md                   — document racine, rôle et routing du système
├── docs/
│   ├── PERPLEXITY.md          — rôle Perplexity dans l'orchestration
│   ├── STATE.md               — état exécutif du chantier
│   ├── CACHE_BOARD.md         — tableau de bord compact de reprise
│   ├── checkpoints/           — jalons structurants
│   ├── doctrine/
│   │   ├── CHARTE_COGNITIVE_V9.md
│   │   ├── ORCHESTRATION_POLICY_V9.md
│   │   ├── MIGRATION_POLICY_V9.md
│   │   └── MEMORY_POLICY_V9.md
│   ├── architecture/
│   │   ├── IMPLEMENTATION_ROADMAP_V9.md
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
│       └── exploitability_db.py
├── ea/
│   ├── V9_Sonde_TF.mq4
│   ├── V9_Sonde_M1.mq4
│   └── V9_Sonde_README.md
├── tests/
│   ├── test_stale_gate.py
│   ├── test_forces_reader.py
│   ├── test_scene_builder.py
│   ├── test_behavior_analyzer.py
│   ├── test_window_gate.py
│   ├── test_exploitability_evaluator.py
│   ├── test_full_chain.py
│   ├── test_market_calendar.py
│   └── fixtures/
├── memory/                    — memory.md / memory_temp.md / exchange.md
├── assets/                    — loop / reading / windows / scenes / behaviors
├── skills/                    — scene-reader, behavior-reader, window-evaluator, replay-confronter, doctrine-keeper
├── agents/                    — orchestrator, force-reader, scene-builder, behavior-analyst, window-gate, reviewer
├── runtime/                   — state / reports / logs / snapshots
├── scripts/                   — deploy_v9.py, validate_ea_output.py, live_integration_test.py
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
4. `docs/doctrine/CHARTE_COGNITIVE_V9.md` — charte cognitive, ordre des couches
5. `docs/lexicon/LEXICON_V9.md` — vocabulaire natif V9
6. `docs/doctrine/ORCHESTRATION_POLICY_V9.md` — politique d'orchestration
7. `docs/doctrine/MIGRATION_POLICY_V9.md` — politique de migration V8→V9

#### Niveau 3 — Formats de la tâche (selon la couche concernée)
8. `docs/architecture/formats/FORMAT_FORCES.md` — si tâche touche la couche Forces
9. `docs/architecture/formats/FORMAT_SCENES.md` — si tâche touche la couche Scènes
10. `docs/architecture/formats/MEMORY_CONTRACT.md` — si tâche touche la mémoire
11. `docs/architecture/formats/FORMAT_COMPORTEMENTS.md` — si tâche touche Comportements
12. `docs/architecture/formats/FORMAT_FENETRES.md` — si tâche touche Fenêtres
13. `docs/architecture/formats/FORMAT_EXPLOITABILITE.md` — si tâche touche Exploitabilité

#### Niveau 4 — Code existant (selon la couche concernée)
14. `core/v9/config.py` — configuration centrale (toujours)
15. `core/v9/db_schema.py` — schéma DB Forces (si couche Forces)
16. `core/v9/forces_reader.py` — reader Forces (si couche Forces)
17. `core/v9/capture_server.py` — serveur TCP (si couche Forces)
18. `core/v9/scene_builder.py` — builder Scènes (si couche Scènes)
19. `core/v9/scene_db.py` — schéma DB Scènes (si couche Scènes)
20. `core/v9/behavior_analyzer.py` — analyzer Comportements (si couche Comportements)
21. `core/v9/behavior_db.py` — schéma DB Comportements (si couche Comportements)
22. `core/v9/window_gate.py` — gate Fenêtres (si couche Fenêtres)
23. `core/v9/window_db.py` — schéma DB Fenêtres (si couche Fenêtres)
24. `core/v9/exploitability_evaluator.py` — évaluateur Exploitabilité (si couche Exploitabilité)
25. `core/v9/exploitability_db.py` — schéma DB Exploitabilité (si couche Exploitabilité)

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
| docs/doctrine/CHARTE_COGNITIVE_V9.md | Charte cognitive, ordre des couches | Toute session de code |
| docs/lexicon/LEXICON_V9.md | Vocabulaire natif V9 | Toute session de code |
| docs/doctrine/ORCHESTRATION_POLICY_V9.md | Politique d'orchestration multi-IA | Si multi-session |
| docs/doctrine/MIGRATION_POLICY_V9.md | Politique de migration V8→V9 | Si reprise de V8 |
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

## Statut du projet (2026-07-05)

| Phase | Couche | Statut | Tests |
|---|---|---|---|
| Phase 1 | Formats (6 fichiers) | ✅ Terminée | 13 blocs JSON valides |
| Phase 2 | Forces (EA MT4 + Python) | ✅ Terminée | 15 tests |
| Phase 3 | Scènes (SceneBuilder) | ✅ Terminée | 13 tests |
| Phase 4 | Comportements (BehaviorAnalyzer) | ✅ Terminée | 21 tests |
| Phase 5 | Fenêtres (WindowGate) | ✅ Terminée | 20 tests |
| Phase 6 | Exploitabilité (ExploitabilityEvaluator) | ✅ Terminée | 26 tests |
| Phase 7 | Déploiement live (market_calendar + scripts) | ✅ Terminée | 22 tests |

**Total : 118 tests, tous verts.** CHAÎNE COGNITIVE V9 COMPLÈTE — 6/6 couches implémentées (Forces → Scènes → Comportements → Fenêtres → Exploitabilité). Outillage de déploiement live prêt (`scripts/deploy_v9.py`, `scripts/validate_ea_output.py`, `scripts/live_integration_test.py`) — voir `docs/deployment/V9_DEPLOYMENT_GUIDE.md`.

## Interdits fondateurs

- Ne pas hériter implicitement de V8, de Hermes legacy, ou de workflows non audités.
- Ne pas introduire d'outillage (RAG, scoring, agentisation, multi-IA) avant d'avoir localisé
  sa place exacte dans la chaîne cognitive.
- Ne pas confondre lecture et décision, comportement et signal, scène et trade.

Voir `AGENT.md` et `docs/doctrine/CHARTE_COGNITIVE_V9.md` pour le détail complet.
