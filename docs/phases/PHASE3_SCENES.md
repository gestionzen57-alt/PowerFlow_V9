# PHASE 3 — Scènes

## Statut
✅ Terminée et fusionnée sur `feat/v9-foundation-clean` (depuis `feat/v9-phase3-scenes`).

## Objectif
Construire la couche Scènes, from scratch (V8 n'avait pas d'équivalent) : structurer l'état
des forces en coalitions, antagonismes, cinématique locale et confluences multi-timeframes.

## Livrables
- `core/v9/scene_builder.py` — `SceneBuilder.build_scene` : détection coalitions/antagonismes, cinématique locale (angle, courbure, pente, pliure, rotation, compression/extension), confluences MTF, contexte temporel, zone, écriture DB + mémoire
- `core/v9/scene_db.py` — schéma SQLite table `scenes` (référence `forces_snapshot_ref`, jamais de duplication)
- `core/v9/config.py` — constantes ajoutées : `COALITION_THRESHOLD`, `ANTAGONISM_THRESHOLD`, `PLIURE_THRESHOLD`, `MTF_LOOKBACK`

## Décisions notables
- Direction par devise propre à la couche Scènes (ne réutilise pas la direction déjà calculée en Forces telle quelle)
- Cinématique calculée par pas de snapshot (pas de fenêtre glissante arbitraire)
- Confluences détectées entre timeframes adjacents uniquement
- Zone dérivée des OHLC de `forces_snapshots`

## Tests
13 tests (`test_scene_builder.py`), fixture `tests/fixtures/forces_snapshots_sample.json`.

## Voir aussi
[docs/checkpoints/CHECKPOINT_20260705_V9_PHASE3.md](../checkpoints/CHECKPOINT_20260705_V9_PHASE3.md),
[docs/checkpoints/CHECKPOINT_20260705_V9_PHASE3_COMPLETE.md](../checkpoints/CHECKPOINT_20260705_V9_PHASE3_COMPLETE.md)
