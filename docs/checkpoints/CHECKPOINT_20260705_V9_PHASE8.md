# CHECKPOINT_20260705_V9_PHASE8

## Date
2026-07-05

## Contexte
La chaîne cognitive V9 est complète (6/6 couches, 118 tests, Phase 7 fusionnée
sur `feat/v9-foundation-clean`). Il manquait un outillage d'observation et de
calibration : voir la chaîne travailler en temps réel, analyser les données
collectées pour suggérer des ajustements de seuils, et exporter/rejouer les
données pour analyse hors ligne. Phase 8, branche `feat/v9-phase8-monitoring`,
worktree dédié `D:\Projet\V9_wt_monitoring`.

## Livrables

### 1. `scripts/v9_dashboard.py` — dashboard terminal temps réel
Lecture seule sur `data/v9_forces.db`. Fonctions de formatage pures
(testables sans DB) séparées des fonctions d'accès DB :
- `market_status_line` : ouvert/fermé + session (délègue à
  `MarketCalendar`, labels français Sydney/Tokyo/Londres/New York/
  chevauchement).
- `format_forces_table` / `format_stale_summary` : tableau des forces du
  dernier snapshot par timeframe (ordre natif M1→D1), badge stale par TF.
- `format_behavior_block` / `format_window_block` / `format_exploitability_block` :
  blocs détaillés du dernier comportement/fenêtre/évaluation.
- `snapshot_age_seconds` / `format_age` : âge d'une ligne DB en texte natif
  (« il y a Xs/Xmin/Xh/Xj »).
- Couleurs via codes ANSI bruts (pas de dépendance externe) ; désactivées
  automatiquement si stdout n'est pas un TTY.
- CLI : `--interval N` (défaut 5s), `--once`, `--watch comportements|fenetres`.
- Affiche « En attente de données... » si les 5 tables sont vides ou si la
  DB n'existe pas encore — jamais d'erreur.

**Point technique notable** : les caractères accentués et box-drawing
(`─`, `═`) provoquent un `UnicodeEncodeError` sur une console Windows en
cp1252 (codepage par défaut, indépendant de PowerShell/Git Bash). Les trois
scripts appellent `stream.reconfigure(encoding="utf-8", errors="replace")`
sur stdout/stderr avant tout affichage — solution stdlib pure (pas de
`rich`/`colorama`), évite le crash quel que soit le codepage actif.

### 2. `scripts/v9_calibration.py` — calibration / export / stats
- `--stats` : comptages par couche, distribution des qualifications de
  comportement, top 5 qualifications, top 5 paires actives, distribution
  des statuts fenêtre/exploitabilité.
- `--export csv|json` : dump intégral des 5 tables vers `output/`
  (`forces_export`, `scenes_export`, `behaviors_export`, `windows_export`,
  `exploitability_export`), toujours créés même si une table est vide.
  `output/` ajouté à `.gitignore` (généré localement).
- `--analyze` : distribution des forces par devise/TF (min/max/mean/stdev),
  amplitude (max-min des 8 forces) par TF, vitesse par TF, fréquence des
  croisements par TF, taux de stale par TF, fréquence des coalitions/
  antagonismes (couche Scènes), puis suggestions de seuils.

**Décision de calibration assumée** : la logique réelle de coalition/
antagonisme (`scene_builder.py`) compare des devises de même direction —
non ré-implémentée ici pour rester un outil d'analyse indépendant du
moteur. À la place, `--analyze` utilise l'écart absolu de force entre
toutes les paires de devises d'un même snapshot comme proxy observable :
`COALITION_THRESHOLD` suggéré au 20e percentile de cette distribution
(petits écarts), `ANTAGONISM_THRESHOLD` au 80e percentile (grands écarts).
`PLIURE_THRESHOLD` est suggéré à partir du 75e percentile des deltas de
vitesse consécutifs par TF (proxy de delta de pente — la cinématique
complète n'est disponible que côté `scenes`, pas `forces_snapshots`).
`STALE_THRESHOLDS_MS` est suggéré par TF à partir du 95e percentile des
intervalles réels entre `bar_time` consécutifs, multiplié par 3 (marge de
sécurité). **Aucune suggestion n'est jamais appliquée automatiquement** —
`core/v9/config.py` n'est jamais modifié par ce script.

### 3. `scripts/v9_replay.py` — replay / inspection en lecture seule
- `--list` : tous les comportements qualifiés (behavior_id, timestamp,
  qualification, intensité, confiance, symbol, timeframe, scene_id_ref).
- `--show <behavior_id>` : comportement complet + scène source
  (désérialisée, champs JSON parsés) + snapshot de forces source + fenêtre
  produite (si existante, jointure sur `windows.behavior_id`) + évaluation
  d'exploitabilité (si existante, jointure sur `exploitability.window_id`).
- `--compare <id1> <id2>` : diff qualification/intensité/phase, diff
  cinématique locale (lue depuis la scène source de chaque comportement),
  diff nombre de coalitions/antagonismes, score de similarité heuristique
  (0.0-1.0, pondération documentée dans le docstring de
  `compute_similarity_score` — indépendant du champ `similarite_score` de
  chaque comportement, qui compare à l'historique replay et non à un autre
  comportement précis).
- `--search key=value [key=value ...]` : filtre AND sur
  `qualification`, `intensite`, `phase`, `symbol`, `timeframe`,
  `min_confiance` (comparaison numérique sur `confiance_qualification`).

### 4. `tests/test_dashboard.py` — 21 tests
Couvre les 6 points demandés : formatage tableau des forces (vide, une
ligne, ordre natif des TF, valeur manquante), détection marché ouvert/fermé
(samedi fermé, mi-semaine ouvert + session Londres, chevauchement Londres/
New York), calcul d'âge de snapshot (secondes exactes, suffixe `Z`,
formatage secondes/minutes/heures), couleur stale/OK (sans couleur, avec
ANSI), formatage comportement (bloc complet), formatage fenêtre (ouverte,
fragile, absente avec `type_fenetre` null).

## Validation
`python -m pytest tests/ -v` → **139 passed** (118 précédents + 21
nouveaux pour `test_dashboard.py`), aucune régression.

Commandes de validation manuelle exécutées avec succès (DB vide/absente) :
- `python scripts/v9_dashboard.py --once` → « En attente de données... »,
  exit 0.
- `python scripts/v9_calibration.py --stats` → rapport vide propre, exit 0.
- `python scripts/v9_calibration.py --export csv` → 5 fichiers produits
  dans `output/` (0 ligne chacun), exit 0.
- `python scripts/v9_replay.py --list` → message DB introuvable, exit 0.

Testés également avec une DB peuplée manuellement (30 snapshots M5, une
scène avec coalition, deux comportements liés scène→fenêtre→exploitabilité) :
`--once` affiche le tableau des forces/chaîne cognitive/derniers blocs
sans erreur ; `--analyze` produit des distributions et suggestions
cohérentes ; `--export csv`/`--export json` comptent correctement les
lignes ; `--show`/`--compare`/`--search` résolvent correctement les
jointures scène/fenêtre/exploitabilité. Toutes les données de test ont
été supprimées après validation (`data/*.db` exclu du dépôt de toute
façon).

## Points ouverts (non bloquants)
- Les suggestions de seuils de `--analyze` reposent sur des proxys
  observables (écarts de force bruts, delta de vitesse) plutôt que sur une
  ré-implémentation exacte de la logique interne de `scene_builder.py` —
  assumé comme un compromis raisonnable pour un outil de calibration
  indépendant du moteur ; à réévaluer si les suggestions s'avèrent trop
  éloignées des seuils réellement pertinents une fois des données de
  marché réelles accumulées.
- `output/` (exports CSV/JSON) est un répertoire généré localement, exclu
  du dépôt par `.gitignore`, comme `data/*.db`.

## Statut
**PHASE 8 TERMINÉE.** Dashboard temps réel, outil de calibration/export/
stats, outil de replay/inspection livrés — tous en lecture seule stricte
sur `data/v9_forces.db`, aucune modification de `config.py`, aucune
logique de trading ou d'exécution d'ordre. 139 tests verts.

## Prochaine étape
Utiliser `scripts/v9_dashboard.py` pendant le prochain test live (marché
ouvert) pour observer la chaîne cognitive en direct, puis
`scripts/v9_calibration.py --analyze` sur les données réelles accumulées
pour ajuster manuellement les seuils de `core/v9/config.py`.
