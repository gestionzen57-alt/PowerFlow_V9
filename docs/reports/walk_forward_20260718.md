# Walk-Forward Validation — all

> Généré : 2026-07-18T06:46:15.692261+00:00
> Version : 1.0

## Verdict : ✅ EDGE RÉEL

- **Trades résolus** : 8771
- **Fenêtres** : 5 (4 folds testés)
- **Expectancy in-sample moyenne** : 6.281 pips
- **Expectancy out-of-sample moyenne** : 7.197 pips
- **Ratio de dégradation OOS/IS** : 1.15
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
| 1 | ≥90 | 618 | 2.317 | 1717 | 8.425 | 98.3% | 0.0000 |
| 2 | ≥90 | 2335 | 6.808 | 1719 | 9.314 | 99.2% | 0.0000 |
| 3 | ≥90 | 4054 | 7.871 | 1166 | 9.020 | 98.3% | 0.0000 |
| 4 | ≥90 | 5220 | 8.128 | 1158 | 2.029 | 71.5% | 0.0000 |

## Interprétation

- **EDGE RÉEL** : l'expectancy tient hors-échantillon (OOS positif,
  majoritaire, significatif) et ne s'effondre pas face à l'in-sample.
- **EDGE RÉEL (dégradé)** : OOS positif et significatif mais forte
  dégradation vs in-sample (ratio < 0.5) — edge réel mais sur-estimé.
- **OVERFITTING** : l'expectancy OOS moyenne est négative — le seuil
  calibré sur le passé ne survit pas au futur.
- **NON CONCLUANT** : OOS positif mais non significatif ou minoritaire.
