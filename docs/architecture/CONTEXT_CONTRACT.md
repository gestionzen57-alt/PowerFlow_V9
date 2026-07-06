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
| `bar_time` | int | PROPAGÉ | SceneBuilder._compute_cinematics (acceleration_vraie) |
| `stale` | bool | PROPAGÉ | toutes couches |
| `mid` | float | PROPAGÉ | PrincipleEngine (pf_mid) |
| `symbol` | str | PROPAGÉ | toutes couches |
| `timeframe` | str | PROPAGÉ | toutes couches |

### Lacune connue
- `vitesse` = devise de base du symbole uniquement (pas un vrai panier 8 devises).
  `velocite_moyenne` est donc un proxy d'une seule devise.
  **Levier P3** : enrichir EA MT4 pour envoyer `vitesse_*` × 8 devises.

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
| `fenetre` | str | DORMANT (P2) | PrincipleEngine ne l'injecte pas — à ajouter |

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
| `point_de_rupture.declencheur` | str | DORMANT (P2) | PrincipleEngine ne l'injecte pas — info qualitative |
| `similarite_score` | float\|None | PROPAGÉ | PrincipleEngine (via confiance_qualification bonus) |
| `cas_references` | list[dict] | DORMANT (P3) | Stocké DB uniquement |
| `singularites_locales` | list[str] | DORMANT (P3) | Stocké DB, jamais relu en aval |
| `variante_de_comportement_connu.est_variante` | bool | DORMANT (P2) | WindowGate ne le lit pas |
| `variante_de_comportement_connu.comportement_reference` | str | DORMANT (P2) | WindowGate ne le lit pas |

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
| `news_phase` | str | PROPAGÉ | Disponible pour conditions YAML — pas encore consommé (cadrage P2) |
| `news_distance_min` | int \| None | PROPAGÉ | Disponible pour conditions YAML — pas encore consommé (cadrage P2) |
| `news_importance` | str | PROPAGÉ | Disponible pour conditions YAML — pas encore consommé (cadrage P2) |
| `news_session_clean` | bool | PROPAGÉ | Disponible pour conditions YAML — pas encore consommé (cadrage P2) |

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

## Métriques DORMANT — récapitulatif priorisé

| Priorité | Métrique | Couche source | Action |
|---|---|---|---|
| P2 | `contexte_temporel.fenetre` | Scènes | Injecter dans _load_shared_context |
| P2 | `point_de_rupture.declencheur` | Comportements | Injecter dans _load_shared_context |
| P2 | `variante_de_comportement_connu` | Comportements | Lire dans WindowGate |
| P3 | `cinematique.rotation_force.*` | Scènes | Brancher sur signal_generator |
| P3 | `confluences_mtf.cascades_temporelles` | Scènes | Consommer dans WindowGate |
| P3 | `zone.structure`, `zone.niveau` | Scènes | Injecter dans _load_shared_context |
| P3 | `risk_assessment.dominant_bloc` | Scènes | Injecter dans _load_shared_context |
| P3 | `behavior.singularites_locales` | Comportements | Consommer dans WindowGate |
| P3 | `vitesse` par devise | Forces | Enrichir EA MT4 (8 colonnes vitesse) |

---

## Règle de mise à jour

Ce fichier doit être mis à jour :
1. Quand une nouvelle métrique est ajoutée dans une couche
2. Quand `_load_shared_context()` est modifié
3. Quand un champ passe de DORMANT à PROPAGÉ
4. À chaque session de calibration ou d'audit

Si un champ DORMANT est délibérément conservé tel quel, la justification
doit être explicite (ex. "sera utilisé Phase 10", "dépend de calibration live").
