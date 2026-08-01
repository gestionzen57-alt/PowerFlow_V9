# OOS DB Freeze Test — Phase 105 (2026-08-01)

## Verdict global

**DEGRADED** (exit_code=1) — la DB source `data/v9_forces.db` est corrompue
structurellement (page 825461, `btreeInitPage() returns error code 11`).
Le freeze snapshot est impossible, le pipeline a basculé en mode
**live-only** best-effort (R6 defensif).

> **Action CEO requise** : la DB doit etre reparee avant que le freeze
> test puisse delivrer un verdict STABLE/DRIFT. Voir section [Diagnostic
> DB](#diagnostic-db-source-corruption) ci-dessous.

## Livrables Phase 105

| Fichier | Role | Statut |
|---|---|---|
| `scripts/v9_oos_freeze_test.py` | Pipeline freeze + walk-forward OOS + verdict | **Livre** (R2 additif, R6 best-effort) |
| `tests/test_v9_oos_freeze_test.py` | 15 tests unitaires + integration | **15/15 verts** |
| `docs/reports/oos_freeze_test_20260801.json` | Rapport live (mode DEGRADED) | **Livre** |
| `backups/oos_freeze_20260801/v9_forces_*.sha256` | Backup MD5 (R8) | **Livre** (pre-freeze + freeze) |

## Pipeline (concu, livre, valide)

```
[DB source] ── backup_md5 (R8) ──> sha256 stocke
            └─ freeze_db (VACUUM INTO) ──> [DB freeze]
                                            │
            ┌───────────────────────────────┘
            ▼
[DB source] ── walk_forward_oos(as_of=t_freeze) ──> live_metrics
[DB freeze] ── walk_forward_oos(as_of=t_freeze) ──> frozen_metrics
            │
            ▼
       compare_metrics(live, frozen)
            │
            ▼
   verdict: STABLE | DRIFT | DEGRADED | ERROR
            │
            ▼
  append_jsonl(data/v9_oos_freeze_log.jsonl)  (R6 best-effort)
            │
            ▼
  exit_code: 0=STABLE | 1=DRIFT/DEGRADED | 4=ERROR
```

### Seuils CEO (calibrage motion Phase 105)

| Metrique | Seuil | Source |
|---|---|---|
| `|delta_wr|` | < 5.0 points | motion Phase 105 |
| `|delta_expectancy|` | < 1.0 pip/trade | motion Phase 105 |
| `n_windows` (defaut) | 5 fenetres | calque walk_forward.py |
| `window_days` (defaut) | 30 jours | calque walk_forward.py Phase 59 |
| `offset_days` (defaut) | 7 jours | anti-overlap |

## Resultat live (mode DEGRADED)

| Window | Start | End | n | WR | Total pips | Expectancy |
|---|---|---|---|---|---|---|
| 0 | 2026-07-02 | 2026-08-01 | 337 | 44.5% | -259.65 | -0.77 |
| 1 | 2026-06-25 | 2026-07-25 | 336 | 44.6% | -246.65 | -0.74 |
| 2 | 2026-06-18 | 2026-07-18 | 127 | 79.5% | +378.00 | +2.98 |
| 3 | 2026-06-11 | 2026-07-11 | 0 | — | — | — |
| 4 | 2026-06-04 | 2026-07-04 | 0 | — | — | — |

**Summary live** : n=800, wins=401, **WR 50.12%**, total pips **-128.3**,
expectancy **-0.16 pip/trade**, 1/3 fenetres non-vides > 70% WR.

> **Note observationnelle** : drift visible entre la fenetre 2 (WR 79.5%,
> +378 pips) et les fenetres 0-1 (WR 44%, -250 pips). C'est exactement
> le pattern que le freeze test est cense detecter formellement — il
> manque la comparaison frozen pour conclure.

## Diagnostic DB source (corruption)

`PRAGMA integrity_check` et `PRAGMA quick_check` retournent tous deux :

```
*** in database main ***
Tree 23 page 825461: btreeInitPage() returns error code 11
```

**Page 825461** est le site de corruption. La taille de la DB est 6.76 GB.

**Origines probables** (a investiguer ulterieurement) :
- WAL checkpoint incomplet lors d'une des 3 sessions 48H recentes
- VACUUM interrompu (cf. `JOURNAL_PHASES.md` Phase 49-54, "purge DB 17.42 -> 10.49 GB")
- Ecrasement de pages par acces concurrents (capture server M1 + cron
  resolve_loop en parallele)

**Recommandations CEO** (par ordre de preference) :

1. **STOP tous les crons qui touchent la DB** (V9_ResolveLoop,
   V9_CalibrationLoop, V9_AutoRestart, V9_MetaAgentScan) pendant la
   reparation. Voir `core/v9/db_schema.py` pour le catalogue.
2. **Reparer depuis backup** : la DB source a un SHA256 documente dans
   `backups/oos_freeze_20260801/v9_forces_pre_freeze_*.sha256`. Si un
   backup anterieur sain existe, restaurer.
3. **Sinon** : `sqlite3 data/v9_forces.db ".dump" | sqlite3 new.db`
   permet de reconstituer une DB propre en perdant uniquement la page
   825461. Le `.dump` peut prendre 1-2h sur 6.76 GB. Surveiller.
4. **Si impossible** : la voie rapide est de recreer un snapshot de
   capture_server M1 et de relancer le pipeline cognitif. Cout : 1-3
   jours de donnees.

## Limites du test (transparence)

- **Brier proxy** : le test utilise `(WR - 0.5)^2` comme proxy binaire.
  Un vrai Brier score necessiterait les probabilites predites par
  chaque signal. Amelioration possible : brancher sur
  `principle_evaluations.confiance` pour un Brier reel.
- **Couverture symboles** : le walk-forward filtre actuellement
  implicitement les trades `GBPUSD haussiere 11-13h` (filtre de
  l'existant `walk_forward.py`). Phase 105 ne change pas ce focus.
- **Comparaison live/frozen** : sur la fenetre 0-1, le live est
  identique au frozen par construction (meme `as_of`). Le delta ne
  devient informatif que si la DB evolue entre `t_freeze` et `t_live`.

## Prochaines etapes (CEO motion requise)

1. **Reparer la DB** (cf. section Diagnostic ci-dessus).
2. **Rejouer le freeze test** : `python scripts/v9_oos_freeze_test.py --oos-days 30 --windows 5 --report docs/reports/oos_freeze_test_YYYYMMDD.json`.
3. **Si verdict STABLE** : la phase est livrable, on peut passer a la
   Phase 106.
4. **Si verdict DRIFT** : STOP, investigation walk-forward approfondie.

## Verification tests

```
$ .venv/Scripts/python.exe -m pytest tests/test_v9_oos_freeze_test.py -v
============================= 15 passed in 1.01s ==============================
```

Couverture :
- `test_backup_md5_writes_files` — backup MD5 R8
- `test_freeze_db_creates_copy` — VACUUM INTO sur DB saine
- `test_freeze_db_corrupt_returns_none` — fallback live-only
- `test_run_freeze_test_degraded_on_corrupt_db` — verdict DEGRADED
- `test_walk_forward_oos_returns_structure` — structure retour
- `test_walk_forward_oos_handles_missing_db` — DB absente = no-op
- `test_compare_metrics_stable` — delta < seuil
- `test_compare_metrics_drift_wr` — drift WR seul
- `test_compare_metrics_drift_expectancy` — drift expectancy seul
- `test_append_jsonl_creates_file` — log append-only
- `test_run_freeze_test_missing_db` — exit 4 si DB absente
- `test_run_freeze_test_end_to_end_stable` — pipeline complet STABLE
- `test_run_freeze_test_end_to_end_drift` — pipeline complet DRIFT
- `test_thresholds_constants` — seuils CEO explicites
- `test_schema_version_present` — rapport porte schema_version=1.0
