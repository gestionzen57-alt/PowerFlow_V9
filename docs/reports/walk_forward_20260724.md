# Walk-Forward Validation — all

> Généré : 2026-07-24T04:30:03.205628+00:00
> Version : 1.0

## Verdict : ✅ EDGE RÉEL

- **Trades résolus** : 9452
- **Fenêtres** : 5 (4 folds testés)
- **Expectancy in-sample moyenne** : 8.967 pips
- **Expectancy out-of-sample moyenne** : 5.979 pips
- **Ratio de dégradation OOS/IS** : 0.67
- **Folds OOS positifs** : 4/4
- **p-value OOS agrégée** : 0.000000

## ⚠️ Provenance des données

Cette validation lit `decisions.resolution_pips` / `decisions.is_win`,
produits par le **résolveur offline**. Ce résolveur n'est pas
path-dependent (il ne rejoue pas TP/SL barre par barre comme
`ExitSimulator` en clôture live) : un WR out-of-sample de 95-99 %
est le symptôme de cet **artefact de résolution** (biais de
distribution documenté), PAS d'un edge réellement exploitable à ce
niveau. À lire donc en **valeur relative** : la _stabilité_ du seuil
calibré (in-sample vs out-of-sample) et la _dégradation entre folds_
restent des signaux valides ; le niveau absolu de WR/expectancy est
gonflé par la résolution offline et ne doit pas être pris au pied
de la lettre. La vérité live vient de `close_open_trades()` +
`ExitSimulator` (≈ breakeven après coûts).

## Détail par fold

| Fold | Seuil conf. | IS n | IS exp. | OOS n | OOS exp. | OOS WR | OOS p |
|---|---|---|---|---|---|---|---|
| 1 | ≥90 | 753 | 8.595 | 1849 | 9.162 | 84.8% | 0.0000 |
| 2 | ≥90 | 2602 | 8.998 | 1855 | 10.909 | 91.6% | 0.0000 |
| 3 | ≥90 | 4457 | 9.794 | 1169 | 3.476 | 62.1% | 0.0000 |
| 4 | ≥90 | 5626 | 8.481 | 1231 | 0.370 | 48.1% | 0.2729 |

## Interprétation

- **EDGE RÉEL** : l'expectancy tient hors-échantillon (OOS positif,
  majoritaire, significatif) et ne s'effondre pas face à l'in-sample.
- **EDGE RÉEL (dégradé)** : OOS positif et significatif mais forte
  dégradation vs in-sample (ratio < 0.5) — edge réel mais sur-estimé.
- **OVERFITTING** : l'expectancy OOS moyenne est négative — le seuil
  calibré sur le passé ne survit pas au futur.
- **NON CONCLUANT** : OOS positif mais non significatif ou minoritaire.
