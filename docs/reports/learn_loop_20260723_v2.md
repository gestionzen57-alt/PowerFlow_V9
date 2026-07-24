# Rapport Learn Loop — Système Prédictif V9

**Date** : 2026-07-24 05:08:09 UTC
**Status** : warning

## Ingestion
- Décisions résolues ingérées : **1029**
- Transitions markov ingérées : **252**
- Cellules contextuelles mises à jour : **198**

## Fit (Platt + Beta)
- n_fit = 9452
- n_cells = 199
- global_wr = 0.6974
- Platt(a, b) = (0.98876, -0.069269)
- Brier Score = 0.208479
- Log-loss = 0.607065
- ECE = 10.8895%
- BSS = 0.0121

## Backtest uplift
- Trades baseline : 9452
- Trades filtrés : 9255
- WR baseline : 69.7400%
- WR filtré : 70.7500%
- **Δ WR** : **+1.01 pts**
- Pips baseline : +55292.5
- Pips filtré : +55962.4
- **PF filtré** : **2.984**

## Walk-forward (cross-validation temporelle)
- n_folds = 5
- n_test_total = 9452
- **WR uplift mean** : **+1.81 pts**
- WR uplift min = -0.00
- WR uplift max = +8.41
- WR uplift stddev = 3.31

### Détail par fold
| Fold | n_test | n_enter | WR base | WR filtré | Δ WR (pts) |
|---:|---:|---:|---:|---:|---:|
| 0 | 1890 | 1815 | 70.63% | 71.13% | +0.49 |
| 1 | 1890 | 1889 | 84.50% | 84.54% | +0.04 |
| 2 | 1890 | 1888 | 91.32% | 91.42% | +0.10 |
| 3 | 1890 | 1888 | 49.05% | 49.05% | -0.00 |
| 4 | 1892 | 1405 | 53.22% | 61.64% | +8.41 |

## ⚠️ Alertes
- bss_low:0.012<0.1
- ece_high:0.1089>0.05
- wr_uplift_low:1.01<5.0

---
*Rapport généré par `core/v9/v9_learn_loop.py run_learn_cycle`.*