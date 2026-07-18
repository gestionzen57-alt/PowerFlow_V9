# Rapport Learn Loop — Système Prédictif V9

**Date** : 2026-07-18 12:40:32 UTC
**Status** : warning

## Ingestion
- Décisions résolues ingérées : **8771**
- Transitions markov ingérées : **114**
- Cellules contextuelles mises à jour : **99**

## Fit (Platt + Beta)
- n_fit = 8771
- n_cells = 99
- global_wr = 0.8407
- Platt(a, b) = (1.390771, 0.345498)
- Brier Score = 0.130958
- Log-loss = 0.427986
- ECE = 0.9784%
- BSS = 0.0220

## Backtest uplift
- Trades baseline : 8771
- Trades filtrés : 6698
- WR baseline : 84.0700%
- WR filtré : 91.4800%
- **Δ WR** : **+7.40 pts**
- Pips baseline : +46628.6
- Pips filtré : +44449.3
- **PF filtré** : **7.185**

## Walk-forward (cross-validation temporelle)
- n_folds = 5
- n_test_total = 8771
- **WR uplift mean** : **+5.36 pts**
- WR uplift min = -0.76
- WR uplift max = +21.46
- WR uplift stddev = 8.31

### Détail par fold
| Fold | n_test | n_enter | WR base | WR filtré | Δ WR (pts) |
|---:|---:|---:|---:|---:|---:|
| 0 | 1754 | 730 | 66.08% | 87.53% | +21.46 |
| 1 | 1754 | 1703 | 98.18% | 98.41% | +0.24 |
| 2 | 1754 | 1704 | 98.92% | 99.53% | +0.61 |
| 3 | 1754 | 1456 | 88.65% | 93.89% | +5.23 |
| 4 | 1755 | 1105 | 68.55% | 67.78% | -0.76 |

## ⚠️ Alertes
- bss_low:0.022<0.1
- walk_forward_high_variance:8.31pts

---
*Rapport généré par `core/v9/v9_learn_loop.py run_learn_cycle`.*