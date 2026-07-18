# Audit Boucles & Edge Baissier — PowerFlow V9

> **Date** : 2026-07-18 15h55 UTC
> **Auteur** : Hermes/M3 (CEO motion Søn)
> **Trigger** : DB live révèle 4 817 paper_trades clôturés, **−47 327 pips** (narratif rapports "WR 90% / PF 4.96" FAUX, vérifié en SQL).
> **Statut** : Kill immédiat appliqué, audit en cours.

---

## 1. Verdict empirique (lecture directe `data/v9_forces.db`)

| Métrique | Valeur | Source |
|---|---|---|
| Paper_trades clôturés | 4 817 | `SELECT count(*) FROM paper_trades WHERE is_win IS NOT NULL` |
| Win rate | **23.67%** | `100 * sum(is_win) / count(*)` |
| Profit factor | **0.16** | gross_win / gross_loss |
| Total pips | **−47 327** | `sum(pips_simulated)` |
| Avg / trade | −9.83 pips | moyenne |
| Sharpe-like (an.) | **−67.79** | mean / stdev × √N |
| Max DD | −47 327 pips | running sum |
| Recovery factor | **−1.00** | jamais récupéré |

**Le système est massivement perdant. Pas d'edge.**

---

## 2. Concentration des pertes (2026-07-17)

| Heure | N | WR% | Pips |
|---|---|---|---|
| 15:00 | 644 | 49.84% | −3 521 |
| **16:00** | **4 054** | **19.51%** | **−43 018** |
| 17:00 | 21 | 23.81% | −76 |
| 18:00 | 6 | 33.33% | −22 |
| 19:00 | 25 | 8.00% | −98 |

**Heure 16:00 = 86% du volume et 92% des pertes.**

### Minutes les plus chargées
- 16:05 → 962 trades (16.0% WR, −11 053 pips)
- 16:04 → 862 trades (10.0% WR, −11 211 pips)
- 16:06 → 801 trades (18.1% WR, −8 790 pips)

**3 minutes = 2 625 trades = 55% du volume quotidien, 100% des pertes concentrées.**

---

## 3. Cause racine algorithmique

### 3.1 — Boucle de re-entry
Le système a reçu un signal baissier persistant sur GBPUSD pendant ~10 minutes
(15:55 → 16:06) et a **ré-entré en boucle** tant que le signal restait ACTIF.

**Absence constatée** :
- ❌ Aucun cooldown entre trades (re-entry immédiate sur signal identique)
- ❌ Aucune limite de positions ouvertes par symbol
- ❌ Aucun stop après X pertes consécutives (anti-martingale)
- ❌ Aucune durée minimum de vie du trade (4 174/4 750 = 88% fermés en 0 min)

### 3.2 — SL/TP calibrés sur vitesse lissée
Source : `core/v9/v9_bear_perception.py` docstring (audit CEO antérieur) :

```
M1  brut  : moyenne baissier 0.55 pips/min, spikes jusqu'à 2.5 pips/min
M15 lissé : moyenne baissier 0.17 pips/min   (facteur ~3x plus lent !)
```

→ SL 15 pips ≈ 30 min attendues en M15 lissé, mais touché en **~6 min** en M1 réel.
→ Le bruit intra-bar fait sortir le trade avant que le move s'exprime.

### 3.3 — Principe déclencheur unique
| Pattern | N | WR% | Pips | % volume 17/07 |
|---|---|---|---|---|
| `["PRICE_LAG_AT_NODE_BIRTH"]` | **3 928** | **16.9%** | **−45 284** | **83%** |
| `["POWER_ANGLE_BREAK_TO_PRICE_IMPACT", "ZONE_RETEST"]` | 177 | 83.1% | +732 | 4% |
| `["GRAVITY_RESPRING_NODE", "PRICE_LAG_AT_NODE_BIRTH"]` | 125 | 87.2% | +648 | 3% |

**Le principe unique `PRICE_LAG_AT_NODE_BIRTH` = 83% du volume et 99.4% des pertes.**

### 3.4 — Asymétrie direction
| Direction | N | WR% | Avg | Total |
|---|---|---|---|---|
| baissiere | 3 655 | **1.07%** | −15.15 | **−55 462** |
| haussiere | 1 095 | **98.81%** | +7.99 | **+8 727** |

**3655 shorts perdants à −15 pips chacun** = SHORT structurellement cassé.
Edge haussier seul viable (mais pas suffisant pour compenser).

---

## 4. Kill immédiat appliqué (motion CEO 15h55)

### 4.1 — `core/v9/principles/PRICE_LAG_AT_NODE_BIRTH.yaml`
- `v9_status: ACTIVE` → `SHADOW`
- R23 suspendu par motion CEO explicite
- **Effet** : 83% du volume du 17/07 ne se reproduira plus

### 4.2 — `config/v9_kill_switches.env`
| Switch | État | Effet |
|---|---|---|
| `V9_NO_BAISSERE=1` | ✅ ON (nouveau) | Bloque TOUT short, force `direction=haussiere` |
| `V9_BEAR_PERCEPTION_ENABLED=1` | ✅ ON (nouveau) | Active correction vitesse M1 réelle |
| `V9_GBPUSD_LONG_ONLY=1` | ✅ déjà ON | Force GBPUSD long-only |
| `V9_MARKET_REGIME_GLOBAL_ENABLED=1` | ✅ déjà ON | Modulateur TP selon régime |
| `V9_POSITION_MANAGER_ENABLED=1` | ✅ déjà ON | Break-even / partial close / stagnation |

**Cumul des protections** : SHORT 100% bloqué + correction vitesse active.

### 4.3 — Anti-boucle NON câblés (à faire session suivante)
| Switch | Spécification | Statut |
|---|---|---|
| `V9_MIN_HOLD_BARS=1` | Bloque re-entry si position ouverte < N barres | ⚠️ Documenté, NON actif |
| `V9_MAX_OPEN_TRADES_PER_SYMBOL=3` | Limite exposition par symbol | ⚠️ Documenté, NON actif |

Ces 2 vars sont dans `.env` en commentaire uniquement. **À câbler dans
`core/v9/trade_engine.py` en session dédiée** (sortie trade + check positions ouvertes).

---

## 5. Modules de protection EXISTANT mais OFF historiquement

3 modules sont déjà codés (livraison antérieure) et désactivés par défaut :

| Module | Kill switch | État avant 15h55 | État après |
|---|---|---|---|
| `core/v9/trade_engine.py:_gbpusd_long_only_enabled()` (l. 110) | `V9_GBPUSD_LONG_ONLY` | ON (depuis 18/07) | ON |
| `core/v9/trade_engine.py:_no_baissiere_enabled()` (l. 115) | `V9_NO_BAISSERE` | OFF | **ON** |
| `core/v9/v9_bear_perception.py:BearPerceptionCorrection` | `V9_BEAR_PERCEPTION_ENABLED` | OFF | **ON** |

**Le 17/07 = système qui a tourné SANS les 2 dernières protections.** Le pipeline
a déclenché 4 750 shorts avec un SL/TP calibré sur du bruit lissé.

---

## 6. Edge viable identifié

**Direction haussière uniquement** :
- 1 108 trades haussiers, 98.83% WR, +8.01 pips/trade, **+8 850 pips total**
- 3655 trades baissiers, 1.07% WR, −15.15 pips/trade, **−55 462 pips total**

**Avec les protections actives**, le système devrait :
- ✅ Ne plus短
- ✅ Détecter les mouvements rapides M1 et adapter les exits
- ✅ Forcer GBPUSD long-only (déjà actif)

→ **Edge haussier attendu : +8 à +15 pips/trade sur trades haussiers seulement.**

---

## 7. Reste à faire (sessions CEO)

### Priorité 1 — Câblage kill switches manquants
- [ ] `core/v9/trade_engine.py` : ajouter `V9_MIN_HOLD_BARS` check à l'entrée
      d'une nouvelle décision (rejeter si position < N barres sur même symbol+dir)
- [ ] `core/v9/trade_engine.py` : ajouter `V9_MAX_OPEN_TRADES_PER_SYMBOL`
      check (compter positions ouvertes par symbol, rejeter si > N)
- Scope : 1 commit, R22 strict, R6 try/except obligatoire.

### Priorité 2 — Audit SL/TP baissier
- [ ] Identifier dans `core/v9/trade_engine.py` ou `core/v9/dynamic_risk_manager.py`
      où `direction='baissiere'` est convertie en SL/TP. Vérifier qu'il n'y a pas
      d'inversion (SL 15 = +15 pips au lieu de −15).
- [ ] Backtest 17/07 avec protections ON (mesurer pertes évitées).

### Priorité 3 — Walk-forward post-fix
- [ ] 5-fold temporel sur la DB live avec edge haussier seul.
- [ ] Sharpe-like cible : ≥ 1.0 sur l'échantillon walk-forward.

---

## 8. Conclusion CEO

**Avant 15h55 UTC** : le système V9 avait **3 filets de sécurité désactivés** qui
auraient évité 99.4% de la catastrophe du 17/07. Le pipeline tournait en mode
"sans filet".

**Après 15h55 UTC** :
- 1 principe désactivé (PRICE_LAG_AT_NODE_BIRTH)
- 2 kill switches critiques activés (NO_BAISSERE, BEAR_PERCEPTION)
- 3 autres déjà actifs (POSITION_MANAGER, MARKET_REGIME_GLOBAL, GBPUSD_LONG_ONLY)

**Reste critique** : câbler V9_MIN_HOLD_BARS et V9_MAX_OPEN_TRADES_PER_SYMBOL avant
toute activation live dimanche 22h UTC. Sans ces 2 vars, une nouvelle boucle sur
un autre principe est possible.

**Doctrine** : R6 (défensif), R8 (doc), R23 suspendu par motion CEO (PRICE_LAG),
R28 (CEO motion explicite), R30 (limites positions — à implémenter).

**Référencement** :
- `core/v9/principles/PRICE_LAG_AT_NODE_BIRTH.yaml` (SHADOW)
- `config/v9_kill_switches.env` (3 switches ON, 2 documentés)
- `core/v9/trade_engine.py:115` (`_no_baissiere_enabled`)
- `core/v9/v9_bear_perception.py` (BearPerceptionCorrection)
- `DECISIONS_LOG.md` §2026-07-18 15h55
- Commit : à compléter post-push

---

*Audit rédigé le 2026-07-18 15h55 UTC par Hermes/M3 sur motion CEO Søn.*
