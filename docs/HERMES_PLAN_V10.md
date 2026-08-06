# PLAN D'ACTION — PowerFlow V10 Edge Fund Quantique
_Document Hermes — Mode autopilote no-limit — 2026-08-05_

> **Plan historique.** Ses modules, seuils de performance et étapes ne sont
> pas le statut courant : la majorité a été livrée ou remplacée. Le statut
> canonique est `docs/V10/DOCUMENT_STATUS.md` puis `docs/V10/STATE.md`
> (HEAD `23cf024`, 1239 tests V10 passés le 06/08).

---

## 🎯 MANDAT HERMES

Tu es Hermes, agent d'exécution no-limit du pipeline V10. Tu opères en mode autopilote proactif sur `feat/v9-foundation-clean`. Ta mission : construire séquentiellement les 8 modules du pipeline edge fund quantique qui reproduit algorithmiquement la lecture Fatman de l'indicateur éditeur.

**Règles absolues :**
- R2 : additif pur — NE JAMAIS modifier les 54 tests verts V9 existants
- R7 : chaque module doit avoir ses propres tests (minimum indiqué) VERTS avant de passer au suivant
- R8 : commit atomique par module — message clair avec résultats tests
- R10 : en cas de doute sur la logique, stop et rapport avant exécution
- **Interdiction absolue** : toucher à V9 core, ouvrir Phase 10, créer des agents spécialisés

---

## 📊 COMPRÉHENSION FATMAN (indicateur éditeur)

### Logique de base
Le Fatman calcule un score de force pour chaque devise (USD/EUR/GBP/JPY/CHF/CAD/AUD/NZD) en agrégeant les données de momentum multi-timeframe.

### Formule reverse-engineerée
```
Score_devise = Σ(poids_TF × momentum_TF) / Σ(poids_TF)

Poids par TF :
  M5  = 1.0
  M15 = 1.5
  M30 = 2.0  ← ajout critique
  H1  = 3.0

Momentum_TF = (close - close[N]) / close[N] × 100
  où N = période de référence du TF (20 bougies)
```

### Signal Fatman
```
Delta = Score_devise_base - Score_devise_quote
Signal FORT  : |Delta| ≥ 2.0  → levier max autorisé
Signal MOYEN : 1.0 ≤ |Delta| < 2.0 → levier standard
Pas de signal : |Delta| < 1.0 → abstention obligatoire
```

### Grille TF Fatman → TF trading
| TF Fatman | TF entrée | TF confirmation |
|---|---|---|
| M5 + M15 | M1 | M5 |
| M15 + M30 | M5 | M15 |
| M30 + H1 | M15 | M30 |
| H1 + H4 | M30 | H1 |

---

## 🏗️ ARCHITECTURE 8 MODULES — SÉQUENCE OBLIGATOIRE

### MODULE 1 — `v10_currency_strength.py` ⚡ PRIORITÉ ABSOLUE
```
Chemin    : core/v10/v10_currency_strength.py
Tests min : 15
Inputs    : OHLCV multi-paires, multi-TF (M5/M15/M30/H1)
Process   : Calcul scores 8 devises selon formule Fatman
Outputs   : Dict {devise: score_float}, delta par paire
Validation: score USD sur EURUSD vs GBPUSD vs USDJPY cohérents
```

### MODULE 2 — Injection M30 modules existants
```
Fichiers  : core/v10/v10_force.py, v10_structure.py, v10_context.py
Tests min : 10 nouveaux (54 existants DOIVENT rester verts)
Action    : Ajouter TIMEFRAME_M30 = 1800 dans les grilles TF
Validation: pytest --tb=short → 64+ tests verts
```

### MODULE 3 — `v10_signal_engine.py`
```
Chemin    : core/v10/v10_signal_engine.py
Tests min : 20
Inputs    : currency_strength + force + structure + context
Process   : Score composite 0-100 + direction + levier recommandé
Outputs   : SignalV10(pair, direction, score, leverage, tf, timestamp)
Validation: backtest 100 signaux historiques → WR ≥ 60%
```

### MODULE 4 — `v10_session_filter.py`
```
Chemin    : core/v10/v10_session_filter.py
Tests min : 10
Logique   : Filtrer signaux hors sessions London + NewYork
Sessions  : London 08:00-17:00 UTC, NewYork 13:00-22:00 UTC
Bonus     : Overlap London/NY 13:00-17:00 UTC = poids ×1.5
```

### MODULE 5 — `v10_atr_manager.py`
```
Chemin    : core/v10/v10_atr_manager.py
Tests min : 10
Logique   : SL = 1.5 × ATR(14, H1), TP = 2.5 × ATR(14, H1)
Adaptatif : ATR recalculé toutes les 4H
Output    : {pair: {sl_pips, tp_pips, rr_ratio}}
```

### MODULE 6 — `v10_backtest_engine.py`
```
Chemin    : core/v10/v10_backtest_engine.py
Tests min : 15
Période   : 6 mois minimum de données
Metrics   : WR, avg R:R, max drawdown, Sharpe ratio, Calmar ratio
Output    : rapport JSON + CSV par setup
```

### MODULE 7 — `v10_live_monitor.py`
```
Chemin    : core/v10/v10_live_monitor.py
Tests min : 10
Logique   : Boucle polling MT4/MT5 → currency_strength → signal_engine
Fréquence : toutes les 60s (M5/M15) ou 30s (M1)
Alerte    : webhook/telegram sur signal fort
```

### MODULE 8 — `v10_portfolio_manager.py`
```
Chemin    : core/v10/v10_portfolio_manager.py
Tests min : 15
Logique   : Gestion corrélations devises, taille positions, max drawdown
Règle     : max 3 positions simultanées corrélées >0.7
Output    : lot_size, position_id, risk_pct
```

---

## 📊 MATRICE SIGNAUX × LEVIER (6 SETUPS)

| Setup | Delta Fatman | TF entrée | Levier | WR cible | R:R min | Fréquence |
|---|---|---|---|---|---|---|
| S1 — Momentum fort | ≥3.0 | M5 | 1:50 | 68% | 1:2.5 | 2-3/j |
| S2 — Continuation | ≥2.0 + structure H1 | M15 | 1:30 | 65% | 1:2.0 | 3-5/j |
| S3 — Reversal M30 | Delta retournement | M30 | 1:20 | 60% | 1:2.0 | 1-2/j |
| S4 — London open | ≥1.5 à 08:00 UTC | M5 | 1:40 | 70% | 1:3.0 | 1/j |
| S5 — NY overlap | ≥2.0 à 13:00 UTC | M1 | 1:50 | 72% | 1:3.0 | 1-2/j |
| S6 — End of trend | Delta divergence | H1 | 1:10 | 55% | 1:3.5 | 0-1/j |

---

## 🔍 FILTRES OBLIGATOIRES EDGE FUND

1. **Filtre nouvelles économiques** : Aucune entrée dans les 30min avant/après news HIGH impact
2. **Filtre spread** : Max 1.5× spread moyen de la paire → pas d'entrée si spread anormal
3. **Filtre volatilité** : ATR(14, H1) doit être dans la plage [percentile 25, percentile 75] sur 3 mois
4. **Filtre corrélation** : Pas de 2 trades simultanés sur paires corrélées >0.8
5. **Filtre drawdown** : Si drawdown journalier >2% → stop trading jusqu'au lendemain
6. **Filtre session** : London ou New York actives uniquement (sauf S1 momentum très fort ≥3.5)

---

## 🚀 SÉQUENCE D'EXÉCUTION HERMES

```
ÉTAPE 0 — Vérification préalable (OBLIGATOIRE avant toute chose)
  → pytest tests/ → confirmer 54 tests verts
  → git status → branche = feat/v9-foundation-clean
  → git log --oneline -5 → lire les 5 derniers commits

ÉTAPE 1 — Créer MODULE 1 (currency_strength)
  → Créer core/v10/v10_currency_strength.py
  → Créer tests/test_v10_currency_strength.py
  → pytest tests/test_v10_currency_strength.py → 15 tests verts
  → git add + commit "feat(v10): add currency_strength module — 15 tests OK"

ÉTAPE 2 — Injecter M30
  → Modifier core/v10/v10_force.py + v10_structure.py + v10_context.py
  → pytest → 64+ tests verts (54 existants + 10 nouveaux M30)
  → git commit "feat(v10): inject M30 timeframe — 64 tests OK"

ÉTAPES 3-8 — Idem, un commit par module
  → Jamais passer à l'étape N+1 si tests étape N non verts
  → Rapport Slack/webhook à chaque étape validée

ÉTAPE FINALE — Premier signal live
  → Lancer v10_live_monitor.py
  → Comparer signal V10 avec lecture visuelle Fatman
  → Si aligné → mode production
  → Si divergence → rapport + correction avant production
```

---

## 📈 VISION POTENTIEL V10

Quand le pipeline est complet :
- **Lecture Fatman algorithmique** : le système voit exactement ce que l'indicateur éditeur voit
- **6 setups automatisés** : signaux en temps réel sur 6 types d'opportunités
- **Gestion de risque dynamique** : taille position adaptée à l'ATR et aux corrélations
- **Edge fund quantique** : WR moyen cible 65%, R:R moyen 1:2.5 → espérance positive solide
- **Scalabilité** : pipeline conçu pour gérer 50+ paires simultanément
- **Audit complet** : chaque signal tracé, chaque trade logué, performance mesurable

_Ce pipeline représente la synthèse de V6 → V7 → V9 → V10. Chaque version a affiné la compréhension. V10 est la version qui trade._
