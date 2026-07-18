---
name: powerflow-v9-predictive-senior
description: "Prédicteur bayésien calibré (Beta-Binomial + Platt + Brier) — transforme la confiance déclarée du signal_generator en probabilité réelle de gain par contexte opérationnel. Fondation mathématique du Système Prédictif V9 (Doctrine R33)."
category: trading
tags: [v9, predictif, bayesien, platt-calibration, beta-binomial, brier-score, r33, phase-e, systeme-anticipatif]
statut: actif
derniere_maj: 2026-07-18
version: 0.1.0
note_chantier: aligne HEAD (post-audit DB 2026-07-18 — 8771 décisions résolues, WR global 84%)
auteur: ZCode sur motion CEO Søn 2026-07-18 (« crée toi une skill de probabilité expert senior »)
---

# PowerFlow V9 — Predictive Senior (Bayesian Predictor)

## Purpose (Philosophie)

Le système V9 produit un score `confiance ∈ [0, 100]` par signal. **Ce score n'est PAS calibré** : conf=80 ne signifie pas 80 % de chance de gain.

**L'audit du 2026-07-18 le prouve** : sur les 8771 décisions résolues :
- WR global = 84.07 %
- Brier naïve (= WR·(1-WR)) = 0.134 — marge significative d'amélioration par calibration
- Aucun mécanisme de calibration Platt par cellule contextuelle

**Ce skill + module** transforme la confiance déclarée en **probabilité réelle de gain**, conditionnellement au contexte `(symbol, regime, phase, vol_atr_bucket)` et au(x) principe(s) ayant déclenché le signal.

**Doctrine** : R33 « Système Prédictif » — anticipation par modèles probabilistes seniors.

## Architecture mathématique

### 1. Modèle Beta-Binomial par cellule

Pour chaque cellule contextuelle `(symbol, timeframe, regime_type, phase, vol_atr_bucket)` :

```
Prior : Beta(α₀, β₀) = Beta(1, 1)         # non-informatif (uniforme)
Data  : w wins, l losses
Post  : Beta(α = w + 1, β = l + 1)
```

- **Espérance** : `E[p] = α/(α+β)` = probabilité moyenne de gain
- **Variance** : `Var[p] = αβ/[(α+β)²(α+β+1)]` — décroît avec n
- **IC95%** : approx. normale `mean ± 1.96·std` (valide pour α, β ≥ 5)

**Pourquoi Beta** : distribution conjuguée pour la Bernoulli, support [0,1], shrinkage naturel vers 0.5 pour n petit (évite le sur-fit).

### 2. Calibration Platt

Transformation logistique de la confiance déclarée :

```
P(is_win | conf) = σ(a · conf_norm + b)
avec conf_norm = conf / 100 ∈ [0, 1]
σ(z) = 1 / (1 + exp(-z))
```

Fit par descente de gradient (200 iter, lr=0.05, L2=1e-4) maximisant la log-vraisemblance :
```
LL = Σ [o · log(σ(z)) + (1-o) · log(1-σ(z))]
```

**Platt local** : si cellule a n_resolved ≥ 30, on utilise Platt global pondéré par shrinkage :
```
Platt_local = (n/60) · Platt_global   # a_eff = a_global · shrink
```

### 3. Combinaison Platt + Beta

```
combined = 0.6 · Platt_proba + 0.4 · Beta_mean
```

- 60 % Platt (ajustement fin sur les confiances déclarées)
- 40 % Beta (régularisation bayésienne, évite le sur-fit Platt)

`confidence_in_calibration = min(1.0, n_resolved / 100)` — qualité statistique du pattern.

### 4. Métriques de calibration

| Métrique | Formule | Cible | Baseline naïve |
|---|---|---|---|
| **Brier Score** | `(1/n) Σ (p_i - o_i)²` | < 0.10 | 0.134 |
| **Brier Skill Score** | `1 - BS/BS_naive` | > 0 | 0 |
| **Log-loss** | `-(1/n) Σ [o·log(p) + (1-o)·log(1-p)]` | < 0.35 | log(2) = 0.693 |
| **ECE** (Expected Calibration Error) | `Σ |acc_bin - conf_bin| · (n_bin/n)` | < 5 % | ~15-20 % |
| **Accuracy** | `mean((p > 0.5) == o)` | > WR global | WR global |

## Le module `core/v9/v9_bayesian_predictor.py`

### API publique

```python
from core.v9.v9_bayesian_predictor import (
    predict,                    # Prédit un signal
    fit_from_decisions_db,      # Fit depuis la DB live
    batch_score,                # Score un batch de signaux
    beta_posterior_from_counts, # Construit Beta(α, β) depuis w, l
    fit_platt,                  # Fit Platt (a, b) par descente de gradient
    compute_calibration_metrics, # Calcule Brier + ECE + log-loss
    init_calibration_db,        # Crée data/v9_calibration.db
)

# Fit (à appeler dans un cron quotidien ou après chaque batch résolu)
result = fit_from_decisions_db(
    db_path="data/v9_forces.db",
    calibration_db="data/v9_calibration.db",
)
# → {"n_fit": 8771, "n_cells": 50, "platt_global": {...}, "global_wr": 0.84, ...}

# Predict (à appeler avant chaque décision trade)
prediction = predict(
    symbol="GBPUSD",
    timeframe="M15",
    regime_type="NEUTRE",
    phase="culmination",
    vol_atr_pips=3.5,
    declared_confiance=80,    # sortie du signal_generator
    tp_pips=10.0,
    sl_pips=15.0,
    edge_threshold=0.55,       # proba min pour "enter"
)
# → Prediction(calibrated_proba=0.74, edge=+5.4p, recommended_action="enter", ...)
```

### Sortie `Prediction`

| Champ | Type | Signification |
|---|---|---|
| `declared_confiance` | int | Confiance brute 0-100 (signal_generator) |
| `calibrated_proba` | float | P(is_win) ∈ [0, 1] — la vraie prédiction |
| `beta_posterior` | BetaPosterior \| None | Distribution Beta(α, β) de la cellule |
| `platt_used` | str | `"global"` \| `"local_<symbol>"` \| `"prior_only"` \| `"error_db"` |
| `confidence_in_calibration` | float | 0-1, qualité statistique (n_resolved / 100) |
| `edge` | float | `p · TP - (1-p) · SL` (expected value par unité de risque) |
| `recommended_action` | str | `"enter"` \| `"reduce_size"` \| `"skip"` |
| `rationale` | str | Explication détaillée (debug) |

### Décision (action)

```python
if calibrated_proba >= edge_threshold and edge > 0:
    action = "enter"
elif calibrated_proba >= 0.5 and edge > 0:
    action = "reduce_size"     # on trade avec sizing réduit
else:
    action = "skip"
```

`edge_threshold` par défaut = 0.55. **On n'entre dans un trade que si la probabilité calibrée de gain dépasse 55 % ET que l'espérance est positive.**

## Activation

**Kill switch** : `V9_BAYESIAN_PREDICTOR_ENABLED` (défaut `1` — APPLY direct sur motion CEO 2026-07-18).

**Workflow** :
1. **Une fois par jour** (cron `V9_BayesianFitLoop` recommandé) : `python scripts/v9_bayesian_fit.py`
2. **Avant chaque trade** (hook dans `trade_engine.process`) : `predict(...)` retourne `recommended_action`

## Schéma DB (`data/v9_calibration.db`)

```sql
CREATE TABLE cell_stats (
    symbol TEXT, timeframe TEXT, regime_type TEXT, phase TEXT, vol_atr_bucket TEXT,
    n_resolved INTEGER, n_wins INTEGER, n_losses INTEGER,
    sum_conf REAL, last_updated_ts REAL,
    PRIMARY KEY (symbol, timeframe, regime_type, phase, vol_atr_bucket)
);

CREATE TABLE platt_global (
    id INTEGER PRIMARY KEY DEFAULT 1,
    a REAL, b REAL, n_fit INTEGER, log_likelihood REAL,
    last_updated_ts REAL
);

CREATE TABLE calibration_meta (
    key TEXT PRIMARY KEY, value TEXT
);
```

## Volet doctrinal (R33)

| Règle | Application |
|---|---|
| R2 | Additif (`predict() → Prediction`), jamais destructif |
| R6 | Try/except DB error → fallback `prior_only` (proba=0.5, action=skip) |
| R7 | 57 tests verts (`tests/test_v9_bayesian_predictor.py`) |
| R8 | DB séparée `v9_calibration.db`, lecture seule sur `v9_forces.db` |
| R18 | Code pur, 100 % stdlib (sqlite3 + math), zéro LLM |
| R23 | Principes YAML consommateurs : aucun requis (le module est autonome) |
| R33 | **Doctrine du Système Prédictif** (cf. SOUL.md) |

## Quand invoquer cette skill

- **Søn demande** « est-ce que le système peut prédire ? », « WR plus performant ? », « skill de probabilité expert »
- **Audit calibration** : tu veux mesurer si la confiance déclarée matche le WR réel
- **Conception nouveau signal** : tu veux savoir si conf=80 vaut 80 % de gain dans CE contexte
- **Backtest uplift** : tu veux mesurer le gain d'ajouter la calibration Platt au pipeline
- **Discussion stratégique** : tu veux comparer Platt vs Isotonic vs Beta seul

## Diagnostic en 5 commandes

```bash
# 1. Fit calibration depuis la DB live
python scripts/v9_bayesian_fit.py --db data/v9_forces.db

# 2. Affiche les métriques de calibration
python scripts/v9_bayesian_fit.py --db data/v9_forces.db --stats

# 3. Predict dry-run pour un contexte
python -m core.v9.v9_bayesian_predictor predict \
    --symbol GBPUSD --timeframe M15 --regime NEUTRE \
    --phase culmination --vol-atr 3.5 --conf 80

# 4. Batch score sur les décisions résolues
python scripts/v9_bayesian_backtest.py --db data/v9_forces.db

# 5. Tests
./.venv/Scripts/pytest.exe tests/test_v9_bayesian_predictor.py -v
```

## Anti-patterns à éviter

| Anti-pattern | Pourquoi c'est mauvais | Alternative |
|---|---|---|
| Confiance déclarée = probabilité réelle | La confiance est déclarée par le moteur, pas mesurée | Toujours calibrer via Platt ou Beta |
| Prédire conf=80 ⇒ entrer | Sur-fit si la calibration locale n'est pas faite | Utiliser `calibrated_proba` + `edge` |
| Markov d'ordre 2 sur phase | État absorbant (89 % culmination), signal marginal | Beta-Binomial par cellule contextuelle |
| ML lourd (XGBoost, réseaux) sur 8771 obs | Overfit garanti, R18 strict | Beta + Platt, 100 % stdlib, math senior |
| Ignorer ECE | Mauvaise calibration = confiance menteuse | Toujours reporter ECE dans les rapports |

## Métaphore senior (Søn)

> *« La confiance d'un moteur, c'est comme un baromètre qu'on n'a jamais étalonné.
> Il dit 80, mais il dit 80 par tous les temps — tempête comme grand beau.
> Platt, c'est l'étalonnage. Beta, c'est l'incertitude sur l'étalonnage.
> Brier, c'est la note : plus c'est bas, plus on peut faire confiance au baromètre.
> Et l'edge, c'est ce qui reste dans ta poche après avoir parié :
> P(gain) · TP - (1-P(gain)) · SL. Si l'edge est négatif,
> même un baromètre bien étalonné te dit de rester sur le banc. »*

## Roadmap (Phase E — Système Prédictif)

- [x] **E.1** Module `v9_bayesian_predictor.py` + skill (2026-07-18)
- [x] **E.2** Module `v9_cycle_memory.py` + intégration (2026-07-18)
- [x] **E.3** Module `v9_meta_strategy_optimizer.py` (consomme cycle memory + bayesian)
- [ ] **E.4** Hook dans `trade_engine.process` : `predict() → recommended_action`
- [ ] **E.5** Backtest uplift sur 8771 décisions résolues (cible +10pts WR, +1.5 PF)
- [ ] **E.6** Cron `V9_BayesianFitLoop` quotidien
- [ ] **E.7** Dashboard live affichant `calibrated_proba` + edge par trade

## Références

- `core/v9/v9_bayesian_predictor.py` — module principal
- `tests/test_v9_bayesian_predictor.py` — 57 tests verts
- `docs/architecture/PREDICTIVE_ENGINE.md` — doc d'architecture (à compléter)
- `workspace/perplexity/memory/DECISIONS_LOG.md` §2026-07-18 « Motion CEO Predictive Engine »
- `docs/DOCTRINE.md` R33 « Système Prédictif » (à ajouter)

---

*Skill rédigée le 2026-07-18 par ZCode sur motion CEO Søn « crée toi une skill de probabilité expert senior ».*
*"La confiance sans calibration, c'est de l'ignorance habillée en science."*
