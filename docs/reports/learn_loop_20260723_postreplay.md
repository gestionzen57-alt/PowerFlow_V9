# Rapport Learn Loop — Système Prédictif V9

**Date** : 2026-07-24 05:05:01 UTC
**Status** : warning

## Ingestion
- Décisions résolues ingérées : **9452**
- Transitions markov ingérées : **252**
- Cellules contextuelles mises à jour : **200**

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
- Trades filtrés : 0
- WR baseline : 69.7400%
- WR filtré : 0.0000%
- **Δ WR** : **-69.74 pts**
- Pips baseline : +55292.5
- Pips filtré : +0.0
- **PF filtré** : **inf**

## Walk-forward (cross-validation temporelle)
- n_folds = 5
- n_test_total = 9452
- **WR uplift mean** : **-69.74 pts**
- WR uplift min = -91.32
- WR uplift max = -49.05
- WR uplift stddev = 16.65

### Détail par fold
| Fold | n_test | n_enter | WR base | WR filtré | Δ WR (pts) |
|---:|---:|---:|---:|---:|---:|
| 0 | 1890 | 0 | 70.63% | 0.00% | -70.63 |
| 1 | 1890 | 0 | 84.50% | 0.00% | -84.50 |
| 2 | 1890 | 0 | 91.32% | 0.00% | -91.32 |
| 3 | 1890 | 0 | 49.05% | 0.00% | -49.05 |
| 4 | 1892 | 0 | 53.22% | 0.00% | -53.22 |

## ⚠️ Alertes
- bss_low:0.012<0.1
- ece_high:0.1089>0.05
- wr_uplift_low:-69.74<5.0
- walk_forward_negative:-69.74pts
- walk_forward_high_variance:16.65pts

---
*Rapport généré par `core/v9/v9_learn_loop.py run_learn_cycle`.*