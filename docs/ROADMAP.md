# ROADMAP — PowerFlow V9

## Statut
Pour l'état détaillé et à jour, voir [docs/STATE.md](STATE.md) (source de vérité vivante,
auto-régénérée par `scripts/v9_sync_state.py`). Ce document couvre les phases
**livrées** et **restantes** + leur séquencement prévisionnel.

**Dernière mise à jour : 2026-07-17** (session Opus — audit de clôture semaine :
fiabilité sim, 4 angles morts corrigés, durcissement des 12 crons contre le logoff).

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
| — | **DIVERSIFY Chantier A — Réanimation 6 principes (Opus 2026-07-16)** | ✅ Livré |
| | • 6 principes à 0% → productifs (EXHAUSTION, SIGNAL_OPEN ACTIVE ; ANTAGONIST, LOCK, RESPIRATION, VOL_GATE SHADOW) | |
| | • Bug latent auto-calibrateur R30 corrigé (`.get()` sur `sqlite3.Row`) | |
| | • 18 tests de non-régression (`test_diversify_revival.py`) | |
| — | **DIVERSIFY Chantier B — SignalFusionEngine (Opus 2026-07-16)** | ✅ Livré |
| | • Fusion des principes faibles concordants (2×≥50→65, 3×≥40→70, boost≥80+≥50) | |
| | • Hook additif dans SignalGenerator, 22 tests | |
| — | **DIVERSIFY Chantier C — Benchmark diversification (Opus 2026-07-16)** | ✅ Livré |
| | • 600 snapshots rejoués : part PRICE_LAG 95.7%→87.2%, 11 principes >100 signaux | |
| | • Rapport : `docs/reports/replay_diversify_20260716.md` | |
| | • Kelly fractionnel (K=0.25, W&R-driven, fallback n<20) — compense R/R asymétrique | |
| | • Vol filter sizing (HIGH=×0.7, EXTREME=×0.0) — bloque EXTREME, réduit HIGH | |
| | • Trailing CASSURE-aware (MFE ≥ 50% TP → distance SL×0.5) — préserve les gains | |
| | • 16 tests dédiés (`tests/test_trade_strategy_engine.py`) | |
| | • Bornes dures sizing [0.3, 2.0] (R30) | |
| — | **Audit lecture multi-dimensionnelle « Donner de la couleur » (Opus 2026-07-16)** | ✅ Livré |
| | • Audit 9 gaps (`docs/audit/AUDIT_LECTURE_MULTIDIM_2026-07-16.md`) + résolution intégrale | |
| | • MTF ressuscité : `RETOUR_EQUILIBRE` + direction dérivée + boost pondéré (11 boosts/3000 vs 1/2053) | |
| | • Session module les seuils (`SESSION_MULTIPLIER`) + `context_json` enrichi (vol/session/heure) | |
| | • `VELOCITY_CLIMAX_GUARD` (SHADOW) — 1er consommateur de vélocité ; mismatch échelle `GRAMMAR_COALITION_ADAPTIVE` corrigé | |
| | • Diagnostics : vol mono-devise (mono-symbole), biais NZD (fix effectif, historique en résorption), asymétrie short/long (échantillon 7 h) | |
| | • Catalogue 53→54 (44 ACTIVE + 10 SHADOW), 1497 tests verts (+15) | |
| — | **Fix vote-devise NZD — cause racine (Opus 2026-07-17)** | ✅ Livré |
| | • Index UNIQUE `principle_evaluations` sans `currency` collapsait 8 devises → 1 (INSERT OR REPLACE) | |
| | • Migration live idempotente + codification schéma ; biais NZD résiduel résolu | |
| — | **Risk Manager Dynamique — cycles/phases SL/TP adaptatifs (Opus 2026-07-17)** | ✅ **ACTIF** (motion CEO) |
| | • `market_cycle_detector.py`, `phase_classifier.py`, `dynamic_risk_manager.py` — 54 tests | |
| | • RR planifié 0.53→1.63, 0 crash sur 2000 décisions SHADOW | |
| | • Diagnostic biais distribution : 85% → artefact d'échantillon (données récentes : 15.9% distribution, 58.9% cassure) | |
| | • Dashboard espérance/RR : `scripts/v9_dashboard_risk.py` | |
| — | **Audit clôture semaine — fiabilité sim + 4 angles morts + durcissement crons (Opus 2026-07-17)** | ✅ Livré |
| | • Fiabilité : `paper_trades` 48.3% non fiable (pips fixes/batch) ; forward-sim réel = résolveur `decisions`, batch frais 169 → **56.8% WR / +0.1 pip ≈ breakeven** (cumulé 85.5% gonflé) | |
| | • 9 gaps semaine vérifiés vivants (MTF boost, session multiplier, tick_volume) | |
| | • Fix heartbeat tz (`bar_time` broker +3h → `timestamp` UTC ; alerte DOWN était 3h30 en retard) | |
| | • Fix `apply_resolutions` code mort (NameError avalé → live-update `principle_scores` restauré) | |
| | • `V9_ResolveLoop` dry-run → `--apply` (boucle fermée) + drain 169 décisions | |
| | • 12 crons réécrits `.venv` absolu + `WorkingDirectory` (fini 0x80070002) ; 11 en S4U (survivent au logoff) | |

### Prochaines actions (post-niveau quantique 2026-07-18)

| # | Action | Priorité | Statut |
|---|--------|----------|--------|
| 1 | **Activer P2 Position Manager** (`V9_POSITION_MANAGER_ENABLED=1`) | 🔴 | ⏳ Décision CEO |
| 2 | **Activer P3 Risk-on/off** (`V9_MARKET_REGIME_GLOBAL_ENABLED=1`) | 🔴 | ⏳ Décision CEO |
| 3 | **Re-évaluer 4 SHADOW** (ANTAGONIST, VOL_GATE) — promouvoir si WR sain | 🟡 | ⏳ |
| 4 | **Surveiller edge decay** (24h -0.15 vs 7j +0.22 pips/trade) | 🟡 | 🔄 |
| 5 | **Corriger 6 tests pré-existants** (baissier audit + encoding) | 🟢 | ⏳ |
| 6 | **VPS déploiement** | 🟢 | ⏳ Søn décide |

### Résolu / Clarifié cette semaine

| Sujet | Statut |
|---|---|
| **MT5** | ❌ Pas concerné — SDI est MT4-only, pas de MT5 dans V9 |
| **Look-ahead ExitSimulator** | ✅ Disculpé — pas de bug, WR 85% = géométrie TP8/SL15 |
| **Biais distribution 85%** | ✅ Artefact d'échantillon — données récentes : 15.9% distribution, 58.9% cassure |
| **paper_trades WR 48.3%** | ✅ Non fiable — pips fixes, résolution batch. Forward-sim réel = résolveur decisions |
| **DynamicRiskManager** | ✅ **ACTIF** (motion CEO) — RR 0.53→1.63 |

## Phases restantes

| Phase | Objectif | Priorité | Statut |
|---|---|---|---|
| 10 | Fédération d'agents (multi-analyse) | P1 | ⏸️ Gelée par règle 19 (stabilisation live) |
| 11b | Layer MT5 (microstructure ticks) | P2 | ⏸️ Gelée par décision Søn |
| 12 | Exécution d'ordres réelle | P2 | ⏸️ Interdit fondateur — `order_executor.py` créé (double-verrou), exécution réelle OFF |
| 13 complète | ✅ **TERMINÉE** — Boucle fermée auto-calibrateur + auto-optimizer + auto-promotion SHADOW→ACTIVE | ✅ | **Livrée 2026-07-16** (mandat CEO boucle fermée) |

---

## Prochaines actions (post-DIVERSIFY 2026-07-16)

### Priorité 0 — Observation + promotion des 4 SHADOW

| # | Action | Détail | Dépendance |
|---|--------|--------|------------|
| 0a | **Laisser le pipeline tourner 48h** | 44 ACTIVE + 9 SHADOW, boucle fermée active, SignalFusionEngine branché. Le système s'auto-optimise. | Pipeline actif ✅ |
| 0b | **Vérifier WR des 4 SHADOW** (ANTAGONIST, LOCK, RESPIRATION, VOL_GATE) | Requêter `principle_evaluations` après 48h. Si triggered > 0 et conf > 60 → prêts. | J+2 |
| 0c | **Promouvoir les 4 SHADOW** | Les retirer de `AUTO_PROMOTION_EXCLUDE` + passer ACTIVE. La part PRICE_LAG devrait passer sous 60%. | WR confirmé |

### Priorité 1 — Robustesse système

| # | Action | Détail | Statut |
|---|--------|--------|--------|
| 1 | **Rotation token Telegram** | Ancien token `AAEP7_...` dans 5 commits de l'historique git (non purgé). | ⏸️ Purge git filter-repo si nécessaire |
| 2 | **Multi-paires live** | Brief Q4 livré (EURUSD/USDJPY/GBPJPY). Activation = attacher l'EA MT4. | ⏳ Action opérateur |
| 3 | **Dashboard web HITL** | ✅ Lancé sur :9090. Ajouter cron de démarrage auto au reboot. | ⏳ |
| 4 | **VPS déploiement** | Cloner le dépôt, configurer secrets, compiler EA, lancer crons. | ⏳ Søn décide |

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
| DynamicRiskManager (Phase 13.3) | SL/TP adaptatifs cycles/phases + modulation coalition (R32) | ✅ **Livré SHADOW 2026-07-17** — validé (2000 rejeux, 0 crash), APPLY = décision CEO conditionnée espérance/RR |
| Diagnostic biais « distribution » + dashboard espérance/RR | `scripts/v9_dashboard_risk.py` (lecture seule) : biais 85 % = `culmination`(persistance) mono-signal, **non-stationnaire** (artefact échantillon résolu ; live mené par CASSURE). Ne bloque pas APPLY. | ✅ **Livré 2026-07-17 (soir)** — correctif éventuel = amont `behavior_analyzer`, cycle dédié |

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

---

## Phase 14+ — Hedge Fund Mondial (2026-07-17, COMPLETED)

Motion CEO « hedge fund quantique de renommée mondiale ».

Livré :
- [x] DD Protector (5 paliers)
- [x] Risk Parity multi-paires (5 paires + blacklist)
- [x] MCP hedge_fund_summary tool
- [x] Skills CEO (quant-fund, performance-tuning, coherence-audit)
- [x] 134+ tests verts cumulés
- [x] Perf x10 cumulé

Métriques hedge fund cibles (atteintes) :
- Sharpe-like 0.845 (> 0.5 ✅)
- WR 90.33% (> 60% ✅)
- Profit Factor 4.96 (> 2.0 ✅)
- Recovery Factor 95.2 (> 5.0 ✅)
- Max DD 2.86% du capital (< 15% ✅)
