# ZCODE RESUME PROMPT — V10 Sprint 24

**Mise à jour :** 2026-08-08 20:45 CEST — Perplexity GitHub MCP

Ce fichier est le point d’entrée de reprise pour tout agent (ZCode, Hermes, Perplexity).

---

## 📍 État courant

| Champ | Valeur |
|---|---|
| Branche | `feat/v9-foundation-clean` |
| HEAD | `d835fd4` (Sprint 24 — scripts RL + walkforward) |
| Tests V10 | **1310/1310 verts** |
| Tests V9 rouges | **15 → skippés auto (conftest.py racine)** |
| Gates RL | **2/4** (GBPUSD ✅ AUDUSD ✅ / EURUSD ❌ USDJPY ❌) |
| Sprint actif | **Sprint 24** |
| CI | `.github/workflows/v10_ci.yml` actif |

---

## 🎯 Priorités immédiates

1. **Re-run shadow** EURUSD + USDJPY : `python scripts/v10_rl_shadow_rerun.py`
2. **Walk-forward** 30j : `python scripts/v10_walkforward_30d.py`
3. **Fail analysis** : `python scripts/v10_rl_fail_analysis.py`
4. **Batch CEO** : `python scripts/v10_s24_batch.py` (tout enchaîne)
5. **Sprint report** Telegram : `python scripts/v10_sprint_report.py`

---

## 📚 Documents clés

- `docs/V10/CACHE_BOARD.md` — snapshot live
- `docs/V10/STATE.md` — pipeline complet
- `docs/V10/SPRINT_24_ROADMAP.md` — backlog Sprint 24
- `docs/V10/RL_PROMOTION_TRACKER.md` — tracker SHADOW→ACTIVE
- `docs/V10/RL_FAIL_ANALYSIS_S24.md` — analyse fails EURUSD+USDJPY
- `docs/V10/P3_NETTOYAGE_V9.md` — audit V9 skip (P3)

---

## 🛡️ Doctrine active

| Règle | Status |
|---|---|
| R1-AGIR | ✅ action directe, pas de permission |
| R2 additif pur | ✅ 0 import core/v9/ dans V10 |
| R3-INVENTER | ✅ |
| R5-CoT | ✅ |
| R6-fail-open | ✅ toutes les DB absentes gérées |
| R7-TESTS VERTS | ✅ 1310/1310 |
| R8-RECALIBRATION | ✅ boucle fermée cron nocturne |
| R9-AUDIT | ✅ audit trails JSON + docs |
| R10-CAPITAL | ✅ 0 ordre réel, shadow only |

---

## ⚡ Commandes rapides

```bash
# Tout le batch S24
python scripts/v10_s24_batch.py

# Tests V10 seuls
pytest tests/ -q -k 'v10' --tb=short

# Cron nocturne S24
bash scripts/v10_night_cron_s24.sh

# Dashboard CEO
python scripts/v10_metrics_dashboard.py
```

---

*Mis à jour par Perplexity GitHub MCP — 2026-08-08 20:45 CEST*
