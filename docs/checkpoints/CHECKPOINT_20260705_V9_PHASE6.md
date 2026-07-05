# CHECKPOINT — PowerFlow V9 — Phase 6 — Couche Exploitabilité

## Date
2026-07-05

## Branche
`feat/v9-phase6-exploitabilite` (worktree `D:\Projet\V9_wt_exploitabilite`)

## Chaîne cognitive officielle
Forces → Scènes → Comportements → Fenêtres → **[Exploitabilité]** → Exécution éventuelle

## Contexte de départ

Au moment de démarrer cette session, `feat/v9-foundation-clean` en était à
Phase 3 (Scènes) fusionnée. En cours de session, une fusion fast-forward de
`feat/v9-phase4-comportements` (Phase 4 — Comportements) a été observée sur
`feat/v9-foundation-clean` (probablement une autre session concurrente),
donnant accès à `core/v9/behavior_analyzer.py` et `core/v9/behavior_db.py`.

**Phase 5 (Fenêtres) n'était pas fusionnée** au moment de cette
implémentation : `core/v9/window_gate.py` et `core/v9/window_db.py`
n'existent pas sur cette branche. Le worktree `D:\Projet\V9_wt_fenetres`
(branche `feat/v9-phase5-fenetres`) a été consulté en lecture seule pour
aligner le schéma exact de la table `windows` (`core/v9/window_db.py`) sur
cette branche non fusionnée, afin que le shim temporaire créé ici soit
directement compatible une fois la fusion faite.

## Livrables

- `core/v9/exploitability_evaluator.py` — `ExploitabilityEvaluator` :
  - `evaluate_window(window_id)` — évaluation complète d'une fenêtre
  - `_determine_status` — 5 statuts (non_exploitable, watchlist, exploitable, refuse, ambigu) déterminés à partir du statut de fenêtre (6 valeurs FORMAT_FENETRES.md) et de la confiance globale
  - `_determine_refus_reason` — cascade priorisée des 5 raisons de refus
  - `_calculate_global_confidence` — bonus/malus documentés (config.py)
  - `_check_hitl_required` — validation humaine (exploitable toujours, watchlist premier cas ou ratio replay incertain)
  - `_build_replay_context` — comparaison aux comportements passés de même qualification, issues WIN/LOSS/UNKNOWN via fichier optionnel `data/replay_outcomes.json`
  - `_write_exploitability_to_db`, `_write_memory`
- `core/v9/exploitability_db.py` — schéma SQLite table `exploitability` (référence `window_id`, jamais de duplication)
- `core/v9/config.py` — 10 constantes ajoutées (SEUIL_EXPLOITABLE=65, SEUIL_WATCHLIST=45, REPLAY_MIN_CAS=3, REPLAY_MIN_WIN_RATE=0.55, BONUS_CONFIANCE_COMPORTEMENT=8, BONUS_CONFLUENCE_MTF_EXPLOIT=10, BONUS_SIMILARITE_EXPLOIT=7, MALUS_STALE_EXPLOIT=25, MALUS_FRAGILITE_EXPLOIT=15, MALUS_REPLAY_INSUFFISANT=10) + `REPLAY_OUTCOMES_PATH`
- `tests/test_exploitability_evaluator.py` — 26 tests, tous verts
- `tests/fixtures/windows_sample.json` — 5 fenêtres consécutives (absente, en_preparation, ouverte/confiance 72, fragile/confiance 70, invalidee)

## Décisions de design

1. **Table `windows` shim, alignée sur le schéma réel non fusionné.** Comme
   `window_gate.py` l'avait fait pour `behaviors` en Phase 5, ce module crée
   sa propre table `windows` (`_ensure_windows_table`) si absente — mais son
   schéma est un reflet **exact** des colonnes de `core/v9/window_db.py` sur
   `feat/v9-phase5-fenetres` (vérifié par lecture directe de cette branche),
   pas une réinterprétation libre. Objectif : que la fusion de Phase 5 rende
   ce shim strictement redondant avec le module officiel, sans migration de
   données ni changement de schéma.

2. **`en_preparation` n'autorise jamais watchlist/exploitable.** FORMAT_EXPLOITABILITE.md
   Règle 1 n'autorise `watchlist`/`exploitable` que si `window_source.statut`
   vaut `ouverte` ou `fragile`. Bien que la mission n'énumère pas explicitement
   le cas `en_preparation`, la règle explicite du format exclut toute autre
   valeur — `en_preparation` est donc mappé sur `non_exploitable`, jamais
   `watchlist`, même à confiance élevée.

3. **Cascade de raison de refus, priorisée et rendue indépendamment testable.**
   Ordre retenu : `fenetre_non_confirmee` (cas `invalidee`, réponse fixe et
   prioritaire) → `scene_ambigue` (mots-clés de contradiction dans
   `fragilite.raison` : "contredit", "annulation") → `comportement_non_qualifiable`
   (confiance du comportement source sous `SEUIL_WATCHLIST`) →
   `replay_insuffisant` (moins de `REPLAY_MIN_CAS` cas comparés) →
   `perception_non_stabilisee` (fenêtre stale) → repli générique
   `fenetre_non_confirmee`. Cet ordre n'est pas imposé littéralement par la
   mission (qui énumère les 5 conditions sans trancher leur priorité relative)
   mais a été choisi pour que chacune des 5 raisons soit atteignable par un
   scénario de test isolé et sans ambiguïté.

4. **Déréférence administrative étroite vers `behaviors`/`scenes`.** La
   confiance du comportement source et le statut de fenêtre sont déjà
   dénormalisés sur la ligne `windows` (traçabilité FORMAT_FENETRES.md) — pas
   besoin de déréférence pour ces champs. En revanche, deux informations ne
   sont disponibles nulle part sur `windows` : (a) `symbol`/`timeframe` pour
   un identifiant lisible (`exploitability_id`), et (b) la confluence MTF de
   la scène source (bonus de confiance globale explicitement demandé par la
   mission). Ces deux déréférences passent par `behavior_id` → table
   `behaviors` → (`scene_id_ref` →) table `scenes`, en lecture seule, sans
   jamais relire une valeur de force ni réinterpréter la scène. Dégradation
   silencieuse (`sqlite3.OperationalError` capturée) si ces tables n'existent
   pas encore — un test de fenêtre pure (sans comportement/scène réels en DB)
   reste valide.

5. **Similarité replay : heuristique légère, pas une redite de BehaviorAnalyzer.**
   `BehaviorAnalyzer._similarity` compare des scènes complètes (Jaccard des
   devises, cinématique). L'Exploitabilité n'a pas vocation à ré-analyser la
   scène — elle compare seulement intensité, phase et proximité de confiance
   entre le comportement courant (déréférencé) et chaque candidat de même
   qualification. C'est une similarité de second ordre, cohérente avec le
   principe « évaluation tardive et subordonnée » de la charte cognitive.

6. **Issues de replay via fichier optionnel, pas de table d'exécution.**
   Aucune couche Exécution n'existe encore en V9 — il n'y a donc aucune
   source native de WIN/LOSS. `REPLAY_OUTCOMES_PATH` (`data/replay_outcomes.json`)
   est un fichier optionnel `behavior_id -> "WIN"|"LOSS"`, absent par défaut
   (toutes les issues valent alors `UNKNOWN`, `replay_context` reste cohérent
   et `non_exploitable`/`refuse` restent des réponses de première classe même
   sans historique). Aucune logique d'exécution d'ordre n'est introduite par
   ce fichier — c'est un journal de confrontation, pas une commande.

7. **`_calculate_global_confidence` pénalise indépendamment ce que la couche
   Fenêtres a déjà pénalisé.** `window.niveau_confiance` reflète déjà, côté
   Fenêtres, un malus de fragilité/staleness (voir `window_gate.py`). La
   couche Exploitabilité applique néanmoins son propre malus de fragilité/
   staleness sur ce chiffre déjà pénalisé — ce n'est pas une double
   comptabilisation accidentelle mais une décision de design : chaque couche
   évalue indépendamment, sans faire confiance aveuglément au score amont
   (cohérent avec « évaluation tardive et subordonnée à la qualité de lecture »,
   charte cognitive V9). Les seuils de fixture ont été calibrés en
   conséquence (ex. fenêtre 4 du fixture : confiance 70, pas 55, pour
   atterrir en watchlist après malus de fragilité + malus de replay
   insuffisant).

## Écarts assumés / points ouverts

- Le shim `windows` et le shim `behaviors` de `window_gate.py` (Phase 5)
  devront être réconciliés lors de la fusion des deux branches — les deux
  couches ont chacune créé une table `windows`/`behaviors` minimale de
  manière indépendante ; leurs schémas sont conçus pour être identiques aux
  modules officiels, mais une vérification post-fusion reste nécessaire.
- `data/replay_outcomes.json` n'a aucune source de production réelle tant que
  la Phase 7 (Exécution éventuelle) n'existe pas — c'est un point d'intégration
  futur, pas un manque de cette implémentation.
- Le seuil `CONFIANCE_COMPORTEMENT_ELEVEE_MIN` (70) et `SIMILARITE_CAS_GAGNANT_MIN`
  (0.75) sont des heuristiques internes au module (non exposées dans
  `config.py`), au même titre que les seuils internes de `behavior_analyzer.py`
  — à recalibrer sur données réelles au même titre que les autres couches.

## Tests

```
python -m pytest tests/test_exploitability_evaluator.py -v
```
26 tests verts. Suite complète du dépôt : 75 tests verts (`python -m pytest tests/ -v`).
