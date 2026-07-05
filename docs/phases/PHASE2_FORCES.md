# PHASE 2 — Forces

## Statut
✅ Terminée et fusionnée sur `feat/v9-foundation-clean`.

## Objectif
Implémenter la couche Forces : sonde EA MT4 (capture brute) et pipeline Python (réception,
gate de fraîcheur, transformation, stockage).

## Livrables

### EA MT4 (branche `feat/v9-phase2-ea-mt4`)
- `ea/V9_Sonde_TF.mq4` — sonde candle-close multi-timeframe (1 instance par TF M5/M15/M30/H1/H4/D1), JSON aligné `FORMAT_FORCES.md`
- `ea/V9_Sonde_M1.mq4` — sonde M1 dédiée, mode tick/vélocité (`OnTick`), fenêtre glissante 5s
- `ea/V9_Sonde_README.md` — procédure de compilation, déploiement, vérification, diagnostic buffers SDI
- Bugs V8 corrigés par construction : décalage broker→UTC non appliqué, EA HTF lisant `PERIOD_M1` hardcodé, ShiftIndex mal aligné

### Python (session `feat/v9-phase2-python-capture`)
- `core/v9/config.py` — configuration centrale
- `core/v9/stale_gate.py` — `StaleGate` bloquant (marque stale, ne supprime jamais)
- `core/v9/forces_reader.py` — transformation JSON brut EA → format V9
- `core/v9/capture_server.py` — serveur TCP asyncio port 31685
- `core/v9/db_schema.py` — schéma SQLite `forces_snapshots` (WAL, busy_timeout 30s)

## Décisions notables
- Seuils STALE_GATE : `config.py` fait foi (M5=35s, M15=95s, M30=185s, H1=365s, H4=1450s, D1=9000s)
- Port TCP 31685 conservé comme port de référence V9 (conflit connu avec V8 en production, basculer sur 31690 pour tester en parallèle)
- Forme du message M1 (`tick_velocity`) à revalider empiriquement à la première capture réelle

## Tests
15 tests (`test_stale_gate.py` + `test_forces_reader.py`), tous verts.

## Voir aussi
[docs/checkpoints/CHECKPOINT_20260705_V9_PHASE2A.md](../checkpoints/CHECKPOINT_20260705_V9_PHASE2A.md),
[docs/checkpoints/CHECKPOINT_20260705_V9_PHASE2B.md](../checkpoints/CHECKPOINT_20260705_V9_PHASE2B.md),
[docs/checkpoints/CHECKPOINT_20260705_V9_PHASE2_COMPLETE.md](../checkpoints/CHECKPOINT_20260705_V9_PHASE2_COMPLETE.md)
