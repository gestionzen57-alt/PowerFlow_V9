"""V10 RL Promotion Gate — tests (Phase 24+ CEO suite).

Cible R7 : 15 tests verts minimum.
"""
from __future__ import annotations

import json
import sqlite3
import tempfile
from pathlib import Path

import pytest

from core.v10.v10_rl_promotion import (
    GATE_MIN_WR_PCT,
    GATE_MIN_SHARPE,
    GATE_MAX_DD_PIPS,
    GATE_MIN_CONSISTENCY,
    RL_MODE_SHADOW,
    RL_MODE_ACTIVE,
    RL_MODE_KILL_SWITCH,
    PromotionGateCriteria,
    PromotionDecision,
    _check_wr_gate,
    _check_sharpe_gate,
    _check_dd_gate,
    _check_consistency_gate,
    decide_rl_promotion,
)
from core.v10.v10_paper_trader import PaperTraderReport, PaperTrade


# ─────────────────────────────────────────────────────────────────────
# CONSTANTS (3)
# ─────────────────────────────────────────────────────────────────────

def test_constants_gates_default():
    """Gates CEO defaults."""
    assert GATE_MIN_WR_PCT == 50.0
    assert GATE_MIN_SHARPE == 0.3
    assert GATE_MAX_DD_PIPS == 50.0
    assert GATE_MIN_CONSISTENCY == 0.75


def test_constants_rl_modes():
    """Modes RL définis."""
    assert RL_MODE_SHADOW == "SHADOW"
    assert RL_MODE_ACTIVE == "ACTIVE"
    assert RL_MODE_KILL_SWITCH == "KILL_SWITCH"


def test_constants_kill_switch_severity():
    """KILL_SWITCH ≠ ACTIVE ≠ SHADOW (3 modes distincts)."""
    assert len({RL_MODE_SHADOW, RL_MODE_ACTIVE, RL_MODE_KILL_SWITCH}) == 3


# ─────────────────────────────────────────────────────────────────────
# HELPERS GATE (4)
# ─────────────────────────────────────────────────────────────────────

def test_check_wr_gate_pass():
    """WR=50.1% ≥ 50% → PASS."""
    gate = PromotionGateCriteria()
    assert _check_wr_gate(50.1, gate) is True


def test_check_wr_gate_fail():
    """WR=49.9% < 50% → FAIL."""
    gate = PromotionGateCriteria()
    assert _check_wr_gate(49.9, gate) is False


def test_check_sharpe_gate_pass():
    """Sharpe=0.4 ≥ 0.3 → PASS."""
    gate = PromotionGateCriteria()
    assert _check_sharpe_gate(0.4, gate) is True


def test_check_dd_gate_pass():
    """max_dd=40p ≤ 50p → PASS."""
    gate = PromotionGateCriteria()
    assert _check_dd_gate(40.0, gate) is True


# ─────────────────────────────────────────────────────────────────────
# CONSISTENCY (3)
# ─────────────────────────────────────────────────────────────────────

def test_check_consistency_empty():
    """Empty per_pair_kpis → FAIL, ratio=0."""
    passed, ratio, n = _check_consistency_gate({}, PromotionGateCriteria())
    assert passed is False
    assert ratio == 0.0
    assert n == 0


def test_check_consistency_all_pass():
    """4/4 paires gate-passed → PASS."""
    per_pair_kpis = {
        "EURUSD": {"wr_pct": 60.0},
        "GBPUSD": {"wr_pct": 55.0},
        "USDCAD": {"wr_pct": 65.0},
        "USDCHF": {"wr_pct": 70.0},
    }
    passed, ratio, n = _check_consistency_gate(per_pair_kpis, PromotionGateCriteria())
    assert passed is True
    assert ratio == 1.0
    assert n == 4


def test_check_consistency_partial():
    """2/4 paires gate-passed → FAIL (50% < 75%)."""
    per_pair_kpis = {
        "EURUSD": {"wr_pct": 60.0},
        "GBPUSD": {"wr_pct": 55.0},
        "USDCAD": {"wr_pct": 40.0},
        "USDCHF": {"wr_pct": 35.0},
    }
    passed, ratio, n = _check_consistency_gate(per_pair_kpis, PromotionGateCriteria())
    assert passed is False
    assert ratio == 0.5
    assert n == 2


# ─────────────────────────────────────────────────────────────────────
# DECISION (5)
# ─────────────────────────────────────────────────────────────────────

def _make_paper_report(global_wr=60.0, global_sharpe=0.5, max_dd=20.0,
                        per_pair_wr=(60.0, 55.0, 65.0, 70.0)):
    """Helper: crée PaperTraderReport factice."""
    per_pair_kpis = {}
    for i, wr in enumerate(per_pair_wr):
        pair = ("EURUSD", "GBPUSD", "USDCAD", "USDCHF")[i]
        per_pair_kpis[pair] = {"wr_pct": wr, "pnl_pips_total": 0, "pnl_usd_total": 0,
                                "avg_pnl_pips": 0, "max_dd_pips": 0, "sharpe_ratio": 0.5,
                                "vsa_signal": "BULLISH", "baseline_wr_m30": 0.5}
    return PaperTraderReport(
        timestamp="2026-08-05T09:30:00Z",
        paper_only=True,
        micro_lot=0.01,
        per_pair_kpis=per_pair_kpis,
        global_kpis={
            "n_trades": 120, "wr_pct": global_wr,
            "pnl_pips_total": 100.0, "pnl_usd_total": 10.0,
            "avg_pnl_pips": 0.83, "max_dd_pips": max_dd,
            "sharpe_ratio": global_sharpe,
        },
    )


def test_decide_promotion_all_gates_pass():
    """WR=60%, Sharpe=0.5, max_dd=20p, consistency=100% → ACTIVE."""
    rep = _make_paper_report(global_wr=60.0, global_sharpe=0.5, max_dd=20.0)
    dec = decide_rl_promotion(rep, timestamp="2026-08-05T10:00:00Z")
    assert dec.promote_to_active is True
    assert dec.promote_mode == RL_MODE_ACTIVE
    assert dec.gate_results["wr_gate"] is True
    assert dec.gate_results["sharpe_gate"] is True
    assert dec.gate_results["dd_gate"] is True
    assert dec.gate_results["consistency_gate"] is True


def test_decide_promotion_sharpe_fail():
    """Sharpe négatif → SHADOW."""
    rep = _make_paper_report(global_wr=60.0, global_sharpe=-0.1, max_dd=20.0)
    dec = decide_rl_promotion(rep)
    assert dec.promote_to_active is False
    assert dec.promote_mode == RL_MODE_SHADOW
    assert dec.gate_results["sharpe_gate"] is False


def test_decide_promotion_dd_fail():
    """max_dd > 50p → SHADOW."""
    rep = _make_paper_report(global_wr=60.0, global_sharpe=0.5, max_dd=80.0)
    dec = decide_rl_promotion(rep)
    assert dec.promote_to_active is False
    assert dec.gate_results["dd_gate"] is False


def test_decide_promotion_kill_switch():
    """max_dd > 2x gate_max (100p) → KILL_SWITCH."""
    rep = _make_paper_report(global_wr=60.0, global_sharpe=0.5, max_dd=120.0)
    dec = decide_rl_promotion(rep)
    assert dec.promote_mode == RL_MODE_KILL_SWITCH
    assert dec.promote_to_active is False


def test_decide_promotion_consistency_fail():
    """Consistency < 75% → SHADOW."""
    rep = _make_paper_report(
        global_wr=60.0, global_sharpe=0.5, max_dd=20.0,
        per_pair_wr=(60.0, 30.0, 30.0, 30.0),  # 1/4 = 25%
    )
    dec = decide_rl_promotion(rep)
    assert dec.promote_to_active is False
    assert dec.gate_results["consistency_gate"] is False


# ─────────────────────────────────────────────────────────────────────
# DATACLASSES (2)
# ─────────────────────────────────────────────────────────────────────

def test_promotion_gate_criteria_default():
    """PromotionGateCriteria() défaut."""
    gate = PromotionGateCriteria()
    assert gate.min_wr_pct == 50.0
    assert gate.min_sharpe == 0.3


def test_promotion_decision_serializable():
    """PromotionDecision JSON-sérialisable (R9 audit)."""
    rep = _make_paper_report()
    dec = decide_rl_promotion(rep, timestamp="2026-08-05T10:00:00Z")
    j = json.dumps(dec.as_dict())
    assert "promote_to_active" in j
    assert "gate_results" in j
    assert "audit" in j