# V10 QUANT UPGRADE — Sprints 2-3 (public strategies + régimes)

**Date** : 2026-08-05
**Mandat** : CEO « install all, no limit, plein pouvoir, go »
**HEAD** : après commit Sprints 2-3
**Cumul tests** : 959 → **1033 verts** (+74)

---

## Doctrine changée (2026-08-05)

- **100% stdlib → stack quant complète** : `pyproject.toml` v0.10.0, dépendances
  scipy/statsmodels/scikit-learn/hmmlearn/ruptures/arch/plotly/finta.
- Installées dans l'interpréteur qui exécute les tests (Hermes venv).
- **R10 inchangé** : zéro ordre réel sans `V9_EXECUTION_ENABLED==1`.

## Sprints livrés

### Sprint 2 — Régimes (hmmlearn + ruptures) — `core/v10/v10_regime_hmm.py`
- `detect_hmm_regime` : HMM Gaussian 5 états sur log-returns →
  TRENDING_UP/DOWN, RANGING, VOLATILE, NEWS_LOCK + confiance.
- `detect_change_points` : ruptures PELT (cost rbf) → détection decay.
- `compose_regime_signal` : HMM + changepoints + bonus si rupture récente.
- R6 fail-open (data insuffisante / lib absente → UNKNOWN).
- **11 tests verts**.

### Sprint 3 — SMC public — `core/v10/v10_smc.py`
- `detect_smc` : BOS/MSS (cassure de structure), Order Blocks (contre-tendance),
  FVG (fair value gap 3-bougies) + zones et `in_*`.
- `smc_to_signal_level` : boost A3→A2 sur MSS/BOS, A1 jamais downgradé par SMC.
- R6 fail-open. **14 tests verts**.

### Sprint 3b (déjà livré) — ICT OTE — `core/v10/v10_ict_ote.py`
- Kill Zones ASIAN/LONDON/NY + OTE Fibonacci 62-79% + conviction score.
- **20 tests verts**.

### Sprint 4 — Pipeline de signal opérationnel
- **`v10_filter_compositor.py`** : chaîne de filtres publics
  (session + ICT OTE + SMC + regime) sur `setup_level`, trace R9 complète,
  R6 fail-open. **10 tests**.
- **`v10_vol_forecast.py`** : GARCH (arch) + fallback EWMA, `sl_tp_from_vol`
  pour dimensionner SL/TP. **9 tests**.
- **`v10_wyckoff_consolidated.py`** : consolide VSA + compression-extension
  en un état Wyckoff unique (MARKUP/MARKDOWN/ACCUMULATION/DISTRIBUTION).
  **8 tests**.

**Cumul tests Sprint 2-4** : 959 → **1060 verts** (+101).

## Backtest public strategies — validation données live

Harness : `scripts/v10_public_strategy_backtest.py` sur `v10_signals_clean`
(8822 signaux). **R9 honnête** : `is_win_proxy` = proxy V9 biaisé → signal
d'edge RELATIF, pas PnL absolu.

| Kill Zone | n | WR | ΔWR vs base |
|---|---|---|---|
| **NY** | 776 | **53.2%** | **+20.0 pts** |
| **LONDON** | 1061 | **44.7%** | **+11.5 pts** |
| **ASIAN** | 2453 | 39.9% | +6.7 pts |
| **OUTSIDE** | 4532 | 23.4% | **−9.8 pts** |

Base WR globale : **33.2%**.

**Conclusion** : le filtre ICT Kill Zones concentre l'edge — NY +20pts,
LONDON +11.5pts, OUTSIDE −9.8pts. Le filtre `apply_ote_to_signal` +
`v10_session_filter` câblé sur l'orchestrateur devrait rehausser le WR des
signaux A1/A2 émis pendant LONDON/NY.

## Files

- `core/v10/v10_regime_hmm.py` (nouveau)
- `core/v10/v10_smc.py` (nouveau)
- `core/v10/v10_ict_ote.py` (Sprint 3b)
- `core/v10/__init__.py` (exports étendus)
- `tests/test_v10_regime_hmm.py`, `tests/test_v10_smc.py` (nouveaux)
- `scripts/v10_public_strategy_backtest.py` (nouveau)
- `reports/v10_public_strategy_backtest_20260805.json`
- `requirements.txt`, `pyproject.toml` (doctrine quant)
