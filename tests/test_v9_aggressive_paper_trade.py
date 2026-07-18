"""Tests Chantier 4 — v9_aggressive_paper_trade (backtest lecture-seule).

Vérifie les fonctions pures : simulation first-touch, métriques (WR/PF/DD/
Sharpe), WR shrinkée, verdict piloté par la stabilité walk-forward.
"""
from __future__ import annotations

import pytest

import scripts.v9_aggressive_paper_trade as bt


# ------------------------------------------------------------------ simulate_first_touch

def _bar(h, l, c=None):
    return {"high": h, "low": l, "close": c if c is not None else (h + l) / 2}


def test_first_touch_tp_long():
    fb = [_bar(1.1035, 1.0995)]  # +35 pips favorable, -5 adverse
    pnl, mode = bt.simulate_first_touch(1.1000, "haussiere", 30, 18, fb, 0.0001)
    assert mode == "tp"
    assert pnl == 30


def test_first_touch_sl_long():
    fb = [_bar(1.1005, 1.0975)]  # -25 adverse breaches sl=18
    pnl, mode = bt.simulate_first_touch(1.1000, "haussiere", 30, 18, fb, 0.0001)
    assert mode == "sl"
    assert pnl == -18


def test_first_touch_both_conservative_sl():
    fb = [_bar(1.1040, 1.0975)]  # TP=30 et SL=18 tous deux dans le range
    pnl, mode = bt.simulate_first_touch(1.1000, "haussiere", 30, 18, fb, 0.0001)
    assert mode == "both_sl"
    assert pnl == -18


def test_first_touch_timeout_close_positive():
    fb = [_bar(1.1010, 1.0995, 1.1008)]  # ni TP ni SL, close +8
    pnl, mode = bt.simulate_first_touch(1.1000, "haussiere", 30, 18, fb, 0.0001)
    assert mode == "timeout_close"
    assert pnl == pytest.approx(8.0, abs=0.1)


def test_first_touch_short_tp():
    fb = [_bar(1.1005, 1.0965)]  # short : favorable = entry-low = 35
    pnl, mode = bt.simulate_first_touch(1.1000, "baissiere", 30, 18, fb, 0.0001)
    assert mode == "tp"
    assert pnl == 30


def test_first_touch_short_sl():
    fb = [_bar(1.1025, 1.0998)]  # short adverse = high-entry = 25 > sl 18
    pnl, mode = bt.simulate_first_touch(1.1000, "baissiere", 30, 18, fb, 0.0001)
    assert mode == "sl"


def test_first_touch_second_bar():
    fb = [_bar(1.1010, 1.0995), _bar(1.1035, 1.1005)]  # TP au 2e bar
    pnl, mode = bt.simulate_first_touch(1.1000, "haussiere", 30, 18, fb, 0.0001)
    assert mode == "tp"


def test_first_touch_empty_forward():
    pnl, mode = bt.simulate_first_touch(1.1000, "haussiere", 30, 18, [], 0.0001)
    assert mode == "timeout_close"
    assert pnl == 0.0


def test_first_touch_skips_bad_bar():
    fb = [{"high": None, "low": 1.0995}, _bar(1.1035, 1.1005)]
    pnl, mode = bt.simulate_first_touch(1.1000, "haussiere", 30, 18, fb, 0.0001)
    assert mode == "tp"


# ------------------------------------------------------------------ beta_shrunk_winrate

def test_shrink_empty_returns_global():
    assert bt.beta_shrunk_winrate(0, 0, 0.84) == 0.84


def test_shrink_pulls_toward_global():
    # 1 win sur 1 mais global 0.5 → lissé bien en dessous de 1.
    wr = bt.beta_shrunk_winrate(1, 1, 0.5)
    assert 0.5 < wr < 1.0


def test_shrink_large_n_approaches_empirical():
    wr = bt.beta_shrunk_winrate(900, 1000, 0.5)
    assert wr == pytest.approx(0.9, abs=0.02)


# ------------------------------------------------------------------ compute_metrics

def test_metrics_empty():
    m = bt.compute_metrics([])
    assert m.n_trades == 0
    assert m.total_pips == 0.0


def test_metrics_zeros_not_counted():
    m = bt.compute_metrics([0.0, 0.0, 10.0])
    assert m.n_trades == 1


def test_metrics_win_rate():
    m = bt.compute_metrics([10, 10, 10, -5])
    assert m.win_rate == pytest.approx(75.0, abs=0.1)


def test_metrics_profit_factor():
    m = bt.compute_metrics([20, -10])
    assert m.profit_factor == pytest.approx(2.0, abs=0.01)


def test_metrics_profit_factor_infinite_no_loss():
    m = bt.compute_metrics([10, 20])
    assert m.profit_factor == float("inf")


def test_metrics_total_pips():
    m = bt.compute_metrics([10, -3, 5])
    assert m.total_pips == pytest.approx(12.0, abs=0.01)


def test_metrics_max_drawdown_negative():
    m = bt.compute_metrics([10, -20, 5])  # équité 10 → -10 → -5, DD = -20
    assert m.max_drawdown <= -15


def test_metrics_max_drawdown_zero_when_monotonic():
    m = bt.compute_metrics([5, 5, 5])
    assert m.max_drawdown == 0.0


def test_metrics_sharpe_zero_when_constant():
    m = bt.compute_metrics([5, 5, 5])
    assert m.sharpe_like == 0.0


def test_metrics_avg_pips():
    m = bt.compute_metrics([10, 20])
    assert m.avg_pips == pytest.approx(15.0, abs=0.01)


# ------------------------------------------------------------------ walk-forward / verdict

def _m(wr, pips=100, pf=2.0):
    return bt.Metrics(n=10, n_trades=10, win_rate=wr, profit_factor=pf,
                      total_pips=pips, max_drawdown=-10, sharpe_like=1.0, avg_pips=10)


def test_wf_spread():
    assert bt.walk_forward_spread([_m(50), _m(95), _m(80)]) == pytest.approx(45.0, abs=0.1)


def test_wf_spread_ignores_empty_folds():
    empty = bt.Metrics(5, 0, 0, 0, 0, 0, 0, 0)
    assert bt.walk_forward_spread([_m(90), empty]) == 0.0


def test_verdict_no_go_on_instability():
    base = _m(80, pips=100)
    full = _m(99, pips=500)
    v = bt._verdict(base, full, wf_spread=45.0)
    assert v.startswith("NO-GO")
    assert "walk-forward" in v


def test_verdict_go_when_stable_and_uplift():
    base = _m(80, pips=100, pf=2.0)
    full = _m(85, pips=500, pf=3.0)
    v = bt._verdict(base, full, wf_spread=5.0)
    assert v.startswith("GO")


def test_verdict_marginal_partial_uplift():
    base = _m(80, pips=100, pf=5.0)
    full = _m(80, pips=500, pf=2.0)  # pips up, PF down
    v = bt._verdict(base, full, wf_spread=5.0)
    assert v.startswith("MARGINAL")


def test_verdict_no_go_no_uplift():
    base = _m(80, pips=500, pf=5.0)
    full = _m(80, pips=100, pf=2.0)
    v = bt._verdict(base, full, wf_spread=5.0)
    assert v.startswith("NO-GO")


def test_metrics_to_row_format():
    row = _m(85, pips=1000).to_row("Test")
    assert row.startswith("| Test |")
    assert "%" in row
