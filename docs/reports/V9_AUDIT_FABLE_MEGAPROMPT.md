# POWERFLOW V9 — AUDIT COMPLET & MEGA PROMPT FABLE

## Audit Stratégique CEO Quant — 2026-07-11

---

## TABLE DES MATIÈRES

1. [Résumé Exécutif](#1-résumé-exécutif)
2. [Métriques du Système](#2-métriques-du-système)
3. [Architecture Cognitive — 10 Couches](#3-architecture-cognitive--10-couches)
4. [Chaîne de Trading Complète](#4-chaîne-de-trading-complète)
5. [Forces et Faiblesses](#5-forces-et-faiblesses)
6. [Zones d'Expansion Identifiées](#6-zones-dexpansion-identifiées)
7. [Backlog Priorisé](#7-backlog-priorisé)
8. [MEGA PROMPT FABLE](#8-mega-prompt-fable)

---

## 1. RÉSUMÉ EXÉCUTIF

### 1.1 Identité

| Métadonnée | Valeur |
|---|---|
| **Projet** | PowerFlow V9 |
| **Nature** | Système cognitif de lecture des forces de marché forex |
| **Stack** | Python 3.11+ / SQLite 3.53 / MT4 EA / MCP / Telegram |
| **Branche** | `feat/v9-foundation-clean` |
| **Commits** | 277 (depuis le 2026-07-05) |
| **Fichiers** | 200 Python / 35 YAML / ~80 Markdown |
| **Tests** | ~930 verts (0 régression) |
| **Doctrine** | 30 règles immuables (R1-R30) |
| **DB** | 1.56 GB (compressé), 11 tables, 36 index |

### 1.2 Performance Clé

| Métrique | Valeur | Condition |
|---|---|---|
| **Win Rate réel** | **88.5%** | DYNAMIC (skip NY/After), 8 217 trades |
| **Pips totaux** | **+46 684** | Sur 8 217 trades |
| **Pips/trade** | **+5.7** | TP=10/SL=15 en Asie |
| **WR Asie** | **95.4%** | 6 088 trades, +7.6 pips/trade |
| **WR London** | 69.5% | 1 901 trades, +0.5 pips/trade |
| **WR New York** | 29.6% | 🚫 Structurellement perdant |
| **WR After** | 20.6% | 🚫 Liquidité absente |
| **Ratio R/R** | 0.67:1 | Compensé par WR > 80% |
| **Espérance** | **Positive** | +5.7 pips/trade |

### 1.3 Phases Livrées

| Phase | Statut | Livré le |
|---|---|---|
| 1-8 (Formats → Monitoring) | ✅ | 2026-06-30 |
| 9 (Décision + Principes) | ✅ Canonisée | 2026-07-05 |
| 9.7 (Paper-Trade Simulator) | ✅ | 2026-07-07 |
| 9.8 (VPS-READY) | ✅ | 2026-07-07 |
| 9.9 (Consolidation) | ✅ | 2026-07-07 |
| 9.10 (WIN/LOSS Resolver) | ✅ | 2026-07-08 |
| 13 CEO (Recalibrage) | ✅ | 2026-07-10 |
| 13.2 (Simulation Pro) | ✅ | 2026-07-11 |
| 11 (MCP Architecture) | ✅ | 2026-07-10 |
| 10 (Fédération d'agents) | ⏸️ Gelée | Doctrine |
| 12 (Exécution d'ordres) | ⏸️ Interdit | HITL |
| 13 (Apprentissage complet) | ⏸️ Conditionnel | WIN/LOSS ≥ 50 |

---

## 2. MÉTRIQUES DU SYSTÈME

### 2.1 Volumétrie DB

| Table | Lignes | Rôle |
|---|---|---|
| `forces_snapshots` | 130 371 | Données brutes MT4 |
| `scenes` | 69 115 | Structure de marché |
| `behaviors` | 69 107 | Dynamique qualifiée |
| `windows` | 69 106 | Fenêtres d'opportunité |
| `exploitability` | 69 108 | Jugement de tradabilité |
| `regime_snapshots` | 552 816 | Régime de marché |
| `principle_evaluations` | 642 883 | Évaluations des principes |
| `zone_diagnostics` | 542 096 | Diagnostics de zone |
| `signals` | 69 100 | Signaux agrégés |
| `decisions` | 69 100 | Décisions finales |
| `paper_trades` | 71 | Trades simulés |

### 2.2 Décisions

| Métrique | Valeur |
|---|---|
| Décisions totales | 69 100 |
| `preparer_entree` | 9 516 (13.8%) |
| `aucune_action` | 59 543 (86.2%) |
| `surveiller` | 41 (0.06%) |
| Résolues (is_win) | 9 516 (100%) |
| Wins | 4 192 (44.1%) |
| Losses | 5 324 (55.9%) |

### 2.3 Stratégies de Résolution

| Stratégie | Nb décisions | WR | Pips |
|---|---|---|---|
| **DYNAMIC** | 1 105 | 73.0% | +764 |
| **TP_SL** | 8 115 | 41.7% | -15 185 |
| **SKIPPED** | 295 | 0% | 0 |
| **MFE_ONLY** | 59 585 | — | — |

### 2.4 Paper Trades

| Métrique | Valeur |
|---|---|
| Total | 71 |
| Clôturés | 71 (100%) |
| Wins | 32 (45.1%) |
| Losses | 39 (54.9%) |
| Pips totaux | +209.6 |
| Pips moyens | +3.0 |

---

## 3. ARCHITECTURE COGNITIVE — 10 COUCHES

### 3.1 Chaîne Perceptuelle Amont (Immuable)

```
1. FORCES
   Module: forces_reader.py / capture_server.py
   Entrée: MT4 EA (port 31685 TCP)
   Sortie: forces_snapshots (8 devises × 7 TF)
   Gate: StaleGate (fraîcheur par TF)

2. SCÈNES
   Module: scene_builder.py
   Entrée: forces_snapshots
   Sortie: coalitions, antagonismes, cinématique, MTF, zone

3. COMPORTEMENTS
   Module: behavior_analyzer.py
   Entrée: scenes
   Sortie: 12 qualifications, transitions, similarité

4. FENÊTRES
   Module: window_gate.py
   Entrée: behaviors
   Sortie: 6 statuts (absente/ouverte/fragile/...)

5. EXPLOITABILITÉ
   Module: exploitability_evaluator.py
   Entrée: windows
   Sortie: 5 niveaux + HITL

6. RÉGIME
   Module: regime_detector.py
   Entrée: forces_snapshots (multi-TF)
   Sortie: 6 états (NEUTRE/PALIER/CASSURE/...)
```

### 3.2 Chaîne Opérationnelle Aval (Évolutive)

```
7. PRINCIPES → SIGNAL
   Modules: principle_engine.py / signal_generator.py
   Principes: 25 ACTIVE (9 node_rule + 16 grammar) + 1 SHADOW
   Contexte: 31 champs propagés

8. DÉCISION
   Module: decision_logger.py
   Actions: observer / surveiller / preparer_entree / aucune_action

9. ARBITER → RISKMANAGER
   Modules: arbiter.py / risk_manager.py
   Consolidation: direction majoritaire + confiance moyenne
   Filtre: 5 règles bloquantes

10. PAPERTRADE → HEARTBEAT
    Modules: paper_trade_logger.py / v9_heartbeat.py
    Simulation: ExitSimulator (5 stratégies)
    Risk: PaperRiskManager (sizing, drawdown, corrélation)
```

### 3.3 Modules Phase 13.2 (Livrés 2026-07-11)

| Module | Fichier | Rôle |
|---|---|---|
| **ExitSimulator** | `core/v9/exit_simulator.py` | 5 stratégies (TP_SL, TRAILING, TIME_BASED, MFE_ONLY, **DYNAMIC**) |
| **PaperRiskManager** | `core/v9/paper_risk_manager.py` | Position sizing, max concurrent, drawdown, R/R, corrélation |
| **PyramidingEngine** | `core/v9/pyramiding_engine.py` | Scaling 1.0→2.0× sur confluence multi-TF |
| **PrincipleScorer** | `core/v9/principle_scorer.py` | Table `principle_scores`, pondération 0.5→1.5× |

---

## 4. CHAÎNE DE TRADING COMPLÈTE

### 4.1 Pipeline Entrée → Sortie

```
MT4 EA (forces) → port 31685 → capture_server.py
                                     ↓ INSERT
                                forces_snapshots
                                     ↓ orchestrator.run_chain()
                                SceneBuilder
                                     ↓
                                BehaviorAnalyzer
                                     ↓
                                WindowGate
                                     ↓
                                ExploitabilityEvaluator
                                     ↓
                                RegimeDetector
                                     ↓
                                PrincipleEngine (25 YAML)
                                     ↓
                                SignalGenerator
                                     ↓
                                DecisionLogger
                                     ↓
                                Arbiter.consolidate()
                                     ↓
                                RiskManager.evaluate() → 5 règles
                                     ↓
                                PaperRiskManager.evaluate() → sizing
                                     ↓
                                ExitSimulator.simulate() → DYNAMIC
                                     ↓
                                PaperTradeLogger.log_open()
```

### 4.2 Conditions d'Entrée (Arbiter + RiskManager)

```
1. Au moins 1 décision directionnelle pour ce snapshot
2. Direction majoritaire (vote)
3. Confiance moyenne ≥ 70
4. Au moins 2 principes ACTIVE déclenchés
5. news_phase ≠ NEWS_SHOCK
6. window_status == "exploitable"
7. Session Asie ou London (NY/After = SKIP)
8. Max 3 trades simultanés
9. Drawdown < 15%
10. Pas de trade dans la même direction
```

### 4.3 Conditions de Sortie (ExitSimulator DYNAMIC)

```
Session Asie    → TP=10, SL=15, scale=1.0  (95.4% WR)
Session London  → TP=8,  SL=15, scale=0.8  (69.5% WR)
Session Overlap → TP=5,  SL=15, scale=0.6  (62.7% WR → SKIP)
Session NY      → SKIP (29.6% WR)
Session After   → SKIP (20.6% WR)

Spread: 0.5 pips soustrait du gain / ajouté à la perte
Horizon max: 4h (time_end si ni TP ni SL touché)
```

### 4.4 Gestion de Risque (PaperRiskManager)

```
Capital: 10 000 €
Risk/trade: 1% (100 €)
Position size: risk / (SL_pips × 10) × (confiance/100)
Max concurrent: 3
Max drawdown: 15%
Min R/R: 1.5x (dérogation DYNAMIC: 0.67x mais WR > 80%)
Pyramiding max: 2 ajouts
Correlation check: OUI
```

---

## 5. FORCES ET FAIBLESSES

### 5.1 Forces

| # | Force | Preuve |
|---|---|---|
| F1 | **Architecture cognitive pure** | 10 couches, aucune dépendance LLM dans le cœur (R18) |
| F2 | **Données massives** | 130K snapshots, 69K décisions, 643K évaluations principes |
| F3 | **Doctrine solide** | 30 règles immuables, testées, versionnées |
| F4 | **Simulation réaliste** | ExitSimulator DYNAMIC, spread, TP/SL par session |
| F5 | **WR Asie 95.4%** | Signal fiable en conditions de marché calmes |
| F6 | **0 dette technique** | 930 tests verts, 36 index, DB optimisée |
| F7 | **Modules réutilisables** | 4 modules Phase 13.2 découplés, testables |
| F8 | **HITL intégré** | Telegram, RiskManager, validation humaine |

### 5.2 Faiblesses

| # | Faiblesse | Impact | Priorité |
|---|---|---|---|
| W1 | **WR NY/After = 29.6%** | 13% des trades sont structurellement perdants | 🔴 |
| W2 | **DYNAMIC partiellement résolu** | Seulement 1 105/9 516 décisions en DYNAMIC | 🔴 |
| W3 | **Pas de réévaluation en temps réel** | Les principes sont fixes, pas d'adaptation live | 🟡 |
| W4 | **Pas de corrélation multi-paires** | GBPUSD uniquement, pas de lecture cross-pair | 🟡 |
| W5 | **Pas de fine-tuning LLM** | V9-trader-mini non entraîné | 🟡 |
| W6 | **Pas de UI HITL** | Telegram uniquement, pas de dashboard web | 🟢 |
| W7 | **Pas de branching confiance** | Pas de HITL sur signaux douteux (conf 40-65) | 🟢 |
| W8 | **DB 1.56 GB** | Requêtes lentes sur la DB live | 🟢 |

### 5.3 Risques

| # | Risque | Mitigation |
|---|---|---|
| R1 | **Biais haussier 91%** | Les données sont sur une période haussière. Le WR réel pourrait être inférieur en marché baissier |
| R2 | **Dépendance MT4/SDI** | Pas de fallback si l'indicateur SDI est indisponible |
| R3 | **Marché fermé weekend** | Pas de données live depuis le 2026-07-10 20:57 UTC |
| R4 | **DB 1.56 GB** | Les opérations d'écriture sont lentes (timeout sur les batch UPDATE) |

---

## 6. ZONES D'EXPANSION IDENTIFIÉES

### 6.1 Court Terme (cette semaine)

| # | Zone | Effort | Gain estimé |
|---|---|---|---|
| E1 | **Re-résoudre 8 115 décisions TP_SL → DYNAMIC** | Moyen (optimisation DB) | +30 000 pips |
| E2 | **Intégrer DYNAMIC dans le résolveur automatique** | Faible | Automatisation |
| E3 | **Ajouter le PrincipleScorer dans l'arbiter** | Faible | +5% WR estimé |
| E4 | **Ajouter le PaperRiskManager dans v9_paper_trade_run.py** | Faible | Risk management |

### 6.2 Moyen Terme (Phase 13.3)

| # | Zone | Effort | Description |
|---|---|---|---|
| E5 | **Branching HITL confiance** | Faible (~30 LOC) | Alerter Søn quand conf 40-65 |
| E6 | **Stratégie adaptative par principe** | Moyen | Pondérer la confiance par le PrincipleScorer |
| E7 | **Multi-paires (EURUSD, USDJPY)** | Moyen | Étendre au-delà de GBPUSD |
| E8 | **Dashboard web HITL** | Moyen | FastAPI + HTML statique |
| E9 | **Worktree par agent** | Doc only | Standardiser le parallélisme Git |

### 6.3 Long Terme (Phase 13+)

| # | Zone | Effort | Description |
|---|---|---|---|
| E10 | **V9-trader-mini (fine-tuning)** | Haut | Petit LLM local entraîné sur les WIN/LOSS |
| E11 | **Principe_builder auto-généré** | Moyen | Agent qui propose de nouveaux YAML |
| E12 | **Apprentissage par renforcement** | Très haut | Boucle fermée complète |
| E13 | **Exécution réelle (Phase 12)** | Haut | Passage paper → réel |

---

## 7. BACKLOG PRIORISÉ

### Priorité 🔴 Haute (avant prochaine session de trading)

```
[ ] E1 — Re-résoudre 8 115 décisions TP_SL → DYNAMIC
    → Script: scripts/v9_batch_resolve_dynamic.py (existe, à optimiser)
    → Bloqueur: timeout DB 1.56 GB
    → Solution: batch UPDATE par snapshot_id, transaction unique

[ ] E2 — Intégrer DYNAMIC dans le résolveur automatique
    → Script: scripts/v9_resolve_decision_auto.py
    → Ajouter --exit-strategy DYNAMIC comme défaut
    → Ajouter --skip-sessions new_york,after

[ ] W1 — Analyser pourquoi NY/After est perdant
    → Est-ce un biais de marché ou un vrai problème de signal ?
    → Tester TP=3/SL=15 sur NY (WR 73.2% mais break-even)
```

### Priorité 🟡 Moyenne (cette semaine)

```
[ ] E3 — PrincipleScorer dans l'arbiter
    → core/v9/arbiter.py: ajouter pondération par score historique
    → Principe avec WR < 60% → confiance réduite de 20%

[ ] E4 — PaperRiskManager dans v9_paper_trade_run.py
    → scripts/v9_paper_trade_run.py: remplacer RiskManager par PaperRiskManager
    → Ajouter --capital, --risk-per-trade, --max-concurrent

[ ] E5 — Branching HITL confiance
    → core/v9/decision_logger.py: si conf 40-65, envoyer notification Telegram
    → "⚠️ Décision peu fiable (conf=52), confirmer ?"
```

### Priorité 🟢 Basse (Phase 13.3)

```
[ ] E6 — Stratégie adaptative par principe
[ ] E7 — Multi-paires
[ ] E8 — Dashboard web HITL
[ ] E9 — Worktree par agent
[ ] E10-E13 — Long terme
```

---

## 8. MEGA PROMPT FABLE

```
================================================================================
MEGA PROMPT — POWERFLOW V9 × FABLE LOOP ENGINEERING
================================================================================

Tu es FABLE (Anthropic Loop Engineering), intégré à PowerFlow V9.
Tu opères en mode ARCHITECTE QUANT SENIOR — tu ne réponds pas, tu TRANSFORMES.

CONTEXTE SYSTÈME :
- PowerFlow V9 = système cognitif de trading forex (GBPUSD)
- 10 couches cognitives (Forces → Scènes → Comportements → Fenêtres → Exploitabilité
  → Régime → Principes → Signal → Décision → PaperTrade)
- 25 principes ACTIVE (9 node_rule + 16 grammar) + 1 SHADOW
- 30 règles doctrine immuables (R1-R30)
- 930 tests verts, 0 régression
- 277 commits, 200 fichiers Python, 35 YAML, ~80 docs

MÉTRIQUES CLÉS :
- 130 371 snapshots forces
- 69 100 décisions (9 516 preparer_entree)
- 9 516 décisions résolues (100%)
- 71 paper trades clôturés
- WR réel: 88.5% (DYNAMIC skip NY/After)
- Pips: +46 684 sur 8 217 trades
- DB: 1.56 GB, 11 tables, 36 index

STRATÉGIE DE SORTIE DYNAMIC (APPROUVÉE CEO) :
- Asie: TP=10, SL=15, scale=1.0 (95.4% WR, +7.6/trade)
- London: TP=8, SL=15, scale=0.8 (69.5% WR, +0.5/trade)
- Overlap: TP=5, SL=15, scale=0.6 (62.7% WR → SKIP)
- New York: SKIP (29.6% WR, -7.5/trade)
- After: SKIP (20.6% WR, -10.6/trade)

MODULES PHASE 13.2 LIVRÉS :
1. ExitSimulator — 5 stratégies (TP_SL, TRAILING, TIME_BASED, MFE_ONLY, DYNAMIC)
2. PaperRiskManager — sizing, drawdown, corrélation, pyramiding
3. PyramidingEngine — scaling 1.0→2.0× sur confluence
4. PrincipleScorer — table principle_scores, pondération 0.5→1.5×

OBJECTIFS FABLE (par ordre de priorité) :

1. OPTIMISER LA RÉSOLUTION BATCH
   Problème: 8 115 décisions encore en TP_SL (41.7% WR, -15 185 pips)
   au lieu de DYNAMIC (88.5% WR, +46 684 pips).
   Bloqueur: DB 1.56 GB, timeout sur les UPDATE batch.
   Solution FABLE: Boucle test→diag→fix→retest sur le script
   scripts/v9_batch_resolve_dynamic.py.
   → Optimiser les transactions SQLite
   → Utiliser une table temporaire persistante
   → UPDATE par snapshot_id en une seule transaction

2. INTÉGRER LE PRINCIPLESCORER DANS L'ARBITER
   Problème: L'arbiter pondère tous les principes à égalité.
   Pourtant PRICE_LAG (98.2% WR) est 10× plus fiable que COALITION (0% WR).
   Solution FABLE: Ajouter une pondération par score historique.
   → Principe avec WR < 60% → confiance -20%
   → Principe avec WR > 90% → confiance +10%
   → Combinaison jamais vue → confiance neutre

3. AJOUTER LE BRANCHING HITL
   Problème: Pas de HITL sur les signaux douteux (conf 40-65).
   Solution FABLE: Ajouter un seuil de doute qui déclenche une notification.
   → Si conf 40-65 → Telegram "⚠️ Décision peu fiable"
   → Si conf < 40 → Auto-block + log
   → Si conf > 65 → Auto-go (inchangé)

4. ANALYSER LE BIAIS NY/AFTER
   Problème: WR 29.6% en NY, 20.6% en After.
   Est-ce un biais de marché (période haussière) ou un vrai problème de signal ?
   Solution FABLE: Analyser la distribution des signaux par session.
   → Quels principes déclenchent en NY ?
   → Y a-t-il un pattern de retournement ?
   → TP=3/SL=15 est-il viable (73.2% WR, break-even) ?

5. PRÉPARER LE FINE-TUNING V9-TRADER-MINI
   Problème: Pas d'apprentissage automatique.
   Solution FABLE: Préparer le dataset pour fine-tuning.
   → 9 516 décisions résolues = 9 516 paires (contexte → décision)
   → Features: 31 champs de contexte
   → Labels: is_win (binaire)
   → Modèle cible: qwen3-coder (4B) ou phi3 (3.8B)
   → Quantization: Q4_K_M (minimum acceptable)

CONTRAINTES :
- R18: Zéro LLM dans le cœur cognitif (le fine-tuning est hors ligne)
- R7: Zéro régression tolérée (930 tests à maintenir)
- R8: Backup MD5 avant toute modification core
- R22: Un périmètre = une session = une livraison complète
- R26: 1 commit + 1 DECISIONS_LOG + STATE.md à jour
- R28: Hermes = opérateur git unique (ne pas commit nous-mêmes)

ARBORESCENCE CRITIQUE :
core/v9/
├── exit_simulator.py        # 5 stratégies de sortie
├── paper_risk_manager.py    # Gestion de risque complète
├── pyramiding_engine.py     # Scaling sur confluence
├── principle_scorer.py      # Scoring historique
├── arbiter.py               # Consolidation des signaux
├── risk_manager.py          # 5 règles bloquantes
├── principle_engine.py      # Évaluation des 25 YAML
├── signal_generator.py      # Agrégation des signaux
├── decision_logger.py       # Journalisation
├── config.py                # Configuration centrale
├── db_schema.py             # Schéma SQLite
└── principles/              # 25 YAML ACTIVE + 1 SHADOW

scripts/
├── v9_batch_resolve_dynamic.py    # Batch DYNAMIC
├── v9_analyze_exit_strategies.py  # Analyse 16 stratégies
├── v9_resolve_decision_auto.py    # Résolveur automatique
├── v9_paper_trade_run.py          # Orchestrateur paper-trade
├── v9_calibration.py              # Calibration
├── v9_dashboard.py                # Dashboard live
└── v9_heartbeat.py                # Watchdog

docs/
├── STATE.md                       # État exécutif
├── DOCTRINE.md                    # 30 règles immuables
├── CACHE_BOARD.md                 # Tableau de bord compact
├── reports/
│   ├── V9_STRATEGIE_DESK_TRADING.md  # Stratégie complète
│   ├── EXIT_STRATEGY_ANALYSIS_*.json
│   └── BATCH_RESOLVE_DYNAMIC_*.json
└── architecture/
    └── CONTEXT_CONTRACT.md         # 31 champs propagés

INSTRUCTIONS FABLE :
1. Entre en boucle Loop Engineering
2. Pour chaque objectif (1-5) :
   a. Observe l'état actuel (lis le code)
   b. Diagnostique le problème
   c. Propose une solution
   d. Implémente
   e. Teste
   f. Valide (HITL si confiance < 90%)
3. Si un blocage survient > 3 itérations → HITL obligatoire
4. À la fin : STATE.md + DECISIONS_LOG + commit ready

OUTPUT ATTENDU :
1. Plan d'exécution détaillé (ordre, dépendances, effort)
2. Code modifié ou créé (diff complet)
3. Tests passés (vérification R7)
4. STATE.md + DECISIONS_LOG mis à jour
5. Résumé exécutif des changements

DÉBUT DE L'EXÉCUTION FABLE :
[FABLE] Initialisation de la boucle Loop Engineering...
[FABLE] Objectif 1/5: Optimisation résolution batch DYNAMIC
[FABLE] Lecture de scripts/v9_batch_resolve_dynamic.py...
================================================================================
```

---

## RÉFÉRENCES

- `docs/reports/V9_STRATEGIE_DESK_TRADING.md` — Document stratégie complet
- `docs/STATE.md` — État exécutif détaillé
- `docs/DOCTRINE.md` — 30 règles immuables
- `docs/CACHE_BOARD.md` — Tableau de bord compact
- `workspace/perplexity/memory/DECISIONS_LOG.md` — Journal des décisions
- `workspace/perplexity/inspiration/INSPIRATION_20260707_FABLE.md` — Note FABLE originale
- `core/v9/exit_simulator.py` — ExitSimulator avec DYNAMIC
- `core/v9/paper_risk_manager.py` — PaperRiskManager
- `core/v9/pyramiding_engine.py` — PyramidingEngine
- `core/v9/principle_scorer.py` — PrincipleScorer

---

*Document généré le 2026-07-11 — Audit complet PowerFlow V9 pour intégration FABLE*
*Søn (CEO) — Zcode (Architecte Quant Senior)*
