# Sprint 24 — Roadmap & Tracking

**Créé :** 2026-08-08 20:34 CEST — Perplexity GitHub MCP (no-limit CEO)
**Branche :** `feat/v9-foundation-clean`
**Base :** HEAD `6d8a9c2` — 1310/1310 verts

---

## 🎯 Objectif Sprint 24

Passer le système V10 de **SHADOW → candidat ACTIVE** en résolvant les 2 gates
RL manquants (EURUSD + USDJPY), consolider le reporting CEO, et préparer la
validation walk-forward 30 jours.

---

## 📋 Backlog Sprint 24

### S24-P1 — RL SHADOW : résoudre EURUSD + USDJPY (P0)

**Contexte :** Phase 17 résultat 2/4 gates.
- EURUSD : baseline 69.3% → shadow 72.0% — gate échoue (critère: 30 consécutifs)
- USDJPY : baseline 58.1% → shadow 66.0% — gate échoue (critère: 30 consécutifs)

**Hypothèse d'échec :**
- EURUSD : très haut baseline (69.3%) → moindre marge de progression réelle
- USDJPY : anomalie JPY pip (corrigée Phase 19) peut biaiser le suivi

**Actions :**
- [ ] Re-run shadow session 100 trades EURUSD + USDJPY POST watchdog fix JPY
- [ ] Ajuster window "30 consécutifs" si baseline > 60% (critère adaptatif)
- [ ] Analyser les trades shadow perdants (pattern récurrent ?)
- [ ] Rapport `reports/v10_rl_shadow_rerun_20260808.json`

---

### S24-P2 — Dashboard métriques live v2 (P1)

**Script :** `scripts/v10_metrics_dashboard.py` (créé ce sprint)

Fournit un résumé CEO lisible en CLI/JSON :
- WR live (paper_trades)
- WR shadow (RL)
- Gates promotion (4 critères)
- Edges actifs (replay batch)
- Watchdog status
- Alertes P0/P1 en cours

---

### S24-P3 — Walk-forward 30 jours EURUSD M30 (P1)

**Scope :** validation out-of-sample sur les 30 derniers jours
- Script : `scripts/v10_walkforward_30d.py`
- Paires : EURUSD M30 (edge 69% confirmé)
- Critères GO : WR ≥ 55%, Sharpe ≥ 0.3, n ≥ 60 trades
- Rapport JSON + Telegram CEO

---

### S24-P4 — CI V9 skip propre (P2) — 🟢 FAIT

- `tests/conftest_v9_skip.py` créé (commit `6d8a9c2`)
- 15 tests V9 rouges → skippés officiellement
- Audit : `docs/V10/P3_NETTOYAGE_V9.md`

---

### S24-P5 — Rapport hebdo Telegram CEO (P2)

- Extension du cron nocturne : ajouter `v10_sprint_report.py`
- Résumé hebdo : gates RL, WR live, edges, alertes P0
- Format : Markdown Telegram (inline keyboard si possible)

---

### S24-P6 — Analyse fails RL EURUSD/USDJPY (P1)

- Lecture `v10_rl_shadow_log` table
- Identification des patterns d'échec (heure, session, setup)
- Ajustement des hyperparamètres Thompson Sampling si nécessaire
- Rapport `docs/V10/RL_FAIL_ANALYSIS_S24.md`

---

## 📊 Métriques cibles Sprint 24

| Métrique | Actuel | Cible S24 |
|---|---|---|
| Gates RL | 2/4 | 4/4 |
| WR live paper | 44.5% | ≥ 50% |
| Edges actifs ≥50% | 8 | ≥ 10 |
| Tests V10 | 1310 | ≥ 1310 |
| Tests V9 rouges | 15 skips | 0 rouge (skips OK) |
| Promotion SHADOW | HOLD | CANDIDAT ACTIVE |

---

## 🔗 Références

- `docs/V10/CACHE_BOARD.md` — snapshot live
- `docs/V10/P3_NETTOYAGE_V9.md` — audit V9 skip
- `reports/v10_rl_shadow_100trades_20260808.json` — Phase 17
- `reports/v10_metrics_watchdog_20260808.json` — Phase 19

---

*Généré automatiquement par Perplexity GitHub MCP — Sprint 24 init 2026-08-08 20:34 CEST*
