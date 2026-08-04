"""Tests V10 — Modules Force / Structure / Contexte / Orchestrateur.

R7 : chaque feature testée unitairement sur données synthétiques contrôlées.
R9 : reproductible, seed déterministe, aucune dépendance au live.

Vérifie en particulier que l'orchestrateur produit des setups A1/A2/A3
quand les conditions sont réunies (pas de faux NONE), et NONE sinon.
"""
import sys
import os
import datetime as dt

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import pytest

from core.v10.v10_force import compute_force
from core.v10.v10_structure import compute_structure
from core.v10.v10_context import compute_context
from core.v10.v10_orchestrator import compose_signal


# ----------------------------------------------------------------------
# Helpers : générateurs de bougies synthétiques
# ----------------------------------------------------------------------
def make_bar(close, high=None, low=None, o=None, vol=100, spread=5):
    high = high if high is not None else close + 2
    low = low if low is not None else close - 2
    o = o if o is not None else close - 1
    return {"open": o, "high": high, "low": low, "close": close,
            "tick_volume": vol, "spread_points": spread, "timestamp": ""}


def rising_bars(n=60, start=1.0, step=0.05, vol=100):
    """Suite haussière régulière → UPTREND + pression acheteurs."""
    bars = []
    px = start
    for i in range(n):
        bars.append(make_bar(px, o=px - step * 0.5, high=px + step, low=px - step,
                             vol=vol, spread=5))
        px += step
    return bars


def ranging_bars(n=60, center=1.0, amp=0.02, vol=100, seed=42):
    """Range stationnaire autour du centre — pas de trend net, pression neutre."""
    import random
    rng = random.Random(seed)
    bars = []
    px = center
    for i in range(n):
        # marche aléatoire bornée qui revient vers le centre (moyenne mobile)
        px = center + 0.6 * (px - center) + rng.uniform(-amp, amp)
        bars.append(make_bar(px, o=px - 0.005, high=px + amp, low=px - amp,
                             vol=vol, spread=5))
    return bars


# ----------------------------------------------------------------------
# Force
# ----------------------------------------------------------------------
def test_force_rising_bars_bullish_pressure():
    bars = rising_bars()
    res = compute_force("GBPUSD", "2026-08-04T12:00:00Z", "M1", bars)
    assert res.f1_buy_pressure > 0.5, "pression acheteurs doit dominer sur uptrend"
    assert res.f2_atr > 0, "ATR doit être positif sur bars réelles"


def test_force_flat_bars_neutral_pressure():
    bars = ranging_bars()
    res = compute_force("GBPUSD", "2026-08-04T12:00:00Z", "M1", bars)
    # Un range court peut dériver légèrement ; borne large = pas de domination nette
    assert 0.2 < res.f1_buy_pressure < 0.8, "range = pas de domination extrême"


def test_force_empty_bars_fail_open():
    res = compute_force("EURUSD", "2026-08-04T12:00:00Z", "M1", [])
    assert res.force_level == "LOW"
    assert res.f2_atr == 0.0


def test_force_high_spread_illiquid():
    bars = rising_bars()
    bars[-1]["spread_points"] = 500  # spread énorme
    res = compute_force("GBPUSD", "2026-08-04T12:00:00Z", "M1", bars)
    assert res.illiquid is True, "spread/ATR trop élevé doit marquer illiquide"


# ----------------------------------------------------------------------
# Structure
# ----------------------------------------------------------------------
def test_structure_rising_bars_uptrend():
    bars = rising_bars()
    res = compute_structure("GBPUSD", "2026-08-04T12:00:00Z", "M1", bars)
    assert res.s7_market_structure == "UPTREND", "HH/HL doit donner UPTREND"
    assert res.s2_trend == "UPTREND"


def test_structure_ranging_bars_range():
    bars = ranging_bars()
    res = compute_structure("GBPUSD", "2026-08-04T12:00:00Z", "M1", bars)
    assert res.s7_market_structure == "RANGE"


def test_structure_pattern_detection():
    # Engulfing haussier : bougie 1 rouge, bougie 2 englobe complètement
    prev = make_bar(close=1.0000, o=1.0020, high=1.0025, low=0.9980)  # rouge
    cur = make_bar(close=1.0040, o=1.0010, high=1.0045, low=1.0005)    # englobe
    res = compute_structure("EURUSD", "2026-08-04T12:00:00Z", "M1",
                            [make_bar(1.0), make_bar(1.0), prev, cur])
    assert res.s3_pattern == "ENGULFING_BULL"


def test_structure_support_resistance():
    bars = rising_bars()
    res = compute_structure("GBPUSD", "2026-08-04T12:00:00Z", "M1", bars)
    assert res.s1_resistance > res.s1_support


# ----------------------------------------------------------------------
# Contexte
# ----------------------------------------------------------------------
def test_context_session_london():
    res = compute_context("EURUSD", "2026-08-04T10:00:00Z", "M5")
    assert res.c1_session == "LONDON"


def test_context_news_block():
    event = dt.datetime(2026, 8, 4, 10, 0, tzinfo=dt.timezone.utc)
    res = compute_context("EURUSD", "2026-08-04T10:10:00Z", "M5", news_events=[event])
    assert res.c2_news_state == "NO_TRADE_ZONE"
    assert res.tradeable is False
    assert "NEWS" in res.blockers


def test_context_no_news_fail_open_tradeable():
    res = compute_context("EURUSD", "2026-08-04T10:10:00Z", "M5", news_events=None)
    assert res.c2_news_state == "CLEAR"
    assert res.tradeable is True


def test_context_day_of_week():
    # 2026-08-04 est un mardi → isoweekday 2
    res = compute_context("EURUSD", "2026-08-04T10:00:00Z", "M5")
    assert res.c5_day_of_week == 2


# ----------------------------------------------------------------------
# Orchestrateur
# ----------------------------------------------------------------------
def test_orchestrator_rising_strong_uptrend_produces_tradeable():
    """Uptrend fort + volume élevé = un vrai setup (au moins A2/A3)."""
    bars = rising_bars(n=80, step=0.08, vol=500)
    sig = compose_signal("GBPUSD", bars[-1]["timestamp"], "M1", bars)
    assert sig.setup_level in ("A1", "A2", "A3"), f"uptrend fort doit donner un setup, got {sig.setup_level}"
    assert sig.tradeable is True


def test_orchestrator_news_blocks_even_good_structure():
    event = dt.datetime(2026, 8, 4, 12, 0, tzinfo=dt.timezone.utc)
    bars = rising_bars(n=80, step=0.08, vol=500)
    # timestamp proche de la news
    bars[-1]["timestamp"] = "2026-08-04T12:10:00Z"
    sig = compose_signal("GBPUSD", bars[-1]["timestamp"], "M1", bars, news_events=[event])
    assert sig.setup_level == "NONE", "news proche doit bloquer"
    assert sig.tradeable is False
    assert "NEWS" in sig.blockers


def test_orchestrator_range_weak_no_trade():
    bars = ranging_bars(n=80, amp=0.005, vol=50)
    sig = compose_signal("EURUSD", bars[-1]["timestamp"], "M1", bars)
    assert sig.tradeable is False, "range faible sans force ne doit pas trader"


def test_orchestrator_empty_bars_fail_open():
    sig = compose_signal("EURUSD", "2026-08-04T12:00:00Z", "M1", [])
    assert sig.setup_level == "NONE"
    assert sig.tradeable is False


def test_orchestrator_as_dict_serializable():
    bars = rising_bars(n=80, step=0.08, vol=500)
    sig = compose_signal("GBPUSD", bars[-1]["timestamp"], "M1", bars)
    d = sig.as_dict()
    assert d["setup_level"] in ("A1", "A2", "A3", "NONE")
    assert d["direction"] in ("BULLISH", "BEARISH")
    assert isinstance(d["reasoning"]["why"], str)


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
