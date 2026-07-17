# Dynamic Risk Manager — SL/TP/BE/Trailing adaptatifs aux cycles

> Phase 13.3 — Mission « Risk Manager Dynamique » (2026-07-17).
> Statut : **SHADOW** (évalue et décrit, n'applique pas). Doctrine R32.

## Pourquoi

Le système lit désormais le marché en haute définition : 5 paires, 8 devises,
coalitions HTF lissées, confirmation LTF, régimes, phases comportementales.
Mais la gestion du risque était restée statique — `TP=8 / SL=15`, identique
pour toutes les paires, tous les régimes, toutes les sessions. Un héritage de
l'époque où le système ne savait pas encore lire le marché.

Un breakout en début de Londres n'a pas le même stop qu'un climax en fin de
New York. Une coalition HTF (D1/H4) a une espérance de vie plus longue qu'une
coalition LTF (M5/M15) éphémère. Le Dynamic Risk Manager adapte SL, TP,
break-even et trailing à ce que le système sait maintenant lire.

## Le cycle de marché

```
ACCUMULATION → CASSURE → TREND → DISTRIBUTION → CLIMAX → RETOUR → ACCUMULATION
```

Chaque phase a une signature comportementale et une gestion du risque propre :

| Phase | Signature | SL | TP | Exit | Trailing | Break-even | Nouvelle position |
|---|---|---|---|---|---|---|---|
| **Accumulation** | range, volatilité faible, coalitions naissantes | serré (10) | modeste (8) | TP_SL | non | non | oui |
| **Cassure** | breakout, volatilité qui explose | large (18) | ambitieux (22) | TRAILING | 50% TP | 30% TP | oui |
| **Trend** | directionnel, coalitions solides | moyen (14) | large (26) | TRAILING | 25% TP | 20% TP | oui |
| **Distribution** | divergence, épuisement | serré (10) | prudent (10) | TP_SL | non | 50% TP | oui |
| **Climax** | extrême, vélocité max | serré (8) | serré (8) | TIME_BASED | non | non | **NON** |
| **Retour** | mean reversion | large (12) | modeste (8) | TP_SL | non | non | oui |

*(Valeurs de base avant modulation coalition ; SL clampé ∈ [6, 25], TP ∈ [4, 40].)*

## Architecture

```
contexte cognitif (contexte_complet décompressé)
   │
   ▼
MarketCycleDetector.extract()      core/v9/market_cycle_detector.py
   │   → CycleSignals (vélocité, accel, compression, coalition,
   │      profondeur MTF, régime, phase comportementale, session)
   ▼
PhaseClassifier.classify()         core/v9/phase_classifier.py
   │   → (MarketPhase, confiance, rationale)      [règles pures]
   ▼
SLTPCalibrator.compute()           core/v9/dynamic_risk_manager.py
   │   → profil de phase × modulation coalition × garde-fou session
   ▼
RiskDecision (SL/TP/exit/trailing/BE/allow_new_position/rationale)
```

`DynamicRiskManager.evaluate(context, decision, previous_phase)` orchestre le
tout et **ne lève jamais** (R6). Phase indéterminée ou contexte absent →
`RiskDecision(source="fallback")` sur le profil session `DYNAMIC_PROFILES`.

### Signaux lus (aucun nouveau calcul de marché — R18)

| Signal | Source | Usage |
|---|---|---|
| vélocité, accélération | `scene.cinematique_json` | climax, cassure |
| compression / extension | `scene.cinematique_json.compression_extension` | accumulation vs cassure |
| intensité / tendance / âge coalition | `scene.coalitions_json[0]` | force, distribution |
| profondeur MTF (D1…M1), emboîtement | `scene.confluences_mtf_json` | modulation HTF/LTF |
| régime | `regime[].regime_type` | cassure/trend/retour |
| phase comportementale | `behavior.phase` | initiation/développement/culmination/resolution |
| session | `contexte_temporel_json` / heure UTC | garde-fou O4 |

## Modulation coalition

Appliquée sur le TP (et le SL pour la profondeur) après le profil de phase :

| Condition | Effet | Raison |
|---|---|---|
| Coalition HTF (D1/H4) | TP ×1.5, SL ×1.2 | espérance de vie longue, mouvement ample |
| Coalition LTF (M5/M15/M1) | TP ×0.8, SL ×0.8 | éphémère, mouvement court |
| Emboîtement multi-TF | TP ×1.3 | confluence = confirmation |
| Coalition forte (>60) | TP ×1.2 | plus de conviction |
| Coalition faible (<30) | TP ×0.7 | moins de conviction |

## Statut SHADOW et activation

Le module est câblé dans `trade_engine.process()` (étape 4b) : il évalue la
`RiskDecision` et l'attache à `result["dynamic_risk"]` **sans modifier** le
`tp_pips`/`sl_pips` réellement utilisé. C'est une couche d'observation.

- Kill switch : `V9_DYNAMIC_RISK_ENABLED` (défaut ON = évaluation shadow ;
  `0` = désactivé).
- **Activation (mode APPLY)** : décision CEO (Søn). Non câblée. Toute
  application devra réconcilier les bornes SHADOW [6,25]/[4,40] avec les
  bornes APPLY de R30 (TP 5-20, SL 5-20).

## Validation empirique (replay 2000 décisions résolues)

| Phase détectée | n | WR | pips moyen |
|---|---|---|---|
| accumulation | 12 | 75.0% | +2.46 |
| trend | 72 | 68.1% | +1.97 |
| distribution | 1704 | 68.7% | +0.44 |
| cassure | 146 | 64.4% | +0.99 |
| retour | 61 | 70.5% | +0.58 |
| **climax** | 5 | **20.0%** | **-6.30** |

Lecture : la phase **climax** isole précisément les pires trades (WR 20 %,
-6.3 pips) — ce que le garde-fou « aucune nouvelle position » évite.
Accumulation et trend concentrent le meilleur pips moyen. Le signal de phase
est donc discriminant et exploitable (à valider en paper trade avant APPLY).

## Fichiers

| Fichier | Rôle |
|---|---|
| `core/v9/market_cycle_detector.py` | extraction signaux + détection phase + transitions |
| `core/v9/phase_classifier.py` | règles pures signals → phase |
| `core/v9/dynamic_risk_manager.py` | RiskDecision + SLTPCalibrator + orchestration |
| `core/v9/trade_engine.py` | hook SHADOW (étape 4b, `_load_full_context`) |
| `tests/test_market_cycle_detector.py` | 24 tests détection/extraction |
| `tests/test_dynamic_risk_manager.py` | 24 tests calibration/modulation/fallback |
| `tests/test_trade_engine_dynamic_risk.py` | 6 tests intégration shadow |
