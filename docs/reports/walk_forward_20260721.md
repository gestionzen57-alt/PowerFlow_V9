# Walk-Forward Validation — all

> Généré : 2026-07-21T07:23:06.365185+00:00
> Version : 1.0

## Verdict : ✅ EDGE RÉEL

- **Trades résolus** : 9103
- **Fenêtres** : 5 (4 folds testés)
- **Expectancy in-sample moyenne** : 6.389 pips
- **Expectancy out-of-sample moyenne** : 6.741 pips
- **Ratio de dégradation OOS/IS** : 1.06
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
| 1 | ≥90 | 684 | 3.010 | 1778 | 8.462 | 98.4% | 0.0000 |
| 2 | ≥90 | 2462 | 6.947 | 1790 | 9.322 | 99.3% | 0.0000 |
| 3 | ≥90 | 4252 | 7.947 | 1099 | 6.513 | 88.4% | 0.0000 |
| 4 | ≥90 | 5351 | 7.652 | 1280 | 2.669 | 71.8% | 0.0000 |

## Interprétation

- **EDGE RÉEL** : l'expectancy tient hors-échantillon (OOS positif,
  majoritaire, significatif) et ne s'effondre pas face à l'in-sample.
- **EDGE RÉEL (dégradé)** : OOS positif et significatif mais forte
  dégradation vs in-sample (ratio < 0.5) — edge réel mais sur-estimé.
- **OVERFITTING** : l'expectancy OOS moyenne est négative — le seuil
  calibré sur le passé ne survit pas au futur.
- **NON CONCLUANT** : OOS positif mais non significatif ou minoritaire.
