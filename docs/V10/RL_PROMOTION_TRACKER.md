# RL SHADOW → ACTIVE : Tracker de Promotion

**Créé :** 2026-08-08 20:34 CEST — Perplexity GitHub MCP
**Objectif :** Atteindre 4/4 gates pour promotion SHADOW→ACTIVE

---

## 🎯 Gates de Promotion (R10)

| Gate | Critère | Phase 17 (08/08) | Cible S24 |
|---|---|---|---|
| G1 — WR global | ≥ 50% | ✅ 57% (GBPUSD) | ≥ 50% global |
| G2 — Sharpe | ≥ 0.3 | ❌ -0.065 | ≥ 0.3 |
| G3 — Max DD | ≤ 50 pips | ❌ 56.9p | ≤ 50p |
| G4 — Consistency | ≥ 75% | ❌ 54% | ≥ 75% |

**Verdict actuel : HOLD (1/4 gates)**

---

## 📊 État RL par paire (Phase 17 — 2026-08-08)

| Paire | Baseline WR | Shadow WR | Delta | Gate 30-consec | Statut |
|---|---|---|---|---|---|
| GBPUSD | 50.8% | 57.0% | +6.2% | ✅ PASS | ✅ Validé |
| AUDUSD | 46.6% | 49.0% | +2.4% | ✅ PASS | ✅ Validé |
| EURUSD | 69.3% | 72.0% | +2.7% | ❌ FAIL | 🟡 À retravailler |
| USDJPY | 58.1% | 66.0% | +7.9% | ❌ FAIL | 🟡 Watchdog fix appliqué |

---

## 🔍 Analyse Échecs

### EURUSD — Gate 30 consécutifs
- Baseline très élevée (69.3%) → amplitude réelle limitée
- Shadow 72.0% = +2.7% réel mais gate "30 consécutifs" très exigeant
- **Hypothèse** : variance haute sur 30 trades consécutifs avec baseline haute
- **Action S24** : re-run post-watchdog fix, analyser fenêtre glissante

### USDJPY — Gate 30 consécutifs
- Bug pip JPY corrigé (Phase 19) — les métriques étaient faussées
- **Action S24** : re-run post-fix JPY obligatoire avant conclusion
- Shadow +7.9% = delta le plus élevé → fort potentiel

---

## 📅 Historique Runs Shadow

| Date | Run | GBPUSD | AUDUSD | EURUSD | USDJPY | Gates |
|---|---|---|---|---|---|---|
| 2026-08-08 | Phase 17 | ✅ 57% | ✅ 49% | ❌ 72% | ❌ 66% | 2/4 |
| 2026-08-08 | P3-clean | — | — | — | — | — |
| À planifier | S24-re-run | ? | ? | ? | ? | ? |

---

## 🚀 Plan d'action S24

1. **Re-run** shadow session EURUSD + USDJPY (post watchdog fix JPY)
2. **Analyser** `v10_rl_shadow_log` pour pattern d'échec (session, heure)
3. **Ajuster** critère gate si baseline > 60% (critère adaptatif R8)
4. **Rapport** `docs/V10/RL_FAIL_ANALYSIS_S24.md`
5. **Push** résultats → décision CEO GO/NO-GO promotion

---

*Mis à jour automatiquement par Perplexity GitHub MCP — 2026-08-08 20:34 CEST*
