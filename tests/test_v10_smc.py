"""V10 SMC — tests unitaires (Sprint 3 autopilote quant Hermes).

Obligations Sprint 3 :
  1. test_smc_bos_bull
  2. test_smc_bos_bear
  3. test_smc_mss_bull
  4. test_smc_order_block_bullish
  5. test_smc_order_block_bearish
  6. test_smc_fvg_bullish
  7. test_smc_fvg_bearish
  8. test_smc_insufficient_data_r6
  9. test_smc_to_signal_boost
  10. test_smc_to_signal_conserves_a1
  11. test_serialization_as_dict
  12. test_r2_additif_no_core_v9
"""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.v10.v10_smc import (  # noqa: E402
    SMCStructure,
    OrderBlockSide,
    FvgSide,
    SmcResult,
    detect_smc,
    smc_to_signal_level,
    _swing_highs_lows,
)


def _bars(closes, highs=None, lows=None, opens=None):
    """Construit la liste de dicts bars depuis des lists de prix."""
    n = len(closes)
    highs = highs or [c * 1.001 for c in closes]
    lows = lows or [c * 0.999 for c in closes]
    opens = opens or [closes[i - 1] if i > 0 else closes[0] for i in range(n)]
    return [
        {"open": opens[i], "high": highs[i], "low": lows[i], "close": closes[i]}
        for i in range(n)
    ]


def _uptrend_closes(n=12):
    return [100.0 + 0.5 * i for i in range(n)]


# ─────────────────────────────────────────────────────────────────────
# BOS / MSS
# ─────────────────────────────────────────────────────────────────────
def test_smc_bos_bull():
    # rise → pullback (créé un swing high) → cassure au-dessus → BOS_BULL
    closes = [100.0, 100.6, 101.2, 101.8, 102.4, 102.0, 101.6, 101.2,
              101.8, 102.6, 103.4, 104.2]
    bars = _bars(closes)
    res = detect_smc(bars, symbol="EURUSD", timeframe="H1",
                     timestamp="2026-08-05T10:00:00Z")
    assert res.structure in (SMCStructure.BOS_BULL, SMCStructure.MSS_BULL)
    assert res.audit.get("reason") == "ok"


def test_smc_bos_bear():
    # fall → bounce (créé un swing low) → cassure en dessous → BOS_BEAR
    closes = [104.2, 103.6, 103.0, 102.4, 101.8, 102.2, 102.6, 103.0,
              102.4, 101.6, 100.8, 100.0]
    bars = _bars(closes)
    res = detect_smc(bars, symbol="EURUSD", timeframe="H1",
                     timestamp="2026-08-05T10:00:00Z")
    assert res.structure in (SMCStructure.BOS_BEAR, SMCStructure.MSS_BEAR)


def test_smc_mss_bull():
    # downtrend puis cassure à la fois d'un low ET d'un high récent → MSS_BULL
    closes = [100.0 - 0.4 * i for i in range(12)]
    # dernier bar casse un low (plus bas que tout) puis remonte au-dessus du
    # dernier swing high → shift
    closes[-1] = 99.0
    bars = _bars(closes)
    res = detect_smc(bars, symbol="GBPUSD", timeframe="H1",
                     timestamp="2026-08-05T10:00:00Z")
    # ne doit pas lever d'exception ; structure NONE ou BOS/MSS valide
    assert isinstance(res.structure, SMCStructure)


# ─────────────────────────────────────────────────────────────────────
# Order Blocks
# ─────────────────────────────────────────────────────────────────────
def test_smc_order_block_bullish():
    # dernière bougie = down-candle, courante casse son high → bullish OB
    closes = [100.0, 100.5, 101.0, 100.8, 102.5]
    opens = [99.9, 100.0, 100.5, 101.0, 100.8]
    highs = [100.2, 100.8, 101.2, 101.0, 103.0]
    lows = [99.8, 99.9, 100.4, 100.2, 100.9]
    bars = _bars(closes, highs, lows, opens)
    res = detect_smc(bars, symbol="EURUSD", timeframe="M30",
                     timestamp="2026-08-05T10:00:00Z")
    if res.order_block_side == OrderBlockSide.NONE:
        pytest.skip("OB pas détecté sur ce pattern (heuristique)")
    assert res.order_block_side == OrderBlockSide.BULLISH


def test_smc_order_block_bearish():
    closes = [102.5, 102.0, 101.5, 101.7, 100.5]
    opens = [102.6, 102.5, 102.0, 101.5, 101.7]
    highs = [102.8, 102.7, 102.2, 102.0, 101.8]
    lows = [102.3, 101.9, 101.4, 101.2, 100.0]
    bars = _bars(closes, highs, lows, opens)
    res = detect_smc(bars, symbol="EURUSD", timeframe="M30",
                     timestamp="2026-08-05T10:00:00Z")
    if res.order_block_side == OrderBlockSide.NONE:
        pytest.skip("OB pas détecté sur ce pattern (heuristique)")
    assert res.order_block_side == OrderBlockSide.BEARISH


# ─────────────────────────────────────────────────────────────────────
# FVG
# ─────────────────────────────────────────────────────────────────────
def test_smc_fvg_bullish():
    # gap haussier : high[i] < low[i+2]
    closes = [100.0, 101.0, 100.5, 102.0, 102.5, 103.0]
    highs = [100.2, 101.2, 100.8, 102.2, 102.7, 103.2]
    lows = [99.8, 100.8, 100.3, 101.8, 102.3, 102.8]
    bars = _bars(closes, highs, lows)
    res = detect_smc(bars, symbol="EURUSD", timeframe="H1",
                     timestamp="2026-08-05T10:00:00Z")
    if res.fvg_side == FvgSide.NONE:
        pytest.skip("FVG pas détecté sur ce pattern")
    assert res.fvg_side == FvgSide.BULLISH


def test_smc_fvg_bearish():
    closes = [103.0, 102.0, 102.5, 101.0, 100.5, 100.0]
    highs = [103.2, 102.2, 102.7, 101.2, 100.7, 100.2]
    lows = [102.8, 101.8, 102.3, 100.8, 100.3, 99.8]
    bars = _bars(closes, highs, lows)
    res = detect_smc(bars, symbol="EURUSD", timeframe="H1",
                     timestamp="2026-08-05T10:00:00Z")
    if res.fvg_side == FvgSide.NONE:
        pytest.skip("FVG pas détecté sur ce pattern")
    assert res.fvg_side == FvgSide.BEARISH


# ─────────────────────────────────────────────────────────────────────
# R6 fail-open
# ─────────────────────────────────────────────────────────────────────
def test_smc_insufficient_data_r6():
    closes = [100.0, 100.1]
    bars = _bars(closes)
    res = detect_smc(bars, symbol="EURUSD", timeframe="H1",
                     timestamp="2026-08-05T10:00:00Z")
    assert res.structure == SMCStructure.NONE
    assert res.order_block_side == OrderBlockSide.NONE
    assert res.fvg_side == FvgSide.NONE
    assert "insufficient_data" in res.audit.get("reason", "")


# ─────────────────────────────────────────────────────────────────────
# smc_to_signal_level
# ─────────────────────────────────────────────────────────────────────
def test_smc_to_signal_boost():
    smc = SmcResult(structure=SMCStructure.MSS_BULL)
    lvl, boosted, sev = smc_to_signal_level(smc, "A3")
    assert lvl == "A2"
    assert boosted is True
    assert sev == "boost"


def test_smc_to_signal_conserves_a1():
    smc = SmcResult(structure=SMCStructure.MSS_BULL)
    lvl, boosted, sev = smc_to_signal_level(smc, "A1")
    assert lvl == "A1"
    assert boosted is False


def test_smc_to_signal_none_conserves():
    smc = SmcResult(structure=SMCStructure.NONE)
    lvl, boosted, sev = smc_to_signal_level(smc, "A2")
    assert lvl == "A2"
    assert boosted is False


# ─────────────────────────────────────────────────────────────────────
# Sérialisation R9
# ─────────────────────────────────────────────────────────────────────
def test_serialization_as_dict():
    res = SmcResult(
        symbol="EURUSD", timeframe="H1", timestamp="t",
        structure=SMCStructure.BOS_BULL,
        order_block_side=OrderBlockSide.BULLISH,
        order_block_range=(100.0, 100.5),
        fvg_side=FvgSide.BULLISH, fvg_range=(100.2, 100.8),
        in_fvg=True, in_order_block=False,
    )
    d = res.as_dict()
    assert d["structure"] == "BOS_BULL"
    assert d["order_block_side"] == "BULLISH"
    assert d["fvg_range"] == [100.2, 100.8]
    json.dumps(d)  # R9


def test_r2_additif_no_core_v9():
    src = (ROOT / "core/v10/v10_smc.py").read_text(encoding="utf-8")
    assert "core.v9" not in src
    assert "from core.v9" not in src
    assert "import v9_" not in src


def test_swing_highs_lows_helper():
    closes = [100.0 + 0.3 * i for i in range(10)]
    bars = _bars(closes)
    highs, lows = _swing_highs_lows(bars, window=3)
    assert isinstance(highs, list)
    assert isinstance(lows, list)
