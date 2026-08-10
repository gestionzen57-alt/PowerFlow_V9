"""tests/test_v10_replay_c21_validation.py — H-REPLAY-C21.

Vérifie les helpers de validation replay C21 (scripts.run_replay_c21_validation) :

  - _pre_wave_phase : COMPRESSION / DIVERGENCE / NEUTRAL depuis une série sigma
  - _compute_pf_pnl : WR / PF / PnL depuis des décisions résolues
  - _compute_pre_wave_breakdown : WR/PF/PnL par phase pre-wave
  - _auto_audit_p5 : seuils doctrinaux (WR<0.75, sharpe<2.5, n>=100)

R9 honnête | R10 compute only. ≥ 5 cas de test.
"""
from __future__ import annotations

import pytest

from scripts.run_replay_c21_validation import (
    _auto_audit_p5,
    _compute_pf_pnl,
    _compute_pre_wave_breakdown,
    _pre_wave_phase,
    _sigma_of_bar,
)

# ─────────────────────────────────────────────────────────────────────
# _pre_wave_phase
# ─────────────────────────────────────────────────────────────────────

def test_pre_wave_phase_compression():
    """Compression sigma (récent << historique) → COMPRESSION."""
    hist = [70.0, 65.0, 60.0, 40.0, 30.0, 20.0, 18.0, 16.0, 14.0, 12.0]
    assert _pre_wave_phase(hist) == "COMPRESSION"


def test_pre_wave_phase_neutral():
    """Sigma stable (sous seuil divergence) → NEUTRAL."""
    hist = [20.0] * 10
    assert _pre_wave_phase(hist) == "NEUTRAL"


def test_pre_wave_phase_short_history():
    """Historique trop court → NEUTRAL (R6 fail-open)."""
    assert _pre_wave_phase([50.0, 48.0]) == "NEUTRAL"
    assert _pre_wave_phase([]) == "NEUTRAL"


# ─────────────────────────────────────────────────────────────────────
# _sigma_of_bar
# ─────────────────────────────────────────────────────────────────────

def test_sigma_of_bar():
    """Sigma des 8 forces d'une barre (écart-type)."""
    bar = {
        "force_usd": 50.0, "force_gbp": 50.0, "force_eur": 50.0,
        "force_jpy": 50.0, "force_cad": 50.0, "force_chf": 50.0,
        "force_aud": 50.0, "force_nzd": 50.0,
    }
    assert _sigma_of_bar(bar) == 0.0
    bar2 = dict(bar)
    bar2["force_usd"] = 70.0
    bar2["force_gbp"] = 30.0
    assert _sigma_of_bar(bar2) > 0.0


# ─────────────────────────────────────────────────────────────────────
# _compute_pf_pnl
# ─────────────────────────────────────────────────────────────────────

def test_compute_pf_pnl():
    """3 trades (2 wins, 1 loss) → WR 0.667, PF = 20/10 = 2.0."""
    by_pair_tf = [{
        "pair": "EURUSD",
        "decisions": [
            {"action": "BUY", "pnl_pips": 10.0},
            {"action": "SELL", "pnl_pips": 10.0},
            {"action": "BUY", "pnl_pips": -10.0},
            {"action": "HOLD", "pnl_pips": 0.0},
        ],
    }]
    res = _compute_pf_pnl(by_pair_tf)
    assert res["n_trades"] == 3
    assert res["wins"] == 2
    assert res["wr"] == pytest.approx(2 / 3, abs=1e-4)
    assert res["pf"] == pytest.approx(2.0, abs=1e-4)
    assert res["pnl_total_pips"] == pytest.approx(10.0, abs=1e-4)


def test_compute_pf_pnl_empty():
    """Aucun trade → WR 0, PF 0, pas d'exception."""
    res = _compute_pf_pnl([{"pair": "EURUSD", "decisions": []}])
    assert res["n_trades"] == 0
    assert res["wr"] == 0.0
    assert res["pf"] == 0.0


# ─────────────────────────────────────────────────────────────────────
# _compute_pre_wave_breakdown
# ─────────────────────────────────────────────────────────────────────

def test_pre_wave_breakdown():
    """Trades répartis par phase pre-wave (via timestamp → phase)."""
    # 2 trades NEUTRAL (1 win, 1 loss), 1 trade COMPRESSION (win)
    by_pair_tf = [{
        "pair": "EURUSD",
        "bars": [
            {"timestamp": "t0", "force_usd": 50.0, "force_gbp": 50.0,
             "force_eur": 50.0, "force_jpy": 50.0, "force_cad": 50.0,
             "force_chf": 50.0, "force_aud": 50.0, "force_nzd": 50.0},
        ],
        "decisions": [
            {"action": "BUY", "timestamp": "t0", "pnl_pips": 10.0},
            {"action": "SELL", "timestamp": "t0", "pnl_pips": -5.0},
            {"action": "BUY", "timestamp": "t0", "pnl_pips": 8.0},
        ],
    }]
    res = _compute_pre_wave_breakdown(by_pair_tf)
    # Toutes les barres sont sigma=0 → NEUTRAL
    assert res["NEUTRAL"]["n_trades"] == 3
    assert res["NEUTRAL"]["wr"] == pytest.approx(2 / 3, abs=1e-4)
    assert res["COMPRESSION"]["n_trades"] == 0
    assert res["DIVERGENCE"]["n_trades"] == 0


# ─────────────────────────────────────────────────────────────────────
# _auto_audit_p5
# ─────────────────────────────────────────────────────────────────────

def test_auto_audit_p5():
    """Seuils doctrinaux : WR<0.75, sharpe<2.5, n>=100."""
    rep = {
        "global_wr": 0.60, "global_pnl": 100.0, "avg_sharpe": 1.5,
        "n_total_trades": 150, "pf": 1.8,
        "live_ready": False, "live_ready_reason": "not_evaluated",
    }
    audit = _auto_audit_p5(rep)
    assert audit["WR_ok"] is True
    assert audit["sharpe_ok"] is True
    assert audit["n_trades_ok"] is True
    assert audit["all_ok"] is True


def test_auto_audit_p5_fail():
    """WR trop haut (>0.75) → WR_ok False, all_ok False (anti-proxy)."""
    rep = {
        "global_wr": 0.90, "global_pnl": 100.0, "avg_sharpe": 1.5,
        "n_total_trades": 150, "pf": 3.0,
        "live_ready": False, "live_ready_reason": "not_evaluated",
    }
    audit = _auto_audit_p5(rep)
    assert audit["WR_ok"] is False
    assert audit["all_ok"] is False
