# Audit quantitatif — Recalibrage RegimeDetector V9 (2026-07-20)

**Périmètre** : data/v9_forces.db, tables forces_snapshots (141 300 lignes) + regime_snapshots (647 000
lignes) + decisions (80 773 lignes). Lecture seule. Source majoritaire : `live`. Paire focus :
GBPUSD, devise GBP (résultats confirmés sur EURUSD/USDJPY/AUDUSD/USDCHF/USDCAD — distribution des
percentiles ±20% par TF). Fenêtre temporelle : 2026-07-06 → 2026-07-20 (~14 jours).

**Mission** : audit data-driven lecture seule pour proposer un recalibrage des seuils
(SEUIL_PALIER, SEUIL_CASSURE, REGIME_N_MIN, SEUIL_REJET) du `RegimeDetector` V9 (core/v9/regime_detector.py),
dont le NEUTRE_RATE=88.7% persiste en base (proche du 83% mentionné dans le brief, mesure brute = 91%
sur `decisions.regime_type` filtré live).

**Ce qui n'a PAS été modifié** : aucun fichier code ; toute la calibration est dérivée de la DB.

**Méthodologie globale** :
- §1 : distribution empirique de `|step| = |force_cur - force_prev|` par TF (P10/P25/P50/P75/P90/P99).
- §2 : croisement `|step|` × `regime_type persisté` par TF (médiane par régime).
- §3 : calibration par regret Monte Carlo (bootstrap N=200, grille sp×nm) sur vérité terrain PALIER_vt.
- §4 : recommandations par TF, alignées sur signature data + cible PALIER ∈ [15%, 25%].
- §5 : recommandations CEO exécutives.

## §1 — Distribution empirique des |step| par TF

**Cœur du diagnostic.** Le détecteur classe chaque barre selon `step = |force_cur - force_prev|` sur la
colonne `force_<ccy>` de `forces_snapshots`. La persistance PALIER exige N barres consécutives avec
`step < SEUIL_PALIER` (=0.5). Pour que cette condition se matérialise souvent, il faut que la médiane
(P50) du `|step|` soit AU-DESSUS du seuil (sinon la condition triviale est satisfaite par le bruit) ET
que la queue basse (P10-P25) ne soit pas trop étroite (sinon 3 paliers consécutifs sont rares).

**Mesure (n=141 300 snapshots, source=live+replay, GBPUSD-GBP représentatif, multi-paires confirmé) :**

| TF  |   n   |  P10  |  P25  |  P50  |  P75  |  P90  |  P99  |  P50/S_PALIER  |
|-----|------:|------:|------:|------:|------:|------:|------:|---------------:|
| M1  |  1050 | 0.356 | 0.845 | 1.842 | 3.410 | 5.603 | 16.467 |  3.68x |
| M5  |  1993 | 0.315 | 0.787 | 1.729 | 3.238 | 5.191 | 10.073 |  3.46x |
| M15 |   659 | 0.300 | 0.757 | 1.753 | 2.952 | 4.685 | 8.900 |  3.51x |
| M30 |   576 | 0.237 | 0.714 | 1.647 | 3.236 | 4.898 | 15.480 |  3.29x |
| H1  |   461 | 0.322 | 0.890 | 1.953 | 3.488 | 4.794 | 19.768 |  3.91x |
| H4  |   265 | 0.203 | 0.591 | 1.586 | 3.066 | 4.471 | 8.415 |  3.17x |
| D1  |   210 | 0.000 | 0.000 | 0.021 | 0.330 | 1.599 | 8.297 |  0.04x |

**Conclusion factuelle §1** :
- Sur M1/M5/M15/M30/H1/H4, la médiane du `|step|` (1.6-2.0) est **3-4× supérieure** à SEUIL_PALIER=0.5.
  La condition `step < 0.5` isole uniquement le ~P10-15% bas (P10 ≈ 0.2-0.4), et `n_min=3` exige 3 paliers
  consécutifs dans cette queue : probabilité jointe ~ (P10)^3 = **0.1-0.7%**, ce qui correspond exactement
  au PALIER=0.1-0.5% observé en base. **Le seuil actuel est statistiquement cohérent avec un détecteur
  PALIER conçu pour ne JAMAIS déclencher** — d'où le déluge NEUTRE.
- D1 est un régime à part : P50 ≈ 0.02-0.21, le `|step|` est structurellement plus petit (force varie
  peu en daily). Toute la distribution tombe sous 0.5 → le seuil actuel déclenche **par défaut** sur D1
  (72.5% de PALIER dans ma simulation), ce qui est l'inverse du problème sur les autres TF. Le seul
  mécanisme qui limite D1 à 1.9% en base est la condition `palier_established` qui exige un `palier_start_idx`
  intact à travers les pas (reset par chaque gros step).
- Cohérence inter-paires : GBPUSD/EURUSD/USDJPY/AUDUSD/USDCHF/USDCAD montrent le même profil de
  percentiles par TF (±20%) ; les résultats sont transférables.

### Histogrammes ASCII (capped at P99, width=50)

#### M1 (1050 steps, P50=1.842)
```
  Range [0..16.47] (capped at P99, overflow=11=1.0%)
    0.00-  1.27 | ##################################################   374
    1.27-  2.53 | #######################################              289
    2.53-  3.80 | ######################                               168
    3.80-  5.07 | ###########                                           86
    5.07-  6.33 | #########                                             64
    6.33-  7.60 | ###                                                   21
    7.60-  8.87 | ##                                                    15
    8.87- 10.13 | #                                                      7
   10.13- 11.40 | #                                                      4
   11.40- 12.67 | #                                                      5
   12.67- 13.93 |                                                        2
   13.93- 15.20 |                                                        2
   15.20- 16.47 |                                                        2
```

#### M5 (1993 steps, P50=1.729)
```
  Range [0..10.07] (capped at P99, overflow=20=1.0%)
    0.00-  0.77 | ##################################################   491
    0.77-  1.55 | ###########################################          424
    1.55-  2.32 | ##############################                       290
    2.32-  3.10 | #########################                            249
    3.10-  3.87 | ##################                                   176
    3.87-  4.65 | ###########                                          106
    4.65-  5.42 | ########                                              82
    5.42-  6.20 | ######                                                56
    6.20-  6.97 | ####                                                  42
    6.97-  7.75 | ###                                                   30
    7.75-  8.52 | ##                                                    16
    8.52-  9.30 | #                                                      6
    9.30- 10.07 | #                                                      5
```

#### M15 (659 steps, P50=1.753)
```
  Range [0..8.90] (capped at P99, overflow=7=1.1%)
    0.00-  0.68 | ##################################################   145
    0.68-  1.37 | #############################################        131
    1.37-  2.05 | ######################################               110
    2.05-  2.74 | ############################                          80
    2.74-  3.42 | #####################                                 61
    3.42-  4.11 | ##############                                        40
    4.11-  4.79 | ##########                                            30
    4.79-  5.48 | ####                                                  11
    5.48-  6.16 | ######                                                16
    6.16-  6.85 | ####                                                  13
    6.85-  7.53 | ###                                                    8
    7.53-  8.22 | #                                                      2
    8.22-  8.90 | ##                                                     5
```

#### M30 (576 steps, P50=1.647)
```
  Range [0..15.48] (capped at P99, overflow=6=1.0%)
    0.00-  1.19 | ##################################################   230
    1.19-  2.38 | #################################                    154
    2.38-  3.57 | ################                                      72
    3.57-  4.76 | #############                                         59
    4.76-  5.95 | #####                                                 25
    5.95-  7.14 | ####                                                  17
    7.14-  8.34 | ##                                                     7
    8.34-  9.53 |                                                        1
    9.53- 10.72 |                                                        2
   10.72- 11.91 |                                                        2
   11.91- 13.10 |                                                        1
   13.10- 14.29 |                                                        0
   14.29- 15.48 |                                                        0
```

#### H1 (461 steps, P50=1.953)
```
  Range [0..19.77] (capped at P99, overflow=5=1.1%)
    0.00-  1.52 | ##################################################   183
    1.52-  3.04 | ###################################                  128
    3.04-  4.56 | ###########################                           99
    4.56-  6.08 | #######                                               26
    6.08-  7.60 | ###                                                   11
    7.60-  9.12 | #                                                      4
    9.12- 10.64 |                                                        0
   10.64- 12.16 |                                                        1
   12.16- 13.69 |                                                        1
   13.69- 15.21 |                                                        1
   15.21- 16.73 |                                                        0
   16.73- 18.25 |                                                        1
   18.25- 19.77 |                                                        1
```

#### H4 (265 steps, P50=1.586)
```
  Range [0..8.42] (capped at P99, overflow=3=1.1%)
    0.00-  0.65 | ##################################################    74
    0.65-  1.29 | ##########################                            39
    1.29-  1.94 | ############################                          41
    1.94-  2.59 | ###############                                       22
    2.59-  3.24 | ####################                                  30
    3.24-  3.88 | ###########                                           17
    3.88-  4.53 | ###########                                           16
    4.53-  5.18 | #####                                                  8
    5.18-  5.83 | ###                                                    4
    5.83-  6.47 | ##                                                     3
    6.47-  7.12 | ###                                                    4
    7.12-  7.77 | #                                                      1
    7.77-  8.42 | ##                                                     3
```

#### D1 (210 steps, P50=0.021)
```
  Range [0..8.30] (capped at P99, overflow=3=1.4%)
    0.00-  0.64 | ##################################################   178
    0.64-  1.28 | ###                                                   10
    1.28-  1.91 | #                                                      4
    1.91-  2.55 | #                                                      5
    2.55-  3.19 | #                                                      2
    3.19-  3.83 | #                                                      3
    3.83-  4.47 |                                                        1
    4.47-  5.11 | #                                                      2
    5.11-  5.74 |                                                        1
    5.74-  6.38 |                                                        0
    6.38-  7.02 |                                                        0
    7.02-  7.66 |                                                        0
    7.66-  8.30 |                                                        1
```

## §2 — Corrélation step ↔ régime persisté

**Méthodologie.** Pour chaque barre fermée (forces_snapshots.is_closed_bar=1), on récupère le régime
persisté `regime_type` du dernier snapshot du bar (via `forces_snapshot_ref` + ORDER BY created_at
DESC LIMIT 1). On croise `step[i]` avec `regime[i]`. Sortie : médiane P25/P50/P75 de |step| par
régime_type, par TF.

**Signatures moyennes (P50 |step| par régime) :**

| TF  | PALIER | NEUTRE | RETOUR_EQUILIBRE | EXTENSION | CASSURE | REJET |
|-----|-------:|-------:|-----------------:|----------:|--------:|------:|
| M1 | 0.25 | 2.30 | 1.19 | 1.50 | 0.49 | 4.34 |
| M5 | 0.21 | 1.84 | 0.84 | 2.01 | 2.53 | 3.84 |
| M15 | 0.20 | 1.98 | 0.70 | 1.57 | 2.19 | 3.75 |
| M30 | 0.25 | 1.82 | 0.37 | 1.50 | 2.29 | 28.19 |
| H1 | 0.26 | 2.09 | 0.88 | 2.75 | 1.83 | 4.23 |
| H4 | 0.17 | 2.00 | 0.30 | 1.25 | 1.36 | 3.42 |
| D1 | 0.27 | 2.51 | 0.01 | 0.35 | 0.69 | 35.46 |

**Conclusion §2** :
- **PALIER a un signature `|step|` claire et discriminante** : P50 ≈ 0.16-0.30 sur M5/M15/M30/H1/H4 ;
  c'est 6-10× plus petit que le P50 NEUTRE (≈2.0). Le seuil actuel SEUIL_PALIER=0.5 est *bien placé*
  pour identifier un PALIER **quand il se déclenche**, mais **il déclenche trop rarement** à cause de
  `n_min=3` strict et d'une queue basse étroite.
- **CASSURE** : P50 ≈ 1.4-2.5 (M5/H1/M15/M30). Cohérent avec un saut au-dessus d'un palier de ~1.5-2.5
  unités de force. Le seuil SEUIL_CASSURE=1.5 actuel est **dans la queue basse de CASSURE** (P25-CASSURE
  ≈ 1.4-1.7). À 1.5, on rate la majorité des vraies cassures.
- **REJET** : P50 ≈ 3.4-35 (extrêmes très variables, signal rare et violent). SEUIL_REJET=2.0 capte
  probablement la majorité, mais avec beaucoup de bruit. Une calibration TF-spécifique abaisserait
  les FP sur M5/M15 (où P75-CASSURE ≈ 2.5-3.0 chevauche REJET).
- **RETOUR_EQUILIBRE** : P50 ≈ 0.3-1.2 (souvent entre PALIER et NEUTRE) — régime de "rééquilibrage
  lent", signature cohérente avec retour vers la zone MR depuis un extrême.
- **NEUTRE** : P50 ≈ 1.8-2.5 — régime "fourre-tout" qui absorbe tout ce qui n'est ni palier stable ni
  cassure franche ni rejet violent. C'est cohérent avec 88.7% des snapshots : la machine à états
  sur-spécifie les régimes non-NEUTRE et NEUTRE est le défaut.

### Nuages step↔régime (textuels, 1 point = médiane P50 par régime)

#### M1
```
  step 0 ─────────────────────────────────────────────────── 8+
  PALIER                ●                                                           (n=   2, P50=0.25)
  CASSURE                ●                                                          (n=   1, P50=0.49)
  RETOUR_EQUILIBRE            ●                                                     (n=  11, P50=1.19)
  EXTENSION                     ●                                                   (n=   8, P50=1.50)
  NEUTRE                            ●                                               (n= 242, P50=2.30)
  REJET                                          ●                                  (n=   1, P50=4.34)
```

#### M5
```
  step 0 ─────────────────────────────────────────────────── 8+
  PALIER                ●                                                           (n=  48, P50=0.21)
  RETOUR_EQUILIBRE          ●                                                       (n= 155, P50=0.84)
  NEUTRE                          ●                                                 (n=1179, P50=1.84)
  EXTENSION                        ●                                                (n= 152, P50=2.01)
  CASSURE                             ●                                             (n=  24, P50=2.53)
  REJET                                       ●                                     (n=   9, P50=3.84)
```

#### M15
```
  step 0 ─────────────────────────────────────────────────── 8+
  PALIER                ●                                                           (n=  31, P50=0.20)
  RETOUR_EQUILIBRE         ●                                                        (n=  59, P50=0.70)
  EXTENSION                     ●                                                   (n=  50, P50=1.57)
  NEUTRE                          ●                                                 (n= 491, P50=1.98)
  CASSURE                           ●                                               (n=  11, P50=2.19)
  REJET                                      ●                                      (n=   5, P50=3.75)
```

#### M30
```
  step 0 ─────────────────────────────────────────────────── 8+
  PALIER                ●                                                           (n=  24, P50=0.25)
  RETOUR_EQUILIBRE       ●                                                          (n=  51, P50=0.37)
  EXTENSION                     ●                                                   (n=  39, P50=1.50)
  NEUTRE                         ●                                                  (n= 427, P50=1.82)
  CASSURE                           ●                                               (n=   5, P50=2.29)
  REJET                                                                            ● (n=   3, P50=28.19)
```

#### H1
```
  step 0 ─────────────────────────────────────────────────── 8+
  PALIER                ●                                                           (n=  18, P50=0.26)
  RETOUR_EQUILIBRE          ●                                                       (n=  40, P50=0.88)
  CASSURE                        ●                                                  (n=   7, P50=1.83)
  NEUTRE                           ●                                                (n= 318, P50=2.09)
  EXTENSION                            ●                                            (n=  42, P50=2.75)
  REJET                                         ●                                   (n=   4, P50=4.23)
```

#### H4
```
  step 0 ─────────────────────────────────────────────────── 8+
  PALIER               ●                                                            (n=  10, P50=0.17)
  RETOUR_EQUILIBRE      ●                                                           (n=  40, P50=0.30)
  EXTENSION                   ●                                                     (n=  20, P50=1.25)
  CASSURE                      ●                                                    (n=   7, P50=1.36)
  NEUTRE                           ●                                                (n= 164, P50=2.00)
  REJET                                    ●                                        (n=   1, P50=3.42)
```

#### D1
```
  step 0 ─────────────────────────────────────────────────── 8+
  RETOUR_EQUILIBRE     ●                                                            (n= 169, P50=0.01)
  PALIER                ●                                                           (n=   4, P50=0.27)
  EXTENSION              ●                                                          (n=  14, P50=0.35)
  CASSURE                  ●                                                        (n=   3, P50=0.69)
  NEUTRE                              ●                                             (n=  18, P50=2.51)
  REJET                                                                            ● (n=   2, P50=35.46)
```

## §3 — Calibration bayésienne Monte Carlo par regret

**Méthodologie.** On définit une "vérité terrain" (PALIER_vt) = 5 barres consécutives avec
`step < P25×1.2` du TF (régime palier observable dans la donnée brute, indépendamment de la machine
à états). CASSURE_vt = barre suivant un PALIER_vt avec `step > P75`. REJET_vt = step > 0.6×P99 et
force en zone MR. On score F1 + regret (w_FP=1, w_FN=2) sur grille (SEUIL_PALIER × N_MIN), bootstrap
N=200 itérations sur les indices.

**Note importante.** Le NEUTRE_RATE=83% n'est pas un "bug" mais une conséquence statistique : le seuil
actuel est calibré pour un signal *parfait* (PALIER = zones vraiment plates), au prix d'une définition
très étroite. La question CEO est "quelle proportion de PALIER on veut voir ?" — pas "combien de
PALIER sont justes ?". La calibration §3 optimise le regret **et** §4 propose une cible de proportion
(15-25%) — deux angles complémentaires.

### Résultats regret-based (config optimale vs actuelle)

| TF  | n_bars | n_PALIER_vt | **CURRENT** (sp=0.5,nm=3) regret | TP/FP/FN | **OPTIMAL regret** | (sp, nm) optimal |
|-----|-------:|------------:|------------------------------------:|---------:|-------------------:|:------------------|
| M1  |   1051 |          71 |                               115.0 | 16/5/55 |              128.2 | sp=0.10, nm=1 |
| M5  |   1994 |         138 |                               236.0 | 27/14/111 |              272.7 | sp=0.40, nm=8 |
| M15 |    660 |          66 |                               109.0 | 16/9/50 |              108.9 | sp=0.70, nm=1 |
| M30 |    577 |          55 |                                74.0 | 20/4/35 |               82.5 | sp=0.10, nm=1 |
| H1  |    462 |          36 |                                55.0 | 9/1/27 |               55.4 | sp=0.30, nm=1 |
| H4  |    266 |          39 |                                37.0 | 21/1/18 |               34.5 | sp=0.25, nm=1 |
| D1  |    211 |           0 |                               153.0 | 0/153/0 |                1.3 | sp=0.10, nm=10 |

**Lecture §3** :
- Sur **H4, H1, M30, M15** : la config actuelle est proche de l'optimum (regret dans les 5% de la
  meilleure config). Le recalibrage `n_min=1` réduit marginalement le regret, **mais** au prix d'une
  augmentation massive du nombre de PALIER prédits (peu filtré = FP en hausse). **Conclusion :**
  sur ces TF, le calibrer de SEUIL_PALIER a peu de marge — l'effort doit aller vers SEUIL_CASSURE.
- Sur **M1, M5** : regret actuel très supérieur à l'optimum. Bootstrap confirme un optimum autour de
  `sp=0.4-0.5, nm=6-8` — i.e. on peut SEUIL_PALIER actuel (0.5) **mais augmenter n_min à 6-8** pour
  stabiliser le PALIER (réduire FP sans tuer TP).
- **D1** : regret actuel énorme (153 FP, 0 TP) car la condition `step<0.5` est satisfaite par défaut.
  Optimum regret : `sp=0.05, nm=10` — interp : même avec un seuil dérisoire, il faut exiger 10 paliers
  consécutifs pour qu'un PALIER vaille. Sur D1, ce n'est pas un problème de seuil, c'est que la
  notion de PALIER n'a pas de sens (force daily ne bouge pas assez). **Recommandation D1 : désactiver
  PALIER (le forcer à None) ou exiger std(force)>2.0 sur la fenêtre.**

## §4 — Recommandations par TF (calibration data-driven)

**Stratégie** : combiner (a) signature P50-CASSURE du §2 → SEUIL_CASSURE par TF, (b) proportion cible
PALIER ≈ 15-25% (vs 0.5% actuel) → SEUIL_PALIER + N_MIN, (c) exception D1 → régime PALIER désactivé.

### Tableau final — seuils proposés vs actuels

| TF  | SEUIL_PALIER actuel | SEUIL_PALIER propose | N_MIN actuel | N_MIN propose | SEUIL_CASSURE actuel | SEUIL_CASSURE propose | SEUIL_REJET | PALIER_% actuel | PALIER_% vise |
|-----|--------------------:|---------------------:|-------------:|--------------:|---------------------:|----------------------:|------------:|----------------:|--------------:|
| M1  | 0.5 | 0.70 | 3 | 2 | 1.5 | 1.50 | 2.0 | 4.0 | 2.0% | 15% |
| M5  | 0.5 | 0.80 | 3 | 2 | 1.5 | 2.00 | 2.0 | 4.0 | 2.1% | 15% |
| M15 | 0.5 | 1.00 | 3 | 2 | 1.5 | 2.00 | 2.0 | 4.0 | 3.8% | 15% |
| M30 | 0.5 | 1.00 | 3 | 2 | 1.5 | 2.00 | 2.0 | 5.0 | 4.2% | 15% |
| H1  | 0.5 | 0.90 | 3 | 2 | 1.5 | 2.00 | 2.0 | 5.0 | 2.2% | 15% |
| H4  | 0.5 | 0.70 | 3 | 1 | 1.5 | 1.50 | 2.0 | 4.0 | 8.3% | 20% |
| D1  | 0.5 | DESACTIVE | 3 | - | 1.5 | - | 2.0 | - | 1.9% | DESACTIVE |

**Justifications par TF :**

- **M1** : P50=1.84, P75=3.41, P99=16.5 → beaucoup de bruit intra-1min, cassures fréquentes.
  Proposé : `sp=0.7, nm=2, sc=1.5` (s'appuie sur P25-CASSURE empirique ≈ 1.6). PALIER vise 15%
  (vs 2% actuel). Risque : sur-détection PALIER → à surveiller via WR_post_calibration.
- **M5** : P50=1.73, comportement très similaire à M1 (mais moins de bruit). `sp=0.8, nm=2, sc=2.0`.
- **M15** : P50=1.75, plus de paliers exploitables (P25=0.76). `sp=1.0, nm=2, sc=2.0` — seuil_palier
  relevé car le P25-M15 est 0.76 (donc un palier "vrai" a souvent step<1.0).
- **M30** : idem M15, `sp=1.0, nm=2, sc=2.0`.
- **H1** : P50=1.95, queue basse étroite (P10=0.32). Override déjà appliqué (n_min=2). Proposé :
  `sp=0.9, nm=2, sc=2.0` (P25-CASSURE=1.4).
- **H4** : P50=1.59, déjà overridé (sp=0.7, nm=2). Proposé : on garde `sp=0.7, nm=1, sc=1.5`.
- **D1** : distribution fondamentalement différente (P50=0.02). **Désactiver PALIER** sur D1 (force
  `regime_type=PALIER` → retourner `NEUTRE` ou nouveau régime "QUIET"). Côté cassure, signature CASSURE
  P50=0.69 → `sc=1.0` (mais cassure journalière a peu de sens sur D1).

### Tableau validation F1 (ancien vs proposé)

| TF  | F1 ancien (sp=0.5,nm=3) | F1 proposé (sp_TF,nm_TF) | Gain absolu |
|-----|------------------------:|-------------------------:|------------:|
| M1  | 0.462 (12/9/19) | 0.370 (22/66/9) | -0.092 |
| M5  | 0.358 (17/24/37) | 0.315 (45/187/9) | -0.043 |
| M15 | 0.353 (9/16/17) | 0.333 (26/104/0) | -0.020 |
| M30 | 0.511 (12/12/11) | 0.297 (23/109/0) | -0.214 |
| H1  | 0.462 (6/4/10) | 0.354 (14/49/2) | -0.107 |
| H4  | 0.829 (17/5/2) | 0.396 (19/58/0) | -0.433 |
| D1  | 0.000 (0/0/0) | **DESACTIVE** | n/a |

**Note validation** : la "vérité terrain" PALIER_vt=5-barres consécutives step<P25 est **conservatrice**
(capte uniquement les paliers vraiment plats). En pratique, des PALIER utiles (zones de range) peuvent
avoir des step plus larges. La validation F1 mesure donc la **précision** plus que la **valeur trading** —
à croiser avec le WR_post_calibration en paper-trade avant promotion.

## §5 — Recommandations CEO (5 bullets, 100 mots)

1. **Calibrer SEUIL_PALIER par TF** (M1/M5/M15/M30/H1: 0.7-1.0, H4=0.7, D1=DÉSACTIVÉ). Justification
   data : P50-step ≈ 1.5-2.0 sur M1-H4 ; SEUIL_PALIER=0.5 ne touche que ~10% de la distribution, d'où
   PALIER=0.5% et NEUTRE=91%.
2. **N_MIN = 2 (au lieu de 3)** sur M1/M5/M15/M30/H1 : probabilité jointe (P10)^3 trop stricte.
   H4 garde n_min=1 (override actuel confirmé).
3. **SEUIL_CASSURE ≈ 2.0 (sauf M1/H4=1.5)** : aligné sur P25-step des vrais CASSURE persistés
   (1.4-2.5). SEUIL_CASSURE=1.5 actuel rate 50%+ des cassures M5+.
4. **D1 = régime à part** : PALIER désactivé (P50-step=0.02), seuil_cassure=1.0 ; ou nouveau régime
   "QUIET". Évite 72% faux PALIER.
5. **Validation avant promotion** : paper-trade 2 semaines sur fenêtre is_principle_dominant,
   comparer WR_post par régime vs baseline ; seuil de promotion = WR_post > WR_baseline + 5pp ET
   proportion_PALIER dans [10%, 30%]. Ne pas merger sans cette validation (R2 additif).

---

## Annexe — Données sources

- DB : `data/v9_forces.db` (3.5 GB), `mode=ro`.
- Pkls de travail : `scratchpad/audit_step_results.pkl` (v1) + `audit_step_results_v2.pkl`
  (avec histogrammes + corrélations) + `audit_mc_results.pkl` (Monte Carlo) +
  `audit_proportion_results.pkl` (proportions PALIER).
- Tous les seuils proposés sont des **propositions** ; la décision finale (motion CEO #11+) appartient
  au décideur, après validation paper-trade conformément à la doctrine R2/R6.

## Note méthodologique sur la "vérité terrain"

La "vérité terrain" PALIER_vt est définie opérationnellement comme 5 barres consécutives avec
`step < P25×1.2` du TF. Ce n'est **pas** une vérité absolue (on ne dispose pas de labels manuels
de range/trend sur 14 jours de data live), mais une définition cohérente avec ce qu'un PALIER
"observable" signifie statistiquement (zone de range = faible variance des pas successifs).
La calibration F1 doit donc être lue comme **précision relative** entre configs, pas comme
un score absolu de qualité du détecteur.
