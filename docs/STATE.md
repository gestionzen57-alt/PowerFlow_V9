# STATE — PowerFlow V9

> **Source de vérité vivante.** La section AUTO ci-dessous est générée
> automatiquement par `scripts/v9_sync_state.py` depuis les sources réelles
> (DB, pytest, git, disque). Ne pas éditer manuellement.
>
> Pour l'historique complet des phases, voir [`JOURNAL_PHASES.md`](JOURNAL_PHASES.md).

## État courant — généré automatiquement

<!-- AUTO:STATE -->
<!-- Généré automatiquement par scripts/v9_sync_state.py — 2026-07-15 21:03 UTC -->
<!-- Ne pas éditer manuellement. Pour forcer : python scripts/v9_sync_state.py -->

| Métrique | Valeur | Source |
|---|---|---|
| HEAD | `531104f feat(v9): activation V9_LEARNING_OFFSET_ENABLED=1` | `git log --oneline -1` |
| Tests collectés | 1401 | `pytest --collect-only` |
| Tables DB | 22 | `sqlite3 data/v9_forces.db` |
| Index DB | 54 | `sqlite3` |
| Taille DB | 1.43 GB | `du -h` |
| Décisions | 66135 | `SELECT count(*) FROM decisions` |
| Forces snapshots | 115851 | DB |
| Scènes | 66153 | DB |
| Principle evals | 621105 | DB |
| Régime snapshots | 529088 | DB |
| Paper trades | 58 | DB |
| Principle scores | 5 | DB |
| Principes YAML | 53 (25 ACTIVE + 23 SHADOW) | `ls core/v9/principles/*.yaml` |
| Serveurs MCP | 8 | `ls mcp_servers/*.py` |
| Crons Ready | 0 | `schtasks /query` |
| V9_TRADER_MINI_ENABLED | 1 | `config/v9_kill_switches.env` |
| V9_AUTO_CALIBRATOR_ENABLED | 1 | env |
| V9_SHADOW_MODE_ENABLED | 1 | env |
| V9_ADAPTIVE_THRESHOLDS_WIRED_ENABLED | 1 | env |
| V9_EXECUTION_ENABLED | 1 | env |

<!-- /AUTO:STATE -->

## Phase actuelle

**Session Claude Code 2026-07-15 — reprise ZCode, tests + strategy profiles** :
Reprise après commit ZCode `98119c4` (infra collaborative IA + trade engine
consolidé + SOUL.md). 8 tests désynchronisés corrigés (comptages ACTIVE/SHADOW
+ scénarios GRAMMAR_CONTEXTE migrés vers GRAMMAR_CONTEXTE_ADAPTIVE, DORMANT
n'étant plus audité). 18 strategy profiles ajoutés aux principes ACTIVE
restants (7 avec données réelles, 11 conservateurs). 1339 verts + 1 skip +
0 fail. Détail : `workspace/perplexity/memory/DECISIONS_LOG.md` §2026-07-15.

**Catalogue principes** : 25 ACTIVE (27→25 : 5 mis DORMANT — COALITION_NODE,
NODE_BIRTH_FAST, RAW_NODE_BIRTH, ELASTIC_BREATH, GRAMMAR_CONTEXTE — + 3
`*_ADAPTIVE` promus ACTIVE — GRAMMAR_CONTEXTE_ADAPTIVE 79.5%,
POWER_ANGLE_BREAK_TO_PRICE_IMPACT_ADAPTIVE 75.0%, ZONE_RETEST_ADAPTIVE 66.7%).
23 SHADOW YAML restants, 5 DORMANT. Sessions tradables : asie + london
uniquement (overlap blacklisté, expectancy -2.26 pips/trade). zone_diagnostics
réactivé (14 SHADOW débloquées). trade_engine : hook orchestrator actif.
PrincipleStrategyEngine : tous les principes ACTIVE ont désormais un champ
`strategy`.

P3-CONSUME-EXTEND **CLOSED** §2.2 (bilan, baseline 1307 verts, tous YAML `*_ADAPTIVE`
SHADOW R25' strict). Promotion ACTIVE = motion CEO distincte ultérieure.

WIRE activé 14/07 commit `ac26c3a` (motion CEO priorité 3). Les `*_ADAPTIVE.yaml`
SHADOW consomment désormais les seuils adaptatifs runtime.

TP_SL P3-D1 **CLOSED-OBSOLETE** §2.3 — 0 cas TP_SL depuis P1-RESOLVE 14/07, neutralisée
par doctrine (DYNAMIC default 8131 cas, 88.65% WR).

**Série Q1→Q5 clôturée** (2026-07-12/13) : trader-mini baseline, auto-calibrateur,
dashboard HITL, multi-paires, order_executor (double-verrou, Phase 12 gelée).
Kill switches `V9_TRADER_MINI_ENABLED=1` et `V9_AUTO_CALIBRATOR_ENABLED=1` activés
par motion CEO 2026-07-14.

**Fable hors service** (pas de crédit). ZCode et Hermes continuent en parallèle
sur `feat/v9-foundation-clean`.

## Dernier commit

Voir `git log --oneline -1` (git gagne toujours — ce champ dérive vite).

## Règles pour toute IA prenant la relève

```
1. Lire docs/CACHE_BOARD.md (2 min) AVANT toute action
2. Lire docs/STATE.md (ce document) — état exécutif complet
3. git pull + pytest tests/ -q + python scripts/v9_guards.py all → confirmer base saine
4. R20' : si marché ouvert → v9_calibration --analyze OBLIGATOIRE
5. R7 : zéro régression non justifiée (assoupli 2026-07-14, DOCTRINE.md)
6. R8 : backup MD5 avant toute modif core/v9/
7. R18 : zéro LLM dans le cœur cognitif
8. R22 : un périmètre = une livraison complète (assoupli 2026-07-14)
9. R26 : 1 commit + 1 DECISIONS_LOG + STATE.md à jour
10. R28 : Hermes = opérateur git unique (assoupli 2026-07-14)
```

## Références pivots

| Document | Rôle |
|---|---|
| `docs/CACHE_BOARD.md` | Tableau de bord compact (2 min) |
| `docs/STATE.md` | **CE DOCUMENT** — état exécutif |
| `docs/JOURNAL_PHASES.md` | Journal historique des phases (archive) |
| `docs/DOCTRINE.md` | 30 règles immuables |
| `workspace/perplexity/memory/DECISIONS_LOG.md` | Journal des décisions |
| `workspace/perplexity/BOARD.md` | Board de coordination |
| `workspace/perplexity/ACTIVE_TASKS.md` | Tâches actives |
| `scripts/v9_guards.py` | Gardiens de cohérence automatisés |
| `scripts/v9_sync_state.py` | Régénérateur automatique de l'état |