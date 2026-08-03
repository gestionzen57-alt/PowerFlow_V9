# memory.md — Mémoire persistante PowerFlow V9

> **Source unique de vérité mémoire pour tous les agents IA** (Hermes, ZCode, Claude CLI).
> Mis à jour à chaque session. Git = source de vérité absolue (R14).

_Mis à jour : 2026-08-03 — Resync post Phase 12 FTMO (v9_sync_state) + ajout kill switches réels env_

## Identité du projet

PowerFlow V9 = système quantique institutionnel de lecture comportementale des forces de marché.
Architecture 4 couches : LECTURE → DÉCISION → OPTIMISATION → EXÉCUTION (Phase 12 activée 02/08).
Branche : `feat/v9-foundation-clean` sur C:/projet/V9.
Pipeline live depuis 2026-07-06. MT4 + EA V9_Sonde_M1.mq4 + capture_server port 31685.
Mission CEO no-stop 01/08/2026 : optimisation max, plein pouvoir, pas de validation requise.

## Conventions immuables

1. `snapshot_id` = `v9-{SYMBOL}-{TF}-{bar_time}-{seq}`
2. `source_type` ∈ {`live`, `replay`, `shadow`} sur 8 tables dérivées
3. `currency` = devise de base pour signal (`GBP` pour GBPUSD)
4. HITL requise avant tout ordre réel (Phase 12 ACTIVE — V9_EXECUTION_ENABLED=1)
5. `decision_id` = `dec_` + uuid5(snapshot_id).hex[:12]
6. Une bougie fermée = un seul snapshot (anti-replay R5)
7. Stale gate rejette données > seuil par TF (R4)

## Architecture cognitive (9 couches)

Forces → Scènes → Comportements → Fenêtres → Exploitabilité → Régime → Principes → Signal → Décision

## Kill switches réels (env live 2026-08-03)

### ON (actifs)
| Switch | Valeur | Rôle |
|---|---|---|
| V9_EXECUTION_ENABLED | 1 | Phase 12 FTMO ACTIVE (motion CEO 02/08) |
| V9_EXECUTION_SIMULATION | 1 | Mode simulation conservatrice |
| V9_SHADOW_MODE_ENABLED | 1 | Shadow evaluator parallèle |
| V9_DYNAMIC_RISK_ENABLED | 1 | DRM APPLY permanent (R32) |
| V9_DYNAMIC_TP_SL_ENABLED | 1 | TP/SL dynamiques par phase |
| V9_LEARNING_OFFSET_ENABLED | 1 | Boucle d'apprentissage |
| V9_NO_BAISSIERE | 1 | Haussier only (bug latent corrigé) |
| V9_LOOP_BREAKER_ENABLED | 1 | Anti boucle de décisions |
| V9_LIVE_WATCHDOG_ENABLED | 1 | Surveillance live 5min |
| V9_BAYESIAN_CALIBRATOR_ENABLED | 1 | Confiance calibrée remplace déclarée |
| V9_BAYESIAN_PREDICTOR_ENABLED | 1 | Champs predictor_* |
| V9_KELLY_FRACTIONAL_ENABLED | 1 | Sizing bayésien [0.3, 2.0] |
| V9_DRAWDOWN_PROTECTOR_ENABLED | 1 | 5 paliers sizing adaptatif |
| V9_RISK_PARITY_ENABLED | 1 | Allocation risque-budget |
| V9_CYCLE_MEMORY_ENABLED | 1 | Mémoire inter-cycles |
| V9_CROSS_PAIR_METRICS_ENABLED | 1 | Dispersion + force ratio |
| V9_META_STRATEGY_OPTIMIZER_ENABLED | 1 | Optimizer méta-stratégie |
| V9_META_STRATEGY_SHADOW_ENABLED | 1 | Mode shadow méta-stratégie |
| V9_META_LEARNING_ENABLED | 1 | Méta-apprentissage |
| V9_PREDICTIVE_ENGINE_ENABLED | 1 | Moteur prédictif |
| V9_LEARN_LOOP_ENABLED | 1 | Boucle d'apprentissage |
| V9_CVD_ENABLED | 1 | CVD tick-level MT4 |
| V9_WALK_FORWARD_ENABLED | 1 | Cron auto walk-forward |
| V9_POSITION_MANAGER_ENABLED | 1 | Gestion positions (break-even, partial, time-exit) |
| V9_MARKET_REGIME_GLOBAL_ENABLED | 1 | Risk-on/off detector |
| V9_UNIFIED_SIZING_ENABLED | 1 | Sizing unifié |
| V9_EDGE_DECAY_MONITOR_ENABLED | 1 | Surveillance edge decay |
| V9_ANTI_SERIE_PERDANTE_ENABLED | 1 | Anti série perdante |
| V9_KILL_DD_WR_ENABLED | 1 | Kill switch DD/WR |
| V9_BLACKLIST_SYMBOLS | USDCAD,AUDUSD,USDJPY,EURUSD,USDCHF | Paires non tradées |
| V9_MIN_HOLD_BARS | 60 | Hold minimum 60 barres |
| V9_MAX_OPEN_TRADES_PER_SYMBOL | 3 | Max 3 trades ouverts par symbole |
| V9_LOOP_BREAKER_WINDOW_MINUTES | 15 | Fenêtre anti-boucle |
| V9_WATCHDOG_DD_24H_PIPS | -200 | Seuil DD 24h watchdog |
| V9_WATCHDOG_WR_WINDOW | 50 | Fenêtre WR watchdog |
| V9_WATCHDOG_WR_WARN | 0.80 | Seuil warning |
| V9_WATCHDOG_WR_CRIT | 0.60 | Seuil critique |
| V9_KILL_DD_PIPS | -100 | Seuil kill DD |
| V9_KILL_WR_FLOOR | 0.40 | Plancher WR kill |
| **L7** mega_edge_l7_grammar_pur_blacklist | 1 | ON (Phase 117, gain +32.6p) |
| **L8** mega_edge_l8_principle_count_blacklist | 1 | ON (Phase 121, gain +725.9p) |

### OFF (défaut, R25' strict)
- V9_AUTO_CALIBRATOR_ENABLED=0
- V9_ADAPTIVE_THRESHOLDS_WIRED_ENABLED=0
- V9_TRADER_MINI_ENABLED=0
- V9_BEAR_PERCEPTION_ENABLED=0
- V9_CONSTITUTIVE_CURRENCY_FILTER=0
- V9_KELLY_CVAR_ENABLED=0 (NO-GO walk-forward)
- V9_REGIME_GATE_ENABLED=0
- V9_HITL_BRANCHING_ENABLED=0
- V9_TELEGRAM_SIGNAL_ALERT_ENABLED=0
- V9_GBPUSD_LONG_ONLY=0
- V9_PAPER_TRADE_HALT=0

## Décisions structurelles (validées)

- GitHub = source de vérité absolue (R14)
- Toute migration V8 → V9 passe par audit + classification A/B/C/D
- Reprise de session : CACHE_BOARD.md → STATE.md → DECISIONS_LOG
- 56 principes YAML (39 ACTIVE + 17 SHADOW sur disque)
- PRINCIPLE_ACTIVE_IDS dans config.py = source runtime v9_status (R25'')
- ExitSimulator DYNAMIC_PROFILES : TP=10/SL=10 par session (fallback)
- DynamicRiskManager : TP/SL adaptatifs par phase de cycle (R32 APPLY)
- Resolver : DRM adaptatif + horizon 8h + filtre blacklist + 2 directions
- Learn loop : edge_threshold=0.55, SL=10, n_enter 94%, WR uplift +1.81pts
- Walk-forward : EDGE RÉEL (OOS 5.979 pips, 4/4 folds positifs)
- L8 (n_principes>=5) : verdict PROMOTE 5/5, gain +725.9 pips mesuré
- L7 (GRAMMAR/ELASTIC pur no-stars) : QUASI_PROMOTE stable, gain +32.6 pips

## Infrastructure

- VPS Windows : tout le runtime (daemon, capture_server, crons, MT4)
- Port daemon : 31685
- MT4 = plateforme de lecture de l'indicateur SDI (pas MT5)
- EA V9_Sonde_M1.mq4 : 6 paires M1 (CVD tick-level déployé et compilé)
- **42 crons Windows Ready** (snapshot 2026-08-03)
- DB : v9_forces.db 5.1 GB (27 tables, 64 index, 104k décisions)
- Tests : 4100 collectés, 81/81 verts sur périmètre L7+L8+trade_engine

## Comportements de marché confirmés

- GBPUSD = paire avec edge (WR 72%, +56K pips replay)
- Session ASIE = meilleure (WR 81%, +8.24 pips/trade)
- Sessions New York + After = perdantes (blacklistées par resolver)
- EURUSD, USDJPY, AUDUSD = paires sans edge (blacklistées)
- Edge authentique 14h-19h UTC (Londres/NY overlap)
- Drain systématique 0h-13h UTC (Asie creuse + début Londres faible)

## Références pivots

| Document | Rôle | Chemin |
|---|---|---|
| SOUL.md | Âme du système | SOUL.md |
| STATE.md | État vivant | docs/STATE.md |
| DOCTRINE.md | 30 règles | docs/DOCTRINE.md |
| CACHE_BOARD.md | Tableau reprise | docs/CACHE_BOARD.md |
| ACTIVE_TASKS | TODO CEO | workspace/perplexity/ACTIVE_TASKS.md |
| DECISIONS_LOG | Décisions structurantes | workspace/perplexity/memory/DECISIONS_LOG.md |
| MEMORY_CANON | Faits gravés | workspace/perplexity/MEMORY_CANON.md |
| CONTEXT_CONTRACT | Propagation inter-couches | docs/architecture/CONTEXT_CONTRACT.md |
| ROADMAP | Phases 9-13 | docs/ROADMAP.md |
| MEMORY_POLICY | Politique mémoire | docs/doctrine/MEMORY_POLICY_V9.md |

## Procédure de session (tous agents)

1. `git pull` + tests verts → base saine
2. Marché ouvert ? → `v9_calibration --analyze` OBLIGATOIRE
3. Périmètre explicité
4. Implémentation
5. Tests verts (zéro régression)
6. CONTEXT_CONTRACT.md si nouveau champ
7. Principes YAML consommateurs (R23)
8. Commits atomiques
9. DECISIONS_LOG entry
10. STATE.md à jour
11. `git push`
