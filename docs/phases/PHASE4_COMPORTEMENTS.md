# PHASE 4 — Comportements

## Statut
✅ Terminée et fusionnée sur `feat/v9-foundation-clean` (depuis `feat/v9-phase4-comportements`).

## Objectif
Qualifier la dynamique d'une scène dans le temps : reconnaître 12 types de comportement,
détecter les transitions, comparer aux cas connus.

## Livrables
- `core/v9/behavior_analyzer.py` — `BehaviorAnalyzer.analyze_scene` : qualification (12 heuristiques), intensité, phase, confiance, transitions (comportement précédent, point de rupture, sens), comparaison cas connus (similarité, singularités, variante), écriture DB + mémoire
- `core/v9/behavior_db.py` — schéma SQLite table `behaviors` (référence `scene_id_ref`, jamais de duplication de la scène)
- `core/v9/config.py` — constantes ajoutées : `BEHAVIOR_HISTORY_LOOKBACK`, `SIMILARITY_THRESHOLD`, `CONFIANCE_PLIURE_SEVERE`, `CONFIANCE_BASCULE_NETTE`

## Décisions notables
- Déréférence administrative étroite de `forces_snapshot_ref` vers `symbol`/`timeframe` uniquement (jamais les valeurs de force), nécessaire car `FORMAT_COMPORTEMENTS.md` exige ces champs au niveau racine alors qu'une scène reste multi-devises/multi-timeframes par conception.
- À la fusion avec Phase 5 : le champ `rejet_repulsion_detecte` (Comportements) a dû être retiré faute d'équivalent réel côté Forces à ce moment — point ouvert tranché lors de la fusion.

## Tests
21 tests (`test_behavior_analyzer.py`), fixture `tests/fixtures/scenes_sample.json`. Couvre les 12 qualifications, intensité, phase, transitions, sens_transition, comparaison cas connus, confiance basse valide, format JSON, écriture DB/mémoire, scénario complet 6 scènes.

## Voir aussi
[docs/checkpoints/CHECKPOINT_20260705_V9_PHASE4.md](../checkpoints/CHECKPOINT_20260705_V9_PHASE4.md),
[docs/checkpoints/CHECKPOINT_20260705_V9_PHASE4_5_COMPLETE.md](../checkpoints/CHECKPOINT_20260705_V9_PHASE4_5_COMPLETE.md)
