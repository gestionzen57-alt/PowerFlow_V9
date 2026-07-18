# Rapport Backtest Uplift — Calibration Bayésienne V9

**Date** : 2026-07-18
**Module** : `core/v9/v9_bayesian_predictor.py` (Doctrine R33)
**Méthode** : Platt calibration globale + Beta-Binomial par cellule contextuelle
**Cible** : WR uplift ≥ +10 pts et PF uplift ≥ +1.5

---

## Configuration

- Décisions chargées : **8771**
- Décisions baseline (tous trades) : **8771**
- Décisions filtrées (calibrated_proba ≥ 0.55) : **8747**
- Filtrage : on ne garde que les trades où `predict.recommended_action == "enter"`

---

## Métriques Trading

| Métrique | Baseline (declared) | Calibrated (filtré) | Uplift |
|---|---:|---:|---:|
| **Win Rate** | 84.0725% | 84.2575% | **+0.18 pts** |
| **Trades** | 8771 | 8747 | -24 |
| **Pips cumulés** | +46628.6 | +46694.6 | +66.0 |
| **Avg pips/trade** | +5.316 | +5.338 | +0.022 |
| **Profit Factor** | 4.894 | 4.925 | **+0.031** |

---

## Métriques de Calibration

| Métrique | Baseline | Calibrated | Δ (négatif = mieux) |
|---|---:|---:|---:|
| **Brier Score** | 0.131267 | 0.120411 | -0.010856 |
| **Brier Skill Score** | 0.0197 | 0.1008 | +0.0811 |
| **Log-loss** | 1.021107 | 0.397712 | -0.623395 |
| **ECE** | 9.0928% | 4.5817% | -4.5111% |
| **Accuracy** | 84.07% | 84.07% | +0.00% |

---

## Verdict CEO

> **❌ NO-GO — uplift insuffisant (+0.2pts WR, +0.03 PF)**

---

## Méthodologie

### Modèle mathématique

1. **Beta-Binomial par cellule** : `Beta(α=wins+1, β=losses+1)` avec prior
   non-informatif `Beta(1, 1)`. Pour 8771 décisions GBPUSD M15 NEUTRE,
   on a typiquement `α=7300, β=1471` → `mean ≈ 0.832`, `std ≈ 0.004`.

2. **Calibration Platt** : `P(is_win | conf) = σ(a · conf_norm + b)`,
   fit par descente de gradient sur log-loss (200 iter, lr=0.05, L2=1e-4).

3. **Combinaison** : `combined = 0.6 · Platt + 0.4 · Beta_mean` (Platt ajuste,
   Beta régularise).

4. **Décision** : `action = "enter"` si `combined ≥ edge_threshold` ET
   `edge = combined · TP - (1-combined) · SL > 0`.

### Fichiers source

- `core/v9/v9_bayesian_predictor.py` — module principal
- `tests/test_v9_bayesian_predictor.py` — 57 tests verts
- `data/v9_calibration.db` — DB de calibration (générée par --fit)
- `data/v9_forces.db` — DB live source (lecture seule)

### Doctrine

- **R33** : Système Prédictif — anticipation par modèles probabilistes seniors.
- **R2** : additif (jamais destructif).
- **R6** : défensif (try/except + fallback prior_only si erreur DB).
- **R8** : DB calibration séparée.
- **R18** : code pur, zéro LLM.

---

*Rapport généré par `scripts/v9_bayesian_fit.py --backtest` le 2026-07-18.*
