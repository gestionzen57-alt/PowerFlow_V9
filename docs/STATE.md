# STATE — PowerFlow V9

> **Source de vérité vivante.** La section AUTO ci-dessous est générée
> automatiquement par `scripts/v9_sync_state.py` depuis les sources réelles
> (DB, pytest, git, disque). Ne pas éditer manuellement.
>
> Pour l'historique complet des phases, voir [`JOURNAL_PHASES.md`](JOURNAL_PHASES.md).

## État courant — généré automatiquement

<!-- AUTO:STATE -->
<!-- Généré automatiquement par scripts/v9_sync_state.py — 2026-07-14 21:54 UTC -->
<!-- Ne pas éditer manuellement. Pour forcer : python scripts/v9_sync_state.py -->

| Métrique | Valeur | Source |
|---|---|---|
| HEAD | `0c86914 feat(v9): P3-WIRE activé + SIGNAL_OPEN/ADAPTIVE_VOL_GATE promus ACTIVE (motion CEO)` | `git log --oneline -1` |
| Tests collectés | 1335 | `pytest --collect-only` |
| Tables DB | 19 | `sqlite3 data/v9_forces.db` |
| Index DB | 49 | `sqlite3` |
| Taille DB | 1.38 GB | `du -h` |
| Décisions | 64325 | `SELECT count(*) FROM decisions` |
| Forces snapshots | 114004 | DB |
| Scènes | 64343 | DB |
| Principle evals | 579122 | DB |
| Régime snapshots | 514608 | DB |
| Paper trades | 0 | DB |
| Principle scores | 5 | DB |
| Principes YAML | 53 (27 ACTIVE + 26 SHADOW) | `ls core/v9/principles/*.yaml` |
| Serveurs MCP | 7 | `ls mcp_servers/*.py` |
| Crons Ready | 0 | `schtasks /query` |
| V9_TRADER_MINI_ENABLED | 1 | `config/v9_kill_switches.env` |
| V9_AUTO_CALIBRATOR_ENABLED | 1 | env |
| V9_SHADOW_MODE_ENABLED | 1 | env |
| V9_ADAPTIVE_THRESHOLDS_WIRED_ENABLED | 1 | env |
| V9_EXECUTION_ENABLED | 0 (commenté) | env |

<!-- /AUTO:STATE -->

## Phase actuelle

**P3-CONSUME-EXTEND en cours** (Hermes, mandat CEO 2026-07-14 ~18:35 UTC) :
génération des variantes `*_ADAPTIVE.yaml` qui consomment les seuils adaptatifs
P3-WIRE. 26 YAML `_ADAPTIVE` créés (5 node_rule + 4 birth/break + 17 grammar/SIGNAL_OPEN),
tous SHADOW par défaut (R25' strict). `V9_ADAPTIVE_THRESHOLDS_WIRED_ENABLED=0` —
activation = décision Søn distincte.

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