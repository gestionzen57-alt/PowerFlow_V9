# CHECKPOINT_20260705_V9_PHASE5

## Contexte
Implémentation de la couche **Fenêtres** (4e couche cognitive) sur la
branche `feat/v9-phase5-fenetres`, dans le worktree dédié
`D:\Projet\V9_wt_fenetres`, basée sur `origin/feat/v9-foundation-clean`
(Phase 2 — couche Forces — fusionnée à ce stade).

**Point important** : la Phase 4 (couche Comportements —
`core/v9/behavior_analyzer.py`, `core/v9/behavior_db.py`) n'était pas
encore fusionnée sur `feat/v9-foundation-clean` au moment de cette session
(elle existe sur la branche parallèle `feat/v9-phase4-comportements`, non
mergée). Conformément à la consigne de session, la couche Fenêtres a donc
été implémentée en consommant strictement le **format** de sortie
`docs/architecture/formats/FORMAT_COMPORTEMENTS.md`, sans dépendre du code
Python de la Phase 4.

## Livrables

### `core/v9/window_gate.py`
- `WindowGate(db_path, config, memory_path)` — gate principal.
- `evaluate_behavior(behavior_id)` → dict conforme à
  `FORMAT_FENETRES.md` (schema_version "1.0").
- Cycle de vie complet : `_check_eligibility`, `_determine_status`,
  `_determine_type`, `_calculate_confidence`, `_detect_fragility`,
  `_define_invalidation_conditions`, `_manage_lifecycle`.
- Écriture DB (`_write_window_to_db`) et mémoire
  (`_write_memory`, statut `hypothese`, format `MEMORY_CONTRACT.md`,
  append dans `memory/memory_temp.md`).
- **Shim `behaviors`** : en l'absence de `core/v9/behavior_db.py`, une
  table `behaviors` minimale (reflet plat de `FORMAT_COMPORTEMENTS.md`)
  est créée et alimentée via `WindowGate.insert_behavior()` /
  `insert_behavior()`. Trois champs auxiliaires non présents dans le
  format v1.0 (`confluence_mtf_confirmee`, `rejet_repulsion_detecte`,
  `stale`) sont portés par cette table car nécessaires aux règles de
  bonus/malus et de type "rebond" explicitement demandées — ce sont des
  signaux que la couche Comportements est censée transmettre en aval,
  jamais lus depuis une scène ou une force directement. **Point ouvert** :
  quand `behavior_db.py` (Phase 4) sera fusionné, `_load_behavior` /
  `_load_behavior_history` devront être adaptés à son schéma réel — le
  reste de la logique (statut, type, fragilité, invalidation, cycle de
  vie) n'est pas affecté.

### `core/v9/window_db.py`
- Table `windows` conforme au schéma demandé (16 colonnes),
  index `(behavior_id)`, `(statut, timestamp)`, `(timestamp_ouverture)`.
- `get_connection()` / `init_window_db()` — mêmes pragmas que
  `db_schema.py` (WAL, busy_timeout 30s).

### `core/v9/config.py` — constantes ajoutées
`CONFIANCE_MIN_FENETRE=50`, `FRAGILITE_CONFIANDE_DELTA=15`,
`WINDOW_LIFECYCLE_LOOKBACK=5`, `BONUS_CONFLUENCE_MTF=10`,
`BONUS_SIMILARITE=8`, `MALUS_STALE=20`, `MALUS_FRAGILITE=15`,
`SIMILARITE_BONUS_THRESHOLD=0.75` (seuil au-delà duquel le bonus de
similarité s'applique, non spécifié explicitement dans la mission —
valeur assumée).

### `tests/fixtures/behaviors_sample.json`
6 comportements consécutifs sur EURUSD/M5, conformes à
`FORMAT_COMPORTEMENTS.md` :
1. `maintien` (confiance 30) → absente
2. `contraction` (confiance 45) → ambigüe
3. `preparation_ouverture_fenetre` (confiance 55) → en_preparation
4. `bascule` (confiance 74, confluence_mtf_confirmee=true,
   similarite_score=0.82) → ouverte, type retournement
5. `extension` (confiance 68, stale=true) → fragile (fragilité détectée
   par le flag stale), type continuation
6. `annulation` (confiance 60) → invalidee, fermeture de la fenêtre
   ouverte en (4)

### `tests/test_window_gate.py`
20 tests, tous verts — couvrent les 6 statuts, les 3 types de fenêtre
(`retournement`, `continuation`, null), les conditions d'invalidation
(bascule → exactement 2), le cycle de vie (ouverture → fragile →
invalidee avec `timestamp_ouverture` conservé), la fragilité (confiance
en baisse ET stale), le niveau de confiance (bonus confluence MTF +
similarité, malus stale + fragilité), la validité du format JSON contre
`FORMAT_FENETRES.md`, `behavior_source.behavior_id` jamais vide,
l'écriture DB et l'écriture mémoire.

## Décisions de conception non explicitement tranchées par la mission

1. **Chevauchement `rupture` (retournement vs rupture_range)** : la
   mission liste `rupture` dans les deux catégories. Résolu par priorité
   au premier match documenté (`retournement`) ; `reequilibrage` seul
   couvre `rupture_range`.
2. **`extension` absente du pseudocode `_determine_status`** — mais le
   plan de fixture demandait explicitement `extension` → fenêtre
   `fragile`. Résolu en traitant `extension` comme `bascule`/`rupture`
   (ouvre/continue une fenêtre si confiance ≥ seuil), la fragilité
   pouvant ensuite rétrograder `ouverte` → `fragile`.
3. **`reequilibrage`** → mission mentionne un statut `"fermee"` qui
   n'existe pas dans l'enum à 6 valeurs. Traduit par `invalidee` (la
   fermeture réelle est portée par `timestamp_fermeture`, pas par un
   statut distinct).
4. **Mémoire** : aucun mécanisme JSONL/mémoire machine n'existait encore
   dans le dépôt pour les couches amont (Forces/Scènes n'écrivent pas non
   plus en mémoire via code Python à ce stade) — `_write_memory` ajoute
   un bloc JSON fenced sous `memory/memory_temp.md`, conforme au schéma
   `MEMORY_CONTRACT.md` (`couche_origine: "fenetres"`, `type: "fenetre"`,
   `statut: "hypothese"`).

## Validation
- `python -m pytest tests/test_window_gate.py -v` → 20 passed
- `python -m pytest tests/ -v` → 35 passed (aucune régression Phase 2)

## Statut Phase 5
**COMPLETE** (implémentation couche Fenêtres consommant le format
Comportements). Le point ouvert n°1 (adaptation au futur
`behavior_db.py` réel) est documenté et non bloquant.

## Prochaine étape
- Fusionner Phase 3 (Scènes) et Phase 4 (Comportements) sur
  `feat/v9-foundation-clean` avant ou en parallèle de cette Phase 5.
- Revalider `_load_behavior` / `_load_behavior_history` contre le
  schéma réel de `core/v9/behavior_db.py` dès sa fusion.
- Phase 6 — Couche Exploitabilité, consommant `FORMAT_FENETRES.md`.
