# DB purge session — 2026-08-15

## Contexte
- Disque C: 80% plein (20 Go libres / 96 Go)
- v9_forces.db = 36,6 Go (35 Go) — 99% du dossier data
- Table `principle_evaluations` = 46,8M rows = ~30 Go (le monstre)
- Croissance non bornée : +1,5M rows/jour, DB 18 → 35 Go en 1 semaine
- Aucun mécanisme de rétention dans le code (R7 motion CEO explicite)
- CEO motion 2026-08-15 : « arrête tous les crons, marché fermé 48h weekend »

## Problème racine
- `principle_evaluations` n'a pas d'index sur `created_at`
- Le pipeline `principle_engine._write_evaluations_to_db` fait `INSERT OR REPLACE`
  en boucle, jamais de `DELETE`
- Conséquence : impossible de purger sans full table scan de 30+ Go

## Stratégie déployée (3 étapes)

### Étape 1 — Rétention auto (commit `d457001`)
- `core/v9/principle_db.py` : `principle_retention_days()` (env var `V9_PRINCIPLE_RETENTION_DAYS`, défaut 30) + `purge_principle_evaluations_older_than(conn, days, chunk=500k)`
- `core/v9/principle_engine.py` : appel automatique après chaque commit d'écriture
- `tests/test_v9_principle_retention.py` : 8 tests verts (kill switch, idempotence, chunking)
- 0 régression sur 55 tests principle_engine

### Étape 2 — Scripts de purge (commit `d457001`)
- `scripts/v9_purge_live.py` : purge mode LIVE tolérant (writers actifs), VACUUM retry sur SQLITE_BUSY
- `scripts/v9_purge_principle_evaluations.py` : purge mode OFFLINE (writers arrêtés)

### Étape 3 — Purge réelle (en cours à l'heure de ce rapport)
- MD5 défensif R8 : `ad66e644752ad5938e521b12942a5b90` (35 Go, 82s de calcul)
- 10 crons Hermes pausés (CEO motion)
- 3 Scheduled Tasks Windows (V9SignalAlerter, V9CvdSentinel, V9CVDWatchdog) en cours de disable
- CREATE INDEX `idx_pe_created_at` lancé (était non indexé → sinon full scan impossible)
- DELETE + VACUUM à enchaîner après création index

## Pièges identifiés

1. **Pas d'index sur `created_at`** → DELETE fait un full table scan de 30+ Go par chunk. Inacceptable en pratique. Solution : CREATE INDEX préalable (one-shot, ~30-60 min sur 47M rows).

2. **Respawn automatique par le Task Scheduler Windows** — le CEO a un système de cron Windows (visible : `svchost.exe -k netsvcs -p -s Schedule`) qui respawn les .bat du dossier `scripts/`. Ce n'est **pas** dans `hermes cron list` (deux systèmes en parallèle). Pour vraiment arrêter les writers, il faut `Disable-ScheduledTask`, pas seulement killer les process.

3. **`Disable-ScheduledTask` ne fonctionne pas sur les tâches Running** — il faut d'abord tuer le process, puis disable. Le pattern : `Stop-Process` puis `Disable-ScheduledTask` (dans cet ordre).

4. **Killer le mauvais process** — un `Where-Object {$cmd -like '*V9*'}` peut matcher un script légitime (par exemple un script de maintenance) parce que son path contient "V9". Toujours killer par PID spécifique, pas par filtre large.

5. **WAL + Stop-Process = wal incoherent** — si on tue un process qui a un DELETE en cours, le wal peut être laissé dans un état bizarre. Le `Stop-Process -Force` fait un rollback propre (le .db-wal revient à 0 octets), mais pendant le cleanup, d'autres queries peuvent timeout.

6. **stdout Python bufférisé** — sans `sys.stdout.reconfigure(line_buffering=True)` ou `-u`, la progression n'est pas visible en temps réel via `process(action='poll')`.

7. **pytest timeout si DB très occupée** — si on lance un test qui accède à la DB pendant que le CREATE INDEX ou un DELETE gros tourne, les tests peuvent timeout (SQLITE_BUSY). C'est attendu, pas une régression.

## État post-purge attendu

| Métrique | Avant | Après (estimé) |
|---|---|---|
| DB size | 35 Go | 5-8 Go |
| `principle_evaluations` rows | 46,8M | ~1-3M (30 derniers jours) |
| Espace libre | 20 Go | 45-50 Go |
| Croissance future | +1,5M rows/jour | 0 (rétention auto) |

## Décision

CEO motion du 2026-08-15 09:00 CEST : nettoyer au max la DB. Réponse 09:08 :
- Garder 30 jours minimum (réponse explicite « peux ton gardr +30 je our pour le Replay »)
- Procéder à la purge

## Rétention future

Le pipeline live (réactivé lundi 17/08 06:00 UTC) purgera automatiquement
les rows > 30 jours après chaque batch d'écriture grâce au patch
`d457001`. Plus de risque de regonflement.

## Traçabilité

- DECISIONS_LOG : DEC-2026-08-15-075 (append-only)
- Commits atomiques :
  - `d457001` perf(v9): rétention auto + scripts purge 30j
  - `d89d913` docs(v9): DECISIONS_LOG entry
- MD5 défensif : `ad66e644752ad5938e521b12942a5b90` (R8)
- Tests : 8/8 nouveaux + 55/55 principle_engine (0 régression)
