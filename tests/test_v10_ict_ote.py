"""V10 ICT OTE — tests unitaires (Sprint 3b autopilote quant Hermes).

Obligations Sprint 3b :
  1. test_kill_zone_asian_hour
  2. test_kill_zone_london_hour
  3. test_kill_zone_ny_hour
  4. test_kill_zone_outside_no_setup
  5. test_ote_in_zone_high_conviction_bullish
  6. test_ote_in_zone_high_conviction_bearish
  7. test_ote_out_of_zone_low_conviction
  8. test_ote_london_bonus_conviction
  9. test_ote_ny_max_conviction
  10. test_r6_failopen_no_data
  11. test_r6_failopen_flat_swing
  12. test_apply_ote_downgrade_a1_outside_killzone
  13. test_apply_ote_conserves_a1_in_ote_ny
  14. test_apply_ote_conserves_a2
  15. test_serialization_as_dict
  16. test_r2_additif (0 import core/v9)
"""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.v10.v10_ict_ote import (  # noqa: E402
    KillZone,
    OteBias,
    OteSetup,
    HIGH_CONVICTION_THRESHOLD,
    OTE_LOW,
    OTE_HIGH,
    compute_ict_ote,
    apply_ote_to_signal,
    _kill_zone_at_hour,
    _retracement_ratio,
)

# ─────────────────────────────────────────────────────────────────────
# Kill Zones
# ─────────────────────────────────────────────────────────────────────
def test_kill_zone_asian_hour():
    assert _kill_zone_at_hour(0) == KillZone.ASIAN
    assert _kill_zone_at_hour(7) == KillZone.ASIAN


def test_kill_zone_london_hour():
    assert _kill_zone_at_hour(8) == KillZone.LONDON
    assert _kill_zone_at_hour(12) == KillZone.LONDON


def test_kill_zone_ny_hour():
    assert _kill_zone_at_hour(13) == KillZone.NY
    assert _kill_zone_at_hour(16) == KillZone.NY


def test_kill_zone_outside_hour():
    assert _kill_zone_at_hour(17) == KillZone.OUTSIDE
    assert _kill_zone_at_hour(23) == KillZone.OUTSIDE


# ─────────────────────────────────────────────────────────────────────
# OTE zone & conviction
# ─────────────────────────────────────────────────────────────────────
def test_ote_in_zone_high_conviction_bullish():
    """Impulse up 1.00→1.10 puis retrace down à 1.075 (75% de la jambe)."""
    closes = [1.00, 1.02, 1.04, 1.06, 1.08, 1.075]
    highs = [1.005, 1.025, 1.045, 1.065, 1.10, 1.10]
    lows = [0.995, 1.015, 1.035, 1.055, 1.075, 1.070]
    ote = compute_ict_ote("EURUSD", "H1", closes,
                          highs=highs, lows=lows,
                          timestamp="2026-08-05T09:00:00Z")
    # swing_high=1.10, swing_low=0.995 → OTE=[1.0701, 1.08795] ; 1.075 in.
    # 09:00 = LONDON
    assert ote.kill_zone == KillZone.LONDON
    assert ote.in_ote is True
    assert ote.bias == OteBias.BULLISH  # tendance dominante UP
    # conviction = 0.60 (in_ote) + 0.15 (LONDON) = 0.75
    assert ote.conviction_score == pytest.approx(0.75)
    assert ote.high_conviction is True


def test_ote_in_zone_high_conviction_bearish():
    """Impulse down 1.10→1.05 puis retrace up à 1.081 (62% de la jambe)."""
    # swing_high=1.10, swing_low=1.05 → OTE=[1.081, 1.0895] ; price 1.081 in.
    closes = [1.100, 1.090, 1.080, 1.060, 1.050, 1.081]
    ote = compute_ict_ote("GBPUSD", "H1", closes,
                          timestamp="2026-08-05T09:00:00Z")
    assert ote.in_ote is True
    assert ote.bias == OteBias.BEARISH  # tendance dominante DOWN
    assert ote.high_conviction is True


def test_ote_out_of_zone_low_conviction():
    """Prix à 1.105 (ratio 1.05 > 1.0) → hors zone, conviction 0.0."""
    closes = [1.00, 1.02, 1.04, 1.06, 1.08, 1.105]
    ote = compute_ict_ote("EURUSD", "H1", closes,
                          timestamp="2026-08-05T09:00:00Z")
    assert ote.in_ote is False
    assert ote.conviction_score == 0.0
    assert ote.high_conviction is False


def test_ote_london_bonus_conviction():
    """in_ote + LONDON → conviction 0.75."""
    # swing_high=1.08, swing_low=1.00 → OTE=[1.0496, 1.0632] ; price 1.06 in.
    closes = [1.00, 1.02, 1.04, 1.06, 1.08, 1.06]
    ote = compute_ict_ote("USDJPY", "H1", closes,
                          timestamp="2026-08-05T09:00:00Z")
    assert ote.kill_zone == KillZone.LONDON
    assert ote.in_ote is True
    assert ote.conviction_score == pytest.approx(0.75)


def test_ote_ny_max_conviction():
    """in_ote + NY → conviction 1.0 (0.60 + 0.15 + 0.25)."""
    closes = [1.00, 1.02, 1.04, 1.06, 1.08, 1.06]
    ote = compute_ict_ote("EURUSD", "H1", closes,
                          timestamp="2026-08-05T14:00:00Z")
    assert ote.kill_zone == KillZone.NY
    assert ote.in_ote is True
    assert ote.conviction_score == pytest.approx(1.0)


def test_ote_bounds_configurable():
    """Bornes OTE custom étendent/rétrécissent la zone."""
    closes = [1.00, 1.02, 1.04, 1.06, 1.08, 1.08]
    ote = compute_ict_ote("EURUSD", "H1", closes,
                          ote_low=0.70, ote_high=0.90,
                          timestamp="2026-08-05T09:00:00Z")
    assert ote.ote_low == pytest.approx(1.00 + 0.70 * 0.08)
    assert ote.ote_high == pytest.approx(1.00 + 0.90 * 0.08)


# ─────────────────────────────────────────────────────────────────────
# R6 fail-open
# ─────────────────────────────────────────────────────────────────────
def test_r6_failopen_no_data():
    ote = compute_ict_ote("EURUSD", "H1", [], timestamp="2026-08-05T09:00:00Z")
    assert ote.kill_zone == KillZone.LONDON  # la zone est calculée quand même
    assert ote.in_ote is False
    assert ote.conviction_score == 0.0
    assert ote.high_conviction is False
    assert ote.audit.get("reason") == "no_data"


def test_r6_failopen_flat_swing():
    closes = [1.00, 1.00, 1.00, 1.00, 1.00, 1.00]
    ote = compute_ict_ote("EURUSD", "H1", closes, timestamp="2026-08-05T09:00:00Z")
    assert ote.in_ote is False
    assert ote.conviction_score == 0.0
    assert ote.audit.get("reason") == "flat_swing"


def test_r6_invalid_timestamp_defaults_now():
    ote = compute_ict_ote("EURUSD", "H1", [1.0, 1.02, 1.04],
                          timestamp="not-a-date")
    assert ote.timestamp != ""  # fallback now UTC
    assert ote.kill_zone in (KillZone.ASIAN, KillZone.LONDON, KillZone.NY,
                             KillZone.OUTSIDE)


# ─────────────────────────────────────────────────────────────────────
# apply_ote_to_signal
# ─────────────────────────────────────────────────────────────────────
def test_apply_ote_downgrade_a1_outside_killzone():
    ote = OteSetup(kill_zone=KillZone.OUTSIDE, in_ote=False,
                   conviction_score=0.0)
    lvl, down, sev = apply_ote_to_signal("A1", ote)
    assert lvl == "A2"
    assert down is True
    assert sev == "soft"


def test_apply_ote_conserves_a1_in_ote_ny():
    ote = OteSetup(kill_zone=KillZone.NY, in_ote=True,
                   conviction_score=1.0)
    lvl, down, sev = apply_ote_to_signal("A1", ote)
    assert lvl == "A1"
    assert down is False
    assert sev == "none"


def test_apply_ote_conserves_a2():
    ote = OteSetup(kill_zone=KillZone.OUTSIDE, in_ote=False,
                   conviction_score=0.0)
    lvl, down, _ = apply_ote_to_signal("A2", ote)
    assert lvl == "A2"
    assert down is False


def test_apply_ote_downgrade_a1_low_conviction():
    ote = OteSetup(kill_zone=KillZone.LONDON, in_ote=True,
                   conviction_score=0.5)
    lvl, down, _ = apply_ote_to_signal("A1", ote)
    assert lvl == "A2"
    assert down is True


# ─────────────────────────────────────────────────────────────────────
# Sérialisation R9
# ─────────────────────────────────────────────────────────────────────
def test_serialization_as_dict():
    closes = [1.00, 1.02, 1.04, 1.06, 1.08, 1.06]
    ote = compute_ict_ote("EURUSD", "H1", closes,
                          timestamp="2026-08-05T14:00:00Z")
    d = ote.as_dict()
    assert d["kill_zone"] == "NY"
    assert d["bias"] == "BULLISH"
    assert d["in_ote"] is True
    # JSON-sérialisable (R9)
    json.dumps(d)
    assert "seed" in d["audit"]
    assert "ote_bounds" in d["audit"]


def test_retracement_ratio_helper():
    assert _retracement_ratio(1.10, 1.00, 1.05) == pytest.approx(0.5)
    assert _retracement_ratio(1.10, 1.00, 1.00) == pytest.approx(0.0)
    assert _retracement_ratio(1.10, 1.00, 1.10) == pytest.approx(1.0)
    # flat swing → 0.0 (R6)
    assert _retracement_ratio(1.00, 1.00, 1.00) == pytest.approx(0.0)


# ─────────────────────────────────────────────────────────────────────
# R2 additif pur
# ─────────────────────────────────────────────────────────────────────
def test_r2_no_core_v9_import():
    """Le module ne doit importer aucun core/v9 (R2 strict)."""
    src = (ROOT / "core/v10/v10_ict_ote.py").read_text(encoding="utf-8")
    assert "core.v9" not in src
    assert "from core.v9" not in src
    assert "import v9_" not in src
