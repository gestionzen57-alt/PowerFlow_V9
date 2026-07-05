# CHECKPOINT_20260705_V9_PHASE4_5_COMPLETE

## Contexte
Fusion de `feat/v9-phase4-comportements` (couche Comportements) et
`feat/v9-phase5-fenetres` (couche Fenêtres) sur `feat/v9-foundation-clean`,
puis revalidation des points ouverts laissés par ces deux phases construites
en parallèle sans se connaître.

## Fusion

### Phase 4 — `feat/v9-phase4-comportements`
Fast-forward, aucun conflit (`feat/v9-foundation-clean` n'avait pas divergé
depuis la Phase 3). Livre `core/v9/behavior_analyzer.py`,
`core/v9/behavior_db.py`, 4 constantes de config, 21 tests.

### Phase 5 — `feat/v9-phase5-fenetres`
Conflits sur 3 fichiers, résolus par combinaison des deux narratifs :
- `core/v9/config.py` : les deux blocs de constantes (Phase 4 :
  `BEHAVIOR_HISTORY_LOOKBACK`, `SIMILARITY_THRESHOLD`,
  `CONFIANCE_PLIURE_SEVERE`, `CONFIANCE_BASCULE_NETTE` ; Phase 5 :
  `CONFIANCE_MIN_FENETRE`, `FRAGILITE_CONFIANDE_DELTA`,
  `WINDOW_LIFECYCLE_LOOKBACK`, `BONUS_CONFLUENCE_MTF`, `BONUS_SIMILARITE`,
  `MALUS_STALE`, `MALUS_FRAGILITE`, `SIMILARITE_BONUS_THRESHOLD`) conservés
  intégralement, aucune perte.
- `docs/STATE.md`, `docs/CACHE_BOARD.md` : narratifs combinés, statut
  unifié Phase 4 + Phase 5 terminées et fusionnées.

## Revalidation des points ouverts

### Point 1 — `window_gate.py` vs schéma réel de `behavior_db.py`
Divergence confirmée : la table shim provisoire de Phase 5
(`BEHAVIORS_SHIM_SCHEMA_SQL`) portait deux champs auxiliaires
(`confluence_mtf_confirmee`, `rejet_repulsion_detecte`) absents du schéma
réel `core/v9/behavior_db.py` (table `behaviors`, 26 colonnes) et absents
de la sortie réelle de `BehaviorAnalyzer.analyze_scene`.

Adaptations apportées à `core/v9/window_gate.py` :
- Suppression de la table shim et de `_ensure_behaviors_table` ;
  `WindowGate.__init__` appelle désormais `behavior_db.init_behavior_db()`.
- `insert_behavior()` réécrit pour insérer dans le schéma réel
  (`BEHAVIOR_COLUMNS` de `behavior_db.py`), toujours utilisable comme
  helper de fixtures/tests (les comportements réels proviennent de
  `BehaviorAnalyzer`).
- `Behavior` (dataclass), `from_row`, `from_format_comportements` :
  champs `confluence_mtf_confirmee` et `rejet_repulsion_detecte` retirés.
- `_calculate_confidence` : bonus `BONUS_CONFLUENCE_MTF` retiré. Raison :
  `BehaviorAnalyzer._compute_confiance` intègre déjà la confluence MTF
  (`scene.confluences_mtf.emboitement_detecte`) dans
  `confiance_qualification` en amont — un second bonus en Fenêtres ferait
  double-compte. La constante `config.BONUS_CONFLUENCE_MTF` est conservée
  (calibration historique) mais n'est plus appliquée.
- `_determine_type` : branche `rejet_repulsion_detecte → "rebond"`
  retirée. Raison : ce signal existe à la couche Forces
  (`forces_reader.py`) mais n'est propagé ni par `SceneBuilder` ni par
  `BehaviorAnalyzer` jusqu'à la couche Comportements — aucune donnée
  réelle ne permet de le qualifier à ce stade. **Point ouvert non
  bloquant** : le type de fenêtre `"rebond"` reste défini dans
  `FORMAT_FENETRES.md` mais n'est actuellement jamais produit ; à trancher
  en Phase 6 si un signal de rejet/répulsion doit être propagé par une
  couche amont.
- `tests/fixtures/behaviors_sample.json` : les deux champs auxiliaires
  retirés des 6 comportements (n'appartiennent pas au format réel).
- `tests/test_window_gate.py::test_niveau_confiance_bonus_malus` : attendu
  recalculé sans `BONUS_CONFLUENCE_MTF` (uniquement `BONUS_SIMILARITE`
  pour le cas bascule).

### Point 2 — déréférence `forces_snapshot_ref` par `BehaviorAnalyzer`
Vérifié contre le schéma réel de `scene_db.py` (table `scenes`) : la scène
ne porte ni `symbol` ni `timeframe` (seulement `timeframes_concernes`
pluriel + `forces_snapshot_ref`), conformément à sa conception
multi-devises/multi-timeframes (Phase 3). La déréférence étroite vers
`forces_snapshots` (colonnes `symbol`, `timeframe` uniquement, jamais les
valeurs de force) reste donc nécessaire et correcte. **Aucun changement**
apporté à `behavior_analyzer._resolve_symbol_timeframe`.

## Validation
`python -m pytest tests/ -v` → **69 passed** (15 Phase 2 + 13 Phase 3 +
21 Phase 4 + 20 Phase 5), aucune régression.

## Statut
Phase 4 (Comportements) et Phase 5 (Fenêtres) **TERMINÉES ET FUSIONNÉES**
sur `feat/v9-foundation-clean`. Les deux points ouverts hérités de la
construction en parallèle des deux phases sont tranchés (point 1) ou
confirmés sans changement requis (point 2).

## Prochaine étape
Phase 6 — Couche Exploitabilité (consommant `FORMAT_FENETRES.md`).
