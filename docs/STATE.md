# STATE — PowerFlow V9

## Dernière mise à jour
2026-07-05

## Statut
PHASE 4 + PHASE 5 TERMINÉES ET FUSIONNÉES — Couche Comportements (`BehaviorAnalyzer`, table `behaviors`, 21 tests) et couche Fenêtres (`WindowGate`, table `windows`, 20 tests) fusionnées sur `feat/v9-foundation-clean`. Phase 3 (Scènes), Phase 2 (EA MT4 + capture Python) et Phase 1 (6 formats) terminées et fusionnées précédemment. Point ouvert Phase 5 résolu à la fusion : `window_gate.py` lit désormais `behavior_db.py` (table `behaviors` réelle) au lieu du shim provisoire.
Prochaine étape : Phase 6 — Exploitabilité.
Voir docs/checkpoints/CHECKPOINT_20260705_V9_PHASE4_5_COMPLETE.md pour le détail complet de la fusion et de la revalidation des points ouverts.

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
Engager la Phase 6 — Couche Exploitabilité, qui consomme les fenêtres qualifiées selon MEMORY_CONTRACT.md. Le branchement temps réel de BehaviorAnalyzer/WindowGate en aval de SceneBuilder, la calibration des seuils heuristiques internes (LUTTE_FORCES_INTENSITE_MIN, PLIURE_SEVERE_MIN, WEAK_EXTENSION_MAX) sur données réelles, et la déréférence symbol/timeframe via `forces_snapshots` (conservée telle quelle — cf. Revalidation post-fusion) restent des chantiers ouverts, non bloquants.

## Chantiers en file
1. Phase 6 — Couche Exploitabilité (consommant FORMAT_FENETRES.md)
2. Branchement temps réel de SceneBuilder → BehaviorAnalyzer → WindowGate en aval de capture_server.py
3. Validation terrain de la sonde EA (ea/V9_Sonde_TF.mq4) avec capture_server.py + calibration des seuils Scènes/Comportements/Fenêtres sur données réelles
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
Phase 6 — Couche Exploitabilité. Le branchement temps réel des couches Scènes/Comportements/Fenêtres et la validation terrain de la sonde EA peuvent être menés en parallèle, sans bloquer le démarrage de la Phase 6.
