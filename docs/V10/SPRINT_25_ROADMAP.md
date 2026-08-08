# Sprint 25 — Roadmap préliminaire

**Créé :** 2026-08-08 20:51 CEST — Perplexity GitHub MCP  
**Précondition :** Sprint 24 terminé (4/4 gates RL, promotion SHADOW→ACTIVE)

---

## 🎯 Objectif Sprint 25

Passage de `PAPER LIVE` → `LIVE RÉEL` sur les 4 paires validées.  
Mise en place du monitoring temps réel, alertes P0 automatiques, drawdown circuit-breaker.

---

## 📋 Backlog Sprint 25

| # | Tâche | Priorité | Dépendance |
|---|---|---|---|
| S25-T1 | Activer paper live GBPUSD + AUDUSD (gates OK) | **P0** | Sprint 24 terminé |
| S25-T2 | Monitoring drawdown temps réel (circuit-breaker 5%) | **P0** | S25-T1 |
| S25-T3 | Alertes P0 Telegram auto (drawdown / WR < seuil) | **P0** | S25-T1 |
| S25-T4 | Activer paper live EURUSD + USDJPY si gates OK | **P1** | Re-run S24 |
| S25-T5 | Walk-forward rolling 7j (vs 30j) — validation continue | **P1** | S25-T1 |
| S25-T6 | Edge Fund Phase 4 — currency strength V2 | **P2** | S25-T3 |
| S25-T7 | Dashboard CEO temps réel (streamlit ou terminal) | **P2** | S25-T1 |
| S25-T8 | Rapport mensuel CEO (PnL, WR, Sharpe, drawdown max) | **P2** | S25-T5 |

---

## 📊 Métriques cibles Sprint 25

| Métrique | Cible |
|---|---|
| Paires paper live | 2/4 minimum (4/4 si S24 complet) |
| Drawdown max autorisé | 5% capital |
| WR paper live minimum | 52% |
| Alertes P0 délai max | < 30 secondes |
| Walk-forward rolling 7j | Actif en continu |

---

## 🛠️ Scripts à créer S25

- `scripts/v10_paper_live_monitor.py` — monitoring temps réel paper trades
- `scripts/v10_circuit_breaker.py` — coupe automatique si drawdown > seuil
- `scripts/v10_weekly_report.py` — rapport CEO hebdo (PnL + Sharpe)
- `scripts/v10_rolling_walkforward.py` — walk-forward rolling 7j

---

## 🔗 Liens Sprint 24

- [Roadmap S24](SPRINT_24_ROADMAP.md)
- [GO/NO-GO Promotion](GO_NO_GO_PROMOTION.md)
- [RL Promotion Tracker](RL_PROMOTION_TRACKER.md)

---

*Perplexity GitHub MCP — 2026-08-08 20:51 CEST*
