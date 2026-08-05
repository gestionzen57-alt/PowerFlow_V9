"""V10 ATR Manager — tests (HERMES_PLAN_V10 ÉTAPE 5).

Couvre :
  - true_range classique
  - ATR(14, H1)
  - SL = 1.5 × ATR / TP = 2.5 × ATR (cohérence plan)
  - RR = TP/SL = 5/3 = 1.67
  - Conversion ATR en pips (4 décimales vs JPY 2 décimales)
  - R6 fail-open (closes vides, period=0, etc.)
  - R8 surcharge ratios
  - R9 audit
  - Multi-paires

Total : 12 tests minimum. 0 import core/v9/ (R2 additif strict).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.v10.v10_atr_manager import (  # noqa: E402
    ATRResult,
    DEFAULT_ATR_PERIOD,
    DEFAULT_SL_MULT,
    DEFAULT_TP_MULT,
    VALID_TIMEFRAMES,
    atr_from_bars,
    check_against_plan,
    compute_sl_tp,
    compute_sl_tp_multi,
    true_range,
)


# ─────────────────────────────────────────────────────────────────────
# Builders
# ─────────────────────────────────────────────────────────────────────
def _bars(closes, atr_size=0.0010):
    """Bars OHLC avec close variable et range ~ATR."""
    out = []
    for c in closes:
        out.append({"high": c + atr_size / 2, "low": c - atr_size / 2,
                    "close": c, "open": c})
    return out


def _rising(n=30, step=0.0005, start=1.3000):
    return [start + i * step for i in range(n)]


# ─────────────────────────────────────────────────────────────────────
# true_range classique
# ─────────────────────────────────────────────────────────────────────
def test_true_range_classique():
    assert true_range(1.305, 1.295, 1.300) == pytest.approx(0.010, abs=1e-9)
    assert true_range(1.305, 1.300, 1.310) == pytest.approx(0.010, abs=1e-9)
    assert true_range(1.310, 1.290, 1.300) == pytest.approx(0.020, abs=1e-9)


def test_true_range_prev_close_zero():
    """Si prev_close = 0 → fallback H-L (R6)."""
    assert true_range(1.305, 1.295, 0.0) == pytest.approx(0.010, abs=1e-9)


# ─────────────────────────────────────────────────────────────────────
# ATR(14, H1) basique
# ─────────────────────────────────────────────────────────────────────
def test_atr_from_bars_minimum():
    """ATR sur 30 barres range constant (50 pips × 1 pip = 50 pips)."""
    bars = _bars(_rising(30), atr_size=0.0010)
    atr, n = atr_from_bars(bars, period=14)
    assert n == 14
    assert atr > 0


def test_atr_from_bars_closes_decroissants_atr_positive():
    """ATR > 0 même sur une tendance (range par bougie)."""
    bars = _bars(_rising(30, step=-0.001), atr_size=0.0005)
    atr, n = atr_from_bars(bars, period=14)
    assert atr > 0


def test_atr_from_bars_vide():
    atr, n = atr_from_bars([], period=14)
    assert atr == 0.0 and n == 0


def test_atr_from_bars_insuffisant():
    """2 barres : pas assez pour TR[0] (skip) → retourne 0."""
    bars = _bars(_rising(2), atr_size=0.001)
    atr, n = atr_from_bars(bars, period=14)
    assert atr == 0.0
    assert n == 0


# ─────────────────────────────────────────────────────────────────────
# compute_sl_tp (cœur ÉTAPE 5)
# ─────────────────────────────────────────────────────────────────────
def test_compute_sl_tp_eurusd_defaults():
    """EURUSD : plan § ÉTAPE 5 — SL=1.5×ATR, TP=2.5×ATR, RR=1.67."""
    bars = _bars(_rising(40), atr_size=0.0010)
    r = compute_sl_tp("EURUSD", bars)
    assert r.status == "LIVE"
    assert r.atr_price > 0
    assert r.atr_pips == pytest.approx(r.atr_price * 10000, abs=0.1)
    assert r.sl_pips == pytest.approx(r.atr_pips * 1.5, abs=0.05)
    assert r.tp_pips == pytest.approx(r.atr_pips * 2.5, abs=0.05)
    assert r.rr_ratio == pytest.approx(2.5 / 1.5, abs=0.01)


def test_compute_sl_tp_jpy_2_decimales():
    """Paire JPY : facteur pip = 100 (2 décimales)."""
    bars = _bars(_rising(30), atr_size=0.10)  # ATR size 0.10 sur USDJPY
    r = compute_sl_tp("USDJPY", bars)
    assert r.atr_pips == pytest.approx(r.atr_price * 100, abs=0.1)


def test_compute_sl_tp_multiplier_surcharge():
    """R8 : sl_mult et tp_mult surchargeables (sans toucher au module)."""
    bars = _bars(_rising(40), atr_size=0.0010)
    r = compute_sl_tp("EURUSD", bars, sl_mult=2.0, tp_mult=4.0)
    assert r.sl_mult == 2.0
    assert r.tp_mult == 4.0
    assert r.sl_pips == pytest.approx(r.atr_pips * 2.0, abs=0.05)
    assert r.tp_pips == pytest.approx(r.atr_pips * 4.0, abs=0.05)
    # Les constantes module n'ont pas bougé
    assert DEFAULT_SL_MULT == 1.5
    assert DEFAULT_TP_MULT == 2.5


def test_compute_sl_tp_insuffisant():
    r = compute_sl_tp("EURUSD", [])
    assert r.status == "INSUFFICIENT"
    assert r.sl_pips == 0.0


def test_compute_sl_tp_audit_serialisable():
    bars = _bars(_rising(40), atr_size=0.0010)
    r = compute_sl_tp("EURUSD", bars)
    json.dumps(r.as_dict())


# ─────────────────────────────────────────────────────────────────────
# Compute multi-paires
# ─────────────────────────────────────────────────────────────────────
def test_compute_sl_tp_multi():
    pairs = {
        "EURUSD": _bars(_rising(30), atr_size=0.0010),
        "GBPUSD": _bars(_rising(30), atr_size=0.0012),
        "USDJPY": _bars(_rising(30), atr_size=0.10),
    }
    out = compute_sl_tp_multi(pairs)
    assert set(out.keys()) == {"EURUSD", "GBPUSD", "USDJPY"}
    for pair, r in out.items():
        assert r.status in ("LIVE", "INSUFFICIENT")
        if r.status == "LIVE":
            assert r.sl_pips > 0
            assert r.tp_pips > 0


def test_compute_sl_tp_multi_paire_vide_ignoree():
    out = compute_sl_tp_multi({"EURUSD": [], "GBPUSD": _bars(_rising(30))})
    assert out["EURUSD"].status == "INSUFFICIENT"
    assert out["GBPUSD"].status == "LIVE"


# ─────────────────────────────────────────────────────────────────────
# Plan check
# ─────────────────────────────────────────────────────────────────────
def test_check_against_plan_conforme():
    bars = _bars(_rising(40))
    r = compute_sl_tp("EURUSD", bars)
    chk = check_against_plan(r)
    assert all(chk.values())


def test_check_against_plan_rr_faible_detectionnee():
    bars = _bars(_rising(40))
    r = compute_sl_tp("EURUSD", bars, sl_mult=5.0, tp_mult=3.0)
    chk = check_against_plan(r)
    # rr = 3/5 < 5/3 → rr_meets_min False, mais autres True
    assert chk["rr_meets_min"] is False
    assert chk["sl_mult_match"] is False
    assert chk["tp_mult_match"] is False


# ─────────────────────────────────────────────────────────────────────
# R9 audit
# ─────────────────────────────────────────────────────────────────────
def test_audit_n_bars_utilisees():
    bars = _bars(_rising(40))
    r = compute_sl_tp("EURUSD", bars, period=14)
    assert r.n_bars_used >= 1


def test_audit_status_live_ou_stale():
    bars = _bars(_rising(40))
    r = compute_sl_tp("EURUSD", bars, timestamp="2026-08-05T10:00:00Z")
    assert r.status in ("LIVE", "STALE")


def test_valid_timeframes_complet():
    assert "H1" in VALID_TIMEFRAMES
    assert "H4" in VALID_TIMEFRAMES
    assert "M30" in VALID_TIMEFRAMES
