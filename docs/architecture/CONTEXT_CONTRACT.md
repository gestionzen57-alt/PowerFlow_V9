# CONTEXT_CONTRACT — PowerFlow V9

## Rôle
Ce fichier est le contrat vivant de propagation des métriques entre couches.
Il définit, pour chaque couche, ce qu'elle produit et ce que les couches
aval consomment réellement.

**Règle doctrine** : toute nouvelle métrique ajoutée dans une couche doit
être tracée ici avec son statut `PROPAGÉ` ou `DORMANT (justifié)`.
Une métrique DORMANT sans justification est une anomalie à corriger.

Mis à jour à chaque session produisant une modification de `_load_shared_context`,
`build_scene`, `analyze_scene` ou d'un module de couche.

---

## Couche 1 — Forces (`forces_reader.py`, `forces_snapshots` DB)

### Champs produits
| Champ | Type | Statut | Consommé par |
|---|---|---|---|
| `force_usd/gbp/eur/jpy/cad/chf/aud/nzd` | float×8 | PROPAGÉ | SceneBuilder |
| `vitesse` | float | PROPAGÉ (partiel) | SceneBuilder._compute_cinematics (velocite_moyenne) |
| `tick_volume` | int | **PROPAGÉ (2026-07-16)** | PrincipleEngine (`volume_regime`/`volume_ratio` dérivés dans `_load_shared_context`) → VOLUME_CONFIRMATION |
| `bar_time` | int | PROPAGÉ | SceneBuilder._compute_cinematics (acceleration_vraie) |
| `stale` | bool | PROPAGÉ | toutes couches |
| `mid` | float | PROPAGÉ | PrincipleEngine (pf_mid) |
| `symbol` | str | PROPAGÉ | toutes couches |
| `timeframe` | str | PROPAGÉ | toutes couches |
| `cvd_delta` | int\|None | **CHANTIER C (2026-07-18)** | SceneBuilder._cvd_assessment — flux agressif du tick (buy/sell). NULL avant migration DB + redéploiement EA. |
| `cvd_cumul` | int\|None | **CHANTIER C (2026-07-18)** | SceneBuilder._cvd_assessment — Cumulative Volume Delta. Kill switch `V9_CVD_ENABLED` (défaut OFF). |

> **CVD (Chantier C)** : colonnes `cvd_delta`/`cvd_cumul` ajoutées à `forces_snapshots` via migration **explicite** (`scripts/v9_migrate_cvd.py`, idempotente). `CREATE TABLE IF NOT EXISTS` ne touche pas la table prod existante ; `capture_server._get_effective_columns` intersecte `FORCES_COLUMNS` avec les colonnes réelles → aucune régression avant migration. L'EA `V9_Sonde_M1.mq4` doit être recompilé/redéployé pour émettre ces champs.

### Lacune connue
- `vitesse` = devise de base du symbole uniquement (pas un vrai panier 8 devises).
  `velocite_moyenne` est donc un proxy d'une seule devise.
  **Levier P3** : enrichir EA MT4 pour envoyer `vitesse_*` × 8 devises.
- **Diagnostic 2026-07-16** : `vitesse` non-nulle à **91% sur M1** (tick) mais ~1%
  sur candle — non par bug, mais parce que la **force SDI est constante intra-bar**
  (99,2% des M15). La vélocité fiable vit sur M1. Next-step : brancher
  `velocite_moyenne` sur la dernière vélocité tick M1 quand le snapshot candle est
  à 0 (chantier calibration séparé, cf. `docs/reports/audit_donnees_ouverture_yeux_20260716.md`).

---

## Couche 2 — Scènes (`scene_builder.py`, `scenes` DB)

### Sous-objets produits par `build_scene()`

#### coalitions_json — par coalition
| Champ | Type | Statut | Consommé par |
|---|---|---|---|
| `devises_alignees` | list[str] | PROPAGÉ | BehaviorAnalyzer, PrincipleEngine (coalition_strength) |
| `intensite_alignement` | float | PROPAGÉ | BehaviorAnalyzer, PrincipleEngine |
| `leader` | str | PROPAGÉ | BehaviorAnalyzer |
| `rotation_leadership.detectee` | bool | PROPAGÉ | BehaviorAnalyzer (_any_rotation_leadership) |
| `rotation_leadership.ancien_leader` | str\|None | PROPAGÉ | PrincipleEngine (coalition_rotation_ancien_leader) |
| `rotation_leadership.nouveau_leader` | str\|None | PROPAGÉ | PrincipleEngine (coalition_rotation_nouveau_leader) |
| `age_bars` | int | PROPAGÉ | RiskMeter, PrincipleEngine (via risk_assessment) |
| `intensite_trend` | str | PROPAGÉ | RiskMeter, PrincipleEngine (via risk_assessment) |
| `stabilite` | float | PROPAGÉ | RiskMeter, PrincipleEngine (via risk_assessment) |

#### antagonismes_json — par antagonisme
| Champ | Type | Statut | Consommé par |
|---|---|---|---|
| `devises_en_conflit` | list[str] | PROPAGÉ | BehaviorAnalyzer, PrincipleEngine |
| `intensite_conflit` | float | PROPAGÉ | BehaviorAnalyzer, PrincipleEngine (bascule_intensite) |
| `bascule_equilibre.detectee` | bool | PROPAGÉ | BehaviorAnalyzer, PrincipleEngine (bascule_detectee) |
| `bascule_equilibre.sens` | str\|None | PROPAGÉ | PrincipleEngine (bascule_devise_dominante) |

#### cinematique_json
| Champ | Type | Statut | Consommé par |
|---|---|---|---|
| `angle` | float | PROPAGÉ | BehaviorAnalyzer (_similarity), PrincipleEngine |
| `pente` | float | PROPAGÉ | BehaviorAnalyzer (_similarity), PrincipleEngine |
| `courbure` | float | PROPAGÉ | PrincipleEngine |
| `pliure.detectee` | bool | PROPAGÉ | BehaviorAnalyzer, PrincipleEngine |
| `pliure.severite` | float\|None | PROPAGÉ | BehaviorAnalyzer, PrincipleEngine |
| `acceleration_deceleration` | str | PROPAGÉ | BehaviorAnalyzer |
| `rotation_force.detectee` | bool | DORMANT (P3) | Aucun consommateur — à brancher sur signal_generator |
| `rotation_force.sens` | str\|None | DORMANT (P3) | Aucun consommateur |
| `compression_extension.etat` | str | PROPAGÉ | BehaviorAnalyzer |
| `compression_extension.intensite` | float | PROPAGÉ | BehaviorAnalyzer |
| `velocite_moyenne` | float | PROPAGÉ | PrincipleEngine |
| `acceleration_vraie` | float | PROPAGÉ | PrincipleEngine |
| `dispersion_velocite` | float | PROPAGÉ | PrincipleEngine |

#### confluences_mtf_json
| Champ | Type | Statut | Consommé par |
|---|---|---|---|
| `emboitement_detecte` | bool | PROPAGÉ | BehaviorAnalyzer (+10 confiance), PrincipleEngine |
| `cascades_temporelles` | list[dict] | DORMANT (P3) | Stocké DB, jamais lu en aval |
| `signatures_coherence` | list[str] | DORMANT (P3) | Stocké mémoire uniquement |
| `coalition_mtf_score` | int | PROPAGÉ | PrincipleEngine |
| `coalition_mtf_depth` | str | PROPAGÉ | PrincipleEngine |

#### contexte_temporel_json
| Champ | Type | Statut | Consommé par |
|---|---|---|---|
| `session` | str | PROPAGÉ | PrincipleEngine (session_marche) |
| `fenetre` | str | **PROPAGÉ (P2)** | PrincipleEngine (contexte_temporel_fenetre) |

#### zone_json
| Champ | Type | Statut | Consommé par |
|---|---|---|---|
| `zone.structure` | str | DORMANT (P3) | PrincipleEngine ne l'injecte pas — à ajouter |
| `zone.niveau` | str | DORMANT (P3) | PrincipleEngine ne l'injecte pas — à ajouter |
| `zone.prix.*` | float | DORMANT (P3) | Aucun consommateur |

#### risk_assessment_json
| Champ | Type | Statut | Consommé par |
|---|---|---|---|
| `risk_sentiment` | str | PROPAGÉ | PrincipleEngine |
| `risk_confidence` | int | PROPAGÉ | PrincipleEngine |
| `risk_on_score` | float | PROPAGÉ | PrincipleEngine |
| `risk_off_score` | float | PROPAGÉ | PrincipleEngine |
| `persistance_confirmee` | bool | PROPAGÉ | PrincipleEngine |
| `dominant_bloc` | list[str] | DORMANT (P3) | Stocké DB, jamais lu en aval |
| `refuge_bloc_direction` | str | DORMANT (P3) | Stocké DB, jamais lu en aval |
| `procyclique_bloc_direction` | str | DORMANT (P3) | Stocké DB, jamais lu en aval |

#### regime_gate (Chantier A, 2026-07-18 — kill switch `V9_REGIME_GATE_ENABLED`)
Champ **in-memory** attaché à `scene` par `build_scene()` (non persisté : `_write_scene_to_db` sélectionne des colonnes fixes, aucune migration). Régime courant projeté sur `trending`/`ranging`/`volatile` (lecture N-1 de `regime_snapshots`). Passthrough `{enabled: False, source: "off"}` quand le kill switch est OFF (défaut).
| Champ | Type | Statut | Consommé par |
|---|---|---|---|
| `regime_gate.enabled` | bool | PROPAGÉ (in-memory) | Observabilité / traçabilité |
| `regime_gate.regime` | str\|None | PROPAGÉ (in-memory) | Observabilité (`trending`/`ranging`/`volatile`) |
| `regime_gate.confidence` | float\|None | PROPAGÉ (in-memory) | Observabilité (cohérence 8 devises) |
| `regime_gate.source` | str | PROPAGÉ (in-memory) | `detector`/`fallback`/`off` |
| `regime_gate.ts` | str\|None | PROPAGÉ (in-memory) | Traçabilité snapshot lu |

#### cvd (Chantier C, 2026-07-18 — kill switch `V9_CVD_ENABLED`)
Champ **in-memory** `scene['cvd']` attaché par `build_scene()` (non persisté). Passthrough `{enabled: False}` quand le kill switch est OFF (défaut).
| Champ | Type | Statut | Consommé par |
|---|---|---|---|
| `cvd.enabled` | bool | PROPAGÉ (in-memory) | Observabilité |
| `cvd.cvd_cumul` | int\|None | PROPAGÉ (in-memory) | Observabilité (Cumulative Volume Delta) |
| `cvd.cvd_delta` | int\|None | PROPAGÉ (in-memory) | Observabilité (flux agressif du dernier tick) |
| `cvd.cvd_divergence` | bool | PROPAGÉ (in-memory) | Flag divergence prix/CVD (essoufflement) |

---

## Couche 3 — Comportements (`behavior_analyzer.py`, `behaviors` DB)

### Champs produits par `analyze_scene()`
| Champ | Type | Statut | Consommé par |
|---|---|---|---|
| `qualification` | str | PROPAGÉ | WindowGate, PrincipleEngine |
| `intensite` | str | PROPAGÉ | WindowGate, PrincipleEngine |
| `phase` | str | PROPAGÉ | WindowGate, PrincipleEngine |
| `confiance_qualification` | int | PROPAGÉ | WindowGate, PrincipleEngine |
| `sens_transition` | str | PROPAGÉ | PrincipleEngine |
| `point_de_rupture.detecte` | bool | PROPAGÉ | PrincipleEngine |
| `point_de_rupture.declencheur` | str | **PROPAGÉ (P2)** | PrincipleEngine (point_de_rupture_declencheur) |
| `similarite_score` | float\|None | PROPAGÉ | PrincipleEngine (via confiance_qualification bonus) |
| `cas_references` | list[dict] | DORMANT (P3) | Stocké DB uniquement |
| `singularites_locales` | list[str] | DORMANT (P3) | Stocké DB, jamais relu en aval |
| `variante_de_comportement_connu.est_variante` | bool | **PROPAGÉ (P2)** | PrincipleEngine (est_variante) |
| `variante_de_comportement_connu.comportement_reference` | str | **PROPAGÉ (P2)** | PrincipleEngine (comportement_reference) |

---

## Couche 4 — Fenêtres (`window_gate.py`, `windows` DB)

### Champs produits
| Champ | Type | Statut | Consommé par |
|---|---|---|---|
| `statut` | str | PROPAGÉ | ExploitabilityEvaluator, PrincipleEngine |
| `type_fenetre` | str | PROPAGÉ | ExploitabilityEvaluator, PrincipleEngine |
| `niveau_confiance` | int | PROPAGÉ | ExploitabilityEvaluator, PrincipleEngine |
| `fragilite_detectee` | bool | PROPAGÉ | ExploitabilityEvaluator, PrincipleEngine |

---

## Couche 5 — Exploitabilité (`exploitability_evaluator.py`, `exploitability` DB)

### Champs produits
| Champ | Type | Statut | Consommé par |
|---|---|---|---|
| `statut` | str | PROPAGÉ | PrincipleEngine |
| `niveau_confiance_global` | int | PROPAGÉ | PrincipleEngine |
| `raison_refus` (`regime_volatile`) | str | **GATE (Chantier A)** | Nouvelle raison : `evaluate_window` force `statut='refuse'` quand le gate régime bloque (kill switch `V9_REGIME_GATE_ENABLED`) |
| `meta.regime_gate` | dict | PROPAGÉ (in-memory) | Trace du gate appliqué (`applied`/`regime`/`confidence`) |

**Gate primaire régime (Chantier A)** : quand `V9_REGIME_GATE_ENABLED=1`, `evaluate_window()` appelle `RegimeDetector.get_current_regime(symbol, timeframe)` (lecture N-1) ; si `regime == "volatile"` **et** `confidence > REGIME_GATE_VOLATILE_CONF` (config.py, défaut 0.7), le `statut` est forcé à `refuse` (`raison_refus=regime_volatile`). Kill switch OFF → passthrough, zéro régression.

---

## Couche 6 — Régime (`regime_detector.py`, `regime_snapshots` DB)

### Champs produits (injectés dans contexte par PrincipleEngine)
| Champ | Type | Statut | Consommé par |
|---|---|---|---|
| `regime_type` | str | PROPAGÉ | PrincipleEngine |
| `cassure_direction` | str\|None | PROPAGÉ | PrincipleEngine |
| `mean_reversion_zone` | bool | PROPAGÉ | PrincipleEngine |
| `state` | str | PROPAGÉ | PrincipleEngine |
| `z_current` | float | PROPAGÉ | PrincipleEngine |
| `z_extreme_dir` | str\|None | PROPAGÉ | PrincipleEngine |
| `bars_in_extreme` | int | PROPAGÉ | PrincipleEngine |
| `tension_score` | float | PROPAGÉ | PrincipleEngine |

### `get_current_regime(symbol, timeframe)` (Chantier A, 2026-07-18)
Méthode additive projetant les 6 régimes par-devise (`PALIER`/`CASSURE`/`EXTENSION`/`RETOUR_EQUILIBRE`/`REJET`/`NEUTRE`) sur la taxonomie du gate — vote majoritaire sur les 8 devises du dernier `forces_snapshot_ref` persisté. R6 : ne lève jamais (fallback `ranging` conf 0.0).
| Champ retourné | Type | Mapping |
|---|---|---|
| `regime` | str | `CASSURE`/`EXTENSION`→`trending` ; `PALIER`/`RETOUR_EQUILIBRE`/`NEUTRE`→`ranging` ; `REJET`→`volatile` |
| `confidence` | float | part de la classe dominante (0.0–1.0) |
| `source` | str | `detector` / `fallback` |
| `ts` | str\|None | timestamp du snapshot de régime lu |

Consommé par : `SceneBuilder._regime_gate` (propagation `scene.regime_gate`) et `ExploitabilityEvaluator._apply_regime_gate` (gate primaire).

---

## Couche 7 — Principes (`principle_engine.py`)

### Contexte complet reçu par `_load_shared_context()`

#### Depuis forces_snapshots
- `pf_mid` (float), `stale` (bool)
- `h1_dir`, `h1_state`, `m5_dir`, `m5_state` (str)

#### Depuis coalitions_json (scène)
- `coalitions_count` (int), `coalition_strength` (float)
- `coalition_rotation_detectee` (bool)
- `coalition_rotation_ancien_leader` (str|None)
- `coalition_rotation_nouveau_leader` (str|None)
- `coalition_mtf_score` (int), `coalition_mtf_depth` (str)

#### Depuis antagonismes_json (scène)
- `antagonismes_count` (int)
- `bascule_detectee` (bool)
- `bascule_devise_dominante` (str|None)
- `bascule_intensite` (float)

#### Depuis cinematique_json (scène)
- `pente`, `courbure`, `velocite_moyenne`, `acceleration_vraie`, `dispersion_velocite`
- `pliure_detectee` (bool), `pliure_severite` (float|None)

#### Depuis risk_assessment_json (scène)
- `risk_sentiment`, `risk_confidence`, `risk_on_score`, `risk_off_score`
- `persistance_confirmee` (bool)

#### Depuis contexte_temporel_json (scène)
- `session_marche` (str), `heure_utc` (int|None), `jour_semaine` (int|None), `marche_ouvert` (bool)

#### Depuis behaviors
- `qualification`, `intensite`, `phase`, `confiance_qualification`
- `point_de_rupture_detecte` (bool), `sens_transition` (str)

#### Depuis windows
- `window_statut`, `type_fenetre`, `niveau_confiance`, `fragilite_detectee`

#### Depuis exploitability
- `exploitability_statut`, `niveau_confiance_global`

#### Depuis regime_snapshots (par devise)
- `regime_type`, `cassure_direction`, `mean_reversion_zone`
- `state`, `z_current`, `z_extreme_dir`, `bars_in_extreme`, `tension_score`

#### Depuis zone_diagnostics
- `zone_type`, `absorption_factor`, `bars_in_extreme_norm`

#### Calculés dans `_load_shared_context()` (news-aware session 4)
- `coalition_news_allow` (bool) — `news_session_clean == True OR news_phase == "POST_NEWS"`. Utilisé par COALITION_NODE pour filtrer les contextes défavorables.

---

## Couche transversale — NewsContext (`core/v9/news_context.py`)

Module pur calendrier économique (aucune DB). Évalue la position temporelle
d'un moment UTC par rapport à `data/economic_calendar.json` (récurrences
statiques : NFP, ISM_PMI, CPI_US, FOMC_RATE, FOMC_MINUTES, GDP_US,
RETAIL_SALES_US).

### Champs produits par `NewsContext().assess(utc_dt)`
| Champ | Type | Statut | Consommé par |
|---|---|---|---|
| `news_type` | str \| None | PROPAGÉ | Disponible pour conditions YAML — pas encore consommé (cadrage P2) |
| `news_phase` | str | PROPAGÉ | **CONSOMMÉ** par POWER_ANGLE_BREAK, NODE_BIRTH_FAST, RAW_NODE_BIRTH, COALITION_NODE (session 4 news-aware) |
| `news_distance_min` | int \| None | PROPAGÉ | **CONSOMMÉ** par POWER_ANGLE_BREAK (bounds pour boost confiance POST_NEWS) |
| `news_importance` | str | PROPAGÉ | Disponible pour conditions YAML — pas encore consommé (cadrage P2) |
| `news_session_clean` | bool | PROPAGÉ | **CONSOMMÉ** indirectement via `coalition_news_allow` calculé dans `_load_shared_context` |

### Vocabulaires
- `news_type` ∈ {"NFP", "ISM_PMI", "CPI_US", "FOMC_RATE", "FOMC_MINUTES", "GDP_US", "RETAIL_SALES_US", None}
- `news_phase` ∈ {"PRE_NEWS", "NEWS_SHOCK", "POST_NEWS", "NEUTRE"}
- `news_importance` ∈ {"HIGH", "MEDIUM", "LOW", "NEUTRE"}
- `news_distance_min` : entier signé (futur > 0, passé < 0), None si `news_phase == "NEUTRE"`
- `news_session_clean` : True = aucune news HIGH dans 90 prochaines minutes

### Règles de phase (brief Perplexity 2026-07-06)
- `distance > 0` (futur) :
  - `≤ window_pre_min` → `PRE_NEWS`
  - sinon → `NEUTRE`
- `distance ≤ 0` (passée) :
  - `|distance| ≤ window_shock_min` → `NEWS_SHOCK`
  - `|distance| ≤ window_post_min` → `POST_NEWS`
  - sinon → `NEUTRE`
- Aucune news dans la fenêtre 4h → `NEUTRE`, `news_distance_min = None`

### Priorité multi-news
Plusieurs news dans la fenêtre : la plus proche (en `|distance|`),
ex-aequo → la plus importante (HIGH > MEDIUM > LOW).

### Fallbacks (robustesse doctrine)
- Calendrier vide / corrompu : retourne `news_phase="NEUTRE"`, `news_type=None`,
  `news_importance="NEUTRE"`, `news_distance_min=None`,
  `news_session_clean=True`.
- Dans `_load_shared_context()` : try/except global avec fallback identique
  (5 champs garantis).
- `assess()` **ne lève jamais d'exception** (contrat strict).

### Câblage
- `core/v9/news_context.py` (module pur)
- `data/economic_calendar.json` (données statiques, tolérance ±3 min)
- `_load_shared_context()` dans `core/v9/principle_engine.py` — bloc injecté
  **EN DERNIER** (après tous les `context.update()`) pour ne rien écraser
  (leçon bug ANTAGONIST_NODE 2026-07-06, commit 046b285).
- Test gardien : `tests/test_news_context.py` (7 tests), calendrier en
  mémoire ou canonique selon le cas.

---

## Métriques DORMANT — récapitulatif 2026-07-16

**Mise à jour majeure** : l'audit 2026-07-14 identifiait 22 champs « jamais consommés par un YAML ».
Vérification code : ces champs sont **tous consommés** par les modules ML :
- `core/v9/trader_mini_weigher.py` (features pour prédiction logistique)
- `scripts/v9_export_dataset.py` (export dataset pour ré-entraînement)

→ **Aucun champ retiré.** Tous maintenus PROPAGÉS. Les 6 métriques P3 historiques
restent DORMANT (pas de consommateur identifié).

### DORMANT historiques (P3, sans consommateur)

| Priorité | Métrique | Couche source | Action |
|---|---|---|---|
| P3 | `cinematique.rotation_force.*` | Scènes | Brancher sur signal_generator |
| P3 | `confluences_mtf.cascades_temporelles` | Scènes | Consommer dans WindowGate |
| P3 | `zone.structure`, `zone.niveau` | Scènes | Injecter dans _load_shared_context |
| P3 | `risk_assessment.dominant_bloc` | Scènes | Injecter dans _load_shared_context |
| P3 | `behavior.singularites_locales` | Comportements | Consommer dans WindowGate |
| P3 | `vitesse` par devise | Forces | Enrichir EA MT4 (8 colonnes vitesse) |

## Audit de cohérence — 2026-07-07 (consolidation C-1)

Les 3 métriques P2 DORMANT listées initialement sont **toutes PROPAGÉES** dans
`_load_shared_context()` (`core/v9/principle_engine.py` lignes 657, 704-706) :
- `contexte_temporel_fenetre` ← `contexte_temporel_json.fenetre`
- `point_de_rupture_declencheur` ← `behaviors.point_de_rupture_declencheur`
- `est_variante` + `comportement_reference` ← `behaviors.est_variante` / `comportement_reference`

**Validé par** : `tests/test_context_propagation.py` (4/4 verts) — couvre présence
de tous les champs, fallbacks scène absente, et conformité au CONTEXT_CONTRACT.
Consommateurs YAML confirmés : `GRAMMAR_CONTEXTE.yaml`, `GRAMMAR_PULLBACK.yaml`,
`GRAMMAR_REGIME.yaml` (cf. `core/v9/principles/`).

**Statut des DORMANT restants (tous P3)** : 6 métriques, reportées post-Phase 11.
Réévaluation prévue à chaque clôture de phase (règle 27).

---

## DORMANT R27 — inventaire 2026-07-11

Application de DOCTRINE.md Règle 27 (« Champ DORMANT > 2 phases → promu ou
supprimé ») : inventaire daté des métriques DORMANT, avec
justification individuelle de maintien. Mis à jour 2026-07-11 (ménage Phase 13 CEO).

| # | Métrique | Priorité | Couche source | Justification |
|---|---|---|---|---|
| 1 | `cinematique.rotation_force.*` | P3 | Scènes | Données disponibles, pas de consommateur YAML identifié à ce jour. Réévaluation Phase 13. |
| 2 | `confluences_mtf.cascades_temporelles` | P3 | Scènes | Données disponibles, pas de consommateur YAML identifié à ce jour. Réévaluation Phase 13. |
| 3 | `zone.structure`, `zone.niveau` | P3 | Scènes | Données disponibles, pas de consommateur YAML identifié à ce jour. Réévaluation Phase 13. |
| 4 | `risk_assessment.dominant_bloc` | P3 | Scènes | Données disponibles, pas de consommateur YAML identifié à ce jour. Réévaluation Phase 13. |
| 5 | `behavior.singularites_locales` | P3 | Comportements | Données disponibles, pas de consommateur YAML identifié à ce jour. Réévaluation Phase 13. |
| 6 | `vitesse` par devise | P3 | Forces | Données disponibles, pas de consommateur YAML identifié à ce jour. Réévaluation Phase 13. |
| 7 | `persistance_confirmee` | P3 | Scènes (risk_assessment) | Retiré de GRAMMAR_PULLBACK.yaml Phase 14b (remplacé par `qualification is_not_null`). Conservé DB pour compatibilité replay. |
| 8 | `point_de_rupture_declencheur` | P3 | Comportements | PROPAGÉ dans `_load_shared_context()` mais jamais consommé par un YAML. Réévaluation Phase 13. |
| 9 | `est_variante` / `comportement_reference` | P3 | Comportements | PROPAGÉ dans `_load_shared_context()` mais jamais consommé par un YAML. Réévaluation Phase 13. |
| 10 | `contexte_temporel_fenetre` | P3 | Scènes (contexte_temporel) | PROPAGÉ dans `_load_shared_context()`, consommé par GRAMMAR_CONTEXTE. Maintenu PROPAGÉ. |
| 11 | `pliure_severite` | P3 | Scènes (cinématique) | PROPAGÉ dans `_load_shared_context()` mais jamais consommé par un YAML. Réévaluation Phase 13. |

---

## Règle de mise à jour

Ce fichier doit être mis à jour :
1. Quand une nouvelle métrique est ajoutée dans une couche
2. Quand `_load_shared_context()` est modifié
3. Quand un champ passe de DORMANT à PROPAGÉ
4. À chaque session de calibration ou d'audit

Si un champ DORMANT est délibérément conservé tel quel, la justification
doit être explicite (ex. "sera utilisé Phase 10", "dépend de calibration live").

---

## Audit 2026-07-14 (ZCode) — 30 champs posés jamais consommés

Généré automatiquement par comparaison `principle_engine._load_shared_context` vs
tous les YAML de `core/v9/principles/*.yaml`. Ces 30 champs sont posés dans le
contexte à chaque snapshot (coût de parse/cast) mais aucun YAML ne les référence.

**Action** : marquer DORMANT ici (R27). Soit créer un YAML qui les consomme, soit
les retirer de `_load_shared_context` pour réduire le bruit runtime.

| # | Champ | Action recommandée |
|---|---|---|
| 1 | `acceleration_vraie` | DORMANT — calculé par SceneBuilder, aucun YAML. Retirer si pas de plan Phase 13. |
| 2 | `adaptive_thresholds_enabled` | DORMANT — pseudo kill switch, jamais consommé. Retirer. |
| 3 | `cassure_direction` | DORMANT — aucun YAML. Réévaluer Phase 13. |
| 4 | `cassure_type` | DORMANT — aucun YAML. Réévaluer Phase 13. |
| 5 | `coalition_rotation_ancien_leader` | DORMANT — déjà tracé R27 #1, toujours sans consommateur. |
| 6 | `comportement_reference` | DORMANT — déjà tracé R27 #9. |
| 7 | `courbure` | DORMANT — aucun YAML. Réévaluer Phase 13. |
| 8 | `dispersion_velocite` | DORMANT — aucun YAML. Réévaluer Phase 13. |
| 9 | `est_variante` | DORMANT — déjà tracé R27 #9. |
| 10 | `exploitability_statut` | DORMANT — utilisé par scripts/ (paper trade) mais pas par YAML. |
| 11 | `force_value` | DORMANT — aucun YAML. Retirer. |
| 12 | `fragilite_detectee` | DORMANT — aucun YAML. Réévaluer Phase 13. |
| 13 | `heure_utc` | DORMANT — aucun YAML. Utilitaire potentiel. |
| 14 | `intensite` | DORMANT — aucun YAML (cf. GRAMMAR_EXTENSION gap). |
| 15 | `jour_semaine` | DORMANT — aucun YAML. Utilitaire potentiel. |
| 16 | `mean_reversion_zone` | DORMANT — aucun YAML. Réévaluer Phase 13. |
| 17 | `niveau_confiance` | DORMANT — aucun YAML direct (niveau_confiance_global aussi). |
| 18 | `niveau_confiance_global` | DORMANT — aucun YAML. |
| 19 | `phase` | DORMANT — aucun YAML. Ambigu (news_phase existe séparément). |
| 20 | `pliure_severite` | DORMANT — déjà tracé R27 #11. |
| 21 | `point_de_rupture_declencheur` | DORMANT — déjà tracé R27 #8. |
| 22 | `point_de_rupture_detecte` | DORMANT — aucun YAML. |
| 23 | `regime_type` | DORMANT — aucun YAML (regime_snapshots alimente zone_diagnostics). |
| 24 | `risk_off_score` | DORMANT — aucun YAML. |
| 25 | `risk_on_score` | DORMANT — aucun YAML. |
| 26 | `sens_transition` | DORMANT — aucun YAML. |
| 27 | `type_fenetre` | DORMANT — aucun YAML (window_statut est utilisé). |
| 28 | `velocite_moyenne` | DORMANT — déjà tracé R27 #6. |
| 29 | `vol_atr_pips` | DORMANT — posé par vol_regime (P6), aucun YAML consomme. |
| 30 | `vol_regime_level` | DORMANT — posé par vol_regime (P6), aucun YAML consomme. |

**Note** : `vol_atr_pips` et `vol_regime_level` sont des sous-produits de `vol_regime`
(P6, livré 2026-07-13). Le principe `vol_regime` est posé dans le contexte mais
seul `vol_regime` (le niveau string) est consommé par ADAPTIVE_VOL_GATE. Les
champs numériques `vol_atr_pips` et `vol_regime_level` attendent un consommateur.

**Champs DORMANT confirmés (déjà tracés R27)** : #6, #9, #21, #28, #8.
**Nouveaux DORMANT (22)** : les 22 autres, à réévaluer au prochain checkpoint de phase.

---

## Rectificatif 2026-07-16 (Claude CLI) — l'audit du 14/07 était YAML-only : les « 22 DORMANT » sont CONSOMMÉS côté ML

L'audit ZCode 2026-07-14 comparait `_load_shared_context` aux **seuls** YAML de
`core/v9/principles/*.yaml`. Il a donc conclu « DORMANT / à retirer » pour 22 champs.
**Ce périmètre était incomplet.** `_load_shared_context()` a **deux autres
consommateurs** en aval, vérifiés dans le code :

1. `core/v9/trader_mini_weigher.py:116` — `features = principle_engine._load_shared_context(...)`
   puis prédiction via le modèle `core/v9/models/trader_mini_baseline_v1.json`.
2. `scripts/v9_export_dataset.py:111` — exporte **tout** le contexte comme jeu de
   features ML (candidats pour le ré-entraînement de trader_mini).

**Preuve** : le champ `feature_names` de `trader_mini_baseline_v1.json` liste
**explicitement** 16 des 22 champs (acceleration_vraie, courbure, dispersion_velocite,
risk_on_score, risk_off_score, intensite=*, phase=*, sens_transition=*, heure_utc,
jour_semaine, niveau_confiance, niveau_confiance_global, fragilite_detectee,
point_de_rupture_detecte, exploitability_statut=*, coalition_rotation_ancien_leader=*).

**Conséquence** : retirer ces champs de `_load_shared_context` remplacerait
silencieusement leur valeur par `None`/0 dans le vecteur de features du modèle actif
(`flat.get(key)` → None) → **dégradation silencieuse de l'inférence trader_mini** et
appauvrissement du jeu exporté. C'est une régression réelle (R30 : pas d'altération de
la couche apprentissage sans DECISIONS_LOG ; décision schéma features = ressort de Søn).

### Reclassement des 22 champs

| Statut corrigé | Champs | Consommateur |
|---|---|---|
| **PROPAGÉ (feature ML active)** | acceleration_vraie, courbure, dispersion_velocite, risk_on_score, risk_off_score, intensite, phase, sens_transition, heure_utc, jour_semaine, niveau_confiance, niveau_confiance_global, fragilite_detectee, point_de_rupture_detecte, exploitability_statut, coalition_rotation_ancien_leader | `trader_mini_weigher` (dans `feature_names` du modèle) + `v9_export_dataset` |
| **PROPAGÉ (feature candidate export)** | force_value, regime_type, cassure_type, cassure_direction, mean_reversion_zone | `v9_export_dataset` (pool de features pour ré-entraînement) ; `regime_type` aussi lu par `trade_engine`/`pyramiding_engine` (via `decisions`, chemin distinct) |
| **Retirable (pseudo-flag, hors marché)** | adaptive_thresholds_enabled | Aucun consommateur de valeur ; reste un état de kill-switch. Conversion en variable locale possible — **différée** : impact sur le schéma du jeu exporté, décision couche apprentissage (Søn / R25'). |

**Décision de session (2026-07-16)** : **aucun retrait**. `_load_shared_context` reste
la source unique du vecteur de features ML — le stabiliser prime sur la réduction de
« bruit runtime » (le coût de parse est marginal, les champs viennent de lignes déjà
lues). Réévaluation du schéma features = prochaine décision Søn sur trader_mini.
