"""V10 Edge Selector — tests unitaires (Sprint R).

Obligations :
  1. test_is_edge_yes
  2. test_is_edge_no_wr
  3. test_is_edge_no_entry
  4. test_is_edge_wrong_direction
  5. test_is_edge_min_trades
  6. test_apply_downgrade_no_edge
  7. test_apply_conserves_edge
  8. test_apply_none
  9. test_from_replay_batch_missing_r6
  10. test_r2_additif_no_core_v9
"""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.v10.v10_edge_selector import (  # noqa: E402
    EdgeSelector,
    DEFAULT_MIN_WR,
    DEFAULT_MIN_TRADES,
)

SAMPLE_MAP = {
    "EURUSD|M30": {"n": 177, "wr": 0.62, "direction": "SELL", "edge": "YES", "delta_pts": 12.2},
    "USDJPY|H4": {"n": 108, "wr": 0.57, "direction": "BUY", "edge": "YES", "delta_pts": 7.8},
    "GBPUSD|H1": {"n": 420, "wr": 0.48, "direction": "BUY", "edge": "NO", "delta_pts": -3.0},
    "USDCHF|H1": {"n": 90, "wr": 0.53, "direction": "BUY", "edge": "YES", "delta_pts": 0.5},
}


def _sel(**kw):
    return EdgeSelector(edge_map=dict(SAMPLE_MAP), **kw)


def test_is_edge_yes():
    sel = _sel()
    assert sel.is_edge("EURUSD", "M30", "SELL") is True


def test_is_edge_no_wr():
    sel = _sel()
    assert sel.is_edge("GBPUSD", "H1", "BUY") is False  # WR < 0.50


def test_is_edge_no_entry():
    sel = _sel()
    assert sel.is_edge("AUDUSD", "H1", "BUY") is False  # absent


def test_is_edge_wrong_direction():
    sel = _sel()
    # EURUSD M30 edge = SELL, demander BUY → pas d'edge
    assert sel.is_edge("EURUSD", "M30", "BUY") is False


def test_is_edge_min_trades():
    sel = _sel(min_trades=200)
    # EURUSD M30 = 177 trades < 200 → pas d'edge
    assert sel.is_edge("EURUSD", "M30", "SELL") is False


def test_is_edge_min_delta():
    sel = _sel()
    # USDCHF H1 : WR 53% ≥ 50% mais Δ=0.5p < 2.0p → bruit, pas d'edge
    assert sel.is_edge("USDCHF", "H1", "BUY") is False
    # EURUSD M30 : Δ=12.2p ≥ 2.0p → edge réel
    assert sel.is_edge("EURUSD", "M30", "SELL") is True


def test_apply_downgrade_no_edge():
    sel = _sel()
    lvl, down, reason = sel.apply("AUDUSD", "H1", "BUY", "A1")
    assert lvl == "A3"
    assert down is True
    assert reason == "no_edge"


def test_apply_conserves_edge():
    sel = _sel()
    lvl, down, reason = sel.apply("EURUSD", "M30", "SELL", "A1")
    assert lvl == "A1"
    assert down is False
    assert reason == "edge_ok"


def test_apply_none():
    sel = _sel()
    lvl, down, _ = sel.apply("EURUSD", "M30", "SELL", "NONE")
    assert lvl == "NONE"
    assert down is False


def test_from_replay_batch_missing_r6():
    sel = EdgeSelector.from_replay_batch("reports/inexistant.json")
    assert sel.edge_map == {}


def test_r2_additif_no_core_v9():
    src = (ROOT / "core/v10/v10_edge_selector.py").read_text(encoding="utf-8")
    assert "core.v9" not in src
    assert "from core.v9" not in src
    assert "import v9_" not in src
