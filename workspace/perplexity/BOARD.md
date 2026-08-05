# BOARD — PowerFlow V10
_Dernière mise à jour : 2026-08-05 (Hermes autopilote quant — Sprint 13)_

---

## 🚀 Dernière livraison Hermes (Sprint 13 — pipeline décision end-to-end)

- ✅ **Pipeline de décision** : `core/v10/v10_decision_pipeline.py` — signal →
  stratégies publiques → bouclier R10 → action BUY/SELL/WAIT + lot_size.
- ✅ **Démo publique live** : `scripts/v10_strategy_demo.py` (EURUSD H1 : TRENDING_DOWN).
- ✅ **1118/1118 tests verts** (1109 → 1118). Commits `ed0f4ec` + `e899811` pushés.
- ✅ Stack publique complète branchée : ICT OTE + SMC + regime HMM + wyckoff
  + filter compositor + risk shield + decision pipeline.
- ⏭️ Next : câbler le pipeline décision dans le live_monitor/cron + connecter Telegram.

---

## 🎯 Situation réelle au 05/08/2026 12h00

### ⚡ ZCODE A LIVRÉ CE MATIN (avant mon push)
- ✅ `v10_currency_strength.py` — FatmanCalculator complet — **812/812 tests verts**
- ✅ M30 intégré (poids=2.0)
- ✅ Filtre currency_strength dans orchestrateur
- ✅ Behavior gate (Phase 32/33)
- ✅ CEO Dashboard live
- ✅ FATMAN_BIBLE.md + Pine Script TradingView
- ✅ Dataset refresh horaire (signals vivants)

### 🔴 Ce qui reste à faire
1. **Calibration live** — aligner sortie FatmanCalculator vs lecture visuelle indicateur
2. `v10_signal_engine.py` — score composite 0-100
3. Filtres session + ATR dynamique
4. Backtester 6 mois
5. Live monitor production

## ⚠️ Note importante
Mes fichiers poussés à 09:40 (BOARD, STATE, ACTIVE_TASKS, HERMES_PLAN, checkpoint) **décrivaient un état déjà dépassé** — Zcode avait terminé TASK-001 à 09:33. Ce fichier est la version corrigée et synchronisée.

## 🗂️ Fichiers pivots
| Fichier | Rôle |
|---|---|
| `docs/STATE.md` | Source de vérité vivante (ce fichier sync) |
| `docs/HERMES_PLAN_V10.md` | Plan Hermes — modules 3-8 restent valides |
| `docs/strategy/FATMAN_BIBLE.md` | Doctrine Fatman (Zcode) |
| `docs/V10/V10_CURRENCY_STRENGTH_SPEC.md` | Spec currency_strength (Zcode) |
| `workspace/checkpoints/CHECKPOINT_V10_20260805.md` | Checkpoint Zcode |
| `workspace/perplexity/ACTIVE_TASKS.md` | Tâches actives mises à jour |

## 📌 Prochaine action Hermes
```
Phase A — Calibration live
→ Lancer v10_live_monitor ou CEO dashboard
→ Observer signal FatmanCalculator sur EURUSD/GBPUSD/USDJPY
→ Comparer avec lecture visuelle indicateur éditeur
→ Rapport écart si >0.3 delta
```
