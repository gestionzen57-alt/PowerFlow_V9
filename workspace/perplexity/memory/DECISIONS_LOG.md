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

### 2026-07-06 — Push final sur origin/feat/v9-foundation-clean
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
