# Optimisation agressive — grid search TP×SL×Kelly (2026-07-18)

> Lecture seule, 8771 décisions, 60 configs (TP×SL×K = 5×4×3). Score = pips pénalisés par l'instabilité walk-forward.


**Configs stables (WF spread ≤ 15 pts) : 0/60.**


## Top 12 configurations (par score)

| Rang | TP | SL | K | Pips | PF | WR | maxDD | WF spread | Score |
|---|---|---|---|---|---|---|---|---|---|
| 1 | 30 | 15 | 0.5 | +82607 | 183.78 | 97.9% | -182 | 44.1 | +28122 |
| 2 | 30 | 18 | 0.5 | +81771 | 172.83 | 97.9% | -187 | 44.1 | +27837 |
| 3 | 30 | 8 | 0.5 | +84593 | 237.26 | 97.7% | -151 | 46.1 | +27543 |
| 4 | 30 | 12 | 0.5 | +83441 | 199.10 | 97.8% | -195 | 45.7 | +27406 |
| 5 | 25 | 15 | 0.5 | +68434 | 211.64 | 98.1% | -149 | 43.3 | +23730 |
| 6 | 25 | 18 | 0.5 | +67627 | 209.99 | 98.1% | -151 | 43.3 | +23450 |
| 7 | 25 | 12 | 0.5 | +69253 | 218.04 | 98.1% | -161 | 44.9 | +23154 |
| 8 | 25 | 8 | 0.5 | +70353 | 240.87 | 97.9% | -134 | 45.7 | +23108 |
| 9 | 30 | 15 | 0.1 | +56902 | 161.43 | 97.9% | -152 | 44.1 | +19371 |
| 10 | 30 | 15 | 0.25 | +56902 | 161.43 | 97.9% | -152 | 44.1 | +19371 |
| 11 | 30 | 18 | 0.1 | +56890 | 152.51 | 97.9% | -159 | 44.1 | +19367 |
| 12 | 30 | 18 | 0.25 | +56890 | 152.51 | 97.9% | -159 | 44.1 | +19367 |

## Lecture

- **Aucune configuration stable** : toutes dépassent le seuil de variance walk-forward. Confirme le diagnostic NO-GO — l'edge est période-spécifique quelle que soit la paramétrisation TP/SL/K.

- Chiffres mesurés sur données réelles, non extrapolés. Aucune promotion live sans revue Søn (R28).
