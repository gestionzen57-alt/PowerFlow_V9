# Saut quantique agressif — bilan backtest (2026-07-18)

> **Recadré** (motion CEO 2026-07-18) : couche backtest lecture-seule, mesurée sur les décisions RÉELLES, magnitude reconstruite depuis l'OHLC, garde-fou short régime-dépendant. **Aucune activation live proposée.**

## Résumé exécutif

- Population : **8771 décisions résolues** (WR base 84.1 %), horizon 16 barres, first-touch conservateur (SL-first si ambigu).
- Baseline : +46629 pips, PF 4.89, WR 87.6 %, maxDD -6853.
- Stack agressif complet : +57205 pips, PF 185.40, WR 97.8 %, maxDD -100.
- Δ pips vs baseline : **+10576**.
- **Verdict : NO-GO — instabilité walk-forward (variance WR 45.3 pts > 15 pts) : edge période-spécifique, non stationnaire. Uplift pips réel mais non exploitable tel quel.**


## Comparatif variantes

| Variante | Trades | WR | PF | Pips | maxDD | Sharpe |
|---|---|---|---|---|---|---|
| Baseline (résolution réelle) | 8416 | 87.6% | 4.89 | +46629 | -6853 | 0.769 |
| Agressif TP/SL (path) | 8770 | 74.4% | 5.12 | +154217 | -29486 | 0.859 |
| + Sizing Kelly | 8770 | 74.4% | 5.12 | +46265 | -8846 | 0.859 |
| + Garde-fou short (régime) | 6560 | 97.8% | 169.93 | +56916 | -135 | 4.779 |
| + Pyramiding (stack complet) | 6560 | 97.8% | 185.40 | +57205 | -100 | 4.608 |

## Walk-forward 5-fold (stack complet, temporel)

| Fold | Trades | WR | PF | Pips | maxDD | Sharpe |
|---|---|---|---|---|---|---|
| Fold 1 | 1478 | 98.0% | 113.45 | +12981 | -48 | 4.131 |
| Fold 2 | 1745 | 99.9% | 3046.47 | +15719 | -5 | 20.059 |
| Fold 3 | 1735 | 99.9% | 4843.00 | +15630 | -3 | 21.329 |
| Fold 4 | 1353 | 99.8% | 1367.96 | +12159 | -6 | 14.084 |
| Fold 5 | 249 | 54.6% | 5.03 | +716 | -100 | 0.554 |

Variance WR inter-fold : **45.3 pts** (seuil d'arrêt mission : 15 pts).


## Magnitude réelle reconstruite (OHLC, top cellules)

| Cellule | n | MFE p50 | MFE p75 | MFE p90 | MAE p90 |
|---|---|---|---|---|---|
| GBPUSD|M15|HIGH | 8344 | 65.3 | 67.4 | 69.5 | 76.2 |
| GBPUSD|M5|MEDIUM | 160 | 5.5 | 12.2 | 15.2 | 13.7 |
| USDJPY|M5|MEDIUM | 32 | 5.0 | 8.1 | 9.0 | 24.3 |
| GBPUSD|M5|LOW | 25 | 3.8 | 6.7 | 10.2 | 9.7 |
| GBPUSD|M15|MEDIUM | 22 | 8.9 | 13.1 | 16.8 | 20.8 |
| EURUSD|M5|MEDIUM | 18 | 5.8 | 10.8 | 12.2 | 5.5 |
| USDCHF|M5|MEDIUM | 18 | 5.0 | 6.5 | 8.7 | 10.6 |
| GBPUSD|H1|HIGH | 16 | 54.9 | 62.7 | 71.8 | 43.5 |

## Risques résiduels

- **MAE ≥ MFE sur GBPUSD** (paire dominante) : l'excursion adverse dépasse l'excursion favorable → un SL serré est touché avant un TP large ; c'est la cause mécanique de tout sous-rendement du stack agressif.
- **p_win walk-forward** lisse vers la base globale : peu de cellules ont un échantillon suffisant → sizing proche de l'uniforme.
- **Régime quasi-toujours NEUTRE** (98.8 %) : le garde-fou short bloque de fait presque tous les shorts (y compris des shorts NEUTRE rentables du backtest).
- Hypothèse first-touch conservatrice (SL-first) : borne basse du rendement réel.


## Décision CEO

**NO-GO — instabilité walk-forward (variance WR 45.3 pts > 15 pts) : edge période-spécifique, non stationnaire. Uplift pips réel mais non exploitable tel quel.** — voir tableau. Chiffres mesurés, non extrapolés. Aucune promotion live sans revue Søn (R28).
