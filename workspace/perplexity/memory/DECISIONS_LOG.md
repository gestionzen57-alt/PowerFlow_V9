# DECISIONS LOG — PowerFlow V10
_Historique des décisions structurantes_

---

## 2026-08-05 — Session Perplexity (11h37 CEST)

### DEC-2026-08-05-001
**Décision** : Intégration du TF M30 dans la grille officielle V10  
**Contexte** : Manquant dans V9 et absent des modules v10_force/structure/context  
**Raison** : Le Fatman utilise M30 comme TF de confirmation intermédiaire entre M15 et H1  
**Impact** : TASK-002 créée — injection M30 après TASK-001 validée  
**Statut** : ✅ Décidé — en attente d'exécution

### DEC-2026-08-05-002
**Décision** : `v10_currency_strength.py` est le module #1 prioritaire absolu  
**Contexte** : Compréhension Fatman confirmée — le signal Fatman est fondé sur les scores de forces devises  
**Raison** : Sans scores devises corrects, tous les autres modules (force, structure, context) produisent du bruit directionnel  
**Impact** : TASK-001 bloquante — rien d'autre ne démarre avant 15 tests verts  
**Statut** : ✅ Décidé

### DEC-2026-08-05-003
**Décision** : Plan Hermes edge fund quantique rédigé et poussé sur le repo  
**Contexte** : Demande de plan d'action complet no-limit pour Hermes en mode autopilote  
**Raison** : Centraliser la vision V10 dans un document unique lisible par Hermes sans contexte de session  
**Impact** : `docs/HERMES_PLAN_V10.md` créé — référence principale pour les sessions Claude Code  
**Statut** : ✅ Décidé

### DEC-2026-08-05-004
**Décision** : Tous les fichiers workspace/perplexity poussés directement via GitHub MCP (sans terminal local)  
**Contexte** : Utilisateur ne voit pas les fichiers Perplexity sur le repo  
**Raison** : Push direct API GitHub = source de vérité garantie sans dépendance au filesystem local  
**Statut** : ✅ Exécuté

---

## 2026-08-04 — Session Perplexity

### DEC-2026-08-04-001
**Décision** : Reverse-engineering du Fatman validé  
**Contexte** : Source code indicateur partagé par l'utilisateur  
**Raison** : Compréhension exacte de la logique calcul — scores devises pondérés multi-TF  
**Impact** : Architecture V10 réorientée vers currency_strength en priorité  
**Statut** : ✅ Décidé

### DEC-2026-08-04-002
**Décision** : 6 setups edge fund identifiés avec levier, WR et R:R  
**Contexte** : Analyse signaux Fatman × structure marché  
**Raison** : Formaliser les edges tradables avant de coder le signal engine  
**Statut** : ✅ Décidé — documenté dans HERMES_PLAN_V10.md

---

## 2026-08-05 — Session Hermes autopilote quant (Sprint 3b)

### DEC-2026-08-05-005
**Décision** : Implémenter la stratégie publique ICT 2022 (Kill Zones + OTE) en pure stdlib
**Contexte** : Mandat autopilote quant Hermes §2.2 (HERMES_PROMPT_AUTOPILOT_QUANT.md) ;
libs quant (ruptures/hmmlearn/scipy/pandas_ta) absentes du venv et projet 100% stdlib.
**Raison** : Sprint 3b = stratégie réelle, additif pur R2, zéro dépendance externe ;
wired sur v10_session_filter (Kill Zones compatibles).
**Impact** : `core/v10/v10_ict_ote.py` (Kill Zones ASIAN/LONDON/NY, OTE 62-79%,
trend_bias linéaire, conviction_score, apply_ote_to_signal A1→A2). Export __init__.
20 tests verts (939→959 cumulés).
**Statut** : ✅ Exécuté — commit `0949fa9` pushé

---

## 2026-08-05 — Session Hermes autopilote quant (CEO no-limit) — QUANT UPGRADE

### DEC-2026-08-05-006
**Décision** : Lever la doctrine "100% stdlib" → stack quant complète
**Contexte** : Mandat CEO « installer tout, no limit, plein pouvoir, go »
**Raison** : Donner au V10 son plein potentiel quant (régimes, changepoint, indicateurs)
**Impact** : pyproject v0.10.0, deps scipy/statsmodels/sklearn/hmmlearn/ruptures/arch/plotly/finta
installées dans l'interpréteur des tests. R10 inchangé (SHADOW/paper obligatoire).
**Statut** : ✅ Exécuté

### DEC-2026-08-05-007
**Décision** : Implémenter stratégies publiques Sprint 2 (régimes) + Sprint 3 (SMC)
**Contexte** : Mandat autopilote §2.1/§2.7/§2.8
**Raison** : Edge mesuré sur données live (ICT Kill Zones NY +20pts)
**Impact** : `v10_regime_hmm.py` (11 tests), `v10_smc.py` (14 tests) — 1033 verts cumulés
**Statut** : ✅ Exécuté

### DEC-2026-08-05-008
**Décision** : Backtest public strategies sur v10_signals_clean (8822 signaux)
**Contexte** : R9 audit honnête
**Raison** : Valider le filtre ICT Kill Zones sur données réelles
**Impact** : NY +20pts, LONDON +11.5pts, OUTSIDE −9.8pts → filtre ICT confirmé
**Statut** : ✅ Exécuté

---

## 2026-08-05 — Session Hermes autopilote quant (CEO no-limit) — SPRINT 4

### DEC-2026-08-05-009
**Décision** : Câbler le pipeline de signal avec les stratégies publiques
**Contexte** : Mandat autopilote "go sans arrêter"
**Raison** : Rendre le V10 opérationnel (filtres combinés + vol + Wyckoff)
**Impact** : `v10_filter_compositor.py` (session+OTE+SMC+regime, 10 tests),
`v10_vol_forecast.py` (GARCH+EWMA, 9 tests), `v10_wyckoff_consolidated.py`
(VSA+CE consolidé, 8 tests) → cumul 1060 verts.
**Statut** : ✅ Exécuté
