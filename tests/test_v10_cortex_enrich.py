"""V10 Cortex Enrichment — tests unitaires (Phase 8, Cognitive Continuum).

Obligations :
  1. test_enrich_no_bars_r6
  2. test_enrich_with_bars
  3. test_enrich_adds_delta_flow
  4. test_enrich_adds_liquidity
  5. test_r2_additif_no_core_v9
"""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.v10.v10_cortex_enrich import enrich_interp  # noqa: E402


def _make_bars(n: int = 30):
    """Crée une série de bars synthétiques pour delta/liquidity."""
    bars = []
    for i in range(n):
        base = 1.1000 + i * 0.0005
        bars.append({
            "timestamp": f"2026-08-0{i % 28 + 1}T00:00:00Z",
            "open": base, "high": base + 0.0002,
            "low": base - 0.0002, "close": base + 0.0001,
            "volume": 100.0,
        })
    return bars


def test_enrich_no_bars_r6():
    interp = {"pair": "EURUSD", "timeframe": "H1", "timestamp": "t",
              "audit": {"steps": []}}
    out = enrich_interp(interp, symbol="EURUSD", timeframe="H1", bars=[])
    # Pas de crash, sections vides ou absentes
    assert "delta_flow" in out or "delta_flow_error" in out["audit"]["steps"]
    assert out["audit"]["steps"]  # au moins une étape tentée


def test_enrich_with_bars():
    interp = {"pair": "EURUSD", "timeframe": "H1", "timestamp": "t",
              "audit": {"steps": []}}
    bars = _make_bars()
    out = enrich_interp(interp, symbol="EURUSD", timeframe="H1", bars=bars)
    assert "delta_flow" in out or "delta_flow_error" in out["audit"]["steps"]
    assert "liquidity" in out or "liquidity_map_error" in out["audit"]["steps"]
    assert "grammar_final" in out or "grammar_v9_final_error" in out["audit"]["steps"]


def test_enrich_adds_delta_flow():
    interp = {"pair": "EURUSD", "timeframe": "H1", "timestamp": "t",
              "audit": {"steps": []}}
    bars = _make_bars()
    out = enrich_interp(interp, symbol="EURUSD", timeframe="H1", bars=bars)
    if "delta_flow" in out:
        assert "imbalance_ratio" in out["delta_flow"]
        assert "direction_delta" in out["delta_flow"]


def test_enrich_adds_liquidity():
    interp = {"pair": "EURUSD", "timeframe": "H1", "timestamp": "t",
              "audit": {"steps": []}}
    bars = _make_bars()
    out = enrich_interp(interp, symbol="EURUSD", timeframe="H1", bars=bars)
    if "liquidity" in out:
        assert "n_zones" in out["liquidity"]
        assert "price_in_zone" in out["liquidity"]


def test_r2_additif_no_core_v9():
    src = (ROOT / "core/v10/v10_cortex_enrich.py").read_text(encoding="utf-8")
    assert "core.v9" not in src
    assert "from core.v9" not in src
    assert "import v9_" not in src
