"""V10 Decision Log — tests unitaires (Sprint 16 autopilote quant).

Obligations Sprint 16 :
  1. test_append_and_read
  2. test_summarize_empty
  3. test_summarize_trades
  4. test_summarize_wr_pnl
  5. test_r6_sqlite_fallback
  6. test_serialization_as_dict
  7. test_r2_additif_no_core_v9
"""
import json
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.v10.v10_decision_log import (  # noqa: E402
    DecisionRecord,
    DecisionLogger,
    summarize_decisions,
)


def _rec(pair, action, win, pnl, tf="H1"):
    return DecisionRecord(pair=pair, timeframe=tf, timestamp="2026-08-05T10:00:00Z",
                          action=action, signal_level="A2", filtered_level="A2",
                          lot_size=0.01, pnl_pips=pnl, is_win=win)


def test_append_and_read(tmp_path):
    db = tmp_path / "test_dec.db"
    logger = DecisionLogger(str(db))
    logger.append(_rec("EURUSD", "SELL", True, 10.0))
    logger.append(_rec("GBPUSD", "BUY", False, -5.0))
    recs = logger.all_records()
    assert len(recs) == 2
    assert recs[0].pair == "EURUSD"
    assert recs[0].is_win is True
    logger.close()


def test_summarize_empty():
    s = summarize_decisions([])
    assert s["n"] == 0


def test_summarize_trades():
    records = [
        _rec("EURUSD", "SELL", True, 10.0),
        _rec("GBPUSD", "BUY", True, 8.0),
        _rec("EURUSD", "SELL", False, -3.0),
    ]
    s = summarize_decisions(records)
    assert s["n_total"] == 3
    assert s["n_trades"] == 3
    assert s["wr"] == pytest.approx(round(2 / 3, 4))
    assert s["total_pnl"] == pytest.approx(15.0)
    assert "EURUSD|SELL" in s["by_pair_action"]


def test_summarize_wr_pnl():
    records = [_rec("AUDUSD", "SELL", True, 5.0),
               _rec("AUDUSD", "SELL", False, -5.0)]
    s = summarize_decisions(records)
    assert s["wr"] == pytest.approx(0.5)
    assert s["total_pnl"] == pytest.approx(0.0)
    assert s["sharpe_like"] == pytest.approx(0.0, abs=1e-6)


def test_r6_sqlite_fallback():
    # chemin invalide → fallback in-memory (R6)
    logger = DecisionLogger(db_path="")
    logger.append(_rec("EURUSD", "BUY", True, 3.0))
    recs = logger.all_records()
    assert len(recs) == 1
    assert recs[0].action == "BUY"
    logger.close()


def test_serialization_as_dict():
    rec = _rec("EURUSD", "SELL", True, 10.0)
    d = rec.as_dict()
    json.dumps(d)  # R9
    assert d["action"] == "SELL"
    assert d["pnl_pips"] == pytest.approx(10.0)


def test_r2_additif_no_core_v9():
    src = (ROOT / "core/v10/v10_decision_log.py").read_text(encoding="utf-8")
    assert "core.v9" not in src
    assert "from core.v9" not in src
    assert "import v9_" not in src
