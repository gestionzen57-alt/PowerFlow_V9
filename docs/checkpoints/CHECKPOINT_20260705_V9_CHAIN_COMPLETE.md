# CHECKPOINT_20260705_V9_CHAIN_COMPLETE

## Date
2026-07-05

## Contexte
Fusion de `feat/v9-phase6-exploitabilite` (couche Exploitabilité) sur
`feat/v9-foundation-clean`, revalidation du shim `windows` hérité de la
construction en parallèle des Phases 5 et 6, mise à jour du README, et
ajout d'un smoke test de bout en bout. Cette fusion clôt la chaîne
cognitive V9 : les 6 couches (Forces, Scènes, Comportements, Fenêtres,
Exploitabilité, plus les 6 formats de Phase 1) sont désormais toutes
implémentées et fusionnées sur la branche de référence.

## Fusion
`git merge feat/v9-phase6-exploitabilite` — conflits sur 3 fichiers,
résolus par combinaison des deux narratifs :
- `core/v9/config.py` : les deux blocs de constantes conservés
  intégralement (Phase 4+5 : `CONFIANCE_MIN_FENETRE`,
  `FRAGILITE_CONFIANDE_DELTA`, `WINDOW_LIFECYCLE_LOOKBACK`,
  `BONUS_CONFLUENCE_MTF`, `BONUS_SIMILARITE`, `MALUS_STALE`,
  `MALUS_FRAGILITE`, `SIMILARITE_BONUS_THRESHOLD` ; Phase 6 :
  `SEUIL_EXPLOITABLE`, `SEUIL_WATCHLIST`, `REPLAY_MIN_CAS`,
  `REPLAY_MIN_WIN_RATE`, `BONUS_CONFIANCE_COMPORTEMENT`,
  `BONUS_CONFLUENCE_MTF_EXPLOIT`, `BONUS_SIMILARITE_EXPLOIT`,
  `MALUS_STALE_EXPLOIT`, `MALUS_FRAGILITE_EXPLOIT`,
  `MALUS_REPLAY_INSUFFISANT`, `REPLAY_OUTCOMES_PATH`), aucune perte.
- `docs/STATE.md`, `docs/CACHE_BOARD.md` : narratifs combinés, statut
  unifié Phase 4 + 5 + 6 terminées et fusionnées, chaîne complète.

## Revalidation du point ouvert — shim `windows`
`exploitability_evaluator.py` avait été implémenté (Phase 6) sur une
table `windows` shim (`WINDOWS_SHIM_SCHEMA_SQL`, `_ensure_windows_table`)
le temps que la Phase 5 soit fusionnée, avec la même précaution que
`window_gate.py` avait prise pour son propre shim `behaviors` en Phase 5 :
schéma copié à l'identique depuis la branche non fusionnée, pas de
réinterprétation libre.

Comparaison ligne à ligne à la fusion : **schéma strictement identique**
entre `WINDOWS_SHIM_SCHEMA_SQL` (16 colonnes) et
`core/v9/window_db.py::SCHEMA_SQL` (mêmes 16 colonnes + un index
supplémentaire `idx_windows_timestamp_ouverture`, sans incidence
fonctionnelle). Tous les champs lus par `ExploitabilityEvaluator`
(`statut`, `niveau_confiance`, `behavior_id`, `stale`,
`fragilite_detectee`, `fragilite_raison`) existent à l'identique dans la
table réelle.

Adaptations apportées à `core/v9/exploitability_evaluator.py` :
- Suppression de `WINDOWS_SHIM_SCHEMA_SQL` et de `_ensure_windows_table` ;
  `ExploitabilityEvaluator.__init__` appelle désormais
  `window_db.init_window_db()`.
- `insert_window()` (fonction module + méthode d'instance) réécrit pour
  insérer via `WINDOWS_COLUMNS` (`window_db.py`), toujours utilisable
  comme helper de fixtures/tests — les fenêtres réelles proviennent de
  `WindowGate.evaluate_behavior`.
- `_load_window` (déjà un `SELECT * FROM windows WHERE window_id = ?`) et
  `WindowRecord.from_row` : **aucun changement requis**.
- Docstring du module mis à jour (note de portage retirée, remplacée par
  une note de revalidation).

**Contrairement à la fusion Phase 4+5** (où `rejet_repulsion_detecte` et
`confluence_mtf_confirmee` avaient dû être retirés du shim `behaviors`
faute d'équivalent réel), **aucun champ n'a dû être retiré** ici : le
shim Phase 6 avait été construit sans dérive par rapport au schéma
Phase 5 au moment de son écriture. Aucun point ouvert résiduel sur ce
point précis.

## Smoke test — chaîne complète
Ajout de `tests/test_full_chain.py` : un snapshot de forces inséré en DB
traverse `SceneBuilder.build_scene` → `BehaviorAnalyzer.analyze_scene` →
`WindowGate.evaluate_behavior` → `ExploitabilityEvaluator.evaluate_window`
sans lever d'exception, chaque couche consommant la sortie DB de la
précédente (jamais de duplication de données amont). Seule
particularité relevée : `SceneBuilder.build_scene` ne persiste pas la
scène lui-même (contrairement aux 3 couches avales qui écrivent en DB en
fin d'appel) — le test appelle explicitement `_write_scene_to_db` après
`build_scene`, comme le fait déjà `tests/test_scene_builder.py`. Ce test
ne vérifie pas la qualité des heuristiques (aucune assertion de
calibration), seulement l'absence de rupture de chaîne.

## Validation
`python -m pytest tests/ -v` → **96 passed** :
- 15 — `test_stale_gate.py` + `test_forces_reader.py` (Phase 2)
- 13 — `test_scene_builder.py` (Phase 3)
- 21 — `test_behavior_analyzer.py` (Phase 4)
- 20 — `test_window_gate.py` (Phase 5)
- 26 — `test_exploitability_evaluator.py` (Phase 6)
- 1 — `test_full_chain.py` (smoke test chaîne complète)

Aucune régression.

## Les 6 couches implémentées
1. **Forces** — `capture_server.py`, `stale_gate.py`, `forces_reader.py`, `db_schema.py` (table `forces_snapshots`)
2. **Scènes** — `scene_builder.py` (table `scenes`) : coalitions, antagonismes, cinématique locale, confluences MTF, contexte temporel/zone
3. **Comportements** — `behavior_analyzer.py` (table `behaviors`) : qualification (12 valeurs), transitions, comparaison cas connus
4. **Fenêtres** — `window_gate.py` (table `windows`) : statut (6 valeurs), type, niveau de confiance, fragilité, cycle de vie
5. **Exploitabilité** — `exploitability_evaluator.py` (table `exploitability`) : statut (5 valeurs), raison de refus, confiance globale, HITL, replay
6. **Exécution éventuelle** — hors périmètre cognitif strict, non implémentée (Phase 7 à statuer)

## Points ouverts restants (non bloquants)
- Branchement temps réel de la chaîne complète en aval de
  `capture_server.py` (aujourd'hui chaque couche est invoquée
  explicitement par référence d'ID, jamais orchestrée en continu).
- Calibration des seuils heuristiques (Scènes, Comportements, Fenêtres,
  Exploitabilité) sur données réelles — toutes les valeurs actuelles de
  `config.py` sont des hypothèses de départ, jamais validées en
  production.
- `data/replay_outcomes.json` n'a aucune source de production réelle
  tant que la Phase 7 (Exécution éventuelle) n'existe pas.
- Décision de périmètre pour la Phase 7 — Exécution éventuelle, dernière
  étape de la chaîne, explicitement hors doctrine cognitive stricte
  (charte V9 : « ne jamais demander au système de trader ce qu'il ne
  sait pas encore décrire »).
- Type de fenêtre `"rebond"` (`FORMAT_FENETRES.md`) toujours jamais
  produit — aucune couche amont ne propage de signal de rejet/répulsion
  jusqu'à `WindowGate` (point ouvert hérité de la fusion Phase 4+5).
- Validation terrain de la sonde EA (`ea/V9_Sonde_TF.mq4`,
  `ea/V9_Sonde_M1.mq4`) avec `capture_server.py` sur données de marché
  réelles.

## Statut
**V9 = CHAÎNE COGNITIVE COMPLÈTE.** Les 6 couches cognitives (Forces →
Scènes → Comportements → Fenêtres → Exploitabilité, plus les formats de
Phase 1) sont implémentées, fusionnées sur `feat/v9-foundation-clean`, et
validées de bout en bout par 96 tests verts + 1 smoke test de chaîne
complète. La branche `feat/v9-phase6-exploitabilite` a été supprimée
(locale + origin) après fusion complète.

## Prochaine étape
Test d'intégration live (branchement réel de la chaîne en aval de
`capture_server.py` sur données de marché) et calibration des seuils
heuristiques sur données réelles, en parallèle de la validation terrain
de la sonde EA. Décision de périmètre Phase 7 (Exécution éventuelle) à
trancher séparément, hors doctrine cognitive stricte.
