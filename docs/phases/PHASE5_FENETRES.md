# PHASE 5 — Fenêtres

## Statut
✅ Terminée et fusionnée sur `feat/v9-foundation-clean` (depuis `feat/v9-phase5-fenetres`).

## Objectif
Qualifier l'ouverture/fermeture d'une opportunité à partir d'un comportement : statut,
type, fragilité, cycle de vie.

## Livrables
- `core/v9/window_gate.py` — `WindowGate` : statut (6 valeurs de l'enum `FORMAT_FENETRES.md`), type_fenetre, niveau_confiance (bonus/malus), détection de fragilité, conditions d'invalidation, cycle de vie (ouverture → fragile → invalidee), écriture DB + mémoire
- `core/v9/window_db.py` — table `windows` (16 colonnes, 3 index), `init_window_db()`
- `core/v9/config.py` — constantes ajoutées : `CONFIANCE_MIN_FENETRE`, `FRAGILITE_CONFIANDE_DELTA`, `WINDOW_LIFECYCLE_LOOKBACK`, `BONUS_CONFLUENCE_MTF`, `BONUS_SIMILARITE`, `MALUS_STALE`, `MALUS_FRAGILITE`, `SIMILARITE_BONUS_THRESHOLD`

## Décisions notables
- Implémenté d'abord sur une table `behaviors` shim (le temps que Phase 4 soit fusionnée), migré vers `core/v9/behavior_db.py` réel à la fusion — aucune divergence de schéma constatée.
- Point ouvert connu : le type de fenêtre "rebond" n'est jamais produit (le champ `rejet_repulsion` n'est pas propagé depuis la couche Forces jusqu'ici) — non bloquant, documenté.

## Tests
20 tests (`test_window_gate.py`), fixture `tests/fixtures/behaviors_sample.json` (6 comportements consécutifs EURUSD/M5).

## Voir aussi
[docs/checkpoints/CHECKPOINT_20260705_V9_PHASE5.md](../checkpoints/CHECKPOINT_20260705_V9_PHASE5.md),
[docs/checkpoints/CHECKPOINT_20260705_V9_CHAIN_COMPLETE.md](../checkpoints/CHECKPOINT_20260705_V9_CHAIN_COMPLETE.md)
