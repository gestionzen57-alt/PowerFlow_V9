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
| [docs/architecture/CONTEXT_CONTRACT.md](architecture/CONTEXT_CONTRACT.md) | Contrat vivant de propagation des métriques entre couches (PROPAGÉ / DORMANT) |

## Les 27 règles immuables

Ces règles sont une synthèse opérationnelle des documents ci-dessus, plus des règles
d'ingénierie (tests, documentation, calibration, process de session) issues des retours live.

| # | Règle | Détail / preuve |
|---|---|---|
| 1 | Le code est la source de vérité, pas la doc | Règle de gouvernance (voir [DOC_GOVERNANCE.md](DOC_GOVERNANCE.md)) |
| 2 | Chaque couche est additive et filtrante | [CHAINE_COGNITIVE.md](architecture/CHAINE_COGNITIVE.md) |
| 3 | Pas de signal si exploitabilité != exploitable | `core/v9/exploitability_evaluator.py` |
| 4 | Les données stale (seuils par TF, voir `config.py`) sont rejetées | `core/v9/stale_gate.py` |
| 5 | Anti-replay : une bougie fermée = un seul snapshot | `core/v9/db_schema.py` — UNIQUE INDEX `bar_time` |
| 6 | L'orchestrateur ne crash jamais (try/except par couche) | `core/v9/orchestrator.py` |
| 7 | Tests obligatoires avant commit — zéro régression tolérée | Convention depuis Phase 1 ; 339 tests verts au 2026-07-06 |
| 8 | Documentation mise à jour à chaque livraison | [DOC_GOVERNANCE.md](DOC_GOVERNANCE.md) |
| 9 | Pas de dette technique héritée (V6/V7/V8 = legacy) | [MIGRATION_POLICY_V9.md](doctrine/MIGRATION_POLICY_V9.md) |
| 10 | MT4 (forces) dicte, MT5 (ticks) confirme | Phase 11 future — pas encore implémenté |
| 11 | Les principes sont des DÉTECTEURS, pas des signaux de trading directs | `core/v9/principle_engine.py` (10 ACTIVE / 17 SHADOW) |
| 12 | Replay et live sont marqués distinctement dans les décisions | Colonne `source_type` sur les 8 tables dérivées ; voir `CHECKPOINT_20260706_V9_SOURCE_TYPE.md` |
| 13 | Le système observe d'abord, agit ensuite (paper → réel) | [CHARTE_COGNITIVE_V9.md](doctrine/CHARTE_COGNITIVE_V9.md) |
| 14 | Le Git courant est la source de vérité, jamais une mémoire de conversation | [README.md](../README.md) « Rituel de lecture » |
| 15 | Une seule source de vérité par sujet — jamais duplication | [DOC_GOVERNANCE.md](DOC_GOVERNANCE.md) règle 8 |
| 16 | La migration métier précède toute agentification généralisée | [ROADMAP.md](ROADMAP.md) |
| 17 | L'autonomie ne progresse qu'après stabilité démontrée en live | [ROADMAP.md](ROADMAP.md) |
| 18 | Aucune dépendance bloquante à un provider LLM pour le cœur cognitif | [ARCHITECTURE.md](ARCHITECTURE.md) |
| 19 | Les chantiers agents/routing/skills auto-générés ne démarrent pas avant canonisation live | [ROADMAP.md](ROADMAP.md) |
| **20** | **Calibration-first : avant tout chantier de code sur marché ouvert, lancer `v9_calibration.py --analyze` et `v9_dashboard.py --once`** | Issue retour live 2026-07-06 : enrichissement de contexte fait à l'aveugle sans calibration préalable. Règle applicable dès que nb_snapshots >= 20. |
| **21** | **Toute métrique ajoutée dans une couche doit être tracée dans `CONTEXT_CONTRACT.md` (PROPAGÉ ou DORMANT justifié) avant ou au moment du commit** | [docs/architecture/CONTEXT_CONTRACT.md](architecture/CONTEXT_CONTRACT.md) ; `tests/test_context_propagation.py` est le gardien automatique |
| **22** | **Une session = un périmètre = une livraison complète. Jamais de chantier ouvert non livré en fin de session** | Retour session 2026-07-06 : tuning YAML reporté d'une session, laissant le contexte enrichi cognitivement muet. Un chantier commencé = terminé dans la même session ou explicitement découpé en unité livrable autonome. |
| **23** | **Les principes YAML consommateurs d'un champ contexte doivent être mis à jour dans la même session que le champ** | Corollaire de la règle 22. Exception acceptée : champ DORMANT (P3) — il doit alors être explicitement marqué DORMANT dans CONTEXT_CONTRACT.md avec raison. |
| **24** | **CONTEXT_CONTRACT.md est mis à jour à la clôture de chaque phase, pas en rattrapage** | Retour Phase 9 : anomalies #3/#4 non détectées pendant 24h. Le CONTEXT_CONTRACT.md créé en fin de Phase 10 fait partie du livrable de la phase, au même titre que les tests. |
| **25** | **La promotion SHADOW → ACTIVE d'un principe ne peut se faire que sur données live réelles (hit_rate >= seuil opérateur) — jamais par décision arbitraire** | `scripts/v9_calibration.py --principes` est la source de vérité pour la promotion. Seuil par défaut : hit_rate >= 60% sur >= 50 déclenchements. |
| **26** | **Chaque session de code produit : 1 commit par unité logique + 1 entrée DECISIONS_LOG + STATE.md à jour. Aucune session ne se ferme sans ces 3 livrables documentaires** | Retour ops 2026-07-06 : STATE.md mis à jour en rattrapage par Perplexity, pas par l'agent implémenteur. Ce retard craint un écart temporaire de source de vérité. |
| **27** | **Un champ DORMANT qui reste DORMANT plus de 2 phases est réévalué : soit promu PROPAGÉ, soit supprimé de la chaîne** | Évite l'accumulation de champs calculés mais jamais consommés. Évaluation lors du checkpoint de chaque phase. |
| **28** | **Hermes est l'opérateur git unique de V9 — Søn ne gère pas le git** | Søn est novice git et déteste le git (confirmé 2026-07-07). Hermes gère TOUT le git seul : commit, push, branch, PR, squash, merge, rebase local. Ne JAMAIS demander validation de message de commit, de squash vs merge, de push, de feature branch. Toujours montrer le SHA + 1 ligne description. Exceptions (re-ask autorisé) : (a) credential/2FA demandé, (b) force-push destructif, (c) opération irréversible hors scope session. |

## Process de session — ordre obligatoire

Ce process s'applique à toute session de code sur `feat/v9-foundation-clean`.

```
┌──────────────────────────────────────────────────────────────────────┐
│ 0. git pull + pytest → confirmer base saine               │
│ 1. [marché ouvert?] OUI → v9_calibration --analyze OBLIGATOIRE   │
│    [marché ouvert?] NON → passer au 2                         │
│ 2. périmètre explicité : un chantier, une livraison complète   │
│ 3. implémentation                                              │
│ 4. tests verts (zéro régression)                              │
│ 5. CONTEXT_CONTRACT.md mis à jour si nouveau champ             │
│ 6. principes YAML consommateurs mis à jour (règle 23)          │
│ 7. commits atomiques (1 par unité logique)                     │
│ 8. DECISIONS_LOG.md — 1 entrée par décision structurante      │
│ 9. STATE.md à jour                                             │
│ 10. git push origin feat/v9-foundation-clean                   │
└──────────────────────────────────────────────────────────────────────┘
```

## Cycle de promotion d'un principe

```
SHADOW ──[live >= 50 déclench., hit_rate >= 60%]──► ACTIVE (décision opérateur)
ACTIVE ──[hit_rate < 40% sur >= 100 déclench.]──► retour SHADOW (décision opérateur)
DORMANT ──[2 phases sans promotion]──► réévaluation : PROPAGÉ ou supprimé (règle 27)
```

## Cycle de vie d'un champ contexte

```
NOUVEAU CHAMP
  │
  ├── calculé + injecté dans _load_shared_context
  ├── tracé dans CONTEXT_CONTRACT.md (PROPAGÉ ou DORMANT P2/P3)
  ├── test_context_propagation.py mis à jour
  └── [si PROPAGÉ] → principes YAML consommateurs mis à jour (même session)
       [si DORMANT] → justification écrite dans CONTEXT_CONTRACT.md
                        réévaluation au prochain checkpoint de phase
```

## Règle de lecture

Pour toute tâche de code touchant une couche précise, se référer au **Niveau 2/3/4** du rituel
de démarrage décrit dans [README.md](../README.md), qui reste la procédure de référence.
Ce fichier DOCTRINE.md est un point d'entrée synthétique, pas un remplacement du rituel.
