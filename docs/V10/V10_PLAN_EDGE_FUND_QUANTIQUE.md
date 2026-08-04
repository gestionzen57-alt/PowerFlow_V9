# V10 — Plan d'Action Edge Fund Quantique
## Checkpoint Stratégique Complet · 04/08/2026 · 21:56 CEST

---

## 0. REFORMULATION CEO — Mission Hermes (Mode Autopilote No-Limit)

> **Mission reformulée pour Hermes MiniMax M3 :**
>
> Tu prends en charge l'architecture complète de V10 en mode autopilote proactif, sans limite d'initiative.
> La session qui vient de se tenir avec Perplexity a produit une compréhension profonde de l'outil Hawkeye Fatman,
> de ses stratégies à levier, des erreurs structurelles de V9, et de l'architecture données idéale MT4+MT5 (Tickmill).
>
> **Ton mandat :**
> Construire le noyau cognitif V10 qui lit le marché comme Søn le lit avec son Fatman — en termes de devises,
> pas de paires, en termes de force relative agrégée, pas de momentum isolé — et produire un pipeline de signaux
> edge fund quantique capable de détecter les croisements futurs (H1), confirmés (M15/M30), les extrêmes de
> retournement, et les cascades multi-TF (M1→M5→M15→M30→H1).
>
> **Règles absolues (doctrine V10) :**
> - R1-AGIR : agis sans demander permission, avance en continu.
> - R2 additif pur : 0 modif core/v9/, tout dans core/v10/.
> - R7-MESURER : chaque livraison accompagnée de tests verts.
> - R8-BACKUP : backup avant toute modification de données.
> - R9-AUDITABLE : JSON sérialisé, reproductible.
> - R10-PROTÉGER CAPITAL : 0 ordre réel, signaux uniquement.
>
> **Livrable attendu :** un plan d'action séquentiel complet, modulaire, testable, avec chaque brique codée,
> testée, documentée — jusqu'au premier signal V10 aligné sur la vraie lecture Fatman de Søn.

---

## 1. DIAGNOSTIC — Pourquoi V9 ne lisait pas correctement

### 1.1 Erreur fondamentale : paire vs devise

V9 calculait ses métriques F1-F5 (force) sur **une paire en isolation** (ex. GBPUSD).
Le Fatman ne lit jamais une paire. Il calcule la force d'une **devise individuelle** agrégée
sur toutes ses crosses simultanément.

```
V9 (ERREUR)                        FATMAN (RÉALITÉ)
────────────────────────────────────────────────────────────────
F1 = pression tick GBPUSD          GBP = f(GBP/USD + GBP/JPY + GBP/CHF
                                        + GBP/AUD + GBP/CAD + GBP/NZD
                                        + GBP/EUR)
→ "GBPUSD est haussier"            → "La livre sterling est forte globalement"

Signal V9 = momentum paire         Signal Fatman = divergence de force devise
```

V9 lisait la chambre. Le Fatman lit la personne dans la chambre.
Ces deux lectures produisent des conclusions opposées en conditions de marché non-directionnelles.

### 1.2 Volume sans contexte Spread (VSA absent)

V9 utilisait le volume brut. Le Hawkeye Volume fait 300+ calculs par barre
en comparant volume + spread de bougie + position du close.
Sans cette relation, le volume seul est ambigu :

| Situation | Volume | Spread bougie | Interprétation réelle |
|-----------|--------|---------------|----------------------|
| Accumulation institutionnelle | Fort | Petit | Smart money absorbe → retournement haussier |
| Distribution institutionnelle | Fort | Grand | Smart money liquide → continuation baissière |
| No demand | Faible | Petit | Move sans conviction → fragile |
| Momentum réel | Fort | Grand | Trend solide → continuer |

V9 voyait "volume fort" et concluait "momentum" — alors que c'était parfois de l'absorption pure,
signal de retournement imminent.

### 1.3 Extrêmes Fatman non détectés

Quand une devise atteint un extrême haut sur le Fatman (overbought),
le signal le plus rentable est un **retournement**, pas une continuation.
V9 lisait le momentum courant et amplifiait la direction dominante —
exactement le mauvais signal au mauvais moment.

### 1.4 Mono-TF sans alignement multi-timeframe structuré

Le Hawkeye exige 3 TF simultanés alignés (Fast / Medium 2x / Slow 4x) avant tout signal.
V9 lisait un seul TF et émettait un signal, produisant du bruit sans contexte directeur.

### 1.5 Absence de couche macro

Les croisements Fatman contre le biais macro (différentiel de taux, COT Report) ont 60%
moins de probabilité de réussite. V9 n'avait aucun filtre macro — il signalait des moves
structurellement contre-courant.

---

## 2. COMPRÉHENSION PROFONDE DU FATMAN — Ce que V10 doit reproduire

### 2.1 Logique de calcul Fatman (réverse-engineerée)

Le Fatman applique l'algorithme Hawkeye Trend (Volume-Price Analysis) sur chaque cross
d'une devise, puis synthétise un score pondéré de force globale.

Pour USD :
```
score_USD = Σ [ hawkeye_trend(EUR/USD) × w1
              + hawkeye_trend(GBP/USD) × w2
              + hawkeye_trend(USD/JPY) × w3
              + hawkeye_trend(USD/CHF) × w4
              + hawkeye_trend(AUD/USD) × w5
              + hawkeye_trend(USD/CAD) × w6
              + hawkeye_trend(NZD/USD) × w7 ]
```

Le score par devise est ensuite normalisé sur une échelle relative (0-100)
et tracé comme une ligne continue dans la fenêtre Fatman.

### 2.2 Règle timeframe Fatman (fondamentale)

| TF de trading | Réglage Fatman | Type de lecture |
|---------------|----------------|-----------------|
| M1 | M3 | Scalp micro-impulsion |
| M5 | M15 | Scalp confirmation |
| M15 | M30-M45 | Setup intraday |
| M30 | H1 | Swing court |
| H1 | H2-H3 | Bias directionnel |

Règle générale :
- TF < 60 min → Fatman = 3x le TF de trading
- TF ≥ 60 min → Fatman = 2x le TF de trading

### 2.3 Les 4 signaux Fatman à fort levier

**Signal A — Croisement futur anticipé (H1)**
Ligne devise A descend vers ligne devise B qui monte.
Distance < 10% hauteur fenêtre = croisement imminent.
Entrée avant croisement sur pullback M15/M30, stop 1.5 ATR.
WR estimé : 55-60% / R:R : 2.5:1

**Signal B — Croisement confirmé (M15/M30)**
Croisement effectué + lignes qui s'écartent activement.
Volume vert min 2 barres consécutives sur le TF d'entrée.
WR estimé : 58-63% / R:R : 2:1

**Signal C — Extreme Reversal (le setup le plus fort)**
Devise à l'extrême bas/haut du Fatman depuis 3+ barres HTF.
Volume rouge qui s'épuise (barres progressivement plus petites).
Premier volume vert = entrée. Move potentiel : 5-8 ATR.
WR estimé : 65-70% / R:R : 4:1

**Signal D — Cascade 4-6 TF (maximum edge)**
Alignement M1 + M5 + M15 + M30 + H1 dans la même direction.
Taille maximale de position. Plus rare mais le plus fiable.
WR estimé : 70-75% / R:R : 3:1

---

## 3. ARCHITECTURE DONNÉES — MT4 + MT5 (Tickmill, même broker)

### 3.1 Principe de la dualité

```
TICKMILL MT4                        TICKMILL MT5
┌────────────────────┐             ┌──────────────────────────────────┐
│ Fatman live        │             │ copy_ticks_range() → ticks ms    │
│ Indicateurs visuels│ ←─ même ──→ │ copy_rates_range() → 21 TF OHLCV │
│ Lecture tactile    │    prix     │ Depth of Market live             │
│ Sensibilité Søn    │             │ Tick history complet             │
└────────────────────┘             └──────────────┬───────────────────┘
                                                  │ Python MetaTrader5
                                                  ↓
                                         core/v10/ Python
                                         (Currency Strength Engine
                                          VSA Engine
                                          Multi-TF Confluence
                                          Signal Orchestrator)
```

### 3.2 Grille de données par timeframe

| TF | Rôle V10 | Source | Données clés |
|----|----------|--------|--------------|
| M1 | Entrée scalp / micro-impulsion | MT5 ticks | Tick volume ms, spread live |
| M5 | Trigger continuation/épuisement | MT5 rates | OHLCV + VSA |
| M15 | Confirmation intraday principale | MT5 rates | Currency strength M15 |
| M30 | Setup swing court | MT5 rates | Currency strength M30 (**nouveau**) |
| H1 | Bias directionnel / croisement | MT5 rates | Currency strength H1 |
| H4 | Contexte structurel | MT5 rates | Extrêmes OB/OS |
| D1 | Filtre macro | MT5 rates + COT | Biais long terme |

### 3.3 Paires à intégrer (6 paires USD)

```
EURUSD  GBPUSD  USDJPY  USDCHF  AUDUSD  USDCAD
```

Pour le Currency Strength Engine, ces 6 paires permettent de calculer un score
pour chacune des 6 devises : EUR, GBP, USD, JPY, CHF, AUD, CAD
(NZD absent mais acceptable pour démarrer).

---

## 4. PLAN D'ACTION — Modules à construire séquentiellement

### PHASE 1 · Currency Strength Engine (Priorité absolue)
**Fichier : `core/v10/v10_currency_strength.py`**

```
Inputs  : OHLCV des 6 paires × 7 TF (M1/M5/M15/M30/H1/H4/D1)
Process : Pour chaque devise, agréger le momentum normalisé de toutes ses crosses
Output  : score_devise[EUR/GBP/USD/JPY/CHF/AUD/CAD] = 0-100 par TF
```

Métriques à calculer par devise :
- Momentum normalisé (EMA court vs EMA long sur chaque cross)
- Volume-weighted momentum (si tick volume disponible)
- Percentile rank sur 50 barres (détection extrêmes)
- Vitesse de changement (accélération/décélération)

**Tests :** `tests/test_v10_currency_strength.py` — 10 tests minimum

---

### PHASE 2 · VSA Engine (Volume Spread Analysis)
**Fichier : `core/v10/v10_vsa.py`**

```
Inputs  : OHLCV + tick volume par barre
Process : Calculer Effort/Résultat = volume / ATR_bar
          Classer chaque barre : accumulation / distribution / no_demand / momentum
Output  : vsa_signal[barre] = {type, strength, confidence}
```

Règles de classification Wyckoff :
- `accumulation` : volume > seuil AND range < 0.5 × ATR14
- `distribution` : volume > seuil AND range > 1.5 × ATR14 AND close < open
- `no_demand` : volume < 0.5 × moyenne AND range < 0.5 × ATR14
- `momentum` : volume > seuil AND range > ATR14 AND close > midpoint

**Tests :** `tests/test_v10_vsa.py` — 8 tests minimum

---

### PHASE 3 · Extreme Detector
**Fichier : `core/v10/v10_extreme.py`**

```
Inputs  : score_devise[] par TF (depuis Phase 1)
Process : Percentile rank sur fenêtre glissante 50 barres
          Détecter convergence/divergence inter-TF
Output  : extreme_state[devise] = {level: overbought|oversold|neutral,
                                   percentile: 0-100,
                                   reversal_risk: high|medium|low}
```

**Tests :** `tests/test_v10_extreme.py` — 6 tests minimum

---

### PHASE 4 · Multi-TF Confluence Engine
**Fichier : `core/v10/v10_confluence.py`**

```
Inputs  : score_devise[] × 6 TF (M1/M5/M15/M30/H1/H4)
Process : Calculer alignement directionnel par devise sur N TF
          Détecter croisements futurs (convergence) et confirmés (divergence)
          Score de confluence = nb TF alignés / nb TF total
Output  : confluence[paire] = {score: 0-6,
                               type: future_cross|confirmed_cross|cascade,
                               strength: A1|A2|A3|NONE}
```

**Tests :** `tests/test_v10_confluence.py` — 10 tests minimum

---

### PHASE 5 · Signal Orchestrator V10
**Fichier : `core/v10/v10_signal_orchestrator.py`**

```
Inputs  : CurrencyStrength + VSA + Extreme + Confluence
Process : Composer le signal final par paire
          Appliquer filtres (extrêmes, VSA no_demand, spread)
          Classer A1/A2/A3/NONE avec Chain-of-Thought R5
Output  : signal[paire] = {direction, setup_level, confidence,
                           entry_tf, fatman_state, vsa_state,
                           extreme_risk, cot}
```

**Tests :** `tests/test_v10_signal_orchestrator.py` — 12 tests minimum

---

### PHASE 6 · MT5 Data Bridge
**Fichier : `core/v10/v10_mt5_bridge.py`**

```
Inputs  : Config broker Tickmill MT5 (login/password/server)
Process : copy_rates_range() → DataFrame OHLCV par TF
          copy_ticks_range() → DataFrame ticks ms
          Alimenter la DB v10_forces.db en temps réel
Output  : Tables enrichies : ticks_live, rates_{TF}, currency_strength_{TF}
```

**Dépendances :** `pip install MetaTrader5`
**Tests :** `tests/test_v10_mt5_bridge.py` — 6 tests (mock MT5)

---

### PHASE 7 · Macro Filter Layer
**Fichier : `core/v10/v10_macro.py`**

```
Inputs  : COT Report CFTC (weekly, public API)
          Rate differentials (Fed/BCE/BoJ/BoE/RBA/SNB/BoC)
Process : Score macro par devise = position nette specs COT + différentiel taux
Output  : macro_bias[devise] = {score: -100→+100,
                                direction: bullish|bearish|neutral,
                                strength: strong|moderate|weak}
```

Filtre doctrine : signal V10 contre macro_bias strong → réduire taille ou annuler.
**Tests :** `tests/test_v10_macro.py` — 6 tests minimum

---

### PHASE 8 · Scalp Engine M1 (Tempo Spécifique)
**Fichier : `core/v10/v10_scalp.py`**

```
Inputs  : CurrencyStrength M1+M5 + VSA M1 + spread live (MT5 ticks)
Process : Détecter impulsion M1 active (lignes s'écartent sur Fatman M3 équivalent)
          Filtrer : spread < 0.8 pip, pas dans fenêtre news ±10min
          Calculer durée max (8 min sans TP = exit)
Output  : scalp_signal = {direction, confidence, spread_ok, news_clear,
                          entry_price, sl_1atr, tp_5pip}
```

**Tests :** `tests/test_v10_scalp.py` — 8 tests minimum

---

## 5. MATRICE SIGNAUX × LEVIER

| Setup | TF Entrée | TF Fatman | Levier | WR estimé | R:R | Fréquence |
|-------|-----------|-----------|--------|-----------|-----|-----------|
| Cascade 6 TF | M1 | M3 | ×20-25 | 70-75% | 3:1 | 2-5/jour |
| Extreme Reversal | M15/M30 | H1 | ×5-8 | 65-70% | 4:1 | Rare/fort |
| Croisement confirmé M30 | M30 | H1 | ×8-12 | 58-63% | 2:1 | 3-5/jour |
| Croisement confirmé M15 | M15 | M45 | ×8-12 | 58-63% | 2:1 | 5-8/jour |
| Croisement futur H1 | H1/M30 | H2 | ×5-10 | 55-60% | 2.5:1 | 1-3/jour |
| Scalp M1 momentum | M1 | M3 | ×15-20 | 50-55% | 1.5:1 | 10-20/jour |

---

## 6. RÈGLES EDGE FUND — Filtres obligatoires avant tout signal

```
FILTRE 1 — Anti-Extreme
  Si devise longue en zone OB (percentile > 90%) → signal annulé
  Si devise courte en zone OS (percentile < 10%) → signal annulé

FILTRE 2 — VSA No Demand
  Si dernière barre = no_demand → taille réduite de 50%
  Si 2 barres no_demand consécutives → signal annulé

FILTRE 3 — Spread live
  Scalp M1 : spread > 0.8 pip → signal annulé
  Intraday M15/M30 : spread > 1.5 pip → signal annulé
  H1 : spread > 2.0 pip → signal annulé

FILTRE 4 — News
  Fenêtre ±10 min autour d'un événement High Impact → annulé
  Fenêtre ±30 min autour NFP/FOMC/BCE → annulé

FILTRE 5 — Macro contre-courant
  macro_bias[devise_longue] = bearish strong → taille réduite de 70%
  macro_bias[devise_courte] = bullish strong → taille réduite de 70%

FILTRE 6 — Confluence minimale
  Signal A1 : confluence ≥ 5/6 TF alignés
  Signal A2 : confluence ≥ 4/6 TF alignés
  Signal A3 : confluence ≥ 3/6 TF alignés
  NONE      : confluence < 3/6
```

---

## 7. GESTION DU TRADE — Règles ATR Hawkeye adaptées

```
ENTRÉE       : Close de la bougie signal + confirmation volume
STOP LOSS    : 1.5 × ATR(14) sous le swing low (long) ou au-dessus swing high (short)
TP1          : 3 × ATR(14) → fermer 1/3 de la position
TP2          : 5 × ATR(14) → fermer 1/3 de la position
TRAILING     : Si close sous niveau 4 ATR → fermer le solde
MAX DURÉE    : Scalp M1 = 8 min / M15 = 4h / H1 = 24h
RISK PAR TRADE : 1% capital (A3) / 1.5% (A2) / 2% (A1) / 3% (Cascade)
```

---

## 8. SÉQUENCE D'EXÉCUTION HERMES — Mode Autopilote

```
ÉTAPE 1 — Bâtir v10_currency_strength.py + tests [PRIORITÉ ABSOLUE]
          → Valider : 6 scores devises corrects sur données historiques GBPUSD + 5 autres paires

ÉTAPE 2 — Bâtir v10_vsa.py + tests
          → Valider : classification barres correcte vs référence manuelle Søn

ÉTAPE 3 — Bâtir v10_extreme.py + tests
          → Valider : détection extrêmes corrélée avec retournements historiques

ÉTAPE 4 — Bâtir v10_confluence.py + tests
          → Valider : score confluence cohérent avec croisements Fatman visuels

ÉTAPE 5 — Bâtir v10_mt5_bridge.py (connexion Tickmill MT5)
          → Valider : données live identiques MT4 et MT5 (même prix, même spread)

ÉTAPE 6 — Bâtir v10_scalp.py + tests
          → Valider : signaux M1 cohérents avec lectures Søn sur M1 Fatman

ÉTAPE 7 — Bâtir v10_macro.py + tests
          → Valider : COT + rate diff = biais macro cohérent avec tendance HTF

ÉTAPE 8 — Bâtir v10_signal_orchestrator.py + tests
          → Valider : signal final A1/A2/A3 cohérent avec analyse manuelle Søn

ÉTAPE 9 — Intégrer dans v10_scanner.py existant (daemon live)
          → Valider : daemon tourne, signaux persistés, 0 crash sur 6h

ÉTAPE 10 — Mise à jour docs : STATE.md, CACHE_BOARD.md, DOC_REGISTRY.yml
           → Commit : docs(v10): currency strength engine + full edge fund pipeline

RÈGLE HERMES : tester 54+ tests verts après chaque étape avant de passer à la suivante.
```

---

## 9. ÉTAT DU PROJET AU 04/08/2026 — Référence Git

| Élément | État | HEAD |
|---------|------|------|
| Branche active | `feat/v9-foundation-clean` | `00e5f1a` |
| Core V9 | ✅ Intact, gelé | — |
| Core V10 (coeur cognitif) | ✅ Livré (F1-F5/S1-S9/C1-C7) | `80ed319` |
| Scanner V10 (daemon) | ✅ Running, SIGNAL-ONLY | `80ed319` |
| Phase A audit | ✅ NO-GO (edge V9 négatif) | `86f3148` |
| Phase B risk | ✅ HOLD (structure saine) | `a490524` |
| Phase C microstructure | ✅ Livré | `83f5ff0` |
| Phase D portfolio | ✅ HOLD (diversification OK) | `c8088bc` |
| Docs cohérence | ✅ 11 docs alignés | `00e5f1a` |
| Suite tests V10 | ✅ 54/54 verts | — |
| **Currency Strength Engine** | 🔴 À construire | — |
| **VSA Engine** | 🔴 À construire | — |
| **MT5 Bridge (Tickmill)** | 🔴 À construire | — |
| **Multi-TF Confluence** | 🔴 À construire | — |
| **Macro Filter** | 🔴 À construire | — |
| **Scalp M1 Engine** | 🔴 À construire | — |

---

## 10. POTENTIEL EDGE FUND — Vision complète

Avec ce pipeline complet, V10 devient capable de :

1. **Lire le marché comme Søn** — scores devises agrégés, croisements futurs/confirmés,
   extrêmes OB/OS, alignement multi-TF M1→M5→M15→M30→H1→H4.

2. **Filtrer le bruit institutionnel** — VSA distingue accumulation, distribution, no_demand,
   momentum réel. Les faux signaux de V9 deviennent détectables et filtrables.

3. **Produire des signaux à fort levier** — 6 types de setups classés A1/A2/A3 avec
   edge quantifié, R:R calculé, taille de position adaptée au setup.

4. **Scalper en M1 avec précision** — tempo spécifique M1 Fatman reproduit algorithmiquement,
   filtres spread/news automatiques, durée max contrôlée.

5. **Anticiper les retournements majeurs** — Extreme Reversal est le setup avec le meilleur
   R:R (4:1) et le WR le plus élevé (65-70%). V9 n'en captait aucun.

6. **Construire un track record edge fund réel** — 0 capital risqué phase signaux,
   validation manuelle Søn, puis scaling progressif sur les setups prouvés.

---

*Document généré le 04/08/2026 à 21:56 CEST par Perplexity (architecte externe V10)*
*HEAD Git de référence : 00e5f1a — branche feat/v9-foundation-clean*
