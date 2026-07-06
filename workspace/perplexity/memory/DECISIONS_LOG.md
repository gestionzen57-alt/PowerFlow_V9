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
