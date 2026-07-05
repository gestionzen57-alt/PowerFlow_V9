# CHECKPOINT_20260705_V9_PHASE2_COMPLETE

## Contexte
Fusion des deux chantiers parallèles de la Phase 2 (couche Forces —
implémentation) sur la branche de référence `feat/v9-foundation-clean` :
- `feat/v9-phase2-ea-mt4` (Phase 2A — sonde EA MT4)
- `feat/v9-phase2-python-capture` (Phase 2B — capture Python)

Aucun conflit de code : les deux branches touchent des répertoires
disjoints (`ea/` vs `core/v9/` + `tests/`). Seuls `docs/STATE.md` et
`docs/CACHE_BOARD.md` présentaient des conflits, résolus en fusionnant
les deux narratifs plutôt qu'en écrasant l'un par l'autre.

## Livrables EA MT4 (Phase 2A, 3 fichiers)
- `ea/V9_Sonde_TF.mq4` — sonde candle-close, 1 instance par timeframe
  (M5, M15, M30, H1, H4, D1), JSON aligné sur `FORMAT_FORCES.md`
  (`schema_version`, `snapshot_id`, `timestamp` ISO8601 UTC, `source`),
  anti-duplicate par signature complète (OHLC + 8 forces), replay
  historique configurable.
- `ea/V9_Sonde_M1.mq4` — sonde M1 dédiée, mode tick/vélocité (`OnTick`,
  sans timer), fenêtre glissante 5000 ms, vitesse par devise.
- `ea/V9_Sonde_README.md` — procédure de compilation, déploiement,
  vérification, diagnostic buffers SDI.

## Livrables Python (Phase 2B, 6 fichiers + 2 fichiers de tests)
- `core/v9/__init__.py` — package vide
- `core/v9/config.py` — configuration centrale (DB_PATH, port TCP,
  devises, timeframes, seuils STALE_GATE, calibration ForcesReader)
- `core/v9/stale_gate.py` — `StaleGate.check_freshness()`, jamais
  bloquant à l'insertion
- `core/v9/forces_reader.py` — `ForcesReader.transform()` : validation,
  champs dérivés (direction, vitesse, croisement, recroisement,
  rejet_repulsion, compression_extension), état mémoire par devise/TF
- `core/v9/capture_server.py` — serveur TCP asyncio, `--status`, `--once`
- `core/v9/db_schema.py` — table `forces_snapshots` (WAL, busy_timeout 30s)
- `tests/test_stale_gate.py` (7 tests), `tests/test_forces_reader.py`
  (8 tests) — 15 tests, tous verts

## Les 3 points tranchés lors de cette fusion

### 1. Seuils STALE_GATE
Divergence entre `config.py` (Phase 2B) et `docs/architecture/formats/FORMAT_FORCES.md`
(Phase 1) : le format documenté portait des seuils plus stricts
(M5=30s, H4=900s/15min, D1=3600s/1h) que ceux réellement implémentés
dans `config.py`. **`config.py` fait foi** — `FORMAT_FORCES.md` a été
mis à jour pour refléter les seuils définitifs :

| Timeframe | Seuil |
|---|---|
| M1 | 5 000 ms |
| M5 | 35 000 ms |
| M15 | 95 000 ms |
| M30 | 185 000 ms |
| H1 | 365 000 ms |
| H4 | 1 450 000 ms (24 min) |
| D1 | 9 000 000 ms (2,5 h) |

### 2. Port de capture (LISTEN_PORT)
`config.py` conserve `LISTEN_PORT = 31685` comme port de référence V9.
Une note a été ajoutée directement dans le code pour documenter le
conflit connu avec V8 en production sur cette même machine :
```
# NOTE: V8 utilise encore 31685 en prod.
# Pour tester V9, changer en 31690 temporairement.
```

### 3. Vélocité M1
`V9_Sonde_M1.mq4` n'existait pas encore au moment où `forces_reader.py`
a été écrit (Phase 2B) ; ses hypothèses sur la forme du message M1
(mêmes clés `force_*`, `timeframe="M1"`, mode `tick_velocity`) étaient
donc spéculatives. La sonde M1 étant désormais livrée (Phase 2A), ce
point n'est plus bloquant pour la clôture de Phase 2, mais reste à
revalider empiriquement dès la première capture réelle bout en bout.

## Fusion
- `feat/v9-phase2-ea-mt4` → `feat/v9-foundation-clean` : fast-forward,
  aucun conflit.
- `feat/v9-phase2-python-capture` → `feat/v9-foundation-clean` : conflits
  sur `docs/STATE.md` et `docs/CACHE_BOARD.md` uniquement, résolus par
  fusion des deux narratifs (aucun contenu perdu).
- Harmonisation STALE_GATE commitée séparément après la fusion.
- Branches temporaires supprimées (locales + remote) après validation.

## Validation
- `python -m pytest tests/ -v` → 15 passed
- Inventaire de fichiers confirmé : `ea/` (3 fichiers), `core/v9/`
  (6 fichiers), `tests/` (2 fichiers de tests + `__init__.py`)

## Statut Phase 2
**COMPLETE.**

## Prochaine étape
Phase 3 — Couche Scènes (lecteur réel), consommant les snapshots de
`forces_snapshots` selon `MEMORY_CONTRACT.md`. La validation terrain de
la chaîne EA MT4 → capture_server.py → v9_forces.db reste un chantier
ouvert, à mener en parallèle sans bloquer le démarrage de la Phase 3.
