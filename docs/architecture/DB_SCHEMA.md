# DB_SCHEMA — PowerFlow V9

## Statut
Schéma SQLite complet de `data/v9_forces.db`, extrait directement des fichiers
`core/v9/*_db.py` le 2026-07-05 (branche `feat/v9-foundation-clean`). **Le code est la
source de vérité** : en cas de divergence, relire le `*_db.py` correspondant plutôt que
ce document. Une seule base SQLite (mode WAL, `busy_timeout=30000`, `synchronous=NORMAL`,
`temp_store=MEMORY` — voir `get_connection()` dans `core/v9/db_schema.py`).

Tables marquées **[Phase 9, en cours]** : créées par du code non commité au moment de la
rédaction, développé sur une session concurrente. Schéma exact mais statut fonctionnel
provisoire (voir [docs/phases/PHASE9_DECISION.md](../phases/PHASE9_DECISION.md)).

## Vue d'ensemble des références inter-tables

Chaque couche référence la couche amont par identifiant textuel, **jamais par duplication**
des colonnes de la couche amont (règle de doctrine, voir [DOCTRINE.md](../DOCTRINE.md) et
`CHARTE_COGNITIVE_V9.md`) :

```
forces_snapshots (snapshot_id)
    ├─ scenes.forces_snapshot_ref
    │     └─ behaviors.scene_id_ref
    │           └─ windows.behavior_id
    │                 └─ exploitability.window_id
    ├─ regime_snapshots.forces_snapshot_ref        [Phase 9]
    ├─ zone_diagnostics.forces_snapshot_ref         [Phase 9, table vide — non alimentée]
    ├─ principle_evaluations.snapshot_id            [Phase 9]
    ├─ signals.snapshot_id (+ exploitability_id)    [Phase 9]
    └─ decisions.snapshot_id (+ signal_id, scene_id, behavior_id, window_id,
                                exploitability_id)  [Phase 9]
principles (catalogue statique, indépendant des snapshots)                [Phase 9]
```

## `forces_snapshots`

Couche Forces. Table racine, 44 colonnes + `id`. Fichier : `core/v9/db_schema.py`.

| Colonne | Type | Notes |
|---|---|---|
| id | INTEGER PK AUTOINCREMENT | |
| snapshot_id | TEXT UNIQUE | |
| schema_version, timestamp, source, symbol, timeframe | TEXT | |
| bar_time, bar_close_time, server_time, capture_time, shift | INTEGER | |
| is_closed_bar | BOOLEAN | clé de l'anti-replay |
| open, high, low, close | REAL | OHLC |
| tick_volume | INTEGER | |
| spread_points | INTEGER | spread_price REAL |
| bid, ask, mid | REAL | |
| force_usd, force_gbp, force_eur, force_jpy, force_cad, force_chf, force_aud, force_nzd | REAL | 8 devises |
| direction | TEXT | vitesse REAL |
| croisement_detecte | BOOLEAN | croisement_partenaire/croisement_direction TEXT |
| recroisement_detecte | BOOLEAN | recroisement_contexte TEXT |
| rejet_repulsion_detecte | BOOLEAN | rejet_intensite REAL |
| compression_extension_etat | TEXT | compression_extension_intensite REAL |
| stale | BOOLEAN | age_ms, stale_threshold_ms INTEGER |
| created_at | TEXT | |

**Index** :
- `idx_forces_timeframe_bartime` (timeframe, bar_time)
- `idx_unique_closed_bar` **UNIQUE** (symbol, timeframe, bar_time) **WHERE is_closed_bar = 1**
  — c'est le mécanisme anti-replay : une bougie clôturée ne peut exister qu'une fois, même
  rejouée avec un `snapshot_id` différent ; les bougies en cours (is_closed_bar=0) peuvent
  légitimement recevoir plusieurs lignes avant clôture.

## `scenes`

Couche Scènes. 14 colonnes + `id`. Fichier : `core/v9/scene_db.py`.

| Colonne | Type |
|---|---|
| id | INTEGER PK |
| scene_id | TEXT UNIQUE |
| schema_version, timestamp, timeframes_concernes | TEXT |
| forces_snapshot_ref | TEXT — référence `forces_snapshots.snapshot_id`, jamais dupliquée |
| forces_snapshot_timestamp | TEXT |
| zone_json, coalitions_json, antagonismes_json, cinematique_json, confluences_mtf_json, contexte_temporel_json | TEXT (JSON sérialisé) |
| stale | BOOLEAN |
| created_at | TEXT |

**Index** : `idx_scenes_timestamp` (timestamp), `idx_scenes_forces_snapshot_ref` (forces_snapshot_ref)

## `behaviors`

Couche Comportements. 24 colonnes + `id`. Fichier : `core/v9/behavior_db.py`.

| Colonne | Type |
|---|---|
| id | INTEGER PK |
| behavior_id | TEXT UNIQUE |
| schema_version, timestamp | TEXT |
| scene_id_ref | TEXT — référence `scenes.scene_id` |
| scene_timestamp, symbol, timeframe, window_start, window_end | TEXT |
| qualification, intensite, phase | TEXT — 12 qualifications possibles (voir `docs/architecture/formats/FORMAT_COMPORTEMENTS.md`) |
| confiance_qualification | INTEGER |
| description_courte | TEXT |
| comportement_precedent | TEXT |
| point_de_rupture_detecte | BOOLEAN — point_de_rupture_timestamp/declencheur TEXT |
| sens_transition | TEXT |
| similarite_score | REAL |
| cas_references_json, singularites_locales_json | TEXT |
| est_variante | BOOLEAN — comportement_reference, ecarts_json TEXT |
| stale, created_at | BOOLEAN / TEXT |

**Index** : `idx_behaviors_scene_id_ref`, `idx_behaviors_symbol_timeframe_timestamp`,
`idx_behaviors_qualification_intensite`

## `windows`

Couche Fenêtres. 15 colonnes + `id`. Fichier : `core/v9/window_db.py`.

| Colonne | Type |
|---|---|
| id | INTEGER PK |
| window_id | TEXT UNIQUE |
| schema_version, timestamp | TEXT |
| behavior_id | TEXT — référence `behaviors.behavior_id` |
| behavior_qualification | TEXT — behavior_confiance INTEGER (dénormalisés pour lecture directe) |
| statut | TEXT — 6 valeurs (absente/en_preparation/ouverte/fragile/invalidee/ambigue) |
| type_fenetre | TEXT — retournement/continuation/rupture_range |
| niveau_confiance | INTEGER |
| timestamp_ouverture, timestamp_fermeture | TEXT |
| fragilite_detectee | BOOLEAN — fragilite_raison TEXT |
| conditions_invalidation_json | TEXT |
| stale, created_at | BOOLEAN / TEXT |

**Index** : `idx_windows_behavior_id`, `idx_windows_statut_timestamp`, `idx_windows_timestamp_ouverture`

## `exploitability`

Couche Exploitabilité. 14 colonnes + `id`. Fichier : `core/v9/exploitability_db.py`.

| Colonne | Type |
|---|---|
| id | INTEGER PK |
| exploitability_id | TEXT UNIQUE |
| schema_version, timestamp | TEXT |
| window_id | TEXT — référence `windows.window_id` |
| window_statut | TEXT — window_niveau_confiance INTEGER (dénormalisés) |
| statut | TEXT — 5 valeurs (non_exploitable/watchlist/exploitable/refuse/ambigu) |
| raison_refus | TEXT — 5 valeurs possibles, cascade priorisée |
| niveau_confiance_global | INTEGER |
| validation_hitl_requise | BOOLEAN — validation_hitl_raison TEXT |
| replay_cas_compares_json | TEXT — replay_nombre_cas INTEGER, replay_synthese TEXT |
| stale, created_at | BOOLEAN / TEXT |

**Index** : `idx_exploitability_window_id`, `idx_exploitability_statut_timestamp`

## `regime_snapshots` — [Phase 9, en cours]

Détection de régime de marché par devise. 19 colonnes + `id`. Fichier : `core/v9/regime_db.py`.
Migration du gap V8 (`pf_regime_detector.py`, 327 112 lignes en V8 sans équivalent V9 avant
cette phase) — adaptée au modèle événementiel (référence `forces_snapshot_ref` au lieu
d'une clé symbol/currency/minute).

| Colonne | Type |
|---|---|
| id | INTEGER PK |
| regime_id | TEXT UNIQUE |
| schema_version, timestamp | TEXT |
| forces_snapshot_ref | TEXT — référence `forces_snapshots.snapshot_id` |
| symbol, timeframe, currency | TEXT |
| force_value | REAL |
| regime_type | TEXT — NEUTRE/PALIER/CASSURE/EXTENSION/RETOUR_EQUILIBRE/REJET |
| cassure_type, cassure_direction | TEXT — cassure_type reste toujours INDETERMINEE (pas de couche tick en V9) |
| palier_start_ts, palier_duration_bars, palier_level | TEXT / INTEGER / REAL |
| tick_freq_hz, spread_mean, delta_vol | REAL / REAL / INTEGER — **NULL tant qu'il n'y a pas de couche tick** (dégradation gracieuse) |
| mean_reversion_zone | BOOLEAN |
| stale, created_at | BOOLEAN / TEXT |

**Index** : `idx_regime_snapshot_currency` **UNIQUE** (forces_snapshot_ref, currency),
`idx_regime_symbol_tf_currency_timestamp`, `idx_regime_type`

## `principles` + `principle_evaluations` — [Phase 9, en cours]

Catalogue de principes + évaluations par snapshot. Fichier : `core/v9/principle_db.py`.
`principles` est peuplé depuis `core/v9/principles/*.yaml` (27 fichiers, migration V8 auditée).

**`principles`** (16 colonnes + `id`, catalogue statique, indépendant des snapshots) :

| Colonne | Type |
|---|---|
| id | INTEGER PK |
| principle_id | TEXT UNIQUE |
| version | INTEGER |
| origin, kind, source_status, v9_status | TEXT — kind ∈ {node_rule, grammar, ...}, v9_status ∈ {ACTIVE, SHADOW} |
| scope_timeframes_json, scope_currencies_json | TEXT |
| conditions_json, emits_json, bounds_json | TEXT |
| anti_signal_bias | BOOLEAN |
| notes, created_by, created_at_source, synced_at | TEXT |

**Index** : `idx_principles_v9_status`

**`principle_evaluations`** (16 colonnes + `id`, référence `snapshot_id`) :

| Colonne | Type |
|---|---|
| id | INTEGER PK |
| evaluation_id | TEXT UNIQUE |
| schema_version, timestamp | TEXT |
| snapshot_id | TEXT — référence `forces_snapshots.snapshot_id` |
| principle_id | TEXT — référence `principles.principle_id` |
| v9_status, kind, symbol, timeframe, currency | TEXT |
| triggered | BOOLEAN |
| direction | TEXT |
| confidence | INTEGER |
| anti_signal_bias | BOOLEAN |
| reason, context_json, created_at | TEXT |

**Index** : `idx_principle_evaluations_snapshot`, `idx_principle_evaluations_principle_triggered`
(principle_id, triggered)

## `signals` — [Phase 9, en cours]

Agrégation des principes déclenchés. 16 colonnes + `id`. Fichier : `core/v9/signal_db.py`.

| Colonne | Type |
|---|---|
| id | INTEGER PK |
| signal_id | TEXT UNIQUE |
| schema_version, timestamp | TEXT |
| snapshot_id | TEXT — référence `forces_snapshots.snapshot_id` |
| symbol, timeframe, currency | TEXT |
| direction | TEXT |
| confiance | INTEGER |
| horizon | TEXT |
| principes_source_json | TEXT |
| regime_type | TEXT |
| exploitability_id, exploitability_statut | TEXT — référence `exploitability.exploitability_id` |
| raison_absence | TEXT — toujours journalisée si aucun signal produit |
| stale, created_at | BOOLEAN / TEXT |

**Index** : `idx_signals_snapshot`, `idx_signals_symbol_timeframe_timestamp`

## `decisions` — [Phase 9, en cours]

Décision finale : signal + contexte complet + action recommandée. 18 colonnes + `id`.
Fichier : `core/v9/decision_db.py`.

| Colonne | Type |
|---|---|
| id | INTEGER PK |
| decision_id | TEXT UNIQUE |
| schema_version, timestamp | TEXT |
| snapshot_id, signal_id | TEXT — références croisées |
| action | TEXT — **qualitatif uniquement** : observer / surveiller / preparer_entree / aucune_action, jamais un ordre |
| symbol, timeframe, currency | TEXT |
| scene_id, behavior_id, window_id, exploitability_id | TEXT — références vers chaque couche amont |
| regime_type, direction | TEXT |
| confiance | INTEGER |
| principes_json | TEXT |
| contexte_complet_json | TEXT — snapshot complet replayable de la décision |
| created_at | TEXT |

**Index** : `idx_decisions_snapshot`, `idx_decisions_signal`, `idx_decisions_symbol_timeframe_timestamp`

## `zone_diagnostics` — [Phase 9, en cours — table créée, non alimentée]

Zones extrêmes HTF (pullback/absorption/tension). 27 colonnes + `id`. Fichier :
`core/v9/zone_db.py`. Migration du gap V8 (`zone_diagnostics`, 36 808 lignes en V8).
**Aucun détecteur ne l'alimente actuellement** — chantier distinct hors scope Phase 9
(estimé 5-8 jours). Tant qu'elle est vide, les 9 principes `node_rule` qui en dépendent
(ex. `ZONE_RETEST`, `NODE_BIRTH_FAST`) sont chargés et évalués mais ne se déclenchent
jamais (conditions non remplies) — dégradation gracieuse, pas d'erreur.

| Colonne | Type |
|---|---|
| id | INTEGER PK |
| zone_diagnostic_id | TEXT UNIQUE |
| schema_version, timestamp | TEXT |
| forces_snapshot_ref | TEXT — référence `forces_snapshots.snapshot_id` |
| symbol, timeframe, currency | TEXT |
| state, prev_state | TEXT |
| zone_level, z_current | REAL |
| z_extreme_dir, prev_z_extreme_dir | TEXT |
| bars_in_extreme, pullback_count, absorbed_pullback_count | INTEGER |
| depth_slope, depth_acceleration, absorption_factor, tension_score, context_score | REAL |
| profile_name | TEXT |
| rank_position, rank_total, duration_bars | INTEGER |
| context_tags_json, raw_diagnosis_json | TEXT |
| stale, created_at | BOOLEAN / TEXT |

**Index** : `idx_zone_diagnostic_currency` **UNIQUE** (forces_snapshot_ref, currency),
`idx_zone_symbol_tf_currency_timestamp`

## Voir aussi
- [docs/architecture/formats/](formats/) — formats JSON par couche (structure des champs `*_json`)
- [docs/architecture/audit_v8_v9_migration.md](audit_v8_v9_migration.md) — origine des gaps V8→V9 comblés en Phase 9
