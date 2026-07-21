# BAYESIAN_CALIBRATOR — Calibration bayésienne V9 (Axe 1.1 / J1)

> Module : `core/v9/bayesian_calibrator.py` (+ lecteur DB `core/v9/_bayesian_db.py`)
> Kill switch : `V9_BAYESIAN_CALIBRATOR_ENABLED` (défaut **OFF**, R25')
> Statut : livré 2026-07-21, **non câblé** dans le pipeline live (additif R2).

## 1. Problème

Le `signal_generator` produit une **confiance déclarée** (entier 0-100) qui
ne reflète pas la **probabilité réelle de gain**. Preuve empirique (smoke live,
fenêtre 7 j, 2026-07-21) : la confiance déclarée est *anti-calibrée* —

| bucket confiance | n | WR observé | écart |
|---|---|---|---|
| 0.6–0.7 | 132 | 0.523 | −0.144 |
| 0.7–0.8 | 62 | 0.516 | −0.212 |
| 0.8–0.9 | 12 | 0.583 | −0.242 |
| 0.9–1.0 | 424 | 0.467 | **−0.531** |

Brier global 7 j = **0.4484** (pire que l'aléatoire 0.25). Sans calibration,
on ne distingue pas un edge d'un bruit et tout sizing Kelly est biaisé.

## 2. Modèle mathématique — Beta-Binomial conjugué

Chaque contexte `(principle × symbol × timeframe × session × regime)` a un WR
inconnu θ. Les issues WIN/LOSS sont des Bernoulli(θ). Le conjugué de la
vraisemblance binomiale est la loi **Beta** :

```
prior      θ ~ Beta(α₀, β₀)
posterior  θ | (w wins, l losses) ~ Beta(α₀ + w, β₀ + l)
```

- **Moyenne** : `E[θ] = α / (α+β)`
- **Variance** : `Var[θ] = αβ / ((α+β)²(α+β+1))` — décroît en ~1/n (l'incertitude
  se resserre avec les observations)
- **Intervalle crédible 95 %** : quantiles 2.5 % / 97.5 % de la Beta
- **P(edge réel)** : `P(θ > s) = 1 − CDF_Beta(s)`

### Prior uniforme Beta(1,1)

`α₀ = β₀ = 1` → prior **uniforme** sur [0,1] : aucune préférence a priori pour
un WR plutôt qu'un autre (le maximum d'entropie sur [0,1]). Choix conservateur
et non-informatif : un contexte sans donnée retombe sur `mean = 0.5` (pièce
équilibrée), et un contexte à faible n reste tiré vers 0.5 tant que les
observations ne dominent pas le prior (régularisation naturelle contre le
sur-apprentissage des petits échantillons).

## 3. Implémentation — pure stdlib, scipy optionnel

Le calcul de la CDF/quantile Beta utilise la **fonction beta incomplète
régularisée** `I_x(a,b)` implémentée en pur Python (continued fraction,
Numerical Recipes §6.4, précision ~1e-12) — `_betai` / `_beta_cdf` / `_beta_ppf`.

`scipy.stats.beta` est **détecté** (`_HAS_SCIPY`) mais **désactivé par défaut**.
Rationnel R6 : sur l'hôte de prod, scipy s'appuie sur OpenBLAS qui peut échouer
par OOM (`abort()` non rattrapable en Python) → routing scipy risqué en
production. Il n'est activé que sur opt-in explicite `V9_BAYESIAN_USE_SCIPY=1`
(bench / validation croisée). Le fallback pur est validé à 1e-9 contre scipy
(test `test_pure_python_betai_matches_scipy_when_available`).

## 4. Workflow : fit → calibrate → size → kill switch

```
                         ┌───────────────────────────┐
  decisions (mode=ro) ─▶ │ read_context_aggregates    │  explosion principes_json,
  DYNAMIC, is_win≠NULL   │ (fenêtre 30 j, min_n)      │  session dérivée du timestamp
                         └────────────┬──────────────┘
                                      ▼
                         ┌───────────────────────────┐
                         │ BayesianCalibrator          │
                         │  fit_context(ctx) → Beta    │
                         │  fit_all_contexts(min_n=20) │
                         └────────────┬──────────────┘
                          ┌───────────┼────────────────┐
                          ▼           ▼                ▼
                 is_edge_real   kelly_fraction   calibrate_confidence
                 (H0: WR≤0.5)   (sizing borné)   (signal_generator)
```

- **`fit_context(context_key)`** — `context_key = (principle, symbol, timeframe,
  session, regime)`. Contexte inconnu → prior Beta(1,1), `n=0` (jamais d'exception).
- **`is_edge_real(post, threshold=0.5, conf=0.95)`** → `(is_edge, p_value)`.
  `is_edge = P(WR>threshold) ≥ conf`. `p_value = P(WR ≤ threshold) = CDF_Beta(threshold)`
  (masse postérieure sous H0 ; petit = edge crédible).
- **`kelly_fraction(post, rr=1.0, fraction=0.25, floor=0.3, cap=2.0)`** →
  **multiplicateur de taille** (voir §5), ou `None` (garde-fous).
- **`calibrate_confidence(raw_conf, ctx, calibrator)`** (dans `signal_generator`) —
  renvoie `posterior.mean` si `n ≥ 20`, sinon fallback `raw_conf/100` (R6).
  **ADDITIF, non câblé** dans `generate()`.

## 5. Kelly fractionnel — sémantique de multiplicateur

Kelly complet : `f_full = (p·b − q) / b` avec `p = posterior.mean`, `q = 1−p`,
`b = rr` (reward:risk). On renvoie un **multiplicateur de taille** :

```
multiplier = clamp( f_full / fraction , floor , cap )
```

`fraction` (0.25) est la **référence de Kelly-complet cartographiée sur 1.0×** :
un contexte dont l'edge vaut 25 % du Kelly complet trade à la taille de base 1.0×.

> **Divergence assumée vs la spec littérale** (`f* = (p·b−q)/b × fraction`) :
> `f_full ∈ (−∞, p) < 1` **toujours**, donc borner le Kelly brut par un `cap=2.0`
> n'aurait aucun effet. Le multiplicateur, lui, peut légitimement dépasser 1.0,
> ce qui rend `floor 0.3` / `cap 2.0` sensés. Tracé DECISIONS_LOG §J1.

Garde-fous (R6, kill statistique) — `kelly_fraction` renvoie `None` si :
- `n < 20` (échantillon trop court),
- `P(WR>0.5) < 0.6` (edge non confirmé),
- `f_full ≤ 0` ou `rr ≤ 0` (pas d'edge).

## 6. Brier score & calibration plot

- `BrierScorer.brier_score(preds, outcomes)` = `mean((p−y)²)` — 0 parfait,
  0.25 aléatoire. **Cible < 0.20.**
- `reliability_table(preds, outcomes, n_bins=10)` — toujours `n_bins` déciles
  (bins vides inclus) ; `mean_pred ≈ mean_outcome` = bien calibré.
- `platt_scale(raw, outcomes)` → `(A, B)` de `sigmoid(A·x + B)` (régression
  logistique 1-D, descente de gradient pure). `apply_platt(x, A, B)` transforme
  une confiance brute en probabilité calibrée.

## 7. Limites

- **n < 20** → fallback (prior domine ; pas de sizing). Régularisation voulue.
- **Régime changeant / non-stationnarité** — le WR 30 j peut masquer une
  dérive récente (cf. Brier 7 j anti-calibré alors que les contextes 30 j
  affichent des WR élevés). **Recommandation : re-fit quotidien** + surveiller
  le Brier court terme comme signal d'alerte de dérive.
- **`resolution_strategy='DYNAMIC'` seulement** — les 330 `SKIPPED` (is_win=0
  par convention, non de vraies pertes) sont exclus pour ne pas polluer les WR.
- **Contexte principe-explosé** — une décision multi-principes compte dans le
  contexte de chaque principe (pas d'attribution causale ; c'est une
  co-occurrence, pas un test d'indépendance des principes).

## 8. Activation

`V9_BAYESIAN_CALIBRATOR_ENABLED=0` par défaut. Le module est de l'**outillage
d'analyse** (smoke `scripts/v9_bayesian_calibrator_smoke.py`) + une fonction
`calibrate_confidence` **inerte** (non consommée par `generate()`). Promotion
ACTIVE (consommation de la confiance calibrée / du sizing Kelly par le pipeline)
= **motion CEO séparée** (R25' strict). Aucune écriture DB, aucune migration.
```
python scripts/v9_bayesian_calibrator_smoke.py --min-n 20 --top 10
```
(sur Windows : préfixer `PYTHONIOENCODING=utf-8` pour l'affichage des accents.)
