"""Tests Chantier 4b — v9_aggressive_optimize (grid search stabilité-pénalisé)."""
from __future__ import annotations

import pytest

import scripts.v9_aggressive_optimize as opt
import scripts.v9_aggressive_paper_trade as bt


# ------------------------------------------------------------------ stability_score

def test_score_equals_pips_when_stable():
    assert opt.stability_score(1000.0, 5.0) == 1000.0


def test_score_penalized_when_unstable():
    s = opt.stability_score(1000.0, 30.0)  # spread 2× le seuil → ~×0.5
    assert s < 1000.0
    assert s == pytest.approx(500.0, abs=1.0)


def test_score_penalty_monotonic():
    a = opt.stability_score(1000.0, 20.0)
    b = opt.stability_score(1000.0, 45.0)
    assert b < a


def test_score_zero_spread_no_crash():
    assert opt.stability_score(1000.0, 0.0) == 1000.0


def test_score_at_threshold_full_pips():
    assert opt.stability_score(500.0, bt.WF_STABILITY_MAX_SPREAD) == 500.0


# ------------------------------------------------------------------ grilles

def test_grids_within_mission_bounds():
    assert min(opt.TP_GRID) >= 10 and max(opt.TP_GRID) <= 30
    assert min(opt.SL_GRID) >= 8 and max(opt.SL_GRID) <= 18


def test_grid_cardinality():
    assert len(opt.TP_GRID) * len(opt.SL_GRID) * len(opt.K_GRID) == 60


# ------------------------------------------------------------------ run_config / grid (données synthétiques)

def _synthetic():
    """Marché minimal : 1 paire, barres montantes, 6 décisions long."""
    bars = [{"bar_time": 1000 + i * 100, "high": 1.30 + i * 0.001 + 0.0008,
             "low": 1.30 + i * 0.001 - 0.0006, "close": 1.30 + i * 0.001}
            for i in range(10)]
    market = {"bars": {("GBPUSD", "M15"): bars},
              "times": {("GBPUSD", "M15"): [b["bar_time"] for b in bars]},
              "horizon": 6}
    recs = []
    for i in range(6):
        recs.append(bt.DecisionRec(
            idx=i, timestamp=f"2026-07-1{i}", symbol="GBPUSD", timeframe="M15",
            direction="haussiere", regime="NEUTRE", phase="initiation",
            confiance=80.0, entry_bar_time=1000 + i * 100, entry_close=1.30 + i * 0.001,
            baseline_pips=10.0, baseline_win=1,
        ))
    return recs, market


def test_run_config_returns_result():
    recs, market = _synthetic()
    p_win = opt.precompute_pwin(recs, market, 2)
    r = opt.run_config(recs, market, p_win, 15, 10, 0.25, k_folds=2)
    assert isinstance(r, opt.ConfigResult)
    assert r.tp == 15 and r.sl == 10 and r.kelly == 0.25


def test_run_config_records_metrics():
    recs, market = _synthetic()
    p_win = opt.precompute_pwin(recs, market, 2)
    r = opt.run_config(recs, market, p_win, 20, 12, 0.25, k_folds=2)
    assert r.total_pips >= 0.0
    assert 0.0 <= r.win_rate <= 100.0


def test_precompute_pwin_length():
    recs, market = _synthetic()
    p_win = opt.precompute_pwin(recs, market, 2)
    assert len(p_win) == len(recs)
    assert all(0.0 <= p <= 1.0 for p in p_win)


def test_grid_search_sorted_by_score():
    recs, market = _synthetic()
    p_win = opt.precompute_pwin(recs, market, 2)
    results = opt.grid_search(recs, market, p_win, k_folds=2)
    assert len(results) == 60
    scores = [c.score for c in results]
    assert scores == sorted(scores, reverse=True)


def test_grid_search_best_is_first():
    recs, market = _synthetic()
    p_win = opt.precompute_pwin(recs, market, 2)
    results = opt.grid_search(recs, market, p_win, k_folds=2)
    assert results[0].score == max(c.score for c in results)


def test_short_gate_zeroes_shorts():
    recs, market = _synthetic()
    for r in recs:
        r.direction = "baissiere"  # NEUTRE shorts → gated
    p_win = opt.precompute_pwin(recs, market, 2)
    r = opt.run_config(recs, market, p_win, 20, 12, 0.25, k_folds=2, gate=True)
    assert r.total_pips == 0.0  # tous gated → aucun trade


# ------------------------------------------------------------------ rapport

def test_build_report_contains_table():
    recs, market = _synthetic()
    p_win = opt.precompute_pwin(recs, market, 2)
    results = opt.grid_search(recs, market, p_win, k_folds=2)
    rep = opt.build_report(results, len(recs))
    assert "grid search" in rep.lower()
    assert "| Rang |" in rep


def test_build_report_flags_no_stable():
    # Force des résultats tous instables.
    unstable = [opt.ConfigResult(15, 10, 0.25, 1000, 2.0, 90, -50, 40.0, 375)]
    rep = opt.build_report(unstable, 100)
    assert "Aucune configuration stable" in rep


def test_build_report_reports_best_stable():
    stable = [opt.ConfigResult(20, 12, 0.25, 800, 3.0, 88, -20, 5.0, 800)]
    rep = opt.build_report(stable, 100)
    assert "Meilleure config stable" in rep or "meilleure config stable" in rep.lower()
