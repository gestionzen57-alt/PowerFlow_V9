# STATE — PowerFlow V9

## Dernière mise à jour
2026-07-05

## Statut
PHASE 9 TERMINÉE — couche Décision et Principes (2026-07-05, branche `feat/v9-foundation-clean`).
Chaîne cognitive étendue : Forces → Scènes → Comportements → Fenêtres → Exploitabilité →
Régime → Principes → Signal → Décision. Nouveaux modules `core/v9/` : `regime_db.py` /
`regime_detector.py` (table `regime_snapshots`, gap V8 comblé — machine à états palier/
cassure/extension/retour_equilibre/rejet portée depuis `pf_regime_detector.py` V8, fenêtre
glissante `REGIME_LOOKBACK_BARS` au lieu d'un batch historique) ; `principle_db.py` /
`principle_engine.py` (tables `principles` / `principle_evaluations`, 27 grammaires YAML
migrées telles quelles depuis V8 dans `core/v9/principles/` — 9 `kind: node_rule` + 18
`kind: grammar`, 10 ACTIVE / 17 SHADOW) ; `signal_db.py` / `signal_generator.py` (table
`signals`, filtre exploitabilité + régime, vote majoritaire sur les principes ACTIVE
déclenchés) ; `decision_db.py` / `decision_logger.py` (table `decisions`, contexte complet
replayable, action qualitative observer/surveiller/preparer_entree/aucune_action) ;
`zone_db.py` (table `zone_diagnostics`, schéma migré de V8, **non alimentée cette phase** —
gap Priorité 2 documenté, ~5-8j, cf. `docs/audit_v8_v9_migration.md`). `orchestrator.py`
étend `run_chain` avec les 4 étapes Régime/Principes/Signal/Décision (même pattern
fail-soft-par-étape que les couches précédentes).
Gap connu : 9 des 27 principes (`node_rule`) référencent des champs `zone_diagnostics`
(état/z_extreme_dir/tension_score/...) absents tant que cette table n'est pas alimentée —
dégradation gracieuse (jamais d'erreur), documentée dans `core/v9/principle_engine.py` et
`core/v9/zone_db.py`. `regime_snapshots.cassure_type` reste `INDETERMINEE` (pas de couche
tick en V9). `scripts/v9_dashboard.py` (`--watch signals`/`--watch decisions` + section
chaîne étendue) et `scripts/v9_calibration.py` (`--principes`, hit rate/confiance/
suggestions de promotion ACTIVE ou de blocage par le gap zone_diagnostics) mis à jour.
75 nouveaux tests (`test_regime_detector.py` 10, `test_principle_engine.py` 36,
`test_signal_generator.py` 17, `test_decision_logger.py` 12) — 214 tests au total, tous
verts (139 précédents + 75). `scripts/regenerate_chain.py` rejoué sur les 1194 snapshots
non-stale : 0 erreur, latence moyenne 189,58ms/snapshot (chaîne complète 8 couches) — sous
la cible de 200ms grâce à un cache process-local du catalogue de principes (le rechargement
YAML par snapshot coûtait ~30ms, cf. commentaire `_YAML_CACHE` dans `principle_engine.py`).
Note de coordination : une session concurrente travaille en parallèle sur `docs/v9-governance`
(gouvernance documentaire, lecture seule sur le code) — voir note ci-dessous et
`docs/phases/PHASE9_DECISION.md`, volontairement non modifié par cette session pour éviter
tout conflit avec ce travail documentaire en cours.

## Correctif post-Phase 9 (2026-07-05) — idempotence de regenerate_chain.py
`scripts/regenerate_chain.py` n'était pas idempotent : `scene_id`/`behavior_id`/
`window_id`/`exploitability_id`/`signal_id`/`decision_id` sont générés avec un suffixe
aléatoire à chaque appel de `run_chain`, sans clé métier protégeant `scenes`/`behaviors`/
`windows`/`exploitability`/`signals`/`decisions`/`principle_evaluations` contre un rejeu
en double (seule `regime_snapshots` a une contrainte UNIQUE métier réelle). Un rejeu
antérieur avait déjà dupliqué `scenes`/`behaviors`/`windows`/`exploitability` en
production (2388 lignes au lieu de 1194). Corrigé par `--replace-derived` (delete ciblé
des tables dérivées, jamais `forces_snapshots`, puis régénération complète) et un refus
par défaut (exit 2) si la DB dérivée n'est pas vide ; `--dry-run` pour inspecter sans
écrire. Détails : `docs/checkpoints/CHECKPOINT_20260705_V9_REGEN_IDEMPOTENT.md`. 218
tests, tous verts (214 précédents + 4 nouveaux `test_regenerate_chain.py`). La purge de
la duplication déjà présente dans `data/v9_forces.db` reste une action opérateur
(`--replace-derived`, ~245k lignes dérivées supprimées puis régénérées).

GOUVERNANCE DOCUMENTAIRE AJOUTÉE — branche `docs/v9-governance`, en parallèle de la Phase 9
(décision et principes) en cours sur une autre session. Arborescence documentaire canonique
créée à la racine de `docs/` : `ARCHITECTURE.md`, `DOCTRINE.md`, `LEXIQUE.md` (index de
synthèse renvoyant vers `docs/doctrine/*.md` et `docs/lexicon/LEXICON_V9.md`, sans
duplication de contenu détaillé), `NOMENCLATURE.md`, `ROADMAP.md`, `DOC_GOVERNANCE.md`,
`DOC_REGISTRY.yml` (registre de tous les documents du repo). Nouveaux dossiers
`docs/phases/` (un document par phase, 1 à 9), `docs/architecture/CHAINE_COGNITIVE.md` /
`DB_SCHEMA.md` (schéma SQLite complet, y compris les tables Phase 9 en cours) /
`PIPELINE_LIVE.md`, `docs/checkpoints/CHECKPOINT_TEMPLATE.md`, `docs/reports/`. Outillage :
`tools/doc_sync.py` (`--check`/`--update`/`--stale`, vérifié fonctionnel) et
`.github/workflows/doc-freshness.yml` (CI sur push `feat/v9-foundation-clean`/`main`).
Aucun fichier de code modifié — travail strictement documentaire, lecture seule sur le code
de la Phase 9 en cours (documenté par inventaire, marqué « en cours, non finalisé » partout
où il apparaît). Voir `docs/DOC_GOVERNANCE.md` pour les règles et
`docs/phases/PHASE9_DECISION.md` pour le placeholder à compléter à la clôture de la Phase 9.

PHASE 8 TERMINÉE — monitoring + calibration + replay (2026-07-05, branche `feat/v9-phase8-monitoring`, worktree `D:\Projet\V9_wt_monitoring`). Dashboard terminal temps réel (`scripts/v9_dashboard.py`), outil de calibration/export/stats (`scripts/v9_calibration.py`), outil de replay/inspection (`scripts/v9_replay.py`) — tous en lecture seule stricte sur `data/v9_forces.db`, aucune écriture DB, aucune modification de `core/v9/config.py`, aucune logique de trading. Couleurs ANSI brutes (pas de dépendance externe), UTF-8 forcé sur stdout/stderr pour éviter un `UnicodeEncodeError` sur console Windows cp1252. 139 tests, tous verts (118 précédents + 21 nouveaux pour `test_dashboard.py`). Voir `docs/checkpoints/CHECKPOINT_20260705_V9_PHASE8.md` pour le détail complet.
Prochaine étape : test live à l'ouverture du marché avec `scripts/v9_dashboard.py` en observation, puis `scripts/v9_calibration.py --analyze` sur données réelles pour ajuster manuellement les seuils.

PHASE 7 TERMINÉE — fusionnée sur `feat/v9-foundation-clean` (fast-forward, sans conflit, 2026-07-05). Déploiement live + test d'intégration préparés. Référentiel temporel V9 (`core/v9/market_calendar.py`, `MarketCalendar`), outillage de déploiement (`scripts/deploy_v9.py`, `scripts/validate_ea_output.py`, `scripts/live_integration_test.py`) et guide de déploiement (`docs/deployment/V9_DEPLOYMENT_GUIDE.md`) livrés. Port TCP de référence temporairement basculé sur `31690` (V9 test, V8 reste sur `31685`) ; les deux EA (`ea/V9_Sonde_TF.mq4`, `ea/V9_Sonde_M1.mq4`) exposent désormais un input `ServerPort` configurable (remplace le port figé en dur). 118 tests, tous verts (96 précédents + 22 nouveaux pour `market_calendar.py`), revalidés post-fusion sur `feat/v9-foundation-clean`.
Branche `feat/v9-phase7-live-deployment` supprimée (locale + distante) après fusion — plus de branches de phase en attente.
PHASE 4 + 5 + 6 TERMINÉES ET FUSIONNÉES — Couche Comportements (`BehaviorAnalyzer`, table `behaviors`, 21 tests), couche Fenêtres (`WindowGate`, table `windows`, 20 tests) et couche Exploitabilité (`ExploitabilityEvaluator`, table `exploitability`, 26 tests) fusionnées sur `feat/v9-foundation-clean`. Phase 3 (Scènes), Phase 2 (EA MT4 + capture Python) et Phase 1 (6 formats) terminées et fusionnées précédemment. CHAÎNE COGNITIVE V9 COMPLÈTE — 6/6 couches implémentées (Forces → Scènes → Comportements → Fenêtres → Exploitabilité).
Point ouvert Phase 5 résolu à la fusion Phase 4+5 : `window_gate.py` lit `behavior_db.py` (table `behaviors` réelle) au lieu du shim provisoire.
Point ouvert Phase 6 résolu à cette fusion : `exploitability_evaluator.py` lit désormais `window_db.py` (table `windows` réelle) au lieu du shim provisoire — voir section « Revalidation post-fusion Phase 6 » ci-dessous.
Prochaine étape : déploiement live à l'ouverture du marché (dimanche 23h Paris / 22h UTC) — voir `docs/deployment/V9_DEPLOYMENT_GUIDE.md`.
Voir docs/checkpoints/CHECKPOINT_20260705_V9_PHASE7.md pour le détail complet de la Phase 7, et docs/checkpoints/CHECKPOINT_20260705_V9_CHAIN_COMPLETE.md pour la fusion des couches 1-5 et la revalidation des points ouverts.

## Livrables Phase 8 (branche `feat/v9-phase8-monitoring`)
- `scripts/v9_dashboard.py` — dashboard terminal temps réel, lecture seule sur `data/v9_forces.db` : statut marché/session (`MarketCalendar`), tableau des forces du dernier snapshot par TF, badges stale, compteurs par couche avec âge du dernier enregistrement, blocs détaillés dernier comportement/fenêtre/exploitabilité. CLI `--interval N` (défaut 5), `--once`, `--watch comportements|fenetres`. Couleurs ANSI brutes (pas de `rich`/`colorama`), UTF-8 forcé sur stdout/stderr (`stream.reconfigure`) pour éviter un `UnicodeEncodeError` sur console Windows en cp1252 avec les caractères accentués/box-drawing.
- `scripts/v9_calibration.py` — `--stats` (comptages, distributions, top 5 qualifications/paires), `--export csv|json` (dump intégral des 5 tables vers `output/`, répertoire ajouté à `.gitignore`), `--analyze` (distributions forces/amplitude/vitesse/croisements/stale par TF + fréquence coalitions/antagonismes + suggestions de seuils `COALITION_THRESHOLD`/`ANTAGONISM_THRESHOLD`/`PLIURE_THRESHOLD`/`STALE_THRESHOLDS_MS`). Ne modifie jamais `core/v9/config.py` ni la DB — suggestions affichées uniquement. Suggestions basées sur des proxys observables (écarts de force bruts par paire de devises, delta de vitesse consécutif, percentiles d'intervalles réels entre snapshots) plutôt que sur une ré-implémentation de la logique interne de `scene_builder.py`.
- `scripts/v9_replay.py` — `--list`, `--show <behavior_id>` (comportement + scène source désérialisée + snapshot de forces + fenêtre + exploitabilité, jointures via `scene_id_ref`/`forces_snapshot_ref`/`behavior_id`/`window_id`), `--compare <id1> <id2>` (diff qualification/intensité/phase/cinématique/coalitions/antagonismes + score de similarité heuristique documenté), `--search key=value` (qualification, intensite, phase, symbol, timeframe, min_confiance). Lecture seule stricte.
- `tests/test_dashboard.py` — 21 tests (tableau forces, détection marché ouvert/fermé + session, âge de snapshot, badges stale/OK, formatage comportement, formatage fenêtre).
- `.gitignore` — ajout de `output/` (exports de calibration, générés localement).
- Décision de portée : aucune logique d'exécution d'ordre, aucune écriture DB par les 3 scripts, aucune modification automatique de `core/v9/config.py`.
- Voir `docs/checkpoints/CHECKPOINT_20260705_V9_PHASE8.md` pour le détail complet (décisions de calibration assumées, validation manuelle).

## Livrables Phase 7 (branche `feat/v9-phase7-live-deployment`)
- `core/v9/config.py` — référentiel temporel ajouté : `BROKER_UTC_OFFSET_HOURS` (3, Tickmill/FTMO GMT+3), `LOCAL_TIMEZONE` ("Europe/Paris"), `MARKET_OPEN_UTC_DAY/HOUR`, `MARKET_CLOSE_UTC_DAY/HOUR`. Port de référence `LISTEN_PORT` basculé sur `31690` (V9 test — V8 reste sur `31685` en production).
- `core/v9/market_calendar.py` — `MarketCalendar` : `is_market_open`, `current_session` (sydney/tokyo/london/new_york/overlap_london_ny/closed, priorité overlap > london > new_york > tokyo > sydney en cas de chevauchement), `next_open`, `broker_to_utc`/`utc_to_broker` (offset fixe GMT+3), `paris_to_utc` (DST géré via `zoneinfo`, sans dépendance externe).
- `tests/test_market_calendar.py` — 22 tests, tous verts (couvrent explicitement les cas de validation fournis : samedi/dimanche/vendredi pour `is_market_open`, 10h/14h/3h UTC pour `current_session`).
- `ea/V9_Sonde_TF.mq4`, `ea/V9_Sonde_M1.mq4` — ajout de l'input `ServerPort` (remplace la constante Winsock figée qui codait en dur le port `31685` dans le sockaddr packé) ; nouvelle fonction `MakeSockAddr0(port)` qui recalcule dynamiquement l'adresse. Nécessaire pour permettre le test sur le port `31690` sans modifier V8. Recompilation requise pour toute instance existante.
- `ea/V9_Sonde_README.md` — section réseau mise à jour (paramètre `ServerPort`, procédure de bascule 31685/31690).
- `scripts/deploy_v9.py` — `--check` (Python 3.11+, modules `core/v9/` importables, DB + 5 tables, port disponible, vérification souple de connexion EA), `--start` (lance `capture_server.py` en sous-processus, PID file `logs/v9_capture.pid`), `--status` (compteurs par couche + par timeframe, taux de stale, âge du dernier snapshot), `--stop` (arrêt via PID file, `taskkill` sur Windows).
- `scripts/validate_ea_output.py` — reçoit 1 message EA, valide la structure (champs obligatoires, 8 forces, timeframe), vérifie la cohérence timestamp UTC déclaré vs `capture_time` broker reconverti (détecte un `BrokerUTCOffsetHours` incorrect), heuristique de plausibilité AUD (doit se situer entre EUR et NZD à +/-15 unités — signale une inversion de buffer SDI potentielle sans jamais trancher automatiquement).
- `scripts/live_integration_test.py` — attend de nouveaux snapshots non-stale sur la DB de production (lecture seule), copie chaque snapshot vers une DB de test dédiée (`data/v9_live_test.db`, recréée par défaut), fait traverser la chaîne complète (Scènes → Comportements → Fenêtres → Exploitabilité) sur cette DB de test, mesure le temps par couche, rapporte le premier comportement/fenêtre/évaluation avec leur qualification/statut. Ne modifie jamais la DB de production.
- `docs/deployment/V9_DEPLOYMENT_GUIDE.md` — procédure complète (compilation EA, déploiement MT4, démarrage serveur, validation, test d'intégration, diagnostic).
- Décision de portée : aucune logique d'exécution d'ordre, aucune calibration automatique des seuils (`core/v9/config.py` reste la source de vérité, ajustable manuellement après observation du test live).
- Point ouvert (non bloquant) : les `.ex4` compilés existants (`ea/*.ex4`) datent d'avant l'ajout de l'input `ServerPort` — recompilation requise avant tout déploiement réel.

## Livrables Phase 5 (session `feat/v9-phase5-fenetres`, couche Fenêtres)
- `core/v9/window_gate.py` — `WindowGate` : statut (6 valeurs de l'enum FORMAT_FENETRES.md), type_fenetre, niveau_confiance (bonus/malus), détection de fragilité, conditions d'invalidation, cycle de vie (ouverture → fragile → invalidee), écriture DB + mémoire.
- `core/v9/window_db.py` — table `windows` (16 colonnes, 3 index), `init_window_db()`.
- `core/v9/config.py` — constantes ajoutées : `CONFIANCE_MIN_FENETRE`, `FRAGILITE_CONFIANDE_DELTA`, `WINDOW_LIFECYCLE_LOOKBACK`, `BONUS_CONFLUENCE_MTF`, `BONUS_SIMILARITE`, `MALUS_STALE`, `MALUS_FRAGILITE`, `SIMILARITE_BONUS_THRESHOLD`.
- `tests/fixtures/behaviors_sample.json` — 6 comportements consécutifs (EURUSD/M5).
- `tests/test_window_gate.py` — 20 tests, tous verts.
- À la fusion (2026-07-05) : `window_gate.py._load_behavior` / `_load_behavior_history` migrés du shim provisoire vers `core/v9/behavior_db.py` (table `behaviors` réelle). Voir section « Revalidation post-fusion » ci-dessous.

## Résumé exécutif
PowerFlow V9 est lancé comme une refondation propre depuis un dossier vide.
Le projet vise à éliminer la dette de structure, la confusion documentaire et les biais hérités de V8/Hermes.
La doctrine de départ impose une architecture centrée sur la lecture des forces avant toute couche d'exploitabilité.
La Phase 1 (squelette cognitif) a produit les formats JSON des 5 couches (Forces, Scènes, Comportements, Fenêtres, Exploitabilité) ainsi que le contrat de mémoire associé. Les 3 corrections identifiées en revue CEO ont été appliquées et fusionnées.
La Phase 2A a reconstruit la sonde EA MT4 (couche Forces, capture brute) from scratch, en auditant les bugs connus de V8 pour ne pas les reproduire.
La Phase 2B (implémentation Python de la couche Forces) a produit le serveur de capture TCP asyncio, le STALE_GATE bloquant, le lecteur de transformation (ForcesReader) et le schéma DB v9_forces.db, avec 15 tests unitaires. Écrit from scratch, sans reprise de code V8.
La Phase 3 (couche Scènes, from scratch — V8 n'en avait pas) a produit `SceneBuilder` : détection de coalitions/antagonismes, cinématique locale (angle, courbure, pente, pliure, rotation, compression/extension), confluences multi-timeframes, contexte temporel (session/fenêtre), écriture DB (`scenes`) et mémoire (`memory_temp.md`, cycle hypothèse). Consomme uniquement `forces_snapshots`, ne duplique jamais les forces (référence `forces_snapshot_ref`).
La Phase 4 (couche Comportements) a produit `BehaviorAnalyzer` : qualification de la dynamique d'une scène dans le temps (12 qualifications de l'enum FORMAT_COMPORTEMENTS.md), détection de transitions (comportement précédent, point de rupture, sens de transition), comparaison aux cas connus (similarité, variante), écriture DB (`behaviors`) et mémoire (cycle hypothèse). Consomme uniquement la table `scenes` — la seule exception est une déréférence administrative étroite de `forces_snapshot_ref` vers `symbol`/`timeframe` (jamais les valeurs de force), nécessaire car FORMAT_COMPORTEMENTS.md exige ces champs au niveau racine alors qu'une scène reste multi-devises/multi-timeframes par conception.

## Livrables Phase 6 (branche `feat/v9-phase6-exploitabilite`)
- core/v9/exploitability_evaluator.py — `ExploitabilityEvaluator` : evaluate_window, détermination du statut (5 valeurs : non_exploitable, watchlist, exploitable, refuse, ambigu), raison de refus (5 valeurs, cascade priorisée), calcul de confiance globale (bonus/malus documentés), validation HITL (première validation pour tout exploitable, premier cas de type de fenêtre, ratio replay incertain), construction du replay_context (comparaison aux comportements passés de même qualification, issues WIN/LOSS/UNKNOWN depuis un fichier optionnel `data/replay_outcomes.json`), écriture DB + mémoire
- core/v9/exploitability_db.py — schéma SQLite table `exploitability` (référence window_id, jamais de duplication de la fenêtre)
- core/v9/config.py — 10 constantes ajoutées : SEUIL_EXPLOITABLE, SEUIL_WATCHLIST, REPLAY_MIN_CAS, REPLAY_MIN_WIN_RATE, BONUS_CONFIANCE_COMPORTEMENT, BONUS_CONFLUENCE_MTF_EXPLOIT, BONUS_SIMILARITE_EXPLOIT, MALUS_STALE_EXPLOIT, MALUS_FRAGILITE_EXPLOIT, MALUS_REPLAY_INSUFFISANT, plus REPLAY_OUTCOMES_PATH
- tests/test_exploitability_evaluator.py, tests/fixtures/windows_sample.json — 26 tests, tous verts (5 statuts, 5 raisons de refus, HITL sous ses 4 cas, bonus/malus de confiance globale isolés, replay vide, format JSON conforme, écriture DB/mémoire)
- À la fusion (2026-07-05) : table `windows` shim (`WINDOWS_SHIM_SCHEMA_SQL`, `_ensure_windows_table`) retirée au profit de `core/v9/window_db.py` (`init_window_db`, `WINDOWS_COLUMNS`) — schéma strictement identique, aucun champ à adapter. Voir section « Revalidation post-fusion Phase 6 » ci-dessous. Déréférence administrative étroite vers `behaviors` (symbol/timeframe, intensité/phase pour la similarité replay) et `scenes` (confluence MTF) inchangée — jamais de réinterprétation des valeurs de force ou de la scène elle-même
- Voir docs/checkpoints/CHECKPOINT_20260705_V9_PHASE6.md et docs/checkpoints/CHECKPOINT_20260705_V9_CHAIN_COMPLETE.md pour le détail complet (décisions de design, écarts assumés, points ouverts)

## Revalidation post-fusion Phase 6
`exploitability_evaluator.py` a été implémenté sur une table `windows` shim
(reflet plat, 16 colonnes) le temps que la Phase 5 soit fusionnée. À la
fusion des trois branches (2026-07-05), comparaison ligne à ligne du shim
avec le schéma réel de `core/v9/window_db.py` : **schéma identique**, aucune
divergence de colonne. Adaptations apportées :
- Suppression de `WINDOWS_SHIM_SCHEMA_SQL` et de `_ensure_windows_table` ;
  `ExploitabilityEvaluator.__init__` appelle désormais `window_db.init_window_db()`.
- `insert_window()` (module-level et méthode) réécrit pour insérer via
  `WINDOWS_COLUMNS` (`window_db.py`), toujours utilisable comme helper de
  fixtures/tests (les fenêtres réelles proviennent de `WindowGate`).
- `_load_window` (déjà un `SELECT *`) et `WindowRecord.from_row` : aucun
  changement requis, tous les champs lus (`statut`, `niveau_confiance`,
  `behavior_id`, `stale`, `fragilite_detectee`/`fragilite_raison`) existent
  à l'identique dans la table réelle.
- `tests/test_exploitability_evaluator.py` : 26 tests, aucune régression
  après bascule sur `window_db.py`.
- **Aucun point ouvert résiduel** pour cette revalidation (contrairement au
  `rejet_repulsion_detecte` retiré lors de la fusion Phase 4+5) : le shim
  Phase 6 avait été construit en copiant strictement le schéma de la
  branche Phase 5 avant sa fusion, sans dérive.

## Livrables Phase 4 (branche `feat/v9-phase4-comportements`)
- core/v9/behavior_analyzer.py — `BehaviorAnalyzer` : analyze_scene, qualification (12 heuristiques), intensité, phase, confiance, transitions (comportement précédent, point de rupture, sens), comparaison cas connus (similarité, singularités, variante), écriture DB + mémoire
- core/v9/behavior_db.py — schéma SQLite table `behaviors` (référence scene_id_ref, jamais de duplication de la scène)
- core/v9/config.py — 4 constantes ajoutées : BEHAVIOR_HISTORY_LOOKBACK, SIMILARITY_THRESHOLD, CONFIANCE_PLIURE_SEVERE, CONFIANCE_BASCULE_NETTE
- tests/test_behavior_analyzer.py, tests/fixtures/scenes_sample.json — 21 tests, tous verts (12 qualifications couvertes, intensité, phase, transitions, sens_transition, comparaison cas connus, confiance basse valide, format JSON, écriture DB/mémoire, scénario complet 6 scènes)
- Voir docs/checkpoints/CHECKPOINT_20260705_V9_PHASE4.md pour le détail complet (décisions de design, écarts assumés, points ouverts)

## Livrables Phase 3 (fusionnés depuis `feat/v9-phase3-scenes`)
- core/v9/scene_builder.py — `SceneBuilder` : build_scene, détection coalitions/antagonismes, cinématique locale, confluences MTF, contexte temporel, zone, écriture DB + mémoire
- core/v9/scene_db.py — schéma SQLite table `scenes` (référence forces_snapshot_ref, jamais de duplication)
- core/v9/config.py — 4 constantes ajoutées : COALITION_THRESHOLD, ANTAGONISM_THRESHOLD, PLIURE_THRESHOLD, MTF_LOOKBACK
- tests/test_scene_builder.py, tests/fixtures/forces_snapshots_sample.json — 13 tests, tous verts
- Voir docs/checkpoints/CHECKPOINT_20260705_V9_PHASE3.md pour le détail complet (décisions de design : direction par devise propre à la couche Scènes, cinématique par pas de snapshot, confluences entre TF adjacents, zone dérivée des OHLC)

## Livrables Phase 2B (session `feat/v9-phase2-python-capture`)
- core/v9/config.py — configuration centrale (DB_PATH, ports, seuils STALE_GATE, calibration ForcesReader)
- core/v9/stale_gate.py — StaleGate bloquant (marque stale, ne supprime jamais)
- core/v9/forces_reader.py — transformation JSON brut EA → format V9 (direction, vitesse, croisement, recroisement, rejet_repulsion, compression_extension)
- core/v9/capture_server.py — serveur TCP asyncio port 31685 (--status, --once)
- core/v9/db_schema.py — schéma SQLite forces_snapshots (WAL, busy_timeout 30s)
- tests/test_stale_gate.py, tests/test_forces_reader.py — 15 tests, tous verts
- Voir docs/checkpoints/CHECKPOINT_20260705_V9_PHASE2B.md pour le détail complet (décisions de design, écarts assumés, points ouverts)

## Livrables Phase 1A (session parallèle A)
- docs/architecture/formats/FORMAT_FORCES.md — format de sortie de la couche Forces (8 devises, 7 timeframes dont M1 séparé, STALE_GATE)
- docs/architecture/formats/FORMAT_SCENES.md — format de sortie de la couche Scènes (zone, coalitions, antagonismes, cinématique locale, confluences MTF)
- docs/architecture/formats/MEMORY_CONTRACT.md — contrat de mémoire Forces ↔ Scènes (cycle hypothèse → validation/rejet)

## Livrables Phase 1B (session parallèle B)
- docs/architecture/formats/FORMAT_COMPORTEMENTS.md
- docs/architecture/formats/FORMAT_FENETRES.md
- docs/architecture/formats/FORMAT_EXPLOITABILITE.md

## Livrables Phase 2A — EA MT4 (branche `feat/v9-phase2-ea-mt4`)
- ea/V9_Sonde_TF.mq4 — sonde candle-close multi-timeframe (1 instance par TF M5/M15/M30/H1/H4/D1), JSON aligné FORMAT_FORCES.md
- ea/V9_Sonde_M1.mq4 — sonde M1 dédiée, mode tick/vélocité (OnTick, pas de timer), fenêtre glissante 5s, vitesse par devise
- ea/V9_Sonde_README.md — procédure de compilation, déploiement, vérification, diagnostic buffers SDI
- Audit du code V8 (`EA_PowerFlow_V8_Sonde_TF.mq4`, `EA_PowerFlow_V8_UniversalSonde.mq4` + archives de bugs) : aucune inversion confirmée du buffer AUD dans le code EA lui-même (l'ordre 0=AUD,1=GBP,2=JPY,3=USD,4=CAD,5=EUR,6=CHF,7=NZD est une propriété vérifiée de l'indicateur SDI, pas un bug de lecture) — les inversions documentées en V8 concernaient soit une période de données corrompue (EA legacy hardcodant PERIOD_M1 pour tous les TF), soit une interprétation comportementale en aval. Buffers rendus configurables via inputs par sécurité.
- Bugs V8 corrigés par construction en V9 : décalage horaire broker→UTC non appliqué (nouvel input `BrokerUTCOffsetHours`), EA HTF lisant PERIOD_M1 hardcodé (V9 utilise systématiquement `Period()` réel), ShiftIndex mal aligné (M1 et candle-close strictement séparés dans deux fichiers distincts).

## Décisions actées
- V9 part dans un dossier vide.
- GitHub est la source de vérité.
- V8 devient une source de migration curée, pas une base de travail directe.
- La mémoire V9 sera reconstruite proprement.
- Le squelette cognitif officiel est :
  Forces → Scènes → Comportements → Fenêtres → Exploitabilité → Exécution éventuelle.
- Les documents pivots doivent être créés avant tout chantier de code.
- Les formats JSON des couches Comportements, Fenêtres et Exploitabilité sont spécifiés (session parallèle B, branche `feat/v9-phase1-formats-aval`) : `docs/architecture/formats/FORMAT_COMPORTEMENTS.md`, `FORMAT_FENETRES.md`, `FORMAT_EXPLOITABILITE.md`. Chaque format référence explicitement sa couche amont ; aucune logique d'exécution d'ordre n'y figure.
- La revue CEO des 6 formats a validé le fond mais a identifié 3 corrections (scene_source de Comportements, schema_version manquant sur les 3 formats amont, contrat mémoire non étendu aux couches aval). Ces 3 corrections ont été appliquées sur la branche `fix/v9-phase1-review`, puis fusionnées dans `feat/v9-foundation-clean` (branche de référence de ce dépôt).
- Phase 1 est officiellement close : les 6 formats (FORMAT_FORCES, FORMAT_SCENES, MEMORY_CONTRACT, FORMAT_COMPORTEMENTS, FORMAT_FENETRES, FORMAT_EXPLOITABILITE) sont sur la branche de référence, corrigés et validés.
- Phase 2 close par fusion des branches `feat/v9-phase2-ea-mt4` et `feat/v9-phase2-python-capture` sur `feat/v9-foundation-clean`. 3 points ouverts tranchés à cette occasion : (1) seuils STALE_GATE — `config.py` fait foi, `FORMAT_FORCES.md` mis à jour en conséquence (M5=35s, M15=95s, M30=185s, H1=365s, H4=1450s/24min, D1=9000s/2h30) ; (2) port TCP 31685 conservé comme port de référence V9, avec note explicite dans `config.py` sur le conflit avec V8 en production (basculer sur 31690 pour tester en parallèle) ; (3) `V9_Sonde_M1.mq4` étant désormais livré, les hypothèses de forme du message M1 dans `forces_reader.py` (mode tick_velocity, mêmes clés `force_*`) restent à revalider empiriquement dès la première capture réelle, mais ne bloquent plus la clôture de Phase 2.

## Objectif immédiat
La chaîne cognitive V9 est complète (6/6 couches), l'outillage de déploiement live est prêt (Phase 7) et l'outillage de monitoring/calibration/replay est prêt (Phase 8). Chantier immédiat : déploiement réel à l'ouverture du marché (dimanche 23h Paris / 22h UTC) — compilation + déploiement des EA (`ServerPort=31690`), démarrage du serveur de capture, validation de la sonde, test d'intégration live (`scripts/live_integration_test.py`) avec `scripts/v9_dashboard.py` en observation, puis calibration des seuils heuristiques internes sur données réelles via `scripts/v9_calibration.py --analyze`. La déréférence symbol/timeframe via `forces_snapshots` (conservée telle quelle) et l'alimentation réelle de `data/replay_outcomes.json` (actuellement un fichier optionnel vide en l'absence de couche Exécution) restent des points ouverts, non bloquants.

## Chantiers en file
1. Déploiement live à l'ouverture du marché : compilation EA (`ServerPort` nouveau), démarrage serveur, validation sonde, test d'intégration live avec `scripts/v9_dashboard.py`
2. Calibration des seuils sur données réelles (toutes couches), à partir de `scripts/v9_calibration.py --analyze` sur les observations du test d'intégration live
3. Décision de périmètre pour la couche Exécution éventuelle (dernière étape de la chaîne, hors doctrine cognitive stricte)
4. AGENT.md racine V9
5. Inventaire de migration V8 → V9
6. Structure skills / agents / assets / runtime

## Contraintes connues
- Limite de contexte / messages côté assistant
- Besoin de checkpoints persistants
- Volonté d'éviter toute confusion de version
- Préférence forte pour architecture avant code
- Détestation de la gestion manuelle Git par l'utilisateur

## Rôles opérationnels
- Perplexity : doctrine, orchestration, structure, checkpoints, continuité
- Claude Code : implémentation structurée
- Hermes free : support ciblé / itérations légères / expérimentations encadrées

## Règle d'or
Aucune implémentation structurante ne doit être lancée sans ancrage explicite dans la doctrine V9.

## Prochaine étape recommandée
CHAÎNE COGNITIVE V9 COMPLÈTE (6/6 couches), OUTILLAGE DE DÉPLOIEMENT PRÊT (Phase 7) ET OUTILLAGE DE MONITORING/CALIBRATION/REPLAY PRÊT (Phase 8, branche `feat/v9-phase8-monitoring`). 139 tests au total, tous verts. Prochaine étape : test live avec données replay + calibration — suivre `docs/deployment/V9_DEPLOYMENT_GUIDE.md` (compilation EA avec `ServerPort`, démarrage `scripts/deploy_v9.py --start`, validation `scripts/validate_ea_output.py`, test `scripts/live_integration_test.py` sur données replay avec `scripts/v9_dashboard.py` en observation), puis calibration des seuils heuristiques via `scripts/v9_calibration.py --analyze` sur ces observations.
