# CHECKPOINT_20260705_V9_PHASE1_COMPLETE

## Contexte
Clôture de la Phase 1 (squelette cognitif) de PowerFlow V9. Deux sessions
parallèles avaient produit les 6 formats JSON du système :
- `feat/v9-phase1-formats-amont` : FORMAT_FORCES.md, FORMAT_SCENES.md,
  MEMORY_CONTRACT.md
- `feat/v9-phase1-formats-aval` : FORMAT_COMPORTEMENTS.md,
  FORMAT_FENETRES.md, FORMAT_EXPLOITABILITE.md

La revue CEO des 6 formats a validé le fond (10 exemples JSON parsaient
correctement) mais a identifié 3 corrections à appliquer avant fusion
définitive. Cette session a fusionné les deux chantiers, appliqué les
corrections, validé l'ensemble, et fusionné le résultat sur la branche
de référence du dépôt (`feat/v9-foundation-clean` — il n'existe pas de
branche `main` dans ce dépôt).

## Les 6 livrables (Phase 1 complète)
- `docs/architecture/formats/FORMAT_FORCES.md` — sortie de la couche
  Forces (8 devises, 7 timeframes dont M1 séparé, STALE_GATE)
- `docs/architecture/formats/FORMAT_SCENES.md` — sortie de la couche
  Scènes (zone, coalitions, antagonismes, cinématique locale,
  confluences MTF)
- `docs/architecture/formats/MEMORY_CONTRACT.md` — contrat de mémoire
  couvrant désormais les 5 couches (Forces, Scènes, Comportements,
  Fenêtres, Exploitabilité)
- `docs/architecture/formats/FORMAT_COMPORTEMENTS.md` — sortie de la
  couche Comportements (qualification, transitions, comparaison aux cas
  connus)
- `docs/architecture/formats/FORMAT_FENETRES.md` — sortie de la couche
  Fenêtres
- `docs/architecture/formats/FORMAT_EXPLOITABILITE.md` — sortie de la
  couche Exploitabilité

## Les 3 corrections post-review appliquées

### Correction 1 — Restructuration de `scene_source` (FORMAT_COMPORTEMENTS.md)
Problème : `scene_source` contenait `symbol`, `timeframe`, `window_start`,
`window_end` — des champs qui décrivent le périmètre d'observation du
comportement (une paire précise, un TF précis), pas la scène elle-même
(multi-devises, multi-timeframes par conception).
Correction : ces 4 champs sont montés au niveau racine du JSON. `scene_source`
est remplacé par deux champs plats à la racine : `scene_id_ref` et
`scene_timestamp`. Note explicative ajoutée au document, exemple JSON et
règle explicite n°1 mis à jour en conséquence.

### Correction 2 — `schema_version` ajouté aux 3 formats amont
Problème : les 3 formats aval portaient `schema_version: "1.0"`, pas les 3
formats amont — incohérence de contrat entre les deux chantiers.
Correction : `schema_version` ajouté comme premier champ (avant
`snapshot_id` / `scene_id` / `entry_id`) dans la structure documentée et
dans tous les exemples JSON de `FORMAT_FORCES.md`, `FORMAT_SCENES.md` et
`MEMORY_CONTRACT.md`, avec documentation du champ dans une section
« Champs obligatoires ».

### Correction 3 — `MEMORY_CONTRACT.md` étendu aux couches aval
Problème : le contrat mémoire ne couvrait que Forces et Scènes ;
Comportements, Fenêtres et Exploitabilité n'avaient aucune spec mémoire.
Correction : nouvelle section « Couches aval » documentant, pour chacune
des 3 couches, ce qu'elle écrit, ce qu'elle lit, et son cycle de vie
(identique aux couches amont : hypothèse → validation → archive). Ajout
de la Règle E de gouvernance : une couche aval ne peut écrire en mémoire
que des productions validées par sa propre cohérence interne ; les
hypothèses restent en `memory_temp.md` jusqu'à validation.

## Validation effectuée
- Les 13 blocs JSON fencés (`` ```json ``) des 6 documents parsent tous
  sans erreur (`json.loads`).
- `schema_version` présent dans les 6 formats.
- `FORMAT_COMPORTEMENTS.md` ne contient plus `scene_source` comme objet
  englobant ; `symbol`/`timeframe`/`window_start`/`window_end` sont au
  niveau racine.
- `MEMORY_CONTRACT.md` couvre les 5 couches (Forces, Scènes,
  Comportements, Fenêtres, Exploitabilité).
- Aucune référence à V8 comme dépendance technique (une seule mention de
  V8 subsiste, dans `MEMORY_CONTRACT.md`, en référence intentionnelle à
  la Règle 5 — migration curée — pas une contamination de conventions).
- Vocabulaire aligné sur `docs/lexicon/LEXICON_V9.md`.

## Fusion vers la branche de référence
- Branche de travail : `fix/v9-phase1-review`, créée depuis
  `feat/v9-phase1-formats-amont`, fusionnée avec
  `feat/v9-phase1-formats-aval` (conflits résolus dans `docs/STATE.md` et
  `docs/CACHE_BOARD.md`), puis les 3 corrections ont été commitées.
- Fusion (fast-forward) dans `feat/v9-foundation-clean`, poussée sur
  `origin/feat/v9-foundation-clean`.
- Branches temporaires nettoyées : `feat/v9-phase1-formats-amont`
  (locale + origin) et `fix/v9-phase1-review` (locale) supprimées.
  `feat/v9-phase1-formats-aval` conservée (locale + origin) car occupée
  par un worktree actif (`D:/Projet/V9_wt_formats_aval`).

## Incident de session noté
En cours de session, une branche `feat/v9-phase2-ea-mt4` a été créée et
checkoutée dans ce même répertoire de travail partagé par un processus
tiers (session concurrente), déplaçant temporairement le HEAD local.
Aucune perte de travail : les modifications non commitées ont été
préservées lors du retour sur `fix/v9-phase1-review`. Cette branche n'a
pas été touchée par cette session.

## Statut Phase 1
**COMPLETE.** Les 6 formats sont sur la branche de référence, corrigés,
validés et poussés sur origin.

## Prochaine étape
Phase 2 — Couche Forces (implémentation) : lecteur réel, EA, bridge DB.
