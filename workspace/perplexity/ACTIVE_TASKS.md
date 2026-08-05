# ACTIVE TASKS — PowerFlow V10
_Mise à jour : 2026-08-05 12:01 CEST — Synchronisé sur git réel_

---

## ✅ TERMINÉES CE MATIN (Zcode — commits 08:22→09:33)

### ~~TASK-001~~ — `v10_currency_strength.py` ✅ LIVRÉ
- **Commit** : `f2ad0c01` — 09:33
- **Résultat** : FatmanCalculator complet, M30 inclus (poids=2.0), 6 TF
- **Tests** : 812/812 verts (dont 54 V9 base + nouveaux currency_strength)
- **Bonus** : FATMAN_BIBLE.md + Pine Script TradingView + spec 34 tests

### ~~TASK-002~~ — M30 dans currency_strength ✅ LIVRÉ
- **Commit** : `0fb736d3` — 09:21
- **Résultat** : M30 intégré avec poids=2.0, mapping M15→M30 dans get_fatman_tf()
- **Note** : À vérifier si M30 injecté aussi dans v10_force/structure/context séparément

---

## 🔥 TÂCHE ACTIVE PRIORITAIRE

### TASK-005 — Calibration live Phase A
- **Priorité** : P0 ACTUEL
- **Statut** : 🔴 À démarrer
- **Responsable** : Hermes / Zcode
- **Objectif** : Valider que FatmanCalculator produit les mêmes signaux que la lecture visuelle de l'indicateur éditeur
- **Méthode** :
  1. Ouvrir CEO Dashboard
  2. Observer delta devise sur EURUSD / GBPUSD / USDJPY
  3. Comparer avec indicateur éditeur sur MT4/MT5
  4. Si écart |delta| > 0.3 → rapport + ajustement poids TF
- **Critère de succès** : 10 signaux consécutifs alignés sur au moins 3 paires

---

## 📋 TÂCHES SUIVANTES

### TASK-006 — `v10_signal_engine.py`
- **Priorité** : P2 — après calibration validée
- **Statut** : 🟡 En attente
- **Chemin** : `core/v10/v10_signal_engine.py`
- **Logique** : Score composite 0-100 = currency_strength + force + structure + context + behavior
- **Tests minimum** : 20

### TASK-007 — `v10_session_filter.py`
- **Priorité** : P3
- **Statut** : 🟡 En attente
- **Logique** : Filtre London 08:00-17:00 UTC + NY 13:00-22:00 UTC + overlap ×1.5

### TASK-008 — `v10_atr_manager.py`
- **Priorité** : P3
- **Statut** : 🟡 En attente
- **Logique** : SL=1.5×ATR(14,H1), TP=2.5×ATR(14,H1), recalcul toutes les 4H

### TASK-009 — `v10_backtest_engine.py`
- **Priorité** : P4 — après P3 validé
- **Statut** : 🟡 En attente
- **Logique** : 6 mois données, WR + R:R + Sharpe + Calmar

---

## ❄️ TÂCHES GELÉES (doctrine)
- Phase 10 fédération agents
- Skills auto-générés
- Architecture mémoire avancée
- Routing modèles
