"""V10 Risk Shield — tests unitaires (Sprint 10 autopilote quant).

Obligations Sprint 10 :
  1. test_allow_when_all_ok
  2. test_daily_dd_halt
  3. test_position_too_big
  4. test_net_exposure_blocks
  5. test_portfolio_blocks
  6. test_r6_none_gates_ignored
  7. test_serialization_as_dict
  8. test_r2_additif_no_core_v9
"""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.v10.v10_risk_shield import (  # noqa: E402
    RiskShieldDecision,
    evaluate_risk_shield,
)


class FakeExposureGate:
    def __init__(self, can_enter=True, reason=""):
        self.can_enter = can_enter
        self.blocked_reason = reason


def test_allow_when_all_ok():
    dec = evaluate_risk_shield(
        "EURUSD", "long",
        daily_dd_pct=1.0, candidate_risk_pct=1.5,
        exposure_gate_result=FakeExposureGate(can_enter=True),
        portfolio_can_enter=True,
    )
    assert dec.can_enter is True
    assert dec.blocked_reasons == []
    assert dec.gates["daily_dd"] is True
    assert dec.gates["position_size"] is True


def test_daily_dd_halt():
    dec = evaluate_risk_shield(
        "EURUSD", "long",
        daily_dd_pct=12.0, max_daily_dd_pct=10.0, candidate_risk_pct=1.0,
    )
    assert dec.can_enter is False
    assert any("DAILY_DD_HALT" in r for r in dec.blocked_reasons)


def test_position_too_big():
    dec = evaluate_risk_shield(
        "EURUSD", "long",
        candidate_risk_pct=3.0, max_position_pct=2.0,
    )
    assert dec.can_enter is False
    assert any("POSITION_TOO_BIG" in r for r in dec.blocked_reasons)


def test_net_exposure_blocks():
    dec = evaluate_risk_shield(
        "EURUSD", "short",
        exposure_gate_result=FakeExposureGate(
            can_enter=False, reason="DIRECTLY_OPPOSED EURUSD short"),
    )
    assert dec.can_enter is False
    assert any("DIRECTLY_OPPOSED" in r for r in dec.blocked_reasons)


def test_portfolio_blocks():
    dec = evaluate_risk_shield(
        "EURUSD", "long",
        portfolio_can_enter=False, portfolio_blocked_reason="TOO_MANY_CORRELATED",
    )
    assert dec.can_enter is False
    assert any("TOO_MANY_CORRELATED" in r for r in dec.blocked_reasons)


def test_r6_none_gates_ignored():
    dec = evaluate_risk_shield("EURUSD", "long", candidate_risk_pct=1.0)
    assert dec.can_enter is True
    assert dec.gates.get("net_exposure") is None  # pas évalué
    assert dec.audit["gates_evaluated"] == ["daily_dd", "position_size"]


def test_serialization_as_dict():
    dec = RiskShieldDecision(pair="EURUSD", direction="long",
                             can_enter=False, blocked_reasons=["X"])
    d = dec.as_dict()
    json.dumps(d)  # R9
    assert d["can_enter"] is False
    assert d["blocked_reasons"] == ["X"]


def test_r2_additif_no_core_v9():
    src = (ROOT / "core/v10/v10_risk_shield.py").read_text(encoding="utf-8")
    assert "core.v9" not in src
    assert "from core.v9" not in src
    assert "import v9_" not in src
