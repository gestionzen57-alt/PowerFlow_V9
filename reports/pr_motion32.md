## Motion #32 — Résolution drift loop : idempotence `paper_trades`

### TL;DR
Le prompt Motion #32 décrivait une boucle de résolution qui *dérive encore*, avec
doublons, zombies et WR gonflé à 90,33 %. **La vérification sur la base live infirme
la quasi-totalité de ces prémisses** : le schéma ciblé n'existe pas, et l'incident
de duplication était **déjà colmaté**. Cette PR livre l'audit factuel + le **seul
correctif durable pertinent** (contrainte d'unicité + garde applicative), validé par
décision CEO (scope « audit + index préventif »).

### Constats (audit lecture seule)
| Prompt | Réalité live (`data/v9_forces.db`) |
|---|---|
| `paper_trades(snapshot_id, principle_name, side, outcome, profit_pips, resolved_at)` | Colonnes réelles : `trade_id, snapshot_id, direction, confiance, principes_source, opened_at, closed_at, pips_simulated, is_win, risk_go_context` — **5 colonnes du prompt inexistantes** |
| Join `force_snapshots_v2` | Table inexistante (réelle = `forces_snapshots`) |
| Bus `agent_event_bus` | Table inexistante (réelle = `events`) |
| Doublons résolus N fois | **0 doublon** sur `(snapshot_id, direction, principes_source)` |
| Pending zombies | **0 zombie**, 1 trade ouvert légitime |
| WR 90,33 % gonflé | WR réel **69,10 %** (123/178) ; 90,33 % = figure **historique** pré-DROP (4752 trades), non reproductible |

→ La migration destructive + FK + lock du prompt **ne compilent pas** (colonnes/tables
absentes) et corrigeraient un problème **déjà résolu** (18 lignes fantômes déjà archivées
dans `paper_trades_dedup_20260720`).

### Cause racine
`paper_trades` n'avait **aucune contrainte d'unicité** (seul `trade_id` PK). Une
ré-résolution/ré-ouverture du même snapshot recréait une ligne (nouveau `trade_id`)
au lieu d'être rejetée → duplication silencieuse (incident 3 snapshots × 6 le 17-20/07).
Un garde applicatif existait déjà côté `TradeEngine._trade_already_open` (`bff59e2`,
query-time, race-prone) ; cette PR ajoute la **garantie atomique au niveau DB**.

### Correctif (additif, R2)
- **`core/v9/migrations/20260720_unique_paper_trade.sql`** — idempotent : dédup
  `MIN(rowid)` (NO-OP sur prod, 0 doublon) + `UNIQUE INDEX idx_pt_snap_dir_princ
  (snapshot_id, direction, principes_source)`.
- **`core/v9/paper_trade_logger.py`** — `log_open` : `INSERT ... ON CONFLICT DO
  NOTHING`, renvoie le `trade_id` **canonique** existant (jamais un id fantôme) →
  idempotence dans le chemin live (`TradeEngine.log_open`).
- **`core/v9/paper_trades_db.py`** — index unique ajouté au schéma (DB fraîches).
- **`scripts/v9_rollback_motion32.py`** — rollback **non destructif** (DROP INDEX seul,
  `--dry-run`), 0 donnée touchée.

### Application prod
Migration jouée sur `data/v9_forces.db` après pré-check `dup_groups==0` :
**178 → 178** lignes (0 suppression, `DELETE` vérifié NO-OP), index en place, WR inchangé.

### Tests (R7)
- `tests/test_resolve_drift.py` — **6/6 vert** :
  `test_dedup_unique_constraint_blocks_duplicate`, `test_log_open_idempotent_returns_same_trade_id`,
  `test_distinct_direction_creates_two_trades`, `test_migration_idempotent`,
  `test_wr_recomputed_after_dedup`, `test_rollback_path_idempotent`.
- **34** tests paper-trade liés verts (0 régression).

### Hors scope (sur-ingénierie écartée, décision CEO)
FK `force_snapshots_v2` (table inexistante), table `resolve_lock` distribuée,
stress 1000-concurrent, métriques Prometheus — disproportionnés pour 178 lignes /
1 writer SQLite. Dédup `DELETE` massif : **déjà fait** avant cette session.

### Rollback
```bash
python scripts/v9_rollback_motion32.py --dry-run   # inspection
python scripts/v9_rollback_motion32.py             # DROP INDEX (non destructif)
git reset --hard pre-motion-32-resolve-drift       # rollback code
```

### Garde-fous
- `data/strategy_pole/catalogue.json` **non touché**.
- Aucune promotion SHADOW→ACTIVE (R25').
- Tag `pre-motion-32-resolve-drift` posé (`6aee973`).
- 5 events `paper_trade.*` publiés sur le bus.

### Impact WR
90,33 % (annoncé, historique) → **69,10 % (réel, inchangé par cette PR)**. La PR ne
modifie aucun WR : elle empêche structurellement la **future** re-duplication.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
