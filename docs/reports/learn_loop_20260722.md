# Rapport Learn Loop — Système Prédictif V9

**Date** : 2026-07-22 22:05:57 UTC
**Status** : warning

## Ingestion
- Décisions résolues ingérées : **9371**
- Transitions markov ingérées : **217**
- Cellules contextuelles mises à jour : **172**

## Fit (Platt + Beta)
- n_fit = 9371
- n_cells = 172
- global_wr = 0.8131
- Platt(a, b) = (1.298591, 0.254656)
- Brier Score = 0.149103
- Log-loss = 0.472729
- ECE = 6.7347%
- BSS = 0.0187

## Backtest uplift
- Trades baseline : 9371
- Trades filtrés : 2888
- WR baseline : 81.3100%
- WR filtré : 97.2600%
- **Δ WR** : **+15.95 pts**
- Pips baseline : +45676.2
- Pips filtré : +24802.1
- **PF filtré** : **56.511**

## Walk-forward (cross-validation temporelle)
- n_folds = 5
- n_test_total = 9371
- **WR uplift mean** : **+1.22 pts**
- WR uplift min = -25.78
- WR uplift max = +22.32
- WR uplift stddev = 15.68

### Détail par fold
| Fold | n_test | n_enter | WR base | WR filtré | Δ WR (pts) |
|---:|---:|---:|---:|---:|---:|
| 0 | 1874 | 73 | 68.25% | 42.47% | -25.78 |
| 1 | 1874 | 1333 | 98.29% | 98.12% | -0.17 |
| 2 | 1874 | 1428 | 98.56% | 99.72% | +1.16 |
| 3 | 1874 | 34 | 73.80% | 82.35% | +8.55 |
| 4 | 1875 | 20 | 67.68% | 90.00% | +22.32 |

## ⚠️ Alertes
- bss_low:0.019<0.1
- ece_high:0.0673>0.05
- walk_forward_high_variance:15.68pts

---
*Rapport généré par `core/v9/v9_learn_loop.py run_learn_cycle`.*