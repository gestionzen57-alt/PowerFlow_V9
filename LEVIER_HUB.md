# LEVIER_HUB.md — Carte des Leviers V10

> **Référence architecte** (2026-08-07) — Source de vérité leviers.
> Mis à jour à chaque sprint. Couplé à `docs/V10/STATE.md`.

## Vision

Un levier = un module de perception ou d'amélioration qui **modifie
la décision finale** de manière mesurable (ΔWR ou ΔSharpe tracé).
Ce fichier liste tous les leviers actifs, leur état, leur poids Hub,
et leur roadmap d'activation.

---

## Carte des leviers

| # | Levier | Fichier | État | Poids Hub | ΔWR mesuré |
|---|---|---|---|---|---|
| L1 | Fatman Bible (gap/sigma) | `v10_fatman_bible_signals.py` | ✅ ACTIVE | 0.35 | référence |
| L2 | Fractal 7-TF + cinématique | `v10_fractal_context.py` | ✅ ACTIVE | 0.20 | TBM |
| L3 | SMC BOS/MSS/OB/FVG | `v10_smc.py` | ✅ ACTIVE | 0.15 | TBM |
| L4 | HMM Regime 5 états | `v10_regime_hmm.py` | ✅ ACTIVE | 0.10 | TBM |
| L5 | Wyckoff Consolidated | `v10_wyckoff_consolidated.py` | ✅ ACTIVE | 0.05 | TBM |
| L6 | Behavior Registry P90/P10 | `v10_currency_behavior.py` | ✅ ACTIVE | 0.05 | TBM |
| L7 | ICT OTE + Kill Zones | `v10_ict_ote.py` | ✅ ACTIVE | 0.05 | TBM |
| L8 | Sigma Oracle (GREY_ZONE) | `v10_perplexity_sigma_oracle.py` | 🔶 SPRINT 14 | 0.10 | TBD |
| L9 | FatmanIntelligenceHub fusion | `v10_fatman_intelligence_hub.py` | 🔶 SPRINT 15 | HUB | TBD |
| L10 | RL Adapter 8-arms (poids Hub) | `v10_rl_adapter.py` (upgrade) | 🔶 SPRINT 15 | auto | TBD |
| L11 | Fatman Dynamic Calibrator | `v10_fatman_dynamic_calibrator.py` | 🔶 SPRINT 15 | — | TBD |
| L12 | Session Modulator | `adaptive_thresholds_at_runtime.py` | ✅ ACTIVE | — | — |
| L13 | Volatility Regime Guard | `paper_risk_manager.py` | ✅ ACTIVE | — | — |
| L14 | SHAP Explainer (dominant_edge) | via Hub | 🔶 SPRINT 15 | — | — |
| L15 | News Shock Attenuator | `news_context.py` | ✅ ACTIVE | — | — |
| L16 | SignalFusionEngine | `v10_filter_compositor.py` | ✅ ACTIVE | — | — |
| L17 | Bayesian Recalibrator Optuna | `v10_fatman_dynamic_calibrator.py` | 🔶 SPRINT 15 | — | hebdo |
| L18 | IBKR REST API (broker live) | Phase 184 | ⬜ FUTUR | — | — |
| L19 | Dashboard Plotly live | Phase 185 | ⬜ FUTUR | — | — |

**Légende** : ✅ ACTIVE | 🔶 Sprint en cours | ⬜ Futur | TBM = To Be Measured | TBD = To Be Deployed

---

## Cohérence Hub — Vérification somme des poids

```
Σ poids Hub actifs = 0.35+0.20+0.15+0.10+0.10+0.05+0.05+0.05 = 1.05
→ Normalisation obligatoire dans Hub : poids_i / Σ_poids
→ Si module indisponible (R6 fail-open) : redistribution proportionnelle
→ Jamais de signal si tous les modules critiques (L1+L2) sont indisponibles
```

---

## Règle de mesure ΔWR (validation levier)

Pour chaque levier activé, mesure obligatoire après 30 paper trades :

```
ΔWR = WR_avec_levier - WR_sans_levier (même période, même paires)
ΔSharpe = Sharpe_avec - Sharpe_sans

Levier CONSERVÉ    si ΔWR ≥ +1.5% ET ΔSharpe ≥ 0
Levier SHADOW      si ΔWR ∈ [-1%, +1.5%] → surveillance
Levier DÉSACTIVÉ   si ΔWR < -1% OU ΔSharpe < -0.1
```

---

## Matrice de compatibilité inter-leviers

| Levier A | Levier B | Synergie | Note |
|---|---|---|---|
| L3 SMC | L5 Wyckoff | ✅ Forte | BOS + phase institutionnelle |
| L4 HMM | L5 Wyckoff | ✅ Forte | régime + phase (cross-validation) |
| L1 Fatman | L8 Sigma Oracle | ✅ Forte | GREY_ZONE résolue → signal non perdu |
| L2 Fractal | L7 ICT OTE | ✅ Forte | confluence TF + zone Fibonacci |
| L6 Behavior | L12 Session | ✅ Forte | pattern paire + contexte session |
| L13 Vol Guard | L14 SHAP | ✅ Neutre | guard appliqué avant SHAP |

---

## Documents liés

- `SOUL.md` — philosophie et architecture complète
- `PIPELINE_MAP.md` — schéma pipeline 1-page
- `docs/V10/STATE.md` — état live (tests, trades, WR)
- `workspace/perplexity/memory/DECISIONS_LOG.md` — décisions structurantes
