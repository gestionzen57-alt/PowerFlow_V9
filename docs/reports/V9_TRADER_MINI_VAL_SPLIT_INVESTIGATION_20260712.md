# Investigation — rupture de distribution split val, V9-trader-mini (Brief Q1)

- Date : 2026-07-12, Brief Q1 (série "saut quantique" Q1→Q5).
- Prérequis : Brief O5 (dataset exporté, rupture documentée — WR train=93.9%
  vs val=44.6% vs test=89.3%, split chronologique contigu 80/10/9).

## Verdict

**Re-split justifié — effet de période, pas un problème de généralisation du
signal.** Le split contigu isolait un unique épisode de marché corrélé dans
le val, pas un échantillon représentatif. Le val a été re-généré par un split
par blocs entrelacés (voir §Correctif) ; les WR sont désormais cohérents
entre splits (train 88.4%, val 88.9%, test 89.3%).

## Méthode

Requête directe sur `decisions` (mêmes filtres que `scripts/v9_export_dataset.py`
: `action='preparer_entree' AND resolution_strategy='DYNAMIC'`, tri
chronologique), reproduction exacte du split 80/10/9 du Brief O5 pour isoler
le val original (821 décisions).

### (a) Effet de période

Plage de dates par split (avant correctif) :

| Split | Début | Fin | Durée |
|---|---|---|---|
| train | 2026-07-07T08:07:32Z | 2026-07-08T09:11:56Z | ~25h |
| val | 2026-07-08T09:12:00Z | 2026-07-08T10:08:07Z | **~56 minutes** |
| test | 2026-07-08T10:08:11Z | 2026-07-10T15:50:05Z | ~53h |

Le val ne représente pas "10% du temps" mais une fenêtre de **56 minutes**
extraite d'une période totale de ~80h — confirmé : effet de période sévère,
pas un artefact d'implémentation (le split chronologique fait exactement ce
qui est demandé, mais la densité de décisions n'est pas uniforme dans le
temps).

### (b) Mix de sessions

| Split (échantillon) | Sessions |
|---|---|
| train (1000 dernières) | asie 788 (78.8%), london 212 (21.2%) |
| **val (821, intégral)** | **london 821 (100%)** |
| test (823, intégral) | london 698 (84.8%), overlap 85 (10.3%), asie 40 (4.9%) |

Le val est **100% session london** — aucune diversité de session.

### (c) Effet stratégie de résolution / direction

| Split (échantillon) | Direction |
|---|---|
| train (1000 dernières) | haussière 763 (76.3%), baissière 237 (23.7%) |
| **val (821, intégral)** | **baissière 821 (100%)** |
| test (823, intégral) | baissière 710 (86.3%), haussière 113 (13.7%) |

Le val est **100% direction baissière**. Combiné à (b), le val n'est pas
"un échantillon de 821 essais indépendants" mais correspond à **un seul
mouvement de marché baissier continu**, confirmé par :

- **821 `snapshot_id` uniques mais seulement 57 minutes distinctes** —
  jusqu'à 17 décisions/minute sur timeframe M15 (intrabar, cohérent avec le
  comportement M15 "continu" déjà documenté en Phase 14, cf.
  `docs/reports/MTF_DIAGNOSTIC_20260708.md`) : re-déclenchements quasi
  continus du même principe dominant (`PRICE_LAG_AT_NODE_BIRTH`, ~90% des
  triggers globaux) sur la même impulsion de prix.
- **pips gagnants moyens = +7.5 (≈ TP london 8-0.5 spread), pips perdants
  moyens = -15.5 (≈ SL london 15+0.5 spread)** — cohérent avec un mouvement
  qui est allé majoritairement contre la thèse baissière dominante pendant
  cette fenêtre précise (SL touché plus souvent que TP), pas avec un bruit
  aléatoire.

Ce résultat fait écho au biais déjà documenté au Brief O4
(`docs/reports/NY_AFTER_BIAS_20260712.md`) : marché à drift haussier
structurel (~91%) sur la période captée — une salve de signaux baissiers à
contre-tendance perd disproportionnellement plus souvent, indépendamment de
la qualité du principe qui les a déclenchés.

## Conclusion

Les 821 lignes du val original n'étaient pas 821 essais indépendants mais
un nombre bien plus restreint d'épisodes de marché réels, sur-représentés
par le rythme de snapshot M15 intrabar. Un split purement contigu est donc
structurellement vulnérable à isoler une seule salve corrélée dans une
fenêtre de validation — ce n'est pas spécifique à ce dataset, c'est un
risque inhérent au split chronologique naïf sur une série temporelle à
densité d'événements très irrégulière.

## Correctif appliqué

`scripts/v9_export_dataset.py::chronological_split()` modifié (Brief Q1) :

- **test** reste un holdout chronologique **pur** (derniers ~10%, aucune
  contamination futur→passé — condition de déploiement réaliste inchangée).
- **train/val** sont désormais découpés en blocs contigus bornés (taille
  cible 50, resserrée automatiquement pour les petits pools) sur les ~90%
  restants ; 1 bloc sur 9 est assigné à val (~11% du pool, ~10% du total).
  Le val échantillonne ainsi plusieurs épisodes de marché distincts répartis
  dans le temps, au lieu d'une seule fenêtre contiguë.

Résultat après régénération (`docs/reports/DATASET_V9_TRADER_MINI_CARD.md`,
régénéré) :

| Split | N | WR |
|---|---|---|
| train | 6595 | 88.4% |
| val | 800 | 88.9% |
| test | 822 | 89.3% |

Rupture résolue — plus d'écart >15 points entre splits. Détails de
l'implémentation : `core/v9/arbiter.py`/`scripts/v9_export_dataset.py`
(docstring `chronological_split`), tests dédiés
`tests/test_v9_export_dataset.py`.
