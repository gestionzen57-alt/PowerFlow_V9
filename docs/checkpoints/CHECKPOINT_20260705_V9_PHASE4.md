# CHECKPOINT_20260705_V9_PHASE4

## Contexte
Implémentation de la couche Comportements (3e couche cognitive) sur la
branche `feat/v9-phase4-comportements`, dans le worktree
`D:/Projet/V9_wt_comportements`.

Au démarrage de la session, la Phase 3 (couche Scènes) n'était pas
encore fusionnée sur `feat/v9-foundation-clean`. En cours de session,
la fusion de `feat/v9-phase3-scenes` a été réalisée par ailleurs ; le
worktree Phase 4 a été rebasé sur la branche de référence mise à jour
pour consommer directement `core/v9/scene_db.py` et
`core/v9/scene_builder.py` réels, plutôt qu'un schéma de substitution.

## Livrables

- `core/v9/behavior_analyzer.py` — `BehaviorAnalyzer` :
  - `analyze_scene(scene_id)` : lit une scène et son historique
    (même paire + même timeframe), qualifie la dynamique, détecte les
    transitions, compare aux cas connus, écrit en DB et en mémoire.
  - `_qualify_behavior` : 12 heuristiques de qualification (enum
    complet FORMAT_COMPORTEMENTS.md), calcul d'intensité (faible /
    modérée / forte / extrême) à partir de l'intensité maximale
    observée dans les antagonismes, coalitions, sévérité de pliure et
    intensité de compression/extension de la scène ; calcul de phase
    (initiation / développement / culmination / résolution) basé sur
    la position dans le streak de comportements identiques récents ;
    calcul de confiance (0-100) basé sur pliure sévère, bascule nette,
    confirmation MTF et stabilité dans l'historique.
  - `_detect_transitions` : comportement précédent, point de rupture
    (détecté uniquement si la qualification change), sens de
    transition (escalade / désescalade / inversion / neutre) —
    l'intensité est le signal primaire, la phase ne sert que de
    départage à intensité égale (la résolution referme le cycle, elle
    ne "monte" pas par rapport à la culmination).
  - `_compare_to_known_cases` : recherche les comportements passés de
    même qualification, recharge leur scène source (`scene_id_ref`)
    pour comparer paires de devises (Jaccard), timeframe, phase et
    cinématique (angle/pente), retient le top 3, détecte les
    singularités locales (écart de sévérité de pliure vs médiane) et
    qualifie la variante.
  - Écriture DB (`behaviors`) et mémoire (`memory_temp.md`, cycle
    hypothèse, `couche_origine: "comportements"`).

- `core/v9/behavior_db.py` — schéma SQLite table `behaviors` (référence
  `scene_id_ref`, jamais de duplication de la scène), index sur
  `scene_id_ref`, `(symbol, timeframe, timestamp)`,
  `(qualification, intensite)`.

- `core/v9/config.py` — 4 constantes ajoutées : `BEHAVIOR_HISTORY_LOOKBACK`
  (10), `SIMILARITY_THRESHOLD` (0.65), `CONFIANCE_PLIURE_SEVERE` (70),
  `CONFIANCE_BASCULE_NETTE` (75).

- `tests/test_behavior_analyzer.py` — 21 tests, tous verts : les 12
  qualifications de l'enum (dont bascule, lutte_forces, contraction,
  extension, annulation, rotation_leadership), niveaux d'intensité,
  séquence de phases (initiation → développement → culmination →
  résolution), transition (comportement précédent + point de rupture),
  les 4 valeurs de sens_transition, comparaison à un cas connu
  similaire et à l'absence de cas, confiance basse valide (n'empêche
  pas l'émission), format JSON complet round-trip, écriture DB,
  écriture mémoire, et un scénario complet sur les 6 scènes de la
  fixture (maintien → bascule → développement → résolution).

- `tests/fixtures/scenes_sample.json` — 6 scènes consécutives
  (GBPUSD, M5) conformes à FORMAT_SCENES.md : scènes 1-2 maintien avec
  contraction progressive, scène 3 pliure + bascule d'équilibre
  (déclencheur), scènes 4-5 développement de la bascule, scène 6
  résolution (retour au maintien).

## Décisions de design

### 1. Lecture du périmètre d'observation (symbol/timeframe) sans lire les forces

FORMAT_COMPORTEMENTS.md exige `symbol` et `timeframe` au niveau racine
du comportement, alors qu'une scène (FORMAT_SCENES.md) est
multi-devises et multi-timeframes par conception et ne porte pas ces
champs. La table `scenes` réelle (`scene_db.py`) ne les porte pas non
plus.

Résolu par une **déréférence administrative étroite** :
`BehaviorAnalyzer` interroge `forces_snapshots` uniquement pour les
colonnes `symbol` et `timeframe`, via `forces_snapshot_ref` (déjà porté
par la scène) — jamais les valeurs de force elles-mêmes, jamais pour
l'interprétation de la dynamique. C'est un déréférencement de clé
étrangère, pas une lecture des forces au sens de la règle "le
comportement ne lit jamais les forces directement". Ce point est
documenté dans le docstring du module et signalé ici comme candidat à
réconciliation si la Phase 5 (ou une future révision de Phase 3)
préfère dénormaliser `symbol`/`timeframe` directement sur la table
`scenes`.

### 2. Ordre de priorité des heuristiques de qualification

Le mandat liste 12 heuristiques sans préciser leur ordre de priorité
en cas de chevauchement (ex. pliure détectée à la fois avec bascule et
avec accélération). Ordre retenu, du plus spécifique au plus générique :
`rotation_leadership` → `annulation` → `bascule` (pliure + bascule) →
`rupture` (pliure + accélération, sans bascule) → `seconde_bosse` →
`preparation_ouverture_fenetre` → `reequilibrage` → `tension` →
`lutte_forces` → `contraction` / `extension` (état de la scène) →
`maintien` (défaut). `bascule` est vérifiée avant `rupture` car un
signal de bascule d'équilibre est jugé plus informatif qu'une simple
accélération de cinématique.

### 3. sens_transition : intensité prioritaire, phase en départage

FORMAT_COMPORTEMENTS.md définit `escalade`/`desescalade` comme
"intensité ou phase monte/descend". Une lecture stricte en OU aurait
rendu quasi impossible un résultat "neutre" : la phase progresse
mécaniquement d'`initiation` à `developpement` dès la 2e occurrence
d'une même qualification, ce qui aurait classé cette transition comme
"escalade" même à intensité inchangée. Résolu en utilisant l'intensité
comme signal primaire et la phase uniquement comme départage quand
l'intensité est strictement égale, avec un poids de phase où
`resolution` (poids 0) ne "monte" pas par rapport à `culmination`
(poids 2) — la résolution referme un cycle, elle ne l'intensifie pas.

### 4. Comparaison aux cas connus sans champ de signature dédié

Le schéma de la table `behaviors` (imposé par le mandat) ne porte pas
de colonne dédiée aux paires de devises ou à la cinématique du cas
passé. `_compare_to_known_cases` recharge donc la scène source de
chaque candidat via son propre `scene_id_ref` pour recalculer ces
éléments de comparaison à la volée — cohérent avec la règle "le
comportement ne lit jamais les forces" (on relit une scène, la couche
amont immédiate, jamais les forces) et avec le principe de traçabilité
de MEMORY_CONTRACT.md.

### 5. Seuils heuristiques internes non exposés en config.py

Le mandat ne liste que 4 constantes de configuration
(`BEHAVIOR_HISTORY_LOOKBACK`, `SIMILARITY_THRESHOLD`,
`CONFIANCE_PLIURE_SEVERE`, `CONFIANCE_BASCULE_NETTE`). Les seuils
propres aux détecteurs internes (`LUTTE_FORCES_INTENSITE_MIN=40`,
`PLIURE_SEVERE_MIN=15`, `WEAK_EXTENSION_MAX=12`,
`PREPARATION_STREAK_MIN=2`) sont restés des constantes de module dans
`behavior_analyzer.py`, non promues en config.py, faute de mandat
explicite pour les y exposer — à revisiter lors de la calibration sur
données réelles.

## Points ouverts

- Calibration des seuils heuristiques internes sur données réelles
  (actuellement choisis pour être démontrables et cohérents entre eux,
  pas calibrés empiriquement).
- Réconciliation possible de la déréférence symbol/timeframe (point 1
  ci-dessus) si Phase 3 est révisée pour dénormaliser ces champs
  directement sur `scenes`.
- Branchement temps réel de `BehaviorAnalyzer` en aval de
  `SceneBuilder` (actuellement invoqué explicitement via
  `analyze_scene(scene_id)`, pas encore câblé à un flux continu).

## Validation

- `python -m pytest tests/test_behavior_analyzer.py -v` → 21 passed
- `python -m pytest tests/ -v` → 49 passed (15 Phase 2 + 13 Phase 3 +
  21 Phase 4), aucune régression
- Inventaire de fichiers confirmé : `core/v9/behavior_analyzer.py`,
  `core/v9/behavior_db.py`, `tests/test_behavior_analyzer.py`,
  `tests/fixtures/scenes_sample.json`
- Format JSON de sortie validé contre FORMAT_COMPORTEMENTS.md (test
  dédié avec round-trip JSON)
- Les 12 qualifications de l'enum sont toutes couvertes par un test
- La confiance basse (`< 50`) ne bloque pas l'émission du comportement
  (test dédié)

## Statut Phase 4

**COMPLETE** (non fusionnée sur `feat/v9-foundation-clean`).

## Prochaine étape

Fusion de `feat/v9-phase4-comportements` sur `feat/v9-foundation-clean`,
puis Phase 5 — Couche Fenêtres, consommant les comportements qualifiés
selon MEMORY_CONTRACT.md.
