# ROADMAP — PowerFlow V9

## Statut
Pour l'état détaillé et à jour, voir [docs/STATE.md](STATE.md) (source de vérité vivante,
auto-régénérée par `scripts/v9_sync_state.py`). Ce document couvre les phases
**livrées** et **restantes** + leur séquencement prévisionnel.

**Dernière mise à jour : 2026-07-15** (session ZCode — consolidation trade engine,
réactivation zone_diagnostics, optimisation stratégique 23 ACTIVE, overlap blacklist).

## Phases terminées

| Phase | Construction | Statut |
|---|---|---|
| 1 | Formats de données (6 fichiers JSON) | ✅ Terminée |
| 2 | Forces (EA MT4 + capture TCP + DB + stale gate) | ✅ Terminée |
| 3 | Scènes (`scene_builder.py`, coalitions/antagonismes) | ✅ Terminée |
| 4 | Comportements (`behavior_analyzer.py`, 12 qualifications) | ✅ Terminée |
| 5 | Fenêtres (`window_gate.py`, 6 statuts) | ✅ Terminée |
| 6 | Exploitabilité (`exploitability_evaluator.py`, 5 niveaux) | ✅ Terminée |
| 7 | Déploiement live (EA `ServerPort`, `market_calendar.py`, scripts de déploiement) | ✅ Terminée |
| 8 | Monitoring (dashboard, calibration, replay — tous lecture seule) | ✅ Terminée |
| + | Orchestrateur live (chaîne automatique événementielle) | ✅ Terminée |
| 9 | Décision et Principes (Régime → Principes → Signal → Décision) | ✅ Canonisée 2026-07-05 |
| 9.7 | Paper-Trade Simulator (Arbiter + RiskManager + PaperTradeLogger) | ✅ Livrée 2026-07-07 |
| 9.8 | VPS-READY (heartbeat + crons + rollback DNS) | ✅ Livrée 2026-07-07 |
| 9.9 | Consolidation Complète (dette = 0) | ✅ Livrée 2026-07-07 |
| 9.10 | WIN/LOSS resolver + Règle 29 (lecture multi-TF) + Règle 30 (apprentissage progressif) | ✅ Livrée 2026-07-08 |
| 11 | MCP Architecture (7 serveurs MCP) | ✅ Livrée 2026-07-10 (register `.mcp.json` 2026-07-14) |
| 13 CEO | Recalibrage (CONFIANCE_MIN 80→70, arbiter neutre, SIGNAL_OPEN SHADOW) | ✅ Livrée 2026-07-10 |
| 13.2 | Simulation Pro (ExitSimulator + PaperRiskManager + PyramidingEngine + PrincipleScorer) | ✅ Livrée 2026-07-11 |
| O1→O5 | Re-résolution DYNAMIC + PrincipleScorer + HITL branching + biais NY/After + dataset trader-mini | ✅ Livrée 2026-07-12 |
| Q1→Q5 | trader-mini baseline + auto-calibrateur + dashboard HITL + multi-paires + order_executor | ✅ Livrée 2026-07-12/13 |
| Autopilot | P1 DYNAMIC signal + P3 adaptive thresholds + P5 long-term memory + P6 vol_regime | ✅ Livrée 2026-07-13 |
| — | ORDER-BRIDGE (order_queue_watcher) + P2 shadow mode | ✅ Livré 2026-07-14 |
| — | TG-FIX + P3-WIRE (adaptive thresholds câblé, OFF par défaut) | ✅ Livré 2026-07-13 |
| — | P3-CONSUME-EXTEND (26 YAML `_ADAPTIVE`, Hermes) | ✅ Livré 2026-07-14 |
| — | Audit ZCode : gardiens automatisés + sync auto état + corrections factuelles | ✅ Livré 2026-07-14 |
| — | **Session ZCode 2026-07-15 : Infrastructure collaborative IA** | ✅ Livré |
| | • 7 MCP serveurs testés + 30 skills connectés (junction `.zcode/skills/`) | |
| | • 6 subagent profiles ZCode + 6 Hermes (rule-guard, capture-ops, calib-analyst, data-explorer, learn-analyst, session-writer) | |
| | • Bus agent bridge (60 abonnements, pub/sub inter-IA) | |
| | • Hooks SessionStart auto-sync (ZCode + Hermes) | |
| | • AGENTS.md + CLAUDE.md mémoire partagée | |
| — | **Session ZCode 2026-07-15 : Consolidation trade engine** | ✅ Livré |
| | • `core/v9/trade_engine.py` — module unifié (arbiter + PaperRiskManager + PaperTradeLogger + PyramidingEngine + ExitSimulator) | |
| | • Hook orchestrator post-décision → paper-trade automatique | |
| | • SL/TP réels (lus depuis signals, plus de ±10 hardcodés) | |
| | • Superviseur `--paper-trade` utilise TradeEngine directement | |
| | • 6 scripts obsolètes archivés | |
| — | **Session ZCode 2026-07-15 : Optimisation stratégique** | ✅ Livré |
| | • zone_diagnostics réactivé (14 SHADOW débloquées) | |
| | • 5 destroyers → DORMANT (COALITION_NODE, NODE_BIRTH_FAST, RAW_NODE_BIRTH, ELASTIC_BREATH, GRAMMAR_CONTEXTE) | |
| | • GRAMMAR_CONTEXTE_ADAPTIVE promu SHADOW→ACTIVE (WR 79.5% vs 44.7%) | |
| | • Overlap blacklisté (expectancy -2.26 pips/trade) | |
| | • PRINCIPLE_ACTIVE_IDS : 27 → 23 ACTIVE | |
| | • 10 tests corrigés pour nouvelle config | |
| — | **P4 — TradeStrategyEngine avancé (Hermes 2026-07-16)** | ✅ Livré |
| | • Kelly fractionnel (K=0.25, W&R-driven, fallback n<20) — compense R/R asymétrique | |
| | • Vol filter sizing (HIGH=×0.7, EXTREME=×0.0) — bloque EXTREME, réduit HIGH | |
| | • Trailing CASSURE-aware (MFE ≥ 50% TP → distance SL×0.5) — préserve les gains | |
| | • 16 tests dédiés (`tests/test_trade_strategy_engine.py`) | |
| | • Bornes dures sizing [0.3, 2.0] (R30) | |

## Phases restantes

| Phase | Objectif | Priorité | Statut |
|---|---|---|---|
| 10 | Fédération d'agents (multi-analyse) | P1 | ⏸️ Gelée par règle 19 (stabilisation live) |
| 11b | Layer MT5 (microstructure ticks) | P2 | ⏸️ Gelée par décision Søn |
| 12 | Exécution d'ordres réelle | P2 | ⏸️ Interdit fondateur — `order_executor.py` créé (double-verrou), exécution réelle OFF |
| 13 complète | ✅ **TERMINÉE** — Boucle fermée auto-calibrateur + auto-optimizer + auto-promotion SHADOW→ACTIVE | ✅ | **Livrée 2026-07-16** (mandat CEO boucle fermée) |

---

## Prochaines actions (post-session 2026-07-16)

### Priorité 0 — Observation live post-boucle-fermée

| # | Action | Détail | Dépendance |
|---|--------|--------|------------|
| 0a | **Laisser le pipeline tourner 24-48h** | 48 principes ACTIVE, auto-calibrateur writable, auto-optimizer actif. Le système s'auto-optimise. | Pipeline actif ✅ |
| 0b | **Vérifier les premières auto-promotions** | L'auto-calibrateur va promouvoir les SHADOW et ajuster les TP/SL. Vérifier que les décisions sont saines. | 100 trades |
| 0c | **Surveiller l'edge decay PRICE_LAG** | -18.9% sur 50 trades. L'auto-optimizer va ajuster ses TP/SL. Vérifier l'impact. | Auto-optimizer actif |

### Priorité 1 — Robustesse système

| # | Action | Détail | Statut |
|---|--------|--------|--------|
| 1 | **Installer les 11 crons Windows** | Tous installés et Ready (V9_ArbiterRecal, V9_AutoCalibrator, V9_AutoRestart, V9_CalibrationLoop, V9_HeartbeatAlert, V9_HeartbeatCheck, V9_LearningLoop, V9_MetaAgentScan, V9_ResolveLoop, V9_TelegramAgent, V9_TelegramWatch) | ✅ **Fait 2026-07-16** |
| 2 | **Tester Telegram** | Token actif (Hiphopvps_bot). Message de test envoyé avec succès. | ✅ **Fait 2026-07-16** |
| 3 | **Rotation token Telegram** | Ancien token `AAEP7_...` dans 5 commits de l'historique git (non purgé). Token actuel déjà un token de remplacement. | ⏸️ Purge git filter-repo si nécessaire |
| 4 | **VPS déploiement** | Cloner le dépôt, configurer secrets, compiler EA, lancer installateurs cron. | ⏳ Søn décide quand |

### Priorité 2 — Évolution fonctionnelle

| # | Action | Détail |
|---|--------|--------|
| 4 | **Multi-paires live** | Brief Q4 livré (EURUSD/USDJPY/GBPJPY support code). Activation = attacher l'EA à des graphiques supplémentaires (action opérateur MT4). |
| 5 | **Dashboard web HITL en production** | Brief Q3 livré (HTTPS, auth, lecture seule). Déploiement = créer `config/dashboard.json` + certificats. |
| 6 | **TradeStrategyEngine avancé** | Kelly sizing, filtre volatilité, stratégie de sortie adaptative (trailing sur CASSURE). Complément à l'auto-optimizer. |

---

## Leviers transverses

| Levier | Description | Statut |
|---|---|---|
| Calibration live | `v9_calibration.py --analyze`/`--principes` sur session réelle | 🔄 En attente marché ouvert |
| Multi-paires | EURUSD/USDJPY/GBPJPY — code livré (Brief Q4) | ✅ Code prêt, activation = action MT4 |
| `zone_diagnostics` | Alimentée par ZoneDetector — 14 principes SHADOW débloqués | ✅ **Réactivé 2026-07-15** |
| Gardiens automatisés | `v9_guards.py` (5 gardiens) + `v9_sync_state.py` (auto-régénération docs) | ✅ Actifs (audit ZCode) |
| CI GitHub Actions | pytest + gardiens V9 sur chaque push | ✅ Actif (audit ZCode) |
| Infrastructure collaborative IA | Bus agent bridge (60 subs) + hooks SessionStart + mémoire partagée | ✅ **Livré 2026-07-15** |
| Trade engine unifié | `trade_engine.py` — un seul module pour arbiter + risk + paper_trade + exit_sim | ✅ **Livré 2026-07-15** |
| Optimisation stratégique | 23 ACTIVE (5 destroyers DORMANT, 1 promu), overlap blacklisté | ✅ **Livré 2026-07-15** |

---

## Chantiers futurs distincts — ne pas mélanger maintenant

1. **Phase 10 — Fédération d'agents** : un agent par couche cognitive + arbitre + risk manager. Ne démarre qu'après calibration live de la Phase 9 (règle 19).
2. **Architecture globale agents / routing / mémoire avancée** : orchestration multi-agents généralisée. Distinct de la migration métier. Ne sera scopé qu'une fois la Phase 10 amorcée.
3. **Skills/agents auto-générés** : dépend d'un socle stable (Phases 9-10 canonisées et calibrées). Aucune génération automatique avant (règle 19).

---

## Timeline prévisionnelle (indicative, non contractuelle)

| Période | Contenu | Statut |
|---|---|---|
| Juillet 2026, S1-S2 | Phases 1-9 + orchestrateur live | ✅ Fait |
| Juillet 2026, S3 | Phase 9.7/9.8/9.9 + R28/R29/R30 | ✅ Fait |
| Juillet 2026, S4 | Phase 9.10 + Phase 13 CEO + 13.2 + MCP | ✅ Fait |
| Juillet 2026, S4 (14/07) | Q1→Q5 + Autopilot P1/P3/P5/P6 + ORDER-BRIDGE + P2 + P3-CONSUME-EXTEND | ✅ Fait |
| Juillet 2026, S4 (14/07) | Audit ZCode : gardiens + sync auto + corrections | ✅ Fait |
| **Juillet 2026, S4 (15/07)** | **Session ZCode : infra collaborative IA + trade engine consolidé + optimisation stratégique** | ✅ **Fait** |
| Juillet 2026, S4 (15-19/07) | Collecte données post-optimisation (24-48h) + replay benchmark SHADOW | 🔄 En cours |
| Août 2026, S1 | Calibration live + WIN/LOSS ≥ 50 + activation P3-WIRE + VPS | 🔄 Planifié |
| Août 2026, S2 | TradeStrategyEngine (Q1-Q5 : TP/SL dynamique, Kelly sizing, filtre volatilité) | ⏳ Conditionnel |
| Septembre 2026 | Phase 13 complète (auto-calibration continue) + Phase 10 (fédération) | ⏳ Conditionnel |
| Octobre 2026 | Phase 11b (MT5) + Phase 12 (exécution, si Søn active) | ⏳ Conditionnel |

---

## Risques connus

- **Dépendance SDI propriétaire** (MT4 uniquement, pas de fallback).
- **Replay vs live** : stale gate calé pour le live, rejette du replay utile — mode replay distinct à documenter.
- **Latence** : 189,58 ms/snapshot (9 couches, Phase 9) — sous la cible 200 ms, à confirmer sur live réels.
- **Calibration** : seuils de régime `PROVISIONAL` portés V8, pas encore calibrés sur données live V9.
- **Token Telegram** : `AAEP7_...` a fuité dans l'historique git (redacted mais pas purgé via `filter-repo`). Rotation recommandée.
- **Asymétrie R/R structurelle** : le système perd -15 pips (SL) et gagne +5/+8 (TP). L'expectancy est négative sur overlap/NY/after. Les optimisations de cette session (blacklist overlap, 5 destroyers DORMANT) réduisent le risque mais le R/R reste à améliorer via TP/SL dynamique.
- **Mono-principe** : 93% des signaux viennent de PRICE_LAG_AT_NODE_BIRTH. Si ce principe régresse, tout le système s'effondre. La diversification via les SHADOW est critique.
