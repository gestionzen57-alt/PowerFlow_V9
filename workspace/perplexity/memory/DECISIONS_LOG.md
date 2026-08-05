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

---

## 2026-08-05 — Session Hermes autopilote quant (CEO no-limit) — SPRINT 5

### DEC-2026-08-05-010
**Décision** : Brancher les stratégies publiques dans l'orchestrateur (gate final)
**Contexte** : Mandat autopilote "tout brancher, exploiter, apprentissage"
**Raison** : Rendre le pipeline de signal opérationnel end-to-end
**Impact** : `compose_signal_with_context` accepte `public_filters` (session+OTE+SMC+regime)
en GATE FINAL, backward-compatible R2. Fix export `v10_strategy_layers` (gap pré-existant).
**Statut** : ✅ Exécuté

### DEC-2026-08-05-011
**Décision** : Ajouter la boucle d'apprentissage des erreurs (R4/R8)
**Contexte** : Mandat "apprentissage des erreurs, lecture cohérente"
**Raison** : Détecter le drift, recommander la re-calibration par setup
**Impact** : `v10_error_learner.py` (TradeOutcome + ADWIN-like drift + leçons coT, 9 tests).
Cumul tests : 1060 → **1083 verts** (1 pré-existant réparé).
**Statut** : ✅ Exécuté

---

## 2026-08-05 — Session Hermes autopilote quant (CEO no-limit) — SPRINT 6

### DEC-2026-08-05-012
**Décision** : Générer le rapport nocturne consolidé (backtest ICT + error learner + KPI)
**Contexte** : Mandat autopilote "exploiter, apprentissage"
**Raison** : Centraliser les edges exploités en un seul rapport CEO
**Impact** : `scripts/v10_night_report.py` → `reports/v10_night_report_20260805.json`
(8857 signaux : NY +20pts, LONDON +11.4, OUTSIDE -9.8 ; drift détecté)
**Statut** : ✅ Exécuté

### DEC-2026-08-05-013
**Décision** : Validation SHADOW→ACTIVE sur 100 paper trades (gates R10)
**Contexte** : R10 — aucune promotion sans gate mérité
**Raison** : Objectiver la promotion vs proxy biaisé
**Impact** : `scripts/v10_shadow_promotion.py` → verdict **HOLD** (1/4 gates,
WR 54% mais Sharpe 0.047/consistency 49%). R9 honnête : pas de promotion non méritée.
**Statut** : ✅ Exécuté

---

## 2026-08-05 — Session Hermes autopilote quant (CEO no-limit) — SPRINT 7

### DEC-2026-08-05-014
**Décision** : Fermer la boucle R8 auto-recalibration (error learner → bayésien)
**Contexte** : Mandat "apprentissage des erreurs, lecture cohérente, tout brancher"
**Raison** : Rendre l'apprentissage auto-correctif sans intervention humaine
**Impact** : `v10_auto_recalibrator.py` (should_recalibrate + run_auto_recalibration,
8 tests) + `scripts/v10_closed_loop.py`. Live : drift → REVERT (recalib fail-open
after_wr=0 < before_wr=0.49) — conservateur R8. Cumul tests 1083 → **1091**.
**Statut** : ✅ Exécuté

---

## 2026-08-05 — Session Hermes autopilote quant (CEO no-limit) — SPRINT 8

### DEC-2026-08-05-015
**Décision** : Installer le cron nocturne automatique V10 (rapport + boucle R8 + SHADOW)
**Contexte** : Mandat "ne t'arrête pas, fait tout" — le système doit tourner seul
**Raison** : Produire le bilan nocturne + déclencher R8 sans intervention CEO
**Impact** : `scripts/v10_night_cron.sh` + cron Hermes `v10-night-report-r8-loop`
(`d210e2eecd2e`, 01:00 UTC, deliver local). Testé : execution_success=true.
**Statut** : ✅ Exécuté

---

## 2026-08-05 — Session Hermes autopilote quant (CEO no-limit) — SPRINT 9

### DEC-2026-08-05-016
**Décision** : Renforcer R10 — exposition nette par devise + blocage doubles opposées
**Contexte** : Mandat §4c "bloquer les doubles positions opposées"
**Raison** : Le portfolio manager bloquait les corrélées mais pas l'exposition nette/oppositions
**Impact** : `v10_net_exposure.py` (compute_net_exposure, find_directly_opposed,
exposure_gate). Cumul tests 1091 → **1101**. Commit `f2049f4`.
**Statut** : ✅ Exécuté
