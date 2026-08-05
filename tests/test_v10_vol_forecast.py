"""V10 Vol Forecast — tests unitaires (Sprint 4 autopilote quant).

Obligations Sprint 4 :
  1. test_ewma_vol_positive
  2. test_ewma_vol_zero_flat
  3. test_forecast_vol_insufficient_r6
  4. test_forecast_vol_ewma
  5. test_forecast_vol_garch (si arch dispo, sinon skip)
  6. test_sl_tp_from_vol
  7. test_sl_tp_zero_vol_r6
  8. test_serialization_as_dict
  9. test_r2_additif_no_core_v9
"""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.v10.v10_vol_forecast import (  # noqa: E402
    VolForecast,
    forecast_vol,
    sl_tp_from_vol,
    _ewma_vol,
    _log_returns,
)


def _volatile(n=80, vol=0.01):
    """Série avec volatilité soutenue."""
    import random
    rng = random.Random(3)
    out = [100.0]
    for _ in range(1, n):
        out.append(out[-1] * (1 + rng.gauss(0.0, vol)))
    return out


def test_ewma_vol_positive():
    closes = _volatile()
    r = _log_returns(closes)
    vol = _ewma_vol(r)
    assert vol > 0.0
    assert vol < 0.1


def test_ewma_vol_zero_flat():
    closes = [100.0] * 50
    r = _log_returns(closes)
    vol = _ewma_vol(r)
    assert vol == pytest.approx(0.0, abs=1e-9)


def test_forecast_vol_insufficient_r6():
    res = forecast_vol([100.0, 100.1], symbol="EURUSD",
                       timestamp="2026-08-05T10:00:00Z")
    assert res.forecast_vol == 0.0
    assert res.method == "ewma"
    assert "insufficient_data" in res.audit.get("reason", "")


def test_forecast_vol_ewma():
    closes = _volatile()
    res = forecast_vol(closes, symbol="EURUSD", method="ewma",
                       timestamp="2026-08-05T10:00:00Z")
    assert res.method == "ewma"
    assert res.forecast_vol > 0.0
    assert res.n_samples == len(closes) - 1
    assert res.last_price == pytest.approx(closes[-1])


def test_forecast_vol_garch():
    closes = _volatile(120)
    res = forecast_vol(closes, symbol="EURUSD", method="auto",
                       timestamp="2026-08-05T10:00:00Z")
    # méthode auto : GARCH ou EWMA (fallback R6)
    assert res.method in ("garch", "ewma")
    assert res.forecast_vol > 0.0


def test_sl_tp_from_vol():
    fv = VolForecast(forecast_vol=0.01, last_price=1.0)
    d = sl_tp_from_vol(fv, rr=2.0, sl_mult=1.0)
    assert d["valid"] is True
    assert d["sl"] == pytest.approx(0.01)
    assert d["tp"] == pytest.approx(0.02)


def test_sl_tp_zero_vol_r6():
    fv = VolForecast(forecast_vol=0.0)
    d = sl_tp_from_vol(fv)
    assert d["valid"] is False
    assert d["reason"] == "zero_vol"


def test_serialization_as_dict():
    fv = VolForecast(symbol="EURUSD", timestamp="t", forecast_vol=0.012,
                     forecast_vol_pct=0.012, method="garch", n_samples=79,
                     last_price=1.08)
    d = fv.as_dict()
    json.dumps(d)  # R9
    assert d["method"] == "garch"
    assert d["forecast_vol"] == pytest.approx(0.012)


def test_r2_additif_no_core_v9():
    src = (ROOT / "core/v10/v10_vol_forecast.py").read_text(encoding="utf-8")
    assert "core.v9" not in src
    assert "from core.v9" not in src
    assert "import v9_" not in src
