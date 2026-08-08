# GO / NO-GO — Promotion SHADOW → ACTIVE

**Sprint 24 — 2026-08-08 20:51 CEST**  
**Perplexity GitHub MCP**

---

## 🎯 Critères de promotion CEO

Une paire passe de `SHADOW` à `ACTIVE` (paper live) si **tous les critères** sont verts :

| # | Critère | Seuil | Méthode |
|---|---|---|---|
| G1 | Gate consécutif adaptatif | ≥ 20 trades (baseline≥60%) ou ≥ 30 (baseline<60%) | `v10_gate_adaptive.py` |
| G2 | WR shadow ≥ baseline | delta ≥ 0 (shadow ≥ baseline) | `v10_rl_shadow_rerun.py` |
| G3 | Walk-forward 30j | WR ≥ 55%, n ≥ 60 trades, proxy Sharpe ≥ 0.3 | `v10_walkforward_30d.py` |
| G4 | Session filter OK | Pas de session OUTSIDE filtrée bloquante | `v10_thompson_tuner.py` |

---

## 📊 État Sprint 24 (2026-08-08)

| Paire | G1 Gate | G2 WR delta | G3 WF | G4 Session | Verdict |
|---|---|---|---|---|---|
| **GBPUSD** | ✅ | ✅ | ⏳ | ✅ | **GO** (pending WF) |
| **AUDUSD** | ✅ | ✅ | ⏳ | ✅ | **GO** (pending WF) |
| **EURUSD** | ❌ | ✅ (delta +2.7%) | ⏳ | ⚠️ OUTSIDE | **NO-GO** — re-run post-session-filter |
| **USDJPY** | ❌ | ✅ (delta +7.9%) | ⏳ | ✅ | **NO-GO** — re-run post-fix JPY |

---

## 🛠️ Plan d'action EURUSD + USDJPY

1. Appliquer `v10_thompson_tuner.py` → filtrer session OUTSIDE EURUSD
2. Appliquer `v10_session_filter.py` → filtrer signaux hors Kill Zone
3. Relancer `make shadow` → re-run 100 trades post-filtres
4. Valider `make gate` → vérifier gate adaptatif
5. Si gate OK → `make walkforward` → verdict GO/NO-GO final
6. CEO décision promotion → activer paper live

---

## ⚡ Commandes rapides

```bash
# Pipeline complet validation
make thompson && make shadow && make gate && make walkforward

# Dashboard CEO
python scripts/v10_metrics_dashboard.py

# Sprint report Telegram
make report
```

---

## 📋 Historique promotions

| Date | Paire | Action | Résultat |
|---|---|---|---|
| 2026-08-08 | GBPUSD | 100 trades shadow | Gate ✅ Phase 17 |
| 2026-08-08 | AUDUSD | 100 trades shadow | Gate ✅ Phase 17 |
| 2026-08-08 | EURUSD | 100 trades shadow | Gate ❌ — en cours |
| 2026-08-08 | USDJPY | 100 trades shadow | Gate ❌ — fix JPY Phase 19 |

---

*Perplexity GitHub MCP — 2026-08-08 20:51 CEST*
