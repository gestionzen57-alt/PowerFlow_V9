# BOARD — PowerFlow V10
_Dernière mise à jour : 2026-08-05 (Hermes — Cron replay hebdomadaire)_

---

## 🚀 Dernière livraison Hermes (Replay hebdo automatique + carte des edges Telegram)

- ✅ **Cron hebdo** : `v10_replay_batch_cron.sh` (lundi 03:00, `89c26817deb9`)
  — rejoue toute la profondeur, rafraîchit les edges + modèle. execution_success=true.
- ✅ **Edges Telegram** : `v10_edges_telegram_alert.py` — carte des edges notifiée.
- ✅ **1141/1141 tests verts**. Commit `8e7db16` pushé.
- ✅ 3 crons V10 actifs : nocturne (8 étapes) + live 30min + replay hebdo.

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
