# CHECKPOINT_20260705_V9_PHASE3

## Contexte
Phase 3 : construire la couche Scènes de PowerFlow V9 — from scratch
(V8 n'avait pas de couche Scènes). Travail mené dans un worktree dédié
(`D:/Projet/V9_wt_scenes`, branche `feat/v9-phase3-scenes`), rebasée en
cours de session sur `origin/feat/v9-foundation-clean` une fois la
fusion Phase 2 (EA MT4 + capture Python) disponible sur origin.

La couche Scènes consomme uniquement `forces_snapshots` (table SQLite
produite par la Phase 2) et produit le seul matériau que la couche
Comportements (Phase 4) sera autorisée à consommer.

## Livrables
- `core/v9/scene_db.py` — schéma table `scenes` (référence
  `forces_snapshot_ref`/`forces_snapshot_timestamp`, `stale` hérité,
  colonnes `*_json` pour zone/coalitions/antagonismes/cinématique/
  confluences/contexte), index sur `(timestamp)` et
  `(forces_snapshot_ref)`, `init_scene_db()`.
- `core/v9/scene_builder.py` — `SceneBuilder` : `build_scene(snapshot_id)`,
  `_detect_coalitions`, `_detect_antagonisms`, `_compute_cinematics`,
  `_detect_mtf_confluences`, `_identify_context`, `_build_zone`,
  `_write_scene_to_db`, `_write_memory`.
- `core/v9/config.py` — 4 constantes ajoutées : `COALITION_THRESHOLD`
  (5.0), `ANTAGONISM_THRESHOLD` (10.0), `PLIURE_THRESHOLD` (3.0),
  `MTF_LOOKBACK` (10).
- `tests/test_scene_builder.py` — 13 tests, tous verts.
- `tests/fixtures/forces_snapshots_sample.json` — 5 snapshots (3×M5 +
  1×H4 + 1×M1) formant une coalition USD/EUR visible sur plusieurs
  timeframes.

## Décisions de design (non explicitement tranchées par le prompt)

### 1. Une ligne `forces_snapshots` = un panier complet des 8 devises
Chaque ligne de `forces_snapshots` (Phase 2) porte déjà `force_usd`
à `force_nzd` pour un timeframe donné à un instant donné (la sonde EA
calcule le panier SDI des 8 devises en une fois, par timeframe). La
couche Scènes lit donc directement une ligne comme un « snapshot de
forces » complet au sens de `FORMAT_FORCES.md`, sans avoir à agréger
plusieurs lignes entre elles pour reconstituer les 8 devises.

### 2. Direction par devise : calcul propre à la couche Scènes
`forces_snapshots.direction` (colonne Phase 2) ne décrit que la devise
de base du symbole observé par la sonde EA. La couche Scènes a besoin
d'une direction par devise pour les 8 devises afin de détecter
coalitions/antagonismes : elle la calcule elle-même (delta vs.
snapshot précédent du même timeframe). **En l'absence de snapshot
précédent** (première lecture d'un timeframe peu fréquent, ex. H4 avec
peu d'historique), la direction est inférée par position par rapport à
une référence neutre (`NEUTRAL_REFERENCE = 50.0`) plutôt que forcée à
`neutre`. Décision assumée pour permettre la détection de coalitions
même sur un timeframe faiblement échantillonné — documentée dans le
docstring du module. Point à recaler si la calibration réelle SDI ne
centre pas les forces autour de 50.

### 3. Cinématique locale exprimée par pas de snapshot, pas en secondes
`pente`/`courbure` sont calculées comme deltas simples entre snapshots
consécutifs du même timeframe (`delta_time = 1 étape`), pas normalisées
par le temps réel écoulé. Une normalisation en secondes réelles rend
`pente`/`courbure` bien trop petites (échelle `1e-3`) pour jamais
dépasser `PLIURE_THRESHOLD = 3.0`, qui est manifestement calibré dans
la même échelle que `COALITION_THRESHOLD`/`ANTAGONISM_THRESHOLD` (unités
de force brute). Cette lecture reste `locale` à la scène, conformément
à `FORMAT_SCENES.md`.

### 4. Confluences MTF : cascades entre timeframes adjacents présents
`_detect_mtf_confluences` compare uniquement les paires de timeframes
adjacents effectivement présents dans `snapshots_by_tf` (ordre HTF→LTF :
D1, H4, H1, M30, M15, M5, M1), pas toutes les combinaisons possibles —
cohérent avec l'exemple de `FORMAT_SCENES.md` (cascades H4→M15,
M15→M5). Pour chaque timeframe autre que le timeframe primaire, ses
propres coalitions/antagonismes sont recalculés à partir de son
historique local (jusqu'à `MTF_LOOKBACK` lignes), jamais lus depuis une
scène déjà construite (une scène ne lit jamais une autre scène).

### 5. Zone : dérivée des champs OHLC de la ligne de forces primaire
Aucun algorithme de détection de zone n'était détaillé dans la mission
(contrairement aux 6 autres points). `_build_zone` dérive
`niveau_reference`/`borne_basse`/`borne_haute` des colonnes
`close`/`low`/`high` déjà présentes sur la ligne `forces_snapshots`
primaire, `structure` de l'état `compression_extension` de la
cinématique locale, et `niveau` (mineure/intermédiaire/majeure) du
timeframe. Fonction interne, pas un des 7 points nommés du prompt.

### 6. Fixture alignée sur le schéma DB plat, pas sur le JSON agrégé
`FORMAT_FORCES.md` illustre un snapshot agrégé multi-devises sous forme
de liste d'entrées par devise. La table `forces_snapshots` réelle
(Phase 2) est plate : une ligne porte déjà les 8 `force_*`. La fixture
respecte donc les champs obligatoires de `FORMAT_FORCES.md`
(`schema_version`, `stale`, etc.) sous la forme réellement stockée en
DB, pas sous la forme du JSON agrégé illustratif — aucun agrégateur
multi-lignes n'existe en Phase 2/3.

### 7. Mémoire écrite dans `memory/memory_temp.md` (jamais `memory.md`)
`SceneBuilder._write_memory` écrit par défaut au statut `hypothese`
uniquement (la couche Scènes ne s'auto-valide jamais — Règle E,
`MEMORY_CONTRACT.md`). Chaque scène produit une entrée `type: scene`,
une entrée `hypothese_coalition` par coalition, une entrée
`hypothese_antagonisme` par antagonisme, une entrée
`signature_coherence` par libellé de `confluences_mtf`. Format JSON
fenced dans le fichier Markdown, conforme au schéma de
`MEMORY_CONTRACT.md`.

### 8. `stale` de la scène = `stale` du snapshot source, jamais masqué
Le champ `stale` de la table `scenes` est relu directement depuis
`forces_snapshots` au moment de l'écriture (`_write_scene_to_db`), pas
stocké dans le JSON `FORMAT_SCENES.md` lui-même (qui n'a pas ce champ).
Les lignes d'historique utilisées pour cinématique/coalitions/MTF
excluent les lignes `stale=1` (traitées comme absentes, conformément au
STALE_GATE) — seul le snapshot explicitement demandé à `build_scene()`
est toujours inclus tel quel, même s'il est stale, pour rester
l'ancrage (`forces_snapshot_ref`) de la scène.

## Incident de session
Le worktree initial a été créé par erreur sur une révision pré-fusion
Phase 2 (avant que la fusion `feat/v9-phase2-python-capture` →
`feat/v9-foundation-clean` ne soit poussée sur origin), et un premier
`git worktree add` a échoué silencieusement à cause de l'échappement
des antislashes Windows dans l'outil bash (chemin `D:\Projet\V9_wt_scenes`
interprété comme `D:ProjetV9_wt_scenes`, créant un worktree imbriqué
dans le dépôt principal). Le worktree fautif a été supprimé
(`git worktree remove --force`), la branche `feat/v9-phase3-scenes`
recréée proprement avec des slashes (`D:/Projet/V9_wt_scenes`), puis
stash + rebase sur `origin/feat/v9-foundation-clean` une fois la fusion
Phase 2 confirmée sur origin. Aucune perte de travail : le seul commit
local (ajout des 4 constantes de config) a été stashé avant rebase et
ré-appliqué (fusion automatique) après.

## Validation effectuée
- `python -m pytest tests/ -v` → 28 passed (15 Phase 2 + 13 Phase 3).
- JSON de sortie de `build_scene()` vérifié champ par champ contre la
  structure documentée de `FORMAT_SCENES.md` (`schema_version`,
  `scene_id`, `timestamp`, `timeframes_concernes`,
  `forces_snapshot_ref{snapshot_id,timestamp}`,
  `zone{prix,structure,niveau}`, `coalitions[]`, `antagonismes[]`,
  `cinematique_locale{angle,courbure,pente,pliure,
  acceleration_deceleration,rotation_force,compression_extension}`,
  `confluences_mtf{emboitement_detecte,cascades_temporelles,
  signatures_coherence}`, `contexte_temporel{session,fenetre}`), avec
  round-trip `json.dumps`/`json.loads`.
- Confluence MTF vérifiée manuellement sur la fixture : scène construite
  depuis `v9-fixture-m5-003` référence bien `H4` et `M1` en plus de
  `M5`, avec 2 cascades (`H4→M5`, `M5→M1`) portant la coalition
  `EUR/USD`.
- `forces_snapshot_ref` confirmé comme simple référence
  (`snapshot_id`+`timestamp`), aucune duplication des valeurs de force
  dans la scène.
- Écriture DB (`scenes`) et mémoire (`memory/memory_temp.md`) vérifiées
  par tests dédiés.

## Ce qui a été explicitement refusé / évité
- Aucune reprise de code V8 (aucune couche Scènes n'existait en V8).
- Aucune logique de trading, aucune qualification de comportement dans
  le temps, aucune qualification de fenêtre — strictement la lecture
  de scène (zone, coalitions, antagonismes, cinématique locale,
  confluences MTF, contexte temporel).
- La scène ne lit jamais une autre scène ni une couche aval
  (Comportements/Fenêtres/Exploitabilité) — conforme à la Règle D de
  `MEMORY_CONTRACT.md`.

## Prochaine marche
1. Calibrer `NEUTRAL_REFERENCE` (50.0) et les seuils
   `COALITION_THRESHOLD`/`ANTAGONISM_THRESHOLD`/`PLIURE_THRESHOLD` sur
   des données réelles une fois la sonde EA validée en conditions
   réelles (point ouvert hérité de la Phase 2B).
2. Brancher `SceneBuilder` en aval de `capture_server.py` (appel
   `build_scene()` + `_write_scene_to_db()` + `_write_memory()` après
   chaque insertion non stale dans `forces_snapshots`), hors périmètre
   de cette session (mission Phase 3 = builder + tests, pas
   l'orchestration temps réel).
3. Engager la Phase 4 — Couche Comportements, qui consomme les scènes
   validées selon `MEMORY_CONTRACT.md`.

## Risque principal
Les seuils de coalition/antagonisme/pliure et la référence neutre
(50.0) sont des valeurs de départ raisonnables mais non calibrées sur
des données réelles issues de la sonde SDI — comme pour la Phase 2, un
premier lot de captures réelles sera nécessaire avant de considérer les
détections de la couche Scènes comme fiables.
