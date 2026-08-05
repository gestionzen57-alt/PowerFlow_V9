"""V10 Net Exposure — tests unitaires (Sprint 9 autopilote quant).

Obligations Sprint 9 :
  1. test_net_exposure_long_eurusd
  2. test_net_exposure_netting
  3. test_find_directly_opposed
  4. test_find_directly_opposed_none
  5. test_exposure_gate_blocks_opposed
  6. test_exposure_gate_allows_opposed
  7. test_exposure_gate_blocks_net_base
  8. test_exposure_gate_unknown_pair_fail_open
  9. test_serialization_as_dict
  10. test_r2_additif_no_core_v9
"""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.v10.v10_net_exposure import (  # noqa: E402
    Position,
    NetExposureResult,
    ExposureGate,
    compute_net_exposure,
    find_directly_opposed,
    exposure_gate,
    MAJOR_PAIRS,
)


def _pos(pid, pair, direction, lot=1.0, status="OPEN"):
    return Position(position_id=pid, pair=pair, direction=direction,
                    lot_size=lot, status=status)


def test_net_exposure_long_eurusd():
    res = compute_net_exposure([_pos("p1", "EURUSD", "long", 2.0)])
    assert res.exposures["EUR"] == pytest.approx(2.0)
    assert res.exposures["USD"] == pytest.approx(-2.0)
    assert res.total_gross == pytest.approx(2.0)
    assert res.n_positions == 1


def test_net_exposure_netting():
    # long EURUSD 2 + short GBPUSD 1 → EUR +2, GBP -1, USD net -1
    res = compute_net_exposure([
        _pos("p1", "EURUSD", "long", 2.0),
        _pos("p2", "GBPUSD", "short", 1.0),
    ])
    assert res.exposures["EUR"] == pytest.approx(2.0)
    assert res.exposures["GBP"] == pytest.approx(-1.0)
    # USD : -2 (eurusd) + 1 (gbpusd short) = -1
    assert res.exposures["USD"] == pytest.approx(-1.0)


def test_find_directly_opposed():
    positions = [_pos("p1", "EURUSD", "long")]
    assert find_directly_opposed("EURUSD", "short", positions) is True


def test_find_directly_opposed_none():
    positions = [_pos("p1", "EURUSD", "long")]
    assert find_directly_opposed("EURUSD", "long", positions) is False
    assert find_directly_opposed("GBPUSD", "short", positions) is False


def test_exposure_gate_blocks_opposed():
    positions = [_pos("p1", "EURUSD", "long")]
    gate = exposure_gate("EURUSD", "short", positions)
    assert gate.can_enter is False
    assert "DIRECTLY_OPPOSED" in gate.blocked_reason


def test_exposure_gate_allows_opposed():
    positions = [_pos("p1", "EURUSD", "long")]
    gate = exposure_gate("EURUSD", "short", positions, allow_opposed=True)
    assert gate.can_enter is True


def test_exposure_gate_blocks_net_base():
    # beaucoup de longs EUR → net EUR dépasse la limite
    positions = [_pos(f"p{i}", "EURUSD", "long", 2.0) for i in range(3)]  # EUR +6
    gate = exposure_gate("EURUSD", "long", positions, max_net_by_ccy=5.0)
    assert gate.can_enter is False
    assert "NET_EXPOSURE" in gate.blocked_reason


def test_exposure_gate_unknown_pair_fail_open():
    positions = []
    gate = exposure_gate("EURTRY", "long", positions)
    assert gate.can_enter is True  # fail-open
    assert gate.audit.get("reason") == "unknown_pair_fail_open"


def test_serialization_as_dict():
    res = NetExposureResult(exposures={"EUR": 2.0, "USD": -2.0},
                            total_gross=2.0, n_positions=1)
    d = res.as_dict()
    json.dumps(d)  # R9
    assert d["exposures"]["EUR"] == pytest.approx(2.0)

    gate = ExposureGate(pair="EURUSD", direction="long",
                        blocked_reason="TEST")
    gd = gate.as_dict()
    json.dumps(gd)  # R9
    assert gd["pair"] == "EURUSD"


def test_r2_additif_no_core_v9():
    src = (ROOT / "core/v10/v10_net_exposure.py").read_text(encoding="utf-8")
    assert "core.v9" not in src
    assert "from core.v9" not in src
    assert "import v9_" not in src
    assert "v10_portfolio_manager" not in src
