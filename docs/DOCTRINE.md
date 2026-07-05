# DOCTRINE — PowerFlow V9

## Statut
Document pivot de navigation. Ce fichier ne contient pas le détail des règles :
il les résume en une ligne et renvoie vers le document source qui fait foi.
**En cas de divergence, le document source (colonne « Détail ») l'emporte sur ce résumé.**

## Sources de la doctrine

| Document source | Contenu détaillé |
|---|---|
| [docs/doctrine/CHARTE_COGNITIVE_V9.md](doctrine/CHARTE_COGNITIVE_V9.md) | Mission, chaîne cognitive officielle, définitions natives, règles de gouvernance 1-5 |
| [docs/doctrine/MEMORY_POLICY_V9.md](doctrine/MEMORY_POLICY_V9.md) | Types de mémoire, cycle de vie, politique de reprise de session |
| [docs/doctrine/ORCHESTRATION_POLICY_V9.md](doctrine/ORCHESTRATION_POLICY_V9.md) | Rôles d'agents, règles d'appel, conditions HITL |
| [docs/doctrine/MIGRATION_POLICY_V9.md](doctrine/MIGRATION_POLICY_V9.md) | Classification A/B/C/D de tout élément candidat à la migration V8→V9 |
| [docs/architecture/audit_v8_v9_migration.md](architecture/audit_v8_v9_migration.md) | Application de la politique de migration à l'inventaire réel de V8 |

## Les 13 règles immuables

Ces règles sont une synthèse opérationnelle des documents ci-dessus, plus quelques règles
d'ingénierie (tests, documentation, anti-dette) qui n'avaient pas encore de foyer écrit.

| # | Règle | Détail / preuve |
|---|---|---|
| 1 | Le code est la source de vérité, pas la doc | Règle de gouvernance de ce chantier documentaire (voir [DOC_GOVERNANCE.md](DOC_GOVERNANCE.md)) |
| 2 | Chaque couche est additive et filtrante | [docs/v9_processus_complet.md](v9_processus_complet.md) §2 ; [CHAINE_COGNITIVE.md](architecture/CHAINE_COGNITIVE.md) |
| 3 | Pas de signal si exploitabilité != exploitable | `core/v9/exploitability_evaluator.py` (statuts : non_exploitable, watchlist, exploitable, refuse, ambigu) |
| 4 | Les données stale (seuils par TF, voir `config.py`) sont rejetées | `core/v9/stale_gate.py` — StaleGate bloquant, marque stale mais ne supprime jamais |
| 5 | Anti-replay : une bougie fermée = un seul snapshot | `core/v9/db_schema.py` — UNIQUE INDEX sur `bar_time` (`forces_snapshots`) |
| 6 | L'orchestrateur ne crash jamais (try/except par couche) | `core/v9/orchestrator.py` — voir [PIPELINE_LIVE.md](architecture/PIPELINE_LIVE.md) |
| 7 | Tests obligatoires avant commit | Convention de fait depuis Phase 1 (139+ tests, tous verts) ; non encore vérifié par CI, voir [DOC_GOVERNANCE.md](DOC_GOVERNANCE.md) |
| 8 | Documentation mise à jour à chaque PR | [DOC_GOVERNANCE.md](DOC_GOVERNANCE.md) |
| 9 | Pas de dette technique héritée (V6/V7/V8 = legacy) | [MIGRATION_POLICY_V9.md](doctrine/MIGRATION_POLICY_V9.md) — rien n'entre sans classification A/B/C/D |
| 10 | MT4 (forces) dicte, MT5 (ticks) confirme | Levier 5 / Phase 11, [docs/v9_processus_complet.md](v9_processus_complet.md) — pas encore implémenté |
| 11 | Les principes sont des DÉTECTEURS, pas des signaux de trading directs | Phase 9 (en cours), `core/v9/principle_engine.py` — voir [docs/phases/PHASE9_DECISION.md](phases/PHASE9_DECISION.md) |
| 12 | Replay et live sont marqués distinctement dans les décisions | Point ouvert identifié dans [docs/v9_processus_complet.md](v9_processus_complet.md) §5 — non encore implémenté au niveau décision (Phase 9) |
| 13 | Le système observe d'abord, agit ensuite (paper → réel) | [CHARTE_COGNITIVE_V9.md](doctrine/CHARTE_COGNITIVE_V9.md) — priorité 1 « fidélité de lecture », exécution en dernier |

## Règle de lecture

Pour toute tâche de code touchant une couche précise, se référer au **Niveau 2/3/4** du rituel
de démarrage décrit dans [README.md](../README.md), qui reste la procédure de référence.
Ce fichier DOCTRINE.md est un point d'entrée synthétique, pas un remplacement du rituel.
