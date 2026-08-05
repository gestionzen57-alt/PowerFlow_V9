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

---

## 2026-08-05 — Session Hermes autopilote quant (CEO no-limit) — SPRINT 10

### DEC-2026-08-05-017
**Décision** : Bouclier R10 unifié (portfolio + net exposure + DD)
**Contexte** : Mandat "ne t'arrête pas" — R10 = seul vrai garde-fou
**Raison** : Consolider tous les gates R10 en une décision unique pour le live_monitor
**Impact** : `v10_risk_shield.py` (DD halt + position max + net exposure + corrélation).
Cumul tests 1101 → **1109**. Commit `3779cc7`.
**Statut** : ✅ Exécuté

---

## 2026-08-05 — Session Hermes autopilote quant (CEO no-limit) — SPRINT 11

### DEC-2026-08-05-018
**Décision** : Risk dashboard R10 + intégration cron nocturne
**Contexte** : Mandat "ne t'arrête pas" — R10 = seul vrai garde-fou
**Raison** : Exercer le bouclier R10 sur positions live + l'automatiser
**Impact** : `v10_risk_dashboard.py` (net exposure + shield sur positions paper).
Cron nocturne étendu à 4 étapes. Commits `0f42350` + `b7a66ee`.
**Statut** : ✅ Exécuté

---

## 2026-08-05 — Session Hermes autopilote quant (CEO no-limit) — SPRINT 12-13

### DEC-2026-08-05-019
**Décision** : Démo composition publique end-to-end sur DB live + pipeline décision complet
**Contexte** : Mandat "tout brancher, lecture cohérente, apprentissage"
**Raison** : Prouver l'exploitation des stratégies publiques sur données réelles
**Impact** : `scripts/v10_strategy_demo.py` (ICT+SMС+regime+wyckoff+filter sur
forces_snapshots) + `core/v10/v10_decision_pipeline.py` (signal → filtres →
risque → action/lot). Cumul tests 1109 → **1118**. Commits `ed0f4ec` + `e899811`.
**Statut** : ✅ Exécuté

---

## 2026-08-05 — Session Hermes autopilote quant (CEO no-limit) — SPRINT 14

### DEC-2026-08-05-020
**Décision** : Boucle décision live temps-réel (régime → action)
**Contexte** : Mandat "go, lecture cohérente" — le pipeline doit produire en live
**Raison** : Câbler decide_entry dans une boucle de polling temps-réel additif
**Impact** : `scripts/v10_live_decision.py` — direction dérivée du régime HMM.
Live 6 paires : EURUSD/CHF/AUD SELL, GBPUSD BUY, USDJPY/CAD WAIT (range).
Commit `5cc71b7`.
**Statut** : ✅ Exécuté

---

## 2026-08-05 — Session Hermes autopilote quant (CEO no-limit) — SPRINT 15

### DEC-2026-08-05-021
**Décision** : Brancher la boucle décision live en cron (30 min) + persistance
**Contexte** : Mandat "go" — le système doit produire des décisions en continu
**Raison** : Automatiser la génération de signaux sans intervention CEO
**Impact** : `scripts/v10_live_decision_cron.sh` + cron Hermes `v10-live-decision`
(`8c038f0d10e9`, 30 min). Testé : 4 signaux actifs (EURUSD/CHF/AUD SELL, GBPUSD BUY).
**Statut** : ✅ Exécuté

---

## 2026-08-05 — Session Hermes autopilote quant (CEO no-limit) — SPRINT 16

### DEC-2026-08-05-022
**Décision** : Journal persistant des décisions + synthèse de performance
**Contexte** : Mandat "go" — il faut valider l'edge des signaux produits
**Raison** : Mesurer la performance réelle des décisions BUY/SELL (lecture cohérente)
**Impact** : `v10_decision_log.py` (DecisionLogger SQLite + summarize_decisions, 7 tests)
+ câblage dans v10_live_decision (persistance). Cumul tests 1118 → **1125**.
Commits `f6fbb4d` + `9e511cd`.
**Statut** : ✅ Exécuté

---

## 2026-08-05 — Session ZCode audit sync (mandat CEO plein pouvoir, "zéro dette")

### DEC-2026-08-05-023
**Décision** : Réparer le Safe Haven flip inversé (bug moteur Fatman)
**Contexte** : Audit R9 mandat CEO "tout doit servir, pas de zone morte" —
le test safe_haven pré-existant échouait (dette R9 documentée par Hermes).
**Raison** : `_compute_raw_returns` inversait le signe des paires inversées
(USDJPY/USDCHF/USDCAD) : quand JPY/CHF s'apprécient, le moteur les classait
"faibles" et USD "fort" — l'inverse de la réalité. Impact : filtre Safe Haven
(Principe 3 Fatboy) et rankings devises inversés en production.
**Impact** : `returns[quote] = raw` + `USD -= raw` dans v10_currency_strength.py.
Validé : JPY=100/CHF=100/USD=4.6 sur scénario safe_haven (avant : l'inverse).
96 tests currency_strength verts (dette R9 réparée). 1179/1179 tests V10 verts.
**Statut** : ✅ Exécuté — commit `885a851` pushé

### DEC-2026-08-05-024
**Décision** : Réconcilier le doublon strategy_layers vs filter_compositor
**Contexte** : ZCode et Hermes ont créé en parallèle deux chaînes de filtres
publics (session + OTE + SMC + regime) — doublon fonctionnel = dette.
**Raison** : Un seul cœur de filtrage doit exister (R2 additif, zéro duplication).
**Impact** : `v10_strategy_layers` réécrit en WRAPPER de
`v10_filter_compositor.compose_filters` (cœur unique). Export `__init__.py`
vérifié : 27 noms non résolus réparés (zéro zone morte d'API).
**Statut** : ✅ Exécuté

### DEC-2026-08-05-025
**Décision** : Synchroniser les docs d'état multi-acteurs en un seul réel
**Contexte** : STATE.md (racine), CACHE_BOARD, BOARD et AGENTS.md décrivaient
des états différents (692/774/812/959/1118 tests) — désynchronisation
ZCode/Perplexity/Hermes.
**Raison** : Un système multi-IA exige un document de vérité unique (R14).
**Impact** : docs/STATE.md + docs/V10/STATE.md + CACHE_BOARD alignés sur le
réel vérifié : HEAD 9ea7f77, 1179/1179 tests V10 verts.
**Statut** : ✅ Exécuté — ce commit

---

## 2026-08-05 — Session Hermes autopilote quant (CEO no-limit) — SPRINT 17-18 (post-ZCode)

### DEC-2026-08-05-023
**Décision** : Synthèse hebdomadaire + résolution des outcomes réels des décisions
**Contexte** : ZCode a fini sa session (fix safe haven `885a851` intégré, HEAD 99f825f)
**Raison** : Fermer la boucle R8 avec mesure réelle de performance
**Impact** : `scripts/v10_weekly_summary.py` (WR/PnL/Sharpe hebdo vs benchmark,
5e étape cron nocturne) + `scripts/v10_resolve_outcomes.py` (résout pnl/is_win
des décisions depuis prix forward). Cumul tests **1125/1125 verts**.
**Note R9** : ZCode annonce 1179/1179 mais pytest mesure 1125 (écart de comptage).
Commits `83cd046`, `e3d300d`, `77fc04a`.
**Statut** : ✅ Exécuté

---

## 2026-08-05 — Session Hermes autopilote quant (CEO no-limit) — SPRINT 19

### DEC-2026-08-05-024
**Décision** : Notification Telegram des signaux live (canal du projet)
**Contexte** : Mandat "go" — le dernier maillon : notifier le CEO sans surveillance
**Raison** : Envoyer les signaux BUY/SELL sur Telegram via v9_telegram_notifier
**Impact** : `scripts/v10_telegram_alert.py` (testé réel Envoyé=True) + branchement
dans le cron live decision (fix TMPD). Commit `295ad10`. 1125/1125 verts.
**Statut** : ✅ Exécuté

---

## 2026-08-05 — Session Hermes autopilote quant (CEO no-limit) — SPRINT 20

### DEC-2026-08-05-025
**Décision** : Alerte R8 Telegram (recalibration auto sur canal CEO)
**Contexte** : Mandat "go" — fermer la boucle d'alerte d'apprentissage
**Raison** : Notifier le CEO quand le système se recalibre (drift / dégradation)
**Impact** : `scripts/v10_r8_telegram_alert.py` (lit boucle R8 + synthèse hebdo,
alerte DEPLOY/REVERT/HOLD) branché comme 6e étape du cron nocturne.
Testé réel : alerte recalibration REVERT envoyée. Commit `119702a`.
**Statut** : ✅ Exécuté

---

## 2026-08-05 — Session Hermes autopilote quant (CEO no-limit) — REPLAY + APPRENTISSAGE + BILAN

### DEC-2026-08-05-026
**Décision** : Mettre en place replay + apprentissage continu + bilan de la journée
**Contexte** : Mandat CEO "replay + apprentissage continu + bilan quotidien"
**Raison** : Apprendre en continu même en replay (boucle R8), bilan quotidien CEO
**Impact** : `scripts/v10_replay_engine.py` (replay bars → décisions → outcomes → learner,
747 décisions, GBPUSD H1 55.6% + AUDUSD M30 62.7% edges) + `scripts/v10_learning_loop.py`
(apprentissage replay+live, 481 trades WR 50.5%) + `scripts/v10_daily_bilan.py`
(bilan quotidien + reco R8) + notification Telegram (bilan + R8).
Cron nocturne étendu à 8 étapes. Commits `3ff5ea8`→`b7a95d5`. 1125/1125 verts.
**Statut** : ✅ Exécuté

---

## 2026-08-05 — Session Hermes autopilote quant (CEO no-limit) — PERSISTANCE APPRENTISSAGE + REPLAY BATCH

### DEC-2026-08-05-027
**Décision** : Persister le modèle d'apprentissage + replay batch profondeur complète
**Contexte** : Mandat "go" — l'apprentissage doit être continu à travers les sessions
**Raison** : Recharger l'état ErrorLearner entre les runs, carte complète des edges
**Impact** : `v10_learning_persistence.py` (SQLite v10_learning_state + roundtrip, 6 tests,
cumul 1131) + `scripts/v10_replay_batch.py` (replay toute profondeur + edge map + persistance).
Commit `3517eb8`. Batch en cours (arrière-plan).
**Statut** : ✅ Exécuté (code) / ⏳ (batch)

---

## 2026-08-05 — Session Hermes autopilote quant (CEO no-limit) — EDGE SELECTOR

### DEC-2026-08-05-028
**Décision** : Exploiter les 10 edges replay comme filtre de sélectivité dans le pipeline
**Contexte** : Mandat "go" — utiliser les edges appris pour ne trader que les validés
**Raison** : R3/R10 — sélectivité, ne pas trader le marché entier mais les edges validés
**Impact** : `v10_edge_selector.py` (EdgeSelector charge carte replay, ne garde que
WR≥50% + n≥30 + direction dominante) câblé dans v10_live_decision. Résultat live :
EURUSD H1 (WR 40%, pas d'edge) → WAIT, plus conservateur. 10 tests, cumul 1141.
Commit `07da7e4`.
**Statut** : ✅ Exécuté
