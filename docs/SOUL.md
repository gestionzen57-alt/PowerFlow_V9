# SOUL — PowerFlow V10
**Version :** 4.0 — CEO MAX C22  
**Mis à jour :** 2026-08-11 00:39 CEST  
**Branche :** `feat/v10-c20-healthy`  
**Tests :** 1401 ✅ | **DeploymentValidator :** 83.33/100 | **WR M15 :** 59.35%

> Ce fichier est la **vérité unique** du système.  
> Il prime sur tout autre document en cas de conflit.

---

## 0. Identité

PowerFlow V10 est un système algorithmique de trading Forex **paper-first**.  
Il ne passe aucun ordre réel tant que les conditions GO LIVE CEO ne sont pas toutes vertes.  
Il apprend, se recalibre, et dit NON à lui-même quand l'edge n'est pas confirmé.  
C'est sa force, pas sa faiblesse.

**Philosophie CEO :** zéro dette cachée · zéro ordre réel · zéro module orphelin · vérité avant performance.

---

## 1. Chronologie réelle (jalons C22)

| Date | Jalon | Tests |
|---|---|---|
| 2025-10 | Lancement V9 — pipeline 6 couches | — |
| 2026-04 | Lancement V10 — Cognitive Continuum | — |
| 2026-08-07 | Sprints 14-15 — Sigma Oracle + Wyckoff + Behavior gate | 1270 |
| 2026-08-08 | S25-OMEGA — MetaOptimizer + ErrorLearner UCB1 + cron nocturne | 1310 |
| 2026-08-09 | C11→C20 — ShadowTrader + LiveReadiness + BacktestEngine + MasterOrchestrator | 1310 |
| 2026-08-10 | C21 — ZCode Z7-Z11 + Signal 7 PRÉ-VAGUE + Grammar canonical + Health 6 couches | 1361 |
| 2026-08-10 | Hermes PR #7 — wave_predictor + pre-wave live pipeline + RL exports | 1380 |
| 2026-08-10 | CEO-OPT — Kelly adaptatif + Circuit-breaker streak + QUANT Edge Scorer | 1380 |
| 2026-08-11 | Hermes PR #8 — H-LIVE-REPORT + H-REPLAY-C21 | **1401** |

---

## 2. Pipeline — 7 couches (état C22)

```
┌─────────────────────────────────────────────────────────────────────┐
│  COUCHE 0 : CAPTURE                                                 │
│  MT4 bridge port 31685 → forces_snapshots → v9_forces.db (18GB)     │
│  IBKR bridge port 7497 → LiveConnector C19 [⚠️ À CONNECTER]        │
├─────────────────────────────────────────────────────────────────────┤
│  COUCHE 1 : RÉGIMES                                                 │
│  HMM 4 états · GARCH vol · StaleGuard · DataGapValidator            │
├─────────────────────────────────────────────────────────────────────┤
│  COUCHE 2 : FILTRES COMPOSITES                                      │
│  ICT OTE · SMC · Session · Wyckoff · LiquidityMap · BehaviorContext │
│  FatboyGate (sigma/harmonie/safe_haven) · SigmaOracle               │
├─────────────────────────────────────────────────────────────────────┤
│  COUCHE 3 : SCORING HUB                                             │
│  21 modules → score Hub ∈ [0,1] · Σ poids = 1.00                   │
│  NEW C22 : QUANT Edge Scorer (Z-force/phase/régime/level)           │
├─────────────────────────────────────────────────────────────────────┤
│  COUCHE 4 : DÉCISION                                                │
│  decide_entry() : session+OTE+SMC+grammar+fractal+VSA+pre_wave      │
│  Signal 7 PRÉ-VAGUE : COMPRESSION×1.15 / DIVERGENCE watch_only     │
│  CEO Kelly adaptatif + Circuit-breaker streak (3SL→2h / 5SL→4h)    │
├─────────────────────────────────────────────────────────────────────┤
│  COUCHE 5 : VALIDATION                                              │
│  DeploymentValidator C20 · LiveReadiness C11 · WalkForward C18      │
│  LiveHealthCheck 6 couches · AutoRestarter · SystemHealthChecker    │
├─────────────────────────────────────────────────────────────────────┤
│  COUCHE 6 : EXÉCUTION (PAPER ONLY — R10)                            │
│  ShadowTrader · paper_only=True hard-codé · 0 ordre réel            │
│  Promotion LIVE uniquement si GO LIVE CEO validé                    │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 3. Métriques réelles C22 (honnêtes)

| Métrique | Valeur | Contexte | Statut |
|---|---|---|---|
| Tests V10 | **1401 / 1401** | feat/v10-c20-healthy | ✅ |
| DeploymentValidator | **83.33 / 100** | 10/12 critères PASS | ✅ |
| WR M15 focused | **59.35%** | EURUSD+USDCAD+USDCHF LONDON 155 trades | ✅ |
| PF M15 focused | **1.925** | Réel ReplayEngine C10 | ✅ |
| WFA | **MARGINAL** | WR moyen 51.64% ± 7.61%, 2/5 fenêtres | ⚠️ |
| Health score live | **DEGRADED 33/100** | IBKR absent + 9 trous DB | 🔴 |
| broker_connected | **False** | IBKR port 7497 non connecté | 🔴 |
| feed_active | **False** | LiveConnector C19 non lancé | 🔴 |
| ruff erreurs nouvelles | **0** | Sur tous fichiers modifiés C22 | ✅ |

---

## 4. Formule décision CEO (C22)

```
EDGE_SCORE = 0.40×sigmoid(Z_force) + 0.25×phase_w + 0.20×regime_w + 0.15×level_w

KELLY    = (WR - (1-WR)/RR) × 0.25 × ATR_scale  →  clamp [0.5%, 4%]

GO si :
  EDGE_SCORE ≥ 0.55
  + Circuit-breaker CLEAR (streak_SL < 3)
  + Kelly_fraction ≥ 0.005
  + WR rolling 20 ≥ 48%
  + broker_connected = True        ← BLOQUEUR ACTUEL
  + feed_active = True             ← BLOQUEUR ACTUEL
```

---

## 5. GO LIVE — 2 actions humaines restantes

```
ACTION 1 — Søn (30 min)
  1. Ouvrir IB Gateway → se connecter → port 7497
  2. python -c "import socket; s=socket.socket(); print('OK' if s.connect_ex(('127.0.0.1',7497))==0 else 'KO')"
  3. python scripts/run_live_engine.py --include-a2
  4. Attendre 5 min → vérifier feed actif (age_s < 300)

ACTION 2 — Validation CEO (10 min)
  python scripts/run_live_health_check.py    → cible ≥ 90 HEALTHY
  python scripts/run_deployment_validator.py → cible 100/100
  python scripts/run_ceo_dashboard.py --phase COMPRESSION \
         --regime TRENDING_UP --signal-level A1 --force-delta 20
  → GO 🟢 confirmé → PAPER TRADING ACTIVÉ
```

---

## 6. Architecture agents

| Agent | Rôle | Périmètre | Force |
|---|---|---|---|
| **Søn (CEO)** | Décision finale + connexion broker | IBKR, kill-switches, GO LIVE | Humain dans la boucle |
| **ZCode** | Développement core V10 | `core/v10/`, tests, ruff | Vitesse + précision |
| **Hermes** | Pipeline live + sessions nuit | `scripts/`, crons, rebases | Endurance + rigueur |
| **Perplexity** | Architecture + docs + merge | SOUL.md, PR merge, CEO prompt | Vision système |

---

## 7. Règles R — non négociables

| Règle | Libellé | Sanction si violée |
|---|---|---|
| R2 | Zéro suppression — ajout uniquement | Revert immédiat |
| R6 | Fail-open sur chaque import critique | Bug silencieux → interdit |
| R9 | Tout résultat → rapport JSON horodaté | Résultat non traçable = invalide |
| R10 | ZÉRO ordre réel jusqu'à GO LIVE CEO | Arrêt système complet |
| R25' | pytest + ruff AVANT chaque push | Push refusé |

---

## 8. Anti-patterns — ce qui a failli tuer le système

- ❌ **Cycles C10-C20 pushés sans pytest** → 62 erreurs import en cascade (corrigé 10/08)
- ❌ **Deux agents sur le même fichier** → conflit `v10_fatman_wave_predictor.py` (résolu PR #7)
- ❌ **WR 90% shadow** ≠ edge réel → proxy symétrique, pas un backtest (WR réel = 43.9% all-pairs)
- ❌ **Hermes sans `git branch --show-current`** → commits sur fantôme local
- ❌ **SOUL.md périmé** → philosophie système désynchronisée (corrigé V4 ce push)
- ❌ Modifier `core/v10/` sans test pytest associé
- ❌ Bypasser le bouclier R10 en production
- ❌ Créer un module sans l'enregistrer dans `INDEX_MODULES.md`

---

## 9. Prompt de démarrage agent (universel)

```
Tu travailles sur PowerFlow V10 — branche feat/v10-c20-healthy.

AVANT TOUT :
  git fetch origin
  git branch --show-current   → confirmer la branche
  cat docs/SOUL.md             → lire l'état réel du système
  pytest tests/test_v10_*.py -q --tb=no → base actuelle

RÈGLES ABSOLUES : R2 (additif) · R6 (fail-open) · R9 (JSON) · R10 (0 ordre) · R25' (pytest+ruff avant push)
MÉTRIQUES CIBLES : tests ≥ 1401 · WR M15 ≥ 59% · DeploymentValidator ≥ 83/100
BLOQUEURS GO LIVE : broker_connected + feed_active (IBKR Søn)

Ta mission :
[DÉCRIRE ICI LA TÂCHE SPÉCIFIQUE]

Fin de session → envoyer à Perplexity CEO :
  SHA final · tests passés · ruff propre · PR prête ou mergée
```

---

## 10. Dashboard GO LIVE — état temps réel

```
╔══════════════════════════════════════════════════════╗
║         POWERFLOW V10 — GO LIVE STATUS C22           ║
╠══════════════════════════════════════════════════════╣
║  Tests V10          : 1401 ✅                        ║
║  DeploymentValidator: 83/100 ✅                      ║
║  WR M15 focused     : 59.35% ✅                      ║
║  PF M15             : 1.925 ✅                       ║
║  Kelly adaptatif    : ✅ (CEO-OPT1)                  ║
║  Circuit-breaker    : ✅ (CEO-OPT2)                  ║
║  QUANT Edge Score   : ✅ (CEO-OPT3)                  ║
║  WFA robuste        : ⚠️ MARGINAL                    ║
║  IBKR broker        : 🔴 À CONNECTER (Søn)          ║
║  Feed actif         : 🔴 À LANCER (run_live_engine)  ║
╠══════════════════════════════════════════════════════╣
║  DÉCISION CEO       : ⏳ EN ATTENTE IBKR             ║
╚══════════════════════════════════════════════════════╝
```
