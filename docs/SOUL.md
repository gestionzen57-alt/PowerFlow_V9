# SOUL — PowerFlow V10
**Version :** 3.0 — Architect Pass MAX  
**Mis à jour :** 2026-08-07 12:18 CEST  
**Branche :** `feat/v9-foundation-clean`

> Fichier de référence philosophique ET technique du système.  
> Liens croisés : [`PIPELINE_MAP.md`](PIPELINE_MAP.md) · [`LEVIER_HUB.md`](LEVIER_HUB.md) · [`STATE.md`](STATE.md)

---

## 0. Chronologie (jalons uniquement)

| Date | Jalon |
|---|---|
| 2025-10 | Lancement V9 — pipeline 6 couches |
| 2026-01 | Phase 12 — contexte fractal 7 TF |
| 2026-04 | Lancement V10 — Cognitive Continuum |
| 2026-06 | Sprints 1-5 — filtres composites + HMM + ICT |
| 2026-07 | Sprints 6-12 — Risk shield + auto-recalibration + live decision |
| 2026-08 | Sprints 13-15 — pipeline live complet + bug fix Safe Haven |

---

## 1. Mission

PowerFlow V10 est un système algorithmique de trading Forex **paper-only** (zéro ordre réel).  
Objectif : produire des signaux BUY/SELL/WAIT haute-conviction sur 7 paires majeures,  
en combinant analyse multi-temporelle, machine learning (HMM, RL), et scoring composite Hub.

**Philosophie CEO :** zéro dette cachée, zéro ordre réel, zéro module orphelin.

---

## 2. Pipeline — 6 couches

```
┌─────────────────────────────────────────────────────────────┐
│  COUCHE 0 : CAPTURE                                         │
│  capture_server (port 31685) → v9_forces.db                 │
│  259 540+ snapshots · fraîcheur ~1 min                      │
├─────────────────────────────────────────────────────────────┤
│  COUCHE 1 : RÉGIMES                                         │
│  v10_hmm_regime → 4 états (trending/ranging/volatile/calm)  │
│  GARCH vol → v10_garch_volatility                           │
├─────────────────────────────────────────────────────────────┤
│  COUCHE 2 : FILTRES COMPOSITES                              │
│  v10_filter_compositor → ICT OTE + SMC + session + Wyckoff  │
│  v10_strategy_layers (wrapper) → réutilise compositor        │
├─────────────────────────────────────────────────────────────┤
│  COUCHE 3 : SCORING HUB                                     │
│  21 modules → score Hub ∈ [0,1]                             │
│  Σ poids = 1.00 (table dans LEVIER_HUB.md)                  │
├─────────────────────────────────────────────────────────────┤
│  COUCHE 4 : DÉCISION                                        │
│  v10_live_decision → BUY/SELL/WAIT                          │
│  v10_decision_pipeline → decide_entry + bouclier R10        │
│  v10_risk_shield → gates DD/position/corrélation            │
├─────────────────────────────────────────────────────────────┤
│  COUCHE 5 : EXÉCUTION (DÉSACTIVÉE)                          │
│  paper_only=True hard-codé · MT5 bridge lecture seule       │
│  V9_EXECUTION_ENABLED=1 = RÉSIDU V9 (0 consommateur V10)    │
└─────────────────────────────────────────────────────────────┘
```

---

## 3. Modules — Fiche technique

| Module | Fichier | Rôle | Poids Hub | Particularité |
|---|---|---|---|---|
| HMM Regime | `v10_hmm_regime.py` | 4 états marché | 0.12 | 4 features OHLCV |
| GARCH Vol | `v10_garch_volatility.py` | Volatilité conditionnelle | 0.08 | arch lib |
| ICT OTE | `v10_ict_ote.py` | Optimal Trade Entry 62-79% fib | 0.09 | Fractal 7 TF |
| SMC Public | `v10_smc_public.py` | Structure market + BOS | 0.10 | Wyckoff intégré |
| Filter Compositor | `v10_filter_compositor.py` | Hub filtres composites | 0.11 | Cœur unique |
| Strategy Layers | `v10_strategy_layers.py` | Wrapper compositor | 0 | Pas de poids propre |
| Currency Strength | `v10_currency_strength.py` | Force relative 8 devises | 0.09 | Bug Safe Haven réparé |
| Fatman Calculator | `v10_fatman_calculator.py` | Score momentum Fatboy | 0.07 | Principe 3 Fatboy |
| Risk Shield | `v10_risk_shield.py` | Gates R10 | 0.08 | DD halt + 2% max |
| Net Exposure | `v10_net_exposure.py` | Exposition nette | 0.05 | Doubles opposées |
| Live Decision | `v10_live_decision.py` | Signal final 30min | 0.06 | Cron Sprint 15 |
| Decision Pipeline | `v10_decision_pipeline.py` | decide_entry + bouclier | 0.05 | Sprint 13 |
| Auto Recalibrator | `v10_auto_recalibrator.py` | Drift → REVERT | 0.04 | Verdict HOLD actuel |
| Cortex | `v10_cortex.py` | Apprentissage RAG | 0.03 | Cognitive Continuum |
| Night Report | `v10_night_report.py` | Rapport nocturne | 0 | Cron nuit |
| Shadow Promoter | `v10_shadow_promoter.py` | RL SHADOW→ACTIVE | 0 | Gates : WR≥50/Sharpe≥0.3 |
| Error Learner | `v10_error_learner.py` | Apprentissage erreurs | 0.03 | Sprint 5 |

---

## 4. Fusion Hub — Formule

```python
# score_hub = Σ (poids_i × score_i) pour i ∈ modules actifs
# Normalisation si module indisponible : redistribution proportionnelle
# Seuils décision :
#   score_hub > 0.65  → BUY
#   score_hub < 0.35  → SELL
#   0.35 ≤ score ≤ 0.65 → WAIT

def fuse_hub(scores: dict, weights: dict) -> float:
    active = {m: s for m, s in scores.items() if s is not None}
    w_total = sum(weights[m] for m in active)
    if w_total == 0:
        return 0.50  # fail-open neutre
    return sum(weights[m] * active[m] for m in active) / w_total
```

**Vérification Σ poids = 1.00** — voir `LEVIER_HUB.md` section 4.

---

## 5. Stack technologique

| Composant | Statut | Version |
|---|---|---|
| Python | ✅ Actif | 3.11 |
| pytest | ✅ Actif | 7.x |
| scipy / statsmodels | ✅ Actif | latest |
| sklearn / hmmlearn | ✅ Actif | latest |
| ruptures / arch | ✅ Actif | latest |
| plotly / finta | ✅ Actif | latest |
| MT5 bridge | ✅ Paper-only | — |
| SQLite v9_forces.db | ✅ Actif | — |
| Capture server | ✅ port 31685 | — |
| RL module | 🔄 Sprint actif | SHADOW |

---

## 6. Règles R10 (non-négociables)

1. **Zéro ordre réel** — `paper_only=True` hard-codé, 0 occurrence `order_send` dans `core/v10/`
2. **DD halt** — arrêt si drawdown ≥ seuil configuré
3. **Position max 2%** par trade
4. **Pas de doubles opposées** — vérification `v10_net_exposure`
5. **Corrélation** — filtrage positions corrélées > 0.8
6. **Fail-open R6** — module indisponible → score neutre 0.50, redistribution poids

---

## 7. Tables décision rapide

### Session forex
| Session | Paires actives | Multiplicateur |
|---|---|---|
| London (07-16 UTC) | EURUSD, GBPUSD, EURGBP | ×1.2 |
| New York (13-22 UTC) | USDJPY, USDCAD, USDCHF | ×1.1 |
| Overlap (13-16 UTC) | Toutes | ×1.3 |
| Asie (22-07 UTC) | USDJPY, AUDUSD | ×0.8 |

### Volatilité (GARCH)
| État GARCH | Action |
|---|---|
| vol > 2σ | Réduire position ×0.5 |
| vol > 3σ | WAIT forcé |
| vol normal | Scoring normal |

### Gates R10
| Gate | Seuil | Action si déclenché |
|---|---|---|
| DD halt | -50p journalier | Stop toutes positions |
| Position max | 2% capital | Refus signal |
| Corrélation | > 0.8 | Refus doublon |
| Consistency | < 75% 100 derniers | Pas de promotion SHADOW |

---

## 8. Résultats empiriques (honnêtes)

| Métrique | Valeur | Contexte |
|---|---|---|
| WR paper Sprint 14 | ~51% | 3 jours observation |
| Sharpe paper | 0.31 | Hors Phase 180 |
| Auto-recalibration | REVERT | after_wr=0 < before_wr=0.49 |
| Safe Haven V9 | ✅ Réparé | commit `885a851` |

⚠️ **Phase 180 warning** : périodes de retournement brutal invalidant temporairement le scoring — WAIT forcé recommandé lors de news macro Tier-1.

---

## 9. Contacts et responsabilités

| Rôle | Agent | Périmètre |
|---|---|---|
| CEO / Opérateur | Søn | Décisions, validation, trading live |
| Architecte docs | Perplexity | .md, structure, cohérence |
| Développement V10 | Zcode | Python, tests, core/ |
| Sprints Hermes | Hermes | Pipeline live, crons, nuit |

---

## 10. Anti-patterns documentés

- ❌ Modifier `core/v10/` sans test pytest associé
- ❌ Confondre `V9_EXECUTION_ENABLED=1` avec capacité ordre réel
- ❌ Lancer promotion SHADOW sans 100 trades paper validés
- ❌ Bypasser le bouclier R10 en production
- ❌ Créer un nouveau module sans l'enregistrer dans `INDEX_MODULES.md`
- ❌ Modifier `config/v9_kill_switches.env` sans mandat CEO explicite
