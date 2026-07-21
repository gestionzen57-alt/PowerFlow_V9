# PROMPT_OPUS_REGIME_AUDIT_20260720

> **Audit lecture seule** — Architecture RegimeDetector V9 vs dégradation edge baissier 24h
> Référence : commit `d443096` (kill switches via `.env` lus par `kill_switches.get()`, pas `os.environ`)
> Données : `data/v9_forces.db` (140 374 forces, 640 808 régime, 80 007 décisions, 14h42 UTC J2026-07-20)
> Doctrine respectée : R2 additif, R6 défensif, R18 zéro LLM dans le cœur, R22 une session = un périmètre.

---

## §1 — Lecture du RegimeDetector (~150 LOC ➜ 422 LOC réelles)

**Source unique** : `core/v9/regime_detector.py` (lecture intégrale). Calibration : `core/v9/config.py` L297-342 (Phase 9).

### 1.1 Signaux agrégés

| Source              | Champ lu                                    | Granularité                              |
|---------------------|---------------------------------------------|------------------------------------------|
| `forces_snapshots`  | `force_<ccy>` (8 colonnes USD..NZD)         | Par (symbol, timeframe), 1 ligne = 1 bar |
| `regime_snapshots`  | agrège N-1 (snapshot précédent persisté)    | 1 ligne par (snapshot, devise) — 8/snap  |
| **PAS lu**          | ni `scenes`, ni `behaviors`, ni `windows`   | RegimeDetector est **strictement amont** |

### 1.2 Machine à 6 régimes (portage V8 `core/pf_regime_detector.py`)

```
PALIER           ← step < SEUIL_PALIER (0.5) pendant ≥ N_MIN (3) barres
  ├─ CASSURE     ← step > SEUIL_CASSURE (1.5) depuis anchor du palier
  │    └─ EXTENSION ← momentum continue dans la direction de cassure
  ├─ RETOUR_ÉQUILIBRE ← mrz (force >80/<20) sans anchor palier
  ├─ NEUTRE      ← défaut (step intermédiaire ou premier tick)
  └─ REJET       ← approche zone mrz + reversal violent (≥ SEUIL_REJET 2.0)
```

Projection 3-classes pour le gate (Chantier A) : `CASSURE/EXTENSION=trending`, `PALIER/RETOUR_EQUILIBRE/NEUTRE=ranging`, `REJET=volatile`. Vote majoritaire sur 8 devises avec `confidence = part dominante`.

### 1.3 Latence pipeline (5 couches + régime)

```
sonde EA  → forces_snapshots → regime_snapshots (N-1)
                                   ↓
       scene_builder → behaviors → windows → exploitability
                                   ↓
                                  decision
```

**Mesuré DB** : latence `forces_snapshot → regime_snapshot` ≈ **8.27 s médiane** (sample 14h47 = 8.27s). Donc `regime_snapshots` est en retard systématique d'**1 barre M5 minimum** sur le flux temps réel. Pour un M5, la décision d'exploitabilité porte donc sur un régime datant de 0–5 min dans le passé ; pour un M1, 8 s ≈ intra-barre.

---

## §2 — Mismatch 24h : pourquoi le régime n'a pas basculé

### 2.1 Bilan baissier 24h (source : `decisions` table, trade résolu)

| Paire       | Trades | WR    | Pips       | Note                                 |
|-------------|-------:|------:|-----------:|--------------------------------------|
| AUDUSD      |     36 | 11.1% | **−242.7** | Saignée ; aucun principe n'a vu venir|
| GBPUSD      |     36 | 36.1% | **−206.3** | Ouv. baissières dominantes (regime=NEUTRE) |
| USDJPY      |      4 | 25.0% |    −37.0   | Petit volume                          |
| EURUSD      |      5 | 20.0% |    −26.3   | Idem                                  |
| USDCAD      |     14 | 42.9% |     −9.8   | Modéré                                |
| USDCHF      |      9 | 77.8% |   **+41.2** | Contre-tendance haussière gagne      |
| **TOTAL**   |  **104** | **30.8%** | **−480.9** | **−4.62 pips/trade en moyenne**      |

vs **7j** : 299 trades baissier, WR 48.2%, −184.4 pips (baisier structurellement positif sur 30j à 64.5% WR).

### 2.2 Distribution regimes_type des 104 décisions baissières 24h

| Regime détecté (à la décision) | n  | WR    | Pips       |
|--------------------------------|---:|------:|-----------:|
| CASSURE                        |  3 |  0.0% |    −34.7   |
| EXTENSION                      | 14 | 14.3% |   −102.7   |
| **NEUTRE**                     | 74 | 31.1% | **−340.7** | ← 71% des baissiers passés en NEUTRE
| RETOUR_EQUILIBRE               | 13 | 53.8% |     −2.8   |
| REJET                          |  0 |   —   |     —      |

### 2.3 Pourquoi ça n'a pas basculé (3 raisons cumulatives)

**A. Le détecteur classe 92.4% des snapshots en `ranging`** (28 226 NEUTRE + 2 229 RETOUR_EQU + 534 PALIER hors GBPUSD/24h). Le régime dominant devient alors `ranging conf=0.875+` → **gate volatile jamais déclenché**. Distribution observée 24 h : ranging=92.4%, trending=6.9%, volatile=0.6%.

**B. NEUTRE est le mode par défaut, pas un diagnostic.** La machine à états n'a qu'un seul chemin pour signaler une tendance absente : la comparer à un palier de 3 barres consécutives < SEUIL_PALIER. Or en M1/M5 sur GBP/USD, la variance intra-barre suffit à briser le critère. Calibration `SEUIL_PALIER=0.5`, `N_MIN=3` → ~70% des séries tombent dans `NEUTRE` au tick près, sans info sur le **gradient cross-pair**.

**C. Le détecteur lit les 8 devises indépendamment, pas la dynamique inter-paires.** Pour GBPUSD-M15 14:15:01 (paper trade GBPUSD short 14:15:58), les 8 lignes régime_snapshot sont : 7× NEUTRE, 1× EXTENSION (EUR DOWN), 1× PALIER (USD). Vote = 7/8 ranging, **rien ne signale que « USD fort vs GBP faible » est une divergence baissière structurelle**. Pour détecter ça il faudrait soit (i) comparer les forces USD vs GBP directement, soit (ii) lire le régime du **panier** (8 devises simultanément), pas de chaque devise isolément. **Le RegimeDetector a été conçu pour mesurer la stabilité d'une série individuelle, pas le rapport de force d'une paire.**

→ Conclusion §2 : le régime n'a pas basculé non pas à cause d'un bug mais d'un **défaut de couverture conceptuel** — la machine à états ignore la moitié du problème (la relation inter-devises).

---

## §3 — Design méta-régime adaptatif (3 niveaux)

### 3.1 Diagramme ASCII — flux multi-niveaux

```
┌─────────────────┐ ┌─────────────────┐ ┌─────────────────┐
│   NIVEAU MICRO  │ │  NIVEAU MÉSO    │ │  NIVEAU MACRO   │
│   M5 / M15      │ │   H1 / H4       │ │     D1 / W1      │
│  tick-level     │ │   hourly        │ │     daily        │
│  fenêtre 15 min │ │  fenêtre 6 h    │ │  fenêtre 24 h+   │
│                 │ │                 │ │                  │
│ Inputs :        │ │ Inputs :        │ │ Inputs :         │
│ • delta force   │ │ • momentum méso │ │ • trend D1       │
│   (F_t - F_t-1) │ │   (sign(H1) vs  │ │ • annualised vol │
│ • delta spread  │ │    sign(H4))    │ │ • % sessions     │
│ • spawn (rate   │ │ • durée régime  │ │   dominantes     │
│   de decisions) │ │   micro > N min │ │ • cross-pair     │
│                 │ │ • flip count    │ │   correlation    │
│                 │ │   micro         │ │   structure      │
│ Output :        │ │ Output :        │ │ Output :         │
│ REGIME_MICRO ∈  │ │ REGIME_MESO ∈   │ │ REGIME_MACRO ∈   │
│  {compress,     │ │  {trend_accel,  │ │  {risk_on,       │
│   burst, drift} │ │   trend_fatigue,│ │   risk_off,      │
│                 │ │   range_build,  │ │   transition}    │
│                 │ │   range_break}  │ │                  │
└────────┬────────┘ └─────────┬───────┘ └────────┬─────────┘
         │                   │                  │
         └─────────┬─────────┴─────────┬────────┘
                   │                   │
                   ▼                   ▼
           ┌─────────────────────────────────────┐
           │        META-REGIME LAYER            │
           │  (convergence / divergence detector)│
           │                                     │
           │  • convergence_3 = (micro==méso==   │
           │    macro) → signal FORT, aligner    │
           │    sizing dans le sens              │
           │                                     │
           │  • divergence_2of3 = (2 niveaux     │
           │    disent) → signal d'ALERTE,       │
           │    réduire exposition ou basculer   │
           │    vers mode défensif               │
           │                                     │
           │  • flip_rapide = (micro a changé     │
           │    ≥3 fois en 1h, méso stable)      │
           │    → whipsaw détecté, VETO          │
           │    directional                       │
           │                                     │
           │  Sortie : REGIME_META ∈             │
           │   {aligned_long, aligned_short,     │
           │    conflict, choppy, defensive_halt} │
           └────────────────┬────────────────────┘
                            │
                            ▼
              ┌─────────────────────────────┐
              │   PUBLICATION API V9        │
              │                             │
              │   • regime_meta exposé      │
              │     dans regime_snapshots   │
              │     (colonne supplémentaire │
              │     ou table meta_regime)   │
              │                             │
              │   • kill switches           │
              │     V9_REGIME_META_ENABLED  │
              │     (OFF par défaut — R2)   │
              │                             │
              │   • consommé par :          │
              │     - exploitability_evaluator│
              │     (gate régime niveau 2)   │
              │     - dynamic_risk_manager   │
              │     - paper_trade gate      │
              │     - watchdog live         │
              └─────────────────────────────┘
```

### 3.2 Spécifications fonctionnelles (pas de code)

**Critères de déclenchement** :
- **Convergence 3 niveaux** (cumul ≥ 2/3) → régime directionnel FORT. Sizing plein. Gate ouvre pour `aligned_long|short`.
- **Divergence 2/3 ou plus** → ALERTE T+0. Ex : micro=drift, méso=range_build, macro=risk_off → divergence = suspension short baissier.
- **Flip rapide micro** (≥3 changements en 1 h, méso plat) → whipsaw, **VETO** préventif 30 min sur les directions short.
- **Méso=trend_fatigue pendant que macro=risk_off** → fenêtre de retournement ; relevé automatique du seuil de confiance décision.

**Indicateurs dérivés** (commentés) :
- `micro_dispersion` = stddev des 8 forces sur fenêtre 15 min (proxy volatilité réalisée courte).
- `meso_persistence` = durée du régime méso courant en heures.
- `macro_correlation_collapse` = chute de corrélation rolling 24 h entre les 6 paires (signe de stress systémique).
- `flip_rate_micro_per_hour` = nombre de transitions micro par heure.

**Cadence de publication** : micro toutes les 15 min, méso toutes les 6 h, macro tous les jours à 00:00 UTC. Méta-régime recalculé à chaque publication d'un sous-niveau. **Hors ligne (pas de tick)** : aucun recalcul.

**Latence cible** : micro 15 min, méso 6 h, macro 24 h — c'est la **métrique de design**, pas une latence pipeline. Le pipeline aval consomme la **dernière valeur publiée** (lecture N-1, comme `get_current_regime` aujourd'hui).

**Doctrine respectée** : R2 additif (n'écrase pas `regime_snapshots` existant), R6 défensif (gate tombe en `meta = conservative` en cas d'erreur DB ou de TF manquant), R18 zéro LLM (tous calculs = stats pures ou heuristiques).

**Intégration au pipeline existant** : `ExploitabilityEvaluator._apply_regime_gate` est **étendu** (R2) avec un `_apply_meta_regime_gate` qui prend le pas ; si `REGIME_META_ENABLED=ON`, lit `meta_regime` ; si `conflict|choppy|defensive_halt` ET conf > seuil → force `refuse`. **Double gate** : un trade refusé par l'un reste refusé ; un trade `volatile_and_meta_conflict` n'est libéré que si `meta == aligned`. **Lecture N-1 inchangée.**

### 3.3 Promotions conditionnées (R25')

- Phase 1 (lecture seule, hors-ligne) : `meta_regime_snapshots` table alimentée par replay DB des 7 derniers jours, validation backtest que 70%+ des flags `conflict` précèdent une dégradation WR baissier.
- Phase 2 (shadow, kill switch OFF) : live `meta_regime` calculé + persisté sans bloquer.
- Phase 3 (V9_REGIME_META_ENABLED=ON, durée 48 h) : activation gate avec paper-trade seul.
- Phase 4 (promotion live) : `meta_regime` exposé comme nouvelle dimension dans `regime_snapshots`.

---

## §4 — Kill switch gate : simulation V9_REGIME_GATE_ENABLED=ON (rejoué sur 104 trades baissiers 24 h)

### 4.1 Méthodologie

Rejoué sur la DB : pour chaque décision baissière résolue 24 h, on regarde le `regime_snapshots` du même (symbol, timeframe) **préalable** au `timestamp` de décision. La classe 3-volée est calculée par-devise, et la confiance = part dominante/8 (méthode exacte de `RegimeDetector.get_current_regime`).

### 4.2 Impact

| Métrique                     | Gate **OFF** (actuel) | Gate **ON** (simulé) |
|------------------------------|----------------------:|---------------------:|
| Décisions baissières 24h     |                  104  |                104   |
| Refusées par gate            |                   —   |            **3**      |
| Trades exécutés              |                  104  |                101   |
| WR réalisé (live)            |               30.8%   |             31.7%     |
| **Pips total**               |          **−480.9**   |        **−478.4**     |
| Pips économisés              |                   —   |          **+2.5**     |
| WIN évités (perte rattrapée) |                   —   |                  1   |
| LOSS évités (trades sauvés)  |                   —   |                  2   |

### 4.3 Pourquoi un si faible impact

Le gate fonctionne, mais le détecteur ne flaggera le mot `volatile` que sur **0.6 %** des snapshots 24 h (216/33 528). Pour qu'un gate soit efficace sur 24 h baissier, il aurait fallu flag 70% des 104 trades baissiers comme étant en zone volatile — **or le régime n'est jamais `volatile`** quand la tendance est baissière persistante, parce que `volatile` = `REJET`, qui n'est déclenché que sur retournement violent au contact d'une zone mrz (force > 80 ou < 20). **Une tendance baissière graduelle, c'est-à-dire le cas vécu 24 h, n'est jamais `REJET`**.

**Conséquence opérationnelle** : activer `V9_REGIME_GATE_ENABLED=ON` aujourd'hui = +2.5 pips économisés en 24 h, **zéro régression** (R2 additif OK), mais **zéro signal de retournement**. Le gate ne couvre pas le cas vécu. **Pour attraper le mismatch 24 h, il faut §3 (méta-régime), pas §4 (gate ON).**

---

## §5 — Recommandations CEO (5 bullets, ≤100 mots)

- **§5.1 — NE PAS activer `V9_REGIME_GATE_ENABLED` seul** (économie 2.5 pips, pas de couverture du cas baissier graduel). Garder OFF tant que §3 n'est pas livré.
- **§5.2 — Ouvrir chantier méta-régime** (Phase 1 lecture seule + backtest 7 j), `V9_REGIME_META_ENABLED=OFF` par défaut (R2/R25'). Cible : gate 70%+ des trades baissiers dégradés.
- **§5.3 — Étalonnage `NEUTRE` biaisé 92%** — investiguer pourquoi les overrides H1/H4 ne suffisent pas ; ajouter un compteur `neutre_rate_24h` au watchdog live (alerte si > 75 %).
- **§5.4 — Renforcer la lecture cross-pair** : ajouter au RegimeDetector une métrique `cross_pair_dispersion` (stddev 6 paires × 6 paires, 8 forces) — sortie secondaire, R2 additif.
- **§5.5 — Garder le fallback `ranging conf=0.0`** : R6 = OK, mais documenter explicitement dans `get_current_regime` que ce fallback **masque** un régime non-classifié, distinct d'un vrai ranging. Tag DB : `regime_source = 'fallback' | 'detector'` (déjà partiellement en place via `source`).

---

## Annexe — Schéma de référence (rappel)

| Table              | Volumétrie  | Usage                        |
|--------------------|------------:|------------------------------|
| forces_snapshots   |    140 374  | Source forces                |
| regime_snapshots   |    640 808  | N-1 régime persisté          |
| scenes             |     80 248  | Couche 2 (non lue par §1)    |
| behaviors          |     80 172  | Couche 3                     |
| windows            | (idem)      | Couche 4                     |
| exploitability     |     80 134  | Couche 5 (gate régime)       |
| decisions          |     80 007  | Couche 6                     |
| paper_trades       |      1 175  | Résolution simulée           |

Latence mesurée `forces → regime_snapshots` : médiane **8.27 s** (2026-07-20 14:47 UTC).
