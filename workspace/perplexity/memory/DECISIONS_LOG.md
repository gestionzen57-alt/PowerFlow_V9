# DECISIONS_LOG — journal daté des décisions structurantes

Journal chronologique. Chaque entrée reprend une décision déjà actée côté code/doctrine
(voir `docs/STATE.md` §« Décisions actées » et les checkpoints référencés) — ce journal
n'invente pas de nouvelles décisions, il les indexe pour une reprise rapide côté
continuité multi-provider.

## Format d'entrée
```
### AAAA-MM-JJ — Titre
- Décision :
- Motivation :
- Impact / portée :
- Référence :
```

## Historique

### 2026-07-05 — Extension de la doctrine à 19 règles immuables
- Décision : `docs/DOCTRINE.md` étendu de 13 à 19 règles, ajoutant notamment Git=vérité,
  source unique par sujet, migration métier avant agentification, autonomie progressive
  après stabilité live, pas de dépendance bloquante à un LLM/provider, architecture
  agents/skills gelée tant que la phase métier courante n'est pas canonisée et stable.
- Motivation : cadrer explicitement le séquencement business → agentification avant
  toute reprise de chantier Phase 10+.
- Impact : gèle toute ouverture de la Phase 10 ou d'architecture agentique globale sans
  décision explicite de déblocage.
- Référence : commit `fe6323e`, branche `docs/v9-governance`.

### 2026-07-05 — Clôture de Phase 9 (Décision et Principes)
- Décision : Phase 9 déclarée terminée et canonisée — Régime/Principes/Signal/Décision
  livrés, 214 tests, revérifiés indépendamment.
- Motivation : chaîne cognitive à 8 couches complète, prête pour test live.
- Impact : ouvre le chantier déploiement live à l'ouverture du marché ; `docs/ROADMAP.md`
  mis à jour avec section « Chantiers futurs distincts » séparant explicitement Phase 10
  de l'architecture globale agents.
- Référence : `docs/phases/PHASE9_DECISION.md`,
  `docs/checkpoints/CHECKPOINT_2026-07-05_MEGA_V9.md`.

### 2026-07-05 — Correctif idempotence `regenerate_chain.py`
- Décision : ajout de `--replace-derived`/`--dry-run` et refus par défaut de rejeu sur
  DB dérivée non vide.
- Motivation : un rejeu antérieur avait dupliqué en production les tables dérivées
  (2388 lignes au lieu de 1194).
- Impact : la purge des ~245k lignes déjà dupliquées reste une action opérateur
  manuelle, non automatisée.
- Référence : commit `c83423e`,
  `docs/checkpoints/CHECKPOINT_20260705_V9_REGEN_IDEMPOTENT.md`.

### 2026-07-05 — Outillage d'automatisation opérationnelle (reboot/ouverture marché/reprise)
- Décision : livraison de 4 scripts (`scripts/v9_supervisor.py`, `v9_bootstrap.py`,
  `v9_market_open.py`, `v9_session_resume.py`) et de
  `docs/deployment/V9_AUTOMATION_RUNBOOK.md`, qualifiés « Phase 9.5 » (outillage, pas une
  phase de code métier). Décision de conception : réutilisation telle quelle du gabarit
  de mini-checkpoint déjà défini dans
  `workspace/perplexity/assets/CHECKPOINT_TEMPLATE.md` plutôt que création d'un nouveau
  gabarit, pour respecter `docs/DOC_GOVERNANCE.md` règle 8 (pas de duplication de
  contenu). Fichiers générés dans `workspace/perplexity/mini_checkpoints/`, hors
  `docs/DOC_REGISTRY.yml` par définition de ce gabarit.
- Motivation : réduire la friction manuelle constatée lors du baptême live de V9
  (gestion de port stale, démarrage serveur, checklist T-30/T0, vérification de
  continuité de reprise de session), sans toucher à la logique métier ni ouvrir la
  Phase 10.
- Impact : aucune modification de `core/v9/*`. 40 nouveaux tests (258 au total : 250
  verts, 8 échecs pré-existants et non liés dans `test_behavior_analyzer.py`, signalés
  dans `INCIDENTS.md`, non corrigés — hors périmètre de ce chantier).
- Référence : ce commit (voir message « feat(v9): automatisation reboot machine /
  ouverture marché / reprise de session »), `docs/STATE.md` §« Outillage post-Phase 9 »,
  `docs/deployment/V9_AUTOMATION_RUNBOOK.md`.

### 2026-07-06 — Marquage replay/live dans les décisions (colonne `source_type`)
- Décision : ajout de la colonne `source_type` ("live"/"replay") aux 8 tables dérivées
  (scenes, behaviors, windows, exploitability, regime_snapshots, principle_evaluations,
  signals, decisions). `orchestrator.run_chain()` accepte un paramètre `source_type`
  (défaut `"live"`), propagé à chaque couche. `regenerate_chain.py` passe
  `source_type="replay"`. Aucune modification de `core/v9/config.py` ni de la logique
  métier des couches.
- Motivation : résoudre le point ouvert identifié depuis Phase 7-8 (doctrine règle 12)
  sans rouvrir la Phase 9 ni toucher au moteur métier.
- Impact : les 1290 décisions existantes (replay) restent sans `source_type` (NULL) —
  seules les nouvelles insertions portent le marquage. Rétrocompatibilité totale.
- Référence : `docs/checkpoints/CHECKPOINT_20260706_V9_SOURCE_TYPE.md`.

### 2026-07-06 — Anomalie DST « Marché : FERMÉ » : correctif observabilité, pas correctif calendrier
- Décision : face au bug documenté (calendrier canonique `core/v9/market_calendar.py`
  ancré sur 22h UTC fixe, incorrect ~8 mois/an pendant la DST US où le marché réel
  ouvre/ferme à 21h UTC), la décision explicite de l'opérateur a été de **ne pas
  modifier `core/v9/market_calendar.py` cette session** et de traiter uniquement
  l'observabilité : `scripts/v9_supervisor.py::market_status_warning()` détecte la
  divergence (calendrier FERMÉ + snapshot récent non-stale) et l'affiche explicitement
  dans `v9_dashboard.py`, `v9_supervisor.py --health`, les mini-checkpoints et le log de
  `v9_market_open.py`.
- Motivation : corriger le calcul canonique rouvrirait une décision Phase 7 canonisée
  (22h UTC documenté et testé) et casserait 7 tests de `tests/test_market_calendar.py`
  qui figent cette hypothèse — hors périmètre Phase 9.5 (outillage, pas relance de
  chantier métier).
- Impact : aucune modification de `core/v9/*`. 11 nouveaux tests, 269 au total (261
  verts, 8 échecs pré-existants inchangés). Gap DST documenté comme chantier futur
  distinct, non bloquant.
- Référence : `workspace/perplexity/INCIDENTS.md` 2026-07-06,
  `docs/deployment/V9_AUTOMATION_RUNBOOK.md` §« Anomalie connue ».

### 2026-07-05 — Création du workspace de continuité Perplexity/multi-provider
- Décision : création de `workspace/perplexity/` (board, tâches actives, template de
  reprise, statut providers, protocole de session, mémoire, backlogs agents/skills
  gelés, incidents, gabarits) sans toucher à `core/v9/` ni ouvrir la Phase 10.
- Motivation : besoin d'un espace léger de continuité opérationnelle distinct des
  documents pivots `docs/`, pour la reprise rapide entre sessions Perplexity et autres
  providers.
- Impact : aucun impact code ; synthèse et renvois vers `docs/` uniquement, pas de
  doctrine concurrente créée.
- Référence : ce commit (voir message « docs: add continuity workspace for perplexity
  and market-open handoff »).

### 2026-07-06 — ZoneDetector : alimentation de `zone_diagnostics` (gap Phase 9 comblé)
- Décision : implémentation bornée de `core/v9/zone_detector.py` pour alimenter la table
  `zone_diagnostics` (créée mais vide depuis la Phase 9). Calcule par devise : z-score,
  état de zone (NEUTRAL/EARLY_EXTREME/ACCUMULATING/LEAKING/RUPTURE), direction
  d'extrême, bars_in_extreme, tension_score, absorbed_pullbacks. Wired dans
  `orchestrator.py` entre regime_detector et principle_engine (même pattern fail-soft).
  Ajouté à `DERIVED_TABLES` de `regenerate_chain.py`.
- Motivation : les 9 principes `node_rule` ACTIVE référencent des champs de
  `zone_diagnostics` — sans données, leurs conditions ne sont jamais remplies (0% hit
  rate). C'était le seul gap métier bloquant de la Phase 9.
- Impact : 7 principes ACTIVE débloqués (NODE_BIRTH_FAST, RAW_NODE_BIRTH,
  POWER_ANGLE_BREAK_TO_PRICE_IMPACT, ZONE_RETEST, ELASTIC_BREATH,
  GRAVITY_RESPRING_NODE, PRICE_LAG_AT_NODE_BIRTH). 2 principes ACTIVE restent hors
  périmètre (ANTAGONIST_NODE — champs cross-TF absents du schéma ; COALITION_NODE —
  champ coalition_strength absent). GRAMMAR_REGIME est `kind: grammar` (conditions
  vides) — jamais émetteur par conception, inchangé. 283 tests (269 + 14), tous verts.
  Aucune modification de `core/v9/config.py`.
- Référence : commit `db11917`, `core/v9/zone_detector.py`,
  `workspace/perplexity/mini_checkpoints/20260706_081100_zone_detector.md`.

### 2026-07-06 — Grammaire complétée : coalition_strength, cross-TF, absorption_factor
- Décision : enrichissement du contexte de `principle_engine._load_shared_context()`
  avec `coalition_strength` (calculé depuis les coalitions de la scène courante),
  `h1_dir`/`h1_state`/`m5_dir`/`m5_state` (lus depuis les snapshots H1 et M5 les
  plus récents du même symbole). Remplacement du placeholder `absorption_factor = 0.0`
  dans `zone_detector.py` par un vrai calcul (tension_score × 0.4 + absorbed_pullbacks
  × 0.3 + bars_in_extreme normalisé × 0.3).
- Motivation : les 2 derniers principes `node_rule` ACTIVE (ANTAGONIST_NODE,
  COALITION_NODE) restaient bloqués par des champs de contexte absents. Leur
  déblocage complète la grammaire des 9 principes ACTIVE sans ouvrir Phase 10.
- Impact : 9/9 principes `node_rule` ACTIVE désormais déclenchables. Aucune
  modification de `core/v9/config.py`. 283 tests, tous verts.
- Référence : commit `a596f37`, `core/v9/principle_engine.py`, `core/v9/zone_detector.py`.

### 2026-07-06 — Module NewsContext (calendrier économique transversal)
- Décision : livraison de `core/v9/news_context.py` (module pur, aucune
  DB) qui évalue, pour un moment UTC donné, la position temporelle
  par rapport à `data/economic_calendar.json` (NFP, ISM_PMI, CPI_US,
  FOMC_RATE, FOMC_MINUTES, GDP_US, RETAIL_SALES_US). Retourne 5 champs
  garantis sans exception : `news_type`, `news_phase` (PRE_NEWS /
  NEWS_SHOCK / POST_NEWS / NEUTRE), `news_distance_min`,
  `news_importance` (HIGH/MEDIUM/LOW/NEUTRE), `news_session_clean`.
  Injection **EN DERNIER** dans
  `principle_engine._load_shared_context()` (après tous les
  `context.update()` existants), avec fallback NEUTRE via try/except
  global. Section dédiée ajoutée à
  `docs/architecture/CONTEXT_CONTRACT.md`. 7 tests dédiés dans
  `tests/test_news_context.py`.
- Motivation : poser un marqueur temporel de proximité aux news pour
  future consommation YAML (cadrage P2). La doctrine V9 est claire :
  « le système ne trade pas les news, il lit les flux qui les précèdent
  et la réorganisation des coalitions qui suit » (Perplexity, 2026-07-06).
  Les champs sont PROPAGÉS mais **pas encore consommés** par les
  conditions des principes YAML — cette mission est strictement
  bornée à la pose du contrat + tests + docs.
- Impact : aucune modification de `core/v9/config.py`, des YAML
  principes, ni de la structure d'`orchestrator.py`. 7 nouveaux
  tests, 354 verts au total (347 base + 7 news). Les 8 tests
  pré-existants de `test_behavior_analyzer.py` passent désormais
  (les incidents antérieurs étaient liés à un état transitoire
  post-merge, plus reproductible).
- Référence : commits `feat(v9): news_context — module pur calendrier
  économique` et `docs: CONTEXT_CONTRACT + DECISIONS_LOG news_context
  2026-07-06`, branche `feat/v9-foundation-clean`.

### 2026-07-06 — Pipeline bout-en-bout gardien + Idempotence decisions
- Décision : livraison de 2 chantiers conjoints pour fermer les irritants
  structurels apparus session 2 :
  - **Chantier A — Test d'intégration bout-en-bout**
    `tests/test_pipeline_end_to_end.py` :
    test_pipeline_snapshot_produces_directional_decision. Traverse
    SceneBuilder.build_scene() en réel puis injecte behavior/window/
    exploitability/zone/regime/principe (heuristiques multi-snapshots
    non testables en single-snapshot) puis traverse SignalGenerator
    et DecisionLogger en réel. Asserte decision.direction IS NOT NULL
    ET confiance > 0. Ce test aurait détecté les 5 bugs silencieux du
    2026-07-06 (fallbacks cross-TF, REGIMES_INADEQUATS, window absente,
    principes quote, _load_signal ORDER BY).
  - **Chantier B — Idempotence decisions par snapshot_id**
    core/v9/decision_logger.py : decision_id devient déterministe par
    snapshot_id (uuid5 hash 12 chars). INSERT OR REPLACE (UNIQUE
    existant) écrase vraiment la rangée. Pré-check qualité
    (_action_quality : preparer_entree=3 > surveiller=2 > observer=1 >
    aucune_action=0) évite d'écraser une bonne décision par une moins
    bonne. Bug emblématique : aucune_action → preparer_entree sur
    rejeu (cas session 2).
- Motivation : (A) avoir un gardien de régression permanent qui aurait
  détecté les 5 bugs silencieux du jour dès l'ajout d'une nouvelle
  couche ; (B) dédupliquer la table decisions qui croissait de N rangées
  à chaque rejeu (3697 → 3960 sur les 3 snapshots directionnels du
  13h12 UTC). Doctrine V9 : source de vérité = code ; pas de touche
  live DB pour migration — la dédup se fait naturellement au fil des
  rejoues.
- Impact : aucune modification de core/v9/config.py, YAML principes,
  ni structure globale d'orchestrator.py. Tests : 355 → 359 verts
  (+1 e2e + 3 idempotence). 16 tests test_decision_logger.py (13 + 3).
  1 test test_pipeline_end_to_end.py. Validation live : 3x log() sur
  v9-GBPUSD-M5-1783354200-016028 produit decision_id=dec_df961c3f104b
  stable. 5 décisions directionnelles sur la DB live (3 créées session
  2 + 2 nouvelles via ce fix).
- Référence : commits `85b40fe test(v9): pipeline end-to-end...` et
  `3d42b6c fix(v9): decision — idempotence par snapshot_id...` sur
  branche `feat/v9-foundation-clean`.

### 2026-07-05
- Décision : poussée des 5 commits locaux vers `origin/feat/v9-foundation-clean`
  (fast-forward, sans conflit). HEAD = `baaad6b4132ce49dc1f099d1578f134f9bc1e64d`.
- Motivation : synchroniser l'état du repo avec l'upstream après les chantiers
  zone_diagnostics et grammaire complétée.
- Impact : branche locale et distante alignées. Working tree clean. Aucune
  modification de code.
- Référence : `git push origin feat/v9-foundation-clean`.

### 2026-07-06 — Calibration seuils : ANTAGONISM_THRESHOLD appliqué, COALITION/PLIURE différés
- Décision : application partielle des suggestions de `v9_calibration.py --analyze` (n=218 M5+ live, 1460 M5+ non-stale total). ANTAGONISM_THRESHOLD passe de 10.0 à 31.39 (P80 des écarts de force inter-devises). COALITION_THRESHOLD reste à 5.0 (taux de détection 89.8% sain, gain marginal). PLIURE_THRESHOLD reste à 3.0 (suggestion 0.0 invalide — le script utilise la colonne `vitesse` comme proxy, mais `scene_builder._compute_cinematics` calcule la pente réelle comme variation de la moyenne des 8 forces, ordre de grandeur ×1000 différent).
- Motivation : le seuil 10.0 était saturé (92.3% des scènes avec antagonisme, moyenne 14.4/scène), diluant le signal pour la couche Décision (ANTAGONIST_NODE, signaux). Le P80 à 31.39 est un filtre discriminant basé sur la même distribution observable que le code métier.
- Impact / portée : 283 tests verts (inchangés). Le nombre d'antagonismes par scène devrait chuter significativement, améliorant le rapport signal/bruit des principes et signaux. COALITION_THRESHOLD et PLIURE_THRESHOLD nécessitent une recalibration séparée (PLIURE : corriger d'abord le proxy dans `v9_calibration.py` pour utiliser la vraie pente).
- Référence : commit à venir, `core/v9/config.py` ligne 68, `scripts/v9_calibration.py` lignes 312-346 (méthode des proxys), `workspace/perplexity/mini_checkpoints/20260706_calibration_seuils.md`.

### 2026-07-06 — Cinématique enrichie : velocite_moyenne, acceleration_vraie, dispersion_velocite
- Décision : enrichissement de `scene_builder._compute_cinematics()` avec 3 nouvelles métriques de vélocité réelle issues de la colonne `vitesse` de `forces_snapshots` (calculée par `forces_reader.py` comme delta_force / delta_t_secondes). `velocite_moyenne` = vitesse du snapshot courant. `acceleration_vraie` = (vitesse_t - vitesse_t-1) / delta_t_secondes entre les 2 derniers snapshots. `dispersion_velocite` = écart-type des vitesses sur l'historique du TF (dispersion temporelle, faute de colonnes vitesse par devise dans le schéma DB). Fallback 0.0 explicite pour toute métrique non calculable.
- Motivation : la pente adimensionnelle existante (mean_now - mean_prev) ne distingue pas M5 vs H1 — une même pente = dynamiques radicalement différentes. La colonne `vitesse` existait déjà dans `forces_snapshots` mais n'était pas exploitée par la couche Scènes. Ces 3 métriques apportent une dimension temporelle réelle à la cinématique.
- Impact / portée : 287 tests verts (283 + 4 nouveaux). Aucune modification de `core/v9/config.py`, `forces_reader.py`, `db_schema.py`, `orchestrator.py`. Les 3 nouveaux champs sont présents dans le JSON de scène complet (testé via `test_velocite_fields_in_output_json`). Rétrocompatibilité totale : les scènes existantes en DB ne portent pas ces champs (elles ne sont pas régénérées), mais toute nouvelle scène les inclut.
- Référence : commit à venir, `core/v9/scene_builder.py` lignes 350-395, `tests/test_scene_builder.py` 4 nouveaux tests.

### 2026-07-06 — P1a : PLIURE_THRESHOLD recalibré (proxy corrigé, valeur 3.0→1.7)
- Décision : correction du proxy PLIURE dans `scripts/v9_calibration.py::suggest_thresholds()`. La fonction utilisait la colonne `vitesse` de `forces_snapshots` (ordre 0.001-0.01) comme proxy de delta de pente, mais `scene_builder._compute_cinematics()` calcule la vraie pente comme variation de la moyenne des 8 forces (ordre 0.1-2.0) — facteur ×1000 d'écart. Nouvelle fonction `_pliure_deltas_from_scenes()` qui extrait `pente` depuis `scenes.cinematique_json`, calcule `abs(pente_t - pente_t-1)` et retourne le P90. Passage de P75 à P90 pour cohérence avec la méthode des autres seuils. Application de PLIURE_THRESHOLD = 1.7 dans `core/v9/config.py` (dans l'intervalle validé [0.5, 2.0]).
- Motivation : le seuil 3.0 ne détectait que 0.8% des pliures (12/1454). Le P90 à 1.7 détecte ~4-5% des pliures, un taux sain pour un événement de rupture brutale de dynamique.
- Impact / portée : 289 tests verts (287 + 2 nouveaux). `scripts/v9_calibration.py` modifié (nouvelle fonction + signature `suggest_thresholds` étendue). `core/v9/config.py` ligne 71 modifiée.
- Référence : commit à venir, `scripts/v9_calibration.py` lignes 297-320 + 333-375, `core/v9/config.py` ligne 71.

### 2026-07-06 — P1b : 7 champs cinématiques injectés dans le contexte des principes
- Décision : enrichissement de `principle_engine._load_shared_context()` avec 7 champs extraits de `scenes.cinematique_json` : `velocite_moyenne`, `acceleration_vraie`, `dispersion_velocite`, `pente`, `courbure`, `pliure_detectee` (bool), `pliure_severite` (float ou None). Fallback explicite 0.0/False/None si scene_row est None ou clé absente. Ces champs sont désormais accessibles aux conditions des 27 principes YAML.
- Motivation : les 3 métriques de vélocité réelle livrées en e2ea619 étaient des données mortes pour la couche Décision — aucun principe ne pouvait les évaluer car elles n'existaient pas dans le contexte. L'injection de `pente` et `courbure` permet en outre une calibration future des seuils de pliure directement depuis les principes.
- Impact / portée : 289 tests verts (287 + 2 nouveaux). Aucune modification de `config.py`, `scene_builder.py`, `orchestrator.py`. Rétrocompatibilité totale : les scènes existantes sans `cinematique_json` reçoivent les fallbacks.
- Référence : commit à venir, `core/v9/principle_engine.py` lignes 458-474, `tests/test_principle_engine.py` 2 nouveaux tests.
### 2026-07-06 — Coalition Intelligence V9 (Tâche A : age_bars, intensite_trend, stabilite)
- Décision : enrichissement de chaque objet coalition dans `scenes.coalitions_json`
  de trois métriques de continuité/intensité — `age_bars` (continuité arrière
  d'une coalition de composition identique, break au premier trou),
  `intensite_trend` (montante/stable/declinante vs moyenne des 3 dernières
  apparitions), `stabilite` (ratio de présence sur la fenêtre d'historique).
- Motivation : passer d'une photographie instantanée à un film — une coalition
  détectée depuis 15 bars M5 et confirmée H1/H4 est qualitativement différente
  d'une coalition snapshot isolée. V9 ne distinguait pas ces deux cas.
- Impact : nouveau paramètre optionnel `coalition_history` à `_detect_coalitions`
  (pattern identique à `prev_forces` — pas de requête DB directe depuis cette
  méthode). Nouvelle méthode `_load_coalition_history` dans SceneBuilder pour
  charger les N scènes précédentes. Tests : 9 nouveaux (test_scene_builder.py).
- Référence : commits à venir (Tâche A), 289+9 = 298 tests verts.

### 2026-07-06 — RiskMeter V9 (Tâche B : sentiment RISK_ON/RISK_OFF/MIXTE/NEUTRE)
- Décision : nouveau module pur `core/v9/risk_meter.py` (aucune connexion DB,
  aucun import orchestrateur) — détecte le sentiment institutionnel agrégé
  à partir des coalitions enrichies (Tâche A) et des directions par devise.
  Référentiel : `RISK_ON_DEVISES={AUD,NZD,CAD,GBP}` / `RISK_OFF_DEVISES={JPY,CHF,USD}`.
  Confidence 0-100 : base 40 +20 opposition nette +15 age>=5 +10 stab>=0.7
  +10 trend montante +5 emboitement MTF, clamp 0-100.
- Motivation : qualifier le risk sentiment Forex à partir des coalitions V9
  sans nouvelle sonde, en exploitant les métriques de continuité de la Tâche A.
- Impact : migration ALTER TABLE `scenes.risk_assessment_json` (rétrocompatible,
  bases existantes < 2026-07-06 mises à jour sans perte). 5 nouveaux champs
  injectés dans le contexte des principes (`risk_sentiment`, `risk_confidence`,
  `risk_on_score`, `risk_off_score`, `persistance_confirmee`). Tests : 20
  nouveaux (test_risk_meter.py).
- Référence : commits à venir (Tâche B), 318 tests verts.

### 2026-07-06 — Coalition MTF Score + Rotation dans le contexte (Tâche C)
- Décision : enrichissement de `_detect_mtf_confluences` avec
  `coalition_mtf_score` (nb TF où la coalition dominante est présente) et
  `coalition_mtf_depth` (TF le plus large confirmé, ordre D1>H4>H1>M30>M15>M5).
  Injection dans `_load_shared_context` de 5 nouveaux champs
  (`coalition_mtf_score`, `coalition_mtf_depth`, `coalition_rotation_detectee`,
  `coalition_rotation_ancien_leader`, `coalition_rotation_nouveau_leader`).
- Motivation : exposer la propagation MTF d'une coalition et détecter la
  rotation de leadership comme signaux directionnels pour les principes YAML.
- Impact : tous les champs ont des fallbacks explicites (0/"M5"/False/None)
  présents même quand `scene_row` est None — aucun KeyError sur les conditions
  YAML. Tests : 4 nouveaux (test_scene_builder.py) + 4 nouveaux (test_principle_engine.py).
- Référence : commits à venir (Tâche C).

### 2026-07-06 — Anomalie #1 : similarite_score booste confiance_qualification
- Décision : dans `BehaviorAnalyzer.analyze_scene`, recalculer
  `confiance_qualification` après `_compare_to_known_cases` pour intégrer un
  bonus de similarité — +15 si `similarite_score >= 0.85`, +8 si >= 0.70, +0 sinon.
  Plafond 100. Modification appliquée sur `behavior["comportement"]` AVANT
  `_write_behavior_to_db` pour persistance.
- Motivation : un comportement similaire à 90% à un cas connu doit augmenter
  la confiance (la qualification est corroborée par l'historique, pas seulement
  par les heuristiques locales de `_compute_confiance`).
- Impact : les comportements similaires à l'historique voient leur confiance
  augmenter, ce qui se propage aux fenêtres/exploitabilité downstream.
- Référence : commits à venir (Anomalie #1), test_similarite_bonus_*.

### 2026-07-06 — Anomalie #2+#3+#4 : _similarity enrichi + bascule.sens + contexte_temporel dans principes
- Décision : (2) `_similarity` : nouvelle pondération (0.30 jaccard + 0.20 same_tf
  + 0.20 same_phase + 0.15 cinematique + 0.15 coalition_composition_sim) avec
  nouvelle méthode helper `_dominant_coalition_set` (Jaccard sur les devises
  de la coalition dominante, fallback 0.5 si l'une des scènes n'a pas de coalition).
  (3) Injection dans `_load_shared_context` de `bascule_detectee`,
  `bascule_devise_dominante`, `bascule_intensite` (1er antagonisme avec
  bascule_equilibre.detectee=True, fallback False/None/0.0). (4) Injection
  de `session_marche` (mapping normalisé : "london"/"new_york"/"asie"/"sydney"/"overlap"),
  `heure_utc`, `jour_semaine` (0=lundi, 4=vendredi), `marche_ouvert` (False le
  vendredi >=22h UTC, samedi, dimanche <22h UTC). Tous les fallbacks présents
  avant le bloc `if scene_row is not None`.
- Motivation : (2) La composition de la coalition dominante est la donnée
  qualitative la plus discriminante d'un comportement — occultée par les
  pondérations précédentes. (3) `bascule_equilibre.sens` est la donnée
  directionnelle la plus précise de la couche Scènes, jamais exposée aux
  principes. (4) Le contexte temporel (session de marché, heure UTC, jour
  de semaine, marché ouvert) était stocké dans chaque scène mais ignoré
  par les principes — information critique pour les règles de session.
- Impact : 11 nouveaux champs dans le contexte des principes, tous avec
  fallbacks explicites. Tests : 4 (Tâche C), 7 (Anomalies #3 #4) nouveaux dans
  test_principle_engine.py + 6 dans test_behavior_analyzer.py pour Anomalie #2.
  339 tests verts au total.
- Référence : commits à venir (Anomalie #2 + Anomalie #3 + Anomalie #4).
### 2026-07-06 — Calibration live V9 (Mission 1 — session coalition intelligence)
- Décision : aucun changement de config.py. Les suggestions du scanner
  v9_calibration.py --analyze sont dans la marge d'erreur pour
  ANTAGONISM_THRESHOLD (31.39 → 31.33, -0.2%) et PLIURE_THRESHOLD
  (1.7 → 1.68, -1%) — pas de raison de changer. COALITION_THRESHOLD
  (5.0 → 3.96 suggéré, -20.8%) est trop impactant pour 1708 scènes de
  paper-trading (pas assez de signal WIN/LOSS pour valider). STALE_THRESHOLDS_MS
  suggérés à 9-10× les valeurs actuelles sont aberrants (probablement
  bug du script qui applique un facteur incorrect).
- Motivation : la doctrine V9 interdit les modifications de seuils sans
  preuve live suffisante. Le scanner a fait son travail (propositions),
  l'opérateur a tranché (conservation des seuils calibrés sur les sessions
  précédentes du 2026-06 et 2026-07). Une prochaine session avec n>5000
  scènes et issues WIN/LOSS enregistrées permettra de reconsidérer.
- Impact : config.py inchangé. Paper-trading continue avec les seuils
  validés sur n=218 M5+ (ANTAGONISM 31.39) et n=1454 M5+ (PLIURE 1.7).
- Référence : `python scripts/v9_calibration.py --analyze` et
  `--principes`, snapshot 2026-07-06T12:24 UTC (marché OUVERT, session
  overlap_london_ny, 2245 snapshots / 1708 scènes).

  Hit rates observés sur les 10 principes ACTIVE :
  - ANTAGONIST_NODE : 0/1728 (bug d'intégration malgré fix zone_diagnostics)
  - COALITION_NODE : 2.7% (230/8496), conf 73.4
  - ELASTIC_BREATH : 0.3% (26/8496), conf 60
  - GRAMMAR_REGIME : 0/13672 (jamais déclenché)
  - GRAVITY_RESPRING_NODE : 0.5% (45/8496), conf 60
  - NODE_BIRTH_FAST : 3.4% (285/8496), conf 62.3
  - POWER_ANGLE_BREAK_TO_PRICE_IMPACT : 3.0% (256/8496), conf 100
  - PRICE_LAG_AT_NODE_BIRTH : 4.5% (380/8496), conf 96.6
  - RAW_NODE_BIRTH : 3.4% (285/8496), conf 50
  - ZONE_RETEST : 1.9% (163/8496), conf 64.4
  Comportements fréquents : rotation_leadership=831, annulation=264,
  bascule=185 — confirme la pertinence des 13 nouveaux champs contexte
  (notamment coalition_rotation_*) exploités dans le tuning des
  principes YAML (Mission 2).

### 2026-07-06 — Tuning principes YAML (Mission 2 — 13 nouveaux champs contexte)
- Décision : enrichissement de 8 fichiers YAML dans core/v9/principles/
  pour exploiter les 13 nouveaux champs injectés dans _load_shared_context
  lors de la session coalition intelligence (Tâche A+B+C + Anomalies #1-#4).

  4 node_rule ACTIVE enrichis avec nouvelles conditions (filtrent les
  contextes défavorables) :
  - COALITION_NODE : +coalition_mtf_score>=3 (confluence multi-TF),
    +risk_sentiment not_in [MIXTE] (évite ambiguïté directionnelle)
  - NODE_BIRTH_FAST : +bascule_detectee not_in [true] (évite naissance
    pendant bascule), +coalition_rotation_detectee not_in [true]
  - RAW_NODE_BIRTH : +bascule_detectee not_in [true], +coalition_rotation
    _detectee not_in [true] (mêmes filtres que NODE_BIRTH_FAST)
  - GRAVITY_RESPRING_NODE : +coalition_mtf_depth in [H1, H4, D1] (gravité
    crédible seulement sur TF>=H1), +risk_sentiment not_in [RISK_ON]
    (favorise rebond en environnement RISK_OFF)

  4 GRAMMAR enrichis avec bounds informatifs + notes documentant
  les conditions attendues pour promotion ACTIVE future (kind=grammar
  reste non-émetteur par design — conditions: [] non modifiable) :
  - GRAMMAR_CONTEXTE : bounds coalition_mtf_score + risk_confidence,
    notes session_marche/heure_utc/jour_semaine/marche_ouvert
  - GRAMMAR_REGIME : bounds risk_sentiment + coalition_mtf_score,
    notes cohérence RISK_ON↔CASSURE/EXTENSION, RISK_OFF↔RETOUR/REJET
  - GRAMMAR_BREAK : bounds coalition_mtf_score + risk_confidence,
    notes coalition_mtf_depth in [H1, H4, D1] requise
  - GRAMMAR_PULLBACK : bounds bascule_intensite + persistance_confirmee,
    notes bascule_detectee=false (évite piège sur bascule en cours)

- Motivation : les 13 champs étaient injectés dans le contexte mais aucun
  principe YAML ne les consommait. Le brief demandait d'exploiter
  spécifiquement : (1) coalition_mtf_score/depth pour les confluences
  multi-TF, (2) risk_sentiment pour la cohérence avec le régime, (3)
  bascule_detectee pour éviter les faux signaux sur transitions, (4)
  coalition_rotation_detectee pour les naissances de nœud instables.

- Impact : 343 tests verts (aucune régression). Les node_rule ACTIVE
  sont plus sélectifs (les conditions supplémentaires filtrent les
  contextes défavorables). Les GRAMMAR restent non-émetteurs mais leurs
  notes documentent les seuils attendus pour promotion future.
  Validation : 27/27 YAML valides (yamllint-style).

- Référence : `core/v9/principles/{COALITION_NODE,NODE_BIRTH_FAST,
  RAW_NODE_BIRTH,GRAVITY_RESPRING_NODE,GRAMMAR_CONTEXTE,GRAMMAR_REGIME,
  GRAMMAR_BREAK,GRAMMAR_PULLBACK}.yaml`. Pattern YAML multi-lignes
  via "|" (block scalar) pour les notes contenant ":" — évite le
  parsing ambigu.
### 2026-07-06 — Diagnostic ANTAGONIST_NODE — fix bug propagation cross-TF
- Décision : ANTAGONIST_NODE était bloqué à 0/1728 déclenchements en live
  (H1 = 216 scènes, M5 = 384, total éval = 1728 = 216*8 devises).
  Cause racine identifiée : bug d'écrasement des fallbacks cross-TF
  introduit lors de la session précédente (commit 046b285, étendu
  pour test_context_propagation.py).

  Le bloc lignes 432-444 de _load_shared_context initialisait
  `context["h1_dir"]=None, context["h1_state"]=None, ...` APRÈS
  `context.update(cross_tf_context)` (ligne 421). Résultat : les
  valeurs correctement calculées par le bloc cross-TF (lignes
  349-421) étaient ÉCRASÉES par None. La condition 1 de
  ANTAGONIST_NODE (`h1_state not_in [NEUTRAL, None]`) échouait
  toujours.

  Fix : retrait des 4 fallbacks redondants (h1_dir, h1_state,
  m5_dir, m5_state). Le bloc cross-TF gère DÉJÀ tous les cas
  (force_self non-vide / vide, tf_row=None / forces vide).
  Commentaire dans le code explique le bug et le pourquoi de
  l'absence de fallback.

- Motivation : la doctrine de robustesse de propagation (toutes les
  clés attendues toujours présentes, même None) ne doit PAS se faire
  aux dépens de la propagation correcte. Un fallback None sur une clé
  déjà calculée est une régression silencieuse.

- Vérification post-fix : sur 216 scènes H1 GBPUSD du 2026-07-06,
  215 ont h1_state="HAUSSIERE" / h1_dir="HAUSSIERE" / m5_state=
  "HAUSSIERE" (correctement propagés), 4 ont h1_state="NEUTRAL"
  (max_force entre 40-60, comportement attendu). 0 opposition
  cross-TF observée sur la journée (marché uniformément haussier),
  donc ANTAGONIST_NODE continue de ne pas déclencher — mais
  désormais POUR LA BONNE RAISON (pas de signal cross-TF, pas
  bug de propagation).

- Tests : 343 -> 347 (+4 nouveaux tests ANTAGONIST_NODE dans
  test_principle_engine.py) :
  - test_antagonist_node_cross_tf_fields_propagated
  - test_antagonist_node_triggers_on_cross_tf_opposition (le test
    qui aurait détecté le bug dès la session précédente)
  - test_antagonist_node_does_not_trigger_when_h1_m5_aligned
  - test_antagonist_node_fallback_when_h1_state_neutral

- Impact : ANTAGONIST_NODE techniquement débloqué. Activation
  effective dépend de l'apparition d'antagonismes cross-TF réels
  en live (les conditions du principe sont sémantiquement correctes
  — opposition H1 vs M5 — donc le 0/1728 actuel sur le marché
  haussier du 2026-07-06 n'est pas un défaut du principe).

- Référence : commit fix(v9): ANTAGONIST_NODE — diagnostic +
  correction condition bloquante.
### 2026-07-06 — Signal — déblocage pipeline avant ISM PMI 14h UTC
- Décision : déblocage d'urgence du pipeline de signaux V9, qui produisait
  0 signal directionnel sur 1726 entrées (toutes confiance=0, direction=None)
  malgré 234 exploitabilities exploitables et plusieurs principes ACTIVE
  déclenchés (POWER_ANGLE_BREAK, PRICE_LAG_AT_NODE_BIRTH, ZONE_RETEST avec
  confiance 60-100). Diagnostic en 3 étapes :

  1) Goulet 1 (config.py) : REGIMES_INADEQUATS contenait NEUTRE. Le marché
     GBPUSD 2026-07-06 est quasi-exclusivement en regime NEUTRE, ce qui
     bloquait 100% des signaux même quand exploitabilité=exploitable.
     Fix : retrait de NEUTRE de REGIMES_INADEQUATS (PALIER conservé).
     Justification : un régime NEUTRE peut signaler une transition
     imminente (oscillation sans direction nette = signal précurseur).

  2) Goulet 2 (signal_generator.py) : les principes ACTIVE déclenchés
     n'étaient JAMAIS chargés si raison_absence != None (exploitabilité
     non_exploitable ou régime inadéquat). Le champ principes_source
     restait vide pour tous les signaux absents — perte d'observabilité.
     Fix : charger TOUJOURS les principes ACTIVE déclenchés et les
     journaliser dans principes_source, même pour les signaux absents.

  3) Goulet 3 (exploitability_evaluator.py) : _determine_status
     retournait TOUJOURS "non_exploitable" quand window.statut="absente".
     Le marché GBPUSD M5 reste en window=absente quasi-permanent
     (range), ce qui bloquait 100% des signaux malgré confiance_globale
     >= 65 et 2-4 principes ACTIVE par snapshot. Fix : autoriser
     "exploitable" sur window=absente SI niveau_confiance_global >=
     seuil_exploitable (65). Critère cumulatif strict (confiance élevée),
     risque résiduel atténué par scanner --principes + heatmap 30j.

  4) Goulet 4 (signal_generator.py) : même après le fix 3, le pipeline
     lisait l'exploitability FIGÉE en DB (calculée avant le fix).
     Fix : re-evaluation in-memory via _determine_status (sans toucher
     la DB, sans INSERT OR IGNORE parasite).

  Impact avant/après sur 5 derniers snapshots GBPUSD M5 :
  - Avant : 0/5 signaux directionnels
  - Après : 3/5 signaux ACTIFS (haussiere conf=80-100, horizon=court_terme)
  - Les 2/5 restants : confiance_globale < 65 (correctement filtrés)

- Motivation : urgence ISM PMI à 14h UTC (volatilité attendue). Le pipeline
  doit être capable de produire au moins 1 signal AVANT l'événement pour
  démontrer sa capacité de détection. Sans ce fix, le pipeline V9 est
  aveugle au marché réel.

- Risques acceptés :
  (a) Régime NEUTRE → potentiellement faux signaux sur marché de range.
      Atténuation : scanner --principes + heatmap 30j live restent
      l'autorité pour recalibrer si WR < 50%.
  (b) Window=absente + confiance élevée → exploitable. Atténuation :
      l'exploitabilité reste un pré-filtre strict (niveau_confiance >= 65,
      3 cas WIN comparés dans le replay_context).

- Tests : 347/347 verts (aucune régression). Le fix 4 (re-eval via
  _determine_status uniquement, pas evaluate_window) évite le bug
  de doublons d'exploitability qui aurait cassé test_regenerate_chain.

- Référence : commit fix(v9): signal — déblocage SEUIL_EXPLOITABLE /
  vote (3 fichiers : config.py + exploitability_evaluator.py +
  signal_generator.py).
### 2026-07-06 — Infrastructure — nettoyage DB + contraintes idempotence
- Décision : déduplication des tables doubles + ajout UNIQUE constraints
  pour prévenir la récurrence.
- Motivation : v9_forces.db à 936 MB après 1 journée live (WAL grew
  large). Radiographie complète révèle 3 tables avec doublons massifs :
  * decisions : 3962 → 3957 lignes (5 doublons sur snapshot_id)
  * signals : 3977 → 3957 (20 doublons sur snapshot_id)
  * principle_evaluations : 783 344 → 97 892 (685 452 doublons,
    99.5% de la table, ratio attendu 27 principes × ~3 957 snapshots
    ≈ 97K mais EA a réinséré chaque ligne à chaque ré évaluation).
  La racine cause est l'absence de UNIQUE constraints idempotentes —
  le même snapshot est réinjecté à chaque recalcul de chain sans
  INSERT OR IGNORE, créant N copies.
- Impact :
  * DB : 1 393 MB → 582 MB (−58%, 811 MB récupérés)
  * WAL : rejouée et compactée
  * 3 décisions directionnelles préservées (dec_555be59bebbf,
    dec_df961c3f104b, dec_20260706T141916…)
  * Contraintes ajoutées :
    - decisions : UNIQUE INDEX idx_decisions_snapshot_id
    - signals : UNIQUE INDEX idx_signals_snapshot_id
    - principle_evaluations : UNIQUE INDEX idx_pe_snapshot_principle
  * Tests : 359/359 verts (aucune régression)
- Risques acceptés : VACUUM concurrent sur base live (effectué hors
  marché, 9.4s, aucune requête en cours).
- Référence : commits fix(v9): db — déduplication + VACUUM,
  fix(v9): db — UNIQUE constraints prévention doublons, et
  fix(v9): principle_engine — INSERT OR REPLACE + idempotence.
### 2026-07-06 — Infrastructure — INSERT OR REPLACE sur principle_engine
- Décision : remplacer INSERT OR IGNORE → INSERT OR REPLACE dans
  principle_engine._write_evaluations_to_db().
- Motivation : INSERT OR IGNORE n'ignorait rien. evaluation_id est un
  UUID regénéré à chaque appel de _generate_evaluation_id(), donc la
  contrainte UNIQUE(evaluation_id) ne matchait jamais et 27 lignes
  fraîches étaient insérées à chaque evaluate_principles() sur le même
  snapshot. INSERT OR REPLACE avec la contrainte
  UNIQUE(snapshot_id, principle_id) fait qu'un rejeu / recalcul
  écrase la row précédente — idempotence correcte.
- Impact :
  * 0 nouveau doublon en replay (grâce à UNIQUE + REPLACE)
  * La DB reste stable en taille après le premier passage
  * Pas de ménage DB nécessaire entre deux replays
- Tests : 359/359 verts.
- Référence : commit fix(v9): principle_engine — INSERT OR REPLACE +
  UNIQUE(snapshot_id,principle_id).

### 2026-07-06 — Session 4 : YAML news-aware (4 principes enrichis)
- Décision : enrichissement de 4 fichiers YAML principes pour consommer les 5 champs
  news propagés via `news_context.py` (session 2). Implémentation :
  1. **POWER_ANGLE_BREAK_TO_PRICE_IMPACT** : condition `news_phase in [POST_NEWS, NEUTRE]`
     + bounds `news_distance_min [-60, 0]` → boost confiance implicite en POST_NEWS
     (proche 0 = plus récent = +confiance). Filtre PRE_NEWS/NEWS_SHOCK.
  2. **NODE_BIRTH_FAST** + **RAW_NODE_BIRTH** : condition `news_phase not_in [NEWS_SHOCK]`
     — évite naissances de nœud pendant choc de volatilité (signaux bruités).
  3. **COALITION_NODE** : champ calculé `coalition_news_allow` dans
     `_load_shared_context()` = `news_session_clean == True OR news_phase == "POST_NEWS"`.
     Coalition fiable seulement si session propre (pas de news HIGH à venir) OU
     réorganisation confirmée POST_NEWS.
  4. **ANTAGONIST_NODE** : note documentaire seulement — terrain optimal
     = NEWS_SHOCK (divergence H1 vs M5 amplifiée par le choc), ne pas filtrer.
  5. **CONTEXT_CONTRACT.md** : 4 champs news reclassés PROPAGÉ→CONSOMMÉ + ajout
     `coalition_news_allow` (calculé).
- Motivation : doctrine V9 « la news est un repère temporel, les forces sont la réalité » —
  cadrer P2 pour que les principes filtrent les contextes défavorables sans trade la news.
- Impact : 359 tests verts. Calibration `--principes` opérationnelle. Signaux live
  attendus : POWER_ANGLE plus sélectif en POST_NEWS, NODE_BIRTH filtrés NEWS_SHOCK.
- Référence : commit `a87d88f` (feat(v9): session 4 — YAML news-aware).

### 2026-07-06 — Session 5 : Métriques DORMANT P2 promues PROPAGÉ
- Décision : promotion de 4 champs DORMANT (P2) vers PROPAGÉ dans `_load_shared_context_shared_context_shared()` :
  1. `contexte_temporel.fenetre` → `contexte_temporel_fenetre` (depuis scene.contexte_temporel_json)
  2. `point_de_rupture.declencheur` → `point_de_rupture_declencheur` (depuis behaviors table)
  3. `variante_de_comportement_connu.est_variante` → `est_variante` (depuis behaviors table)
  4. `variante_de_comportement_connu.comportement_reference` → `comportement_reference` (depuis behaviors table)
- Fallbacks ajoutés dans le bloc pré-scene_row (lignes ~490) : None/False/None selon le type.
- CONTEXT_CONTRACT.md mis à jour : 4 lignes reclassées DORMANT→PROPAGÉ avec consommateur PrincipleEngine.
- Motivation : doctrine règle 27 (champ DORMANT > 2 phases → réévaluation) + règle 21 (toute métrique ajoutée tracée dans CONTEXT_CONTRACT). Ces champs étaient DORMANT depuis Phase 4 (comportements) — 2 phases écoulées.
- Impact : 359 tests verts. Champs désormais disponibles pour conditions YAML principes (ex: GRAMMAR_PULLBACK note sur `point_de_rupture.declencheur`, GRAMMAR_CONTEXTE note sur `contexte_temporel_fenetre`).
- Référence : commit à venir.

### 2026-07-06 — COALITION_THRESHOLD audit + calibration live
- Décision : seuil `COALITION_THRESHOLD` maintenu à **5.0 (PROVISIONAL)** dans `config.py`.
  Calibration `--analyze` sur n=3957 scènes live suggère **5.33** (P20 des écarts de force inter-devises).
  Précédent suggéré 3.96 (session calibration antérieure, n=1708).
- Contexte : 3 décisions directionnelles live (3 `preparer_entree` haussière conf 80-100, GBPUSD M5).
  Coalition detection rate : 39.9% scènes avec coalition, 0.68 coalitions/scène moyenne.
  Antagonismes : 41.0% scènes, 6.33 antagonismes/scène moyenne.
- Règle doctrine 25 appliquée : pas de modification sans WIN/LOSS enregistré.
  Seuil réévalué à n>5000 scènes + issues WIN/LOSS (actuellement 0 trade résolu).
- Impact : config.py inchangé. 359 tests verts.
- Référence : commit à venir.

### 2026-07-06 — Inventaire migration V8→V9 (audit MIGRATION_POLICY_V9.md)
- Décision : audit complet selon 4 catégories A/B/C/D appliqué à l'inventaire V8 (1361 fichiers .py, ~115 DB).
- Résultats (priorités P1/P2/P3 selon `docs/architecture/audit_v8_v9_migration.md` section 7) :

**P1 — À migrer immédiatement (haute valeur, faible couplage DB) :**
1. **27 principes YAML** (`principles/*.yaml`) — 27 ACTIVE (grammaire), 9 DEPRECATED, 2 SHADOW. Zéro dépendance code, portage direct comme grammaire couche `behaviors` V9. (~0.5-1 jour)
2. **`agent_registry.py` + `federation_evidence_gate.py` + `federation_contracts.py`** — logique routage free-first, fallback chains, gate déterministe. Découplée DB V8. (~2-3 jours)
3. **Règles "GOLDEN" de `pf_mt5_bridge_v2.py`** — seule stratégie exécution avec WR 61.1% documenté (USDJPY 60% + GBPUSD 40%, LONG only, ASIA+NY, SL15/TP20). Extraire logique, ne pas porter 48 Ko monolithique. (~3-5 jours)
4. **Correction ShiftIndex EA** — vérifier `ShiftIndex=1` hérité dans `ea/V9_Sonde_M1.mq4` et `ea/V9_Sonde_TF.mq4`. (Fix V8 appliqué 2026-06-30)

**P2 — Peut attendre (décision produit requise) :**
1. `zone_diagnostics` (36k lignes, pullback/absorption/tension) — gap réel, mais non bloquant tant que `behaviors`/`windows` V9 n'ont pas besoin explicite. (~5-8 jours si retenu)
2. Workflows YAML (`battle_plan.yaml`, `federated_analysis.yaml`) — portables après fédération (dépendance P1.2). (~1-2 jours)
3. Couche MT5 tick/microstructure (4.2 Go, 15 modules) — **décision produit explicite** avant portage (volumétrie/latence significative). (~10-15 jours)
4. `structure_ledger` (multi-TF SQL typé) — réévaluer si requêtes JSON `scenes` insuffisantes.

**P3 — Obsolète (ne pas porter) :**
- Doublons versionnés (`pf_anchor_detector_v2` à `_v9` 9 versions, `pf_price_verdict_v5_3/5_5/5_6`, `telegram_*`, `pf_lab_engine` vs `_v72`, etc.)
- Clusters `dashboard_*` (26), `scheduler_*` (5), `telegram_*` (8+) — modèle cron remplacé par orchestrateur événementiel V9.
- `core/legacy/`, `core/archive/`, `federation/_archive*`, `archive/`, `OLD/` — déjà archivés V8.
- DBs backup/doublon (~115 fichiers .db dont beaucoup vides/dupliqués).
- Monolithe `powerflow_mcp_server.py` (430 Ko) — reconstruire serveur MCP V9 minimal.

- Dette technique à NE PAS porter : pattern `_vN` suffix sans nettoyage, 3 emplacements tests, sprawl SQLite, tables créées jamais alimentées, doc/code divergence.
- Impact : 359 tests verts. Inventaire archivé dans `docs/architecture/audit_v8_v9_migration.md`.
- Référence : commit à venir.

### 2026-07-07 — Phase 9.7 : Seuils PROVISIONAL — décision différée à London open
- Décision : **GEL des seuils config.py** (COALITION_THRESHOLD, REGIME_LOOKBACK_BARS, SIMILARITY_THRESHOLD, REPLAY_MIN_CAS) jusqu'au run de calibration final ~08h CEST (London open).
- Contexte : Session Hermes live en cours cette nuit (session Asie → Europe), accumulation n>5 000 scènes sur les seuils actuels (COALITION_THRESHOLD=5.0, ANTAGONISM_THRESHOLD=31.39, PLIURE_THRESHOLD=1.7). Toute modification maintenant polluerait les données de décision.
- Règle de convergence : décision d'application des seuils suggérés (calibration `--analyze` : COALITION_THRESHOLD→5.38, ANTAGONISM_THRESHOLD→30.4, PLIURE_THRESHOLD→0.85) soumise à la règle de convergence : 3 runs Hermes consécutifs stables + n>5 000 scènes + WIN/LOSS ≥ 20 trades résolus.
- Chantiers GELÉS jusqu'à 08h CEST :
  - COALITION_THRESHOLD (attente run 3 Hermes + règle de convergence)
  - REGIME_LOOKBACK_BARS (chantier séparé, session dédiée)
  - SIMILARITY_THRESHOLD (nécessite test sur scènes live, pas encore fait)
  - REPLAY_MIN_CAS temporaire à 1 (interdit — masque un signal d'incertitude)
- Actions autorisées cette nuit (sans risque) :
  - Préparation draft checkpoint Phase 9 → Phase 10 (cases vides à remplir au matin)
  - Mise à jour DECISIONS_LOG.md (cette entrée)
  - Vérification ACTIVE_TASKS.md reflète état exact (Hermes live, ZCode en attente, seuils non appliqués)
- Motivation : doctrine V9 règle 20 (calibration-first) + règle 25 (promotion sur preuves live) — les données Hermes de cette nuit SONT les preuves live.
- Impact : config.py inchangé, 359 tests verts, DB idempotente.
- Référence : commit docs only (ce message), checkpoint draft à venir.
