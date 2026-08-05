# STATE — PowerFlow V10
_Source de vérité vivante — Mise à jour : 2026-08-05 12:01 CEST_
_Synchronisé sur git log réel — commit `5bc4ca30` → `f2ad0c01`_

---

## Phase active
**Phase V10 — Pipeline edge fund quantique — Phase A Calibration**
Branche : `feat/v9-foundation-clean`
Statut global : 🟢 En cours — currency_strength livré — calibration live à faire

---

## Acquis V9 (base stable)
- ✅ 54 tests verts base V9 (maintenant inclus dans 812 totaux)
- ✅ Modules V9 : `v9_force.py`, `v9_structure.py`, `v9_context.py` stables
- ✅ Bridge MT4/MT5 Tickmill opérationnel (LIVE 3/3 vérifié 08:36)
- ✅ Dashboard live fonctionnel
- ✅ Doctrine R1-R10 respectée — zéro régression

## Acquis V10 — Zcode session 2026-08-05 matin
- ✅ **`v10_currency_strength.py`** — FatmanCalculator complet (M30 inclus, 6 TF) — **812/812 tests verts**
- ✅ **M30 intégré** dans currency_strength (poids=2.0, mapping M15→M30)
- ✅ `v10_currency_strength_api.py` — 30 tests verts (normalisation 0-1, mapping 7 TF, bias EURUSD)
- ✅ Filtre currency_strength dans orchestrateur (R2 additif, fail-open, downgrade A1→NONE)
- ✅ Behavior gate dans orchestrateur (Phase 32/33, R10, CoT R5)
- ✅ CEO Dashboard unifié — auto-refresh 60s — Bridge + Dataset + Devises + Paper trades
- ✅ Dataset refresh loop horaire (v10_signals_clean vivant, 8782 signaux frais)
- ✅ `docs/strategy/FATMAN_BIBLE.md` — doctrine Fatman+Fatboy complète
- ✅ `tools/pine/PINE_SCRIPT_FATMAN_CSM.pine` — Pine Script v5 TradingView
- ✅ `workspace/perplexity/ACTION_PLAN_HERMES.md` — plan Phase A Zcode
- ✅ `docs/V10/V10_CURRENCY_STRENGTH_SPEC.md` — spec complète 34 tests
- ✅ DECISION-2026-08-05-005 à 006 loguées

## Gaps restants
| Gap | Module | Priorité | Statut |
|---|---|---|---|
| M30 dans v10_force/structure/context | Injection TF 1800s | P1 | 🟡 À vérifier (peut être déjà fait) |
| Signal engine composite | `v10_signal_engine.py` | P2 | 🔴 À créer |
| Filtre session | `v10_session_filter.py` | P3 | 🔴 À créer |
| ATR dynamique | `v10_atr_manager.py` | P3 | 🔴 À créer |
| Backtester | `v10_backtest_engine.py` | P4 | 🔴 À créer |
| Calibration live Fatman | Alignement signal vs visuel | P1 | 🔴 Phase A active |

## Dernier checkpoint
→ `docs/checkpoint_20260805.md` (Perplexity)
→ `workspace/checkpoints/CHECKPOINT_V10_20260805.md` (Zcode)

## Compteur tests
**812 tests verts** au 2026-08-05 09:33 (commit `f2ad0c01`)

## Prochaine action prioritaire
**Phase A — Calibration live** : comparer signal V10 FatmanCalculator vs lecture visuelle Fatman sur paires actives.
Zcode a livré le moteur — maintenant valider que la sortie algorithmique correspond à la lecture humaine.
