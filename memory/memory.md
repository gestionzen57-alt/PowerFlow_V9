# memory.md — Mémoire persistante PowerFlow V9

> **Source unique de vérité mémoire pour tous les agents IA** (Hermes, ZCode, Claude CLI).
> Mis à jour à chaque session. Git = source de vérité absolue (R14).

_Mis à jour : 2026-07-24 — Session CEO plein pouvoir (5 causes racines + boucle fermée)_

## Identité du projet

PowerFlow V9 = système de lecture comportementale des forces de marché.
Architecture 4 couches : LECTURE → DÉCISION → OPTIMISATION → EXÉCUTION (simulation).
Branche : `feat/v9-foundation-clean` sur C:/projet/V9.
Pipeline live depuis 2026-07-06. MT4 + EA V9_Sonde_M1.mq4 + capture_server port 31685.

## Conventions immuables

1. `snapshot_id` = `v9-{SYMBOL}-{TF}-{bar_time}-{seq}`
2. `source_type` ∈ {`live`, `replay`} sur 8 tables dérivées
3. `currency` = devise de base pour signal (`GBP` pour GBPUSD)
4. HITL requise avant tout ordre réel (Phase 12 gelée — V9_EXECUTION_ENABLED=0)
5. `decision_id` = `dec_` + uuid5(snapshot_id).hex[:12]
6. Une bougie fermée = un seul snapshot (anti-replay R5)
7. Stale gate rejette données > seuil par TF (R4)

## Architecture cognitive (9 couches)

Forces → Scènes → Comportements → Fenêtres → Exploitabilité → Régime → Principes → Signal → Décision

## Kill switches actifs (24/07)

| Switch | Valeur | Rôle |
|---|---|---|
| V9_EXECUTION_ENABLED | 0 | Gelé Phase 12 (fail-safe fondateur) |
| V9_NO_BAISSIERE | 0 | 2 directions (désactivé 23/07) |
| V9_GBPUSD_LONG_ONLY | 0 | 2 directions (désactivé 23/07) |
| V9_BAYESIAN_CALIBRATOR_ENABLED | 1 | Confiance calibrée remplace déclarée |
| V9_BAYESIAN_PREDICTOR_ENABLED | 1 | Champs predictor_* |
| V9_KELLY_FRACTIONAL_ENABLED | 1 | Sizing bayésien [0.3, 2.0] |
| V9_DRAWDOWN_PROTECTOR_ENABLED | 1 | 5 paliers sizing adaptatif |
| V9_RISK_PARITY_ENABLED | 1 | Allocation risque-budget |
| V9_CYCLE_MEMORY_ENABLED | 1 | Mémoire inter-cycles |
| V9_CROSS_PAIR_METRICS_ENABLED | 1 | Dispersion + force ratio + neutre rate |
| V9_WALK_FORWARD_ENABLED | 1 | Cron auto walk-forward |
| V9_DYNAMIC_RISK_ENABLED | 1 | DRM APPLY permanent (R32) |
| V9_AUTO_CALIBRATOR_ENABLED | 1 | Ajuste seuils tous les 100 trades |
| V9_LEARN_LOOP_ENABLED | 1 | Boucle d'apprentissage |
| V9_CVD_ENABLED | 1 | CVD tick-level MT4 |
| V9_BLACKLIST_SYMBOLS | USDCAD,AUDUSD,USDJPY | Paires non tradées |
| V9_KELLY_CVAR_ENABLED | 0 | CVaR sizing (NO-GO walk-forward) |
| V9_REGIME_GATE_ENABLED | 0 | Gate régime (shadow) |
| V9_HITL_BRANCHING_ENABLED | 0 | Notif Telegram coupée |
| V9_TELEGRAM_SIGNAL_ALERT_ENABLED | 0 | Alerte Telegram signal off |

## Décisions structurelles (validées)

- GitHub = source de vérité absolue (R14)
- Toute migration V8 → V9 passe par audit + classification A/B/C/D
- Reprise de session : CACHE_BOARD.md → STATE.md → DECISIONS_LOG
- 56 principes YAML (48 ACTIVE + 8 SHADOW sur disque, 47 dans PRINCIPLE_ACTIVE_IDS runtime)
- PRINCIPLE_ACTIVE_IDS dans config.py = source runtime v9_status (R25'')
- ExitSimulator DYNAMIC_PROFILES : TP=10/SL=10 par session (fallback)
- DynamicRiskManager : TP/SL adaptatifs par phase de cycle (R32 APPLY)
- Resolver : DRM adaptatif + horizon 8h + filtre blacklist + 2 directions
- Learn loop : edge_threshold=0.55, SL=10, n_enter 94%, WR uplift +1.81pts
- Walk-forward : EDGE RÉEL (OOS 5.979 pips, 4/4 folds positifs)

## Infrastructure

- VPS Windows : tout le runtime (daemon, capture_server, crons, MT4)
- Port daemon : 31685
- MT4 = plateforme de lecture de l'indicateur SDI (pas MT5)
- EA V9_Sonde_M1.mq4 : 6 paires M1 (CVD tick-level déployé et compilé)
- 34 crons Windows Ready
- DB : v9_forces.db 5.2 GB (purge > 7 jours, VACUUM periodique)

## Comportements de marché confirmés

- GBPUSD = paire avec edge (WR 72%, +56K pips replay)
- Session ASIE = meilleure (WR 81%, +8.24 pips/trade)
- Sessions New York + After = perdantes (blacklistées par resolver)
- EURUSD, USDJPY, AUDUSD = paires sans edge (blacklistées)

## Références pivots

| Document | Rôle | Chemin |
|---|---|---|
| SOUL.md | Âme du système | SOUL.md |
| STATE.md | État vivant | docs/STATE.md |
| DOCTRINE.md | 30 règles | docs/DOCTRINE.md |
| CACHE_BOARD.md | Tableau reprise | docs/CACHE_BOARD.md |
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