"""V10 Spread Guard — tests unitaires (Phase 11 Edge Fund).

Couvre les obligations Phase 11 :
  1. test_spread_clean_pair
  2. test_spread_upgraded_to_none_when_hard
  3. test_spread_downgrades_a1_to_a2_when_medium
  4. test_spread_rollover_guard_blocks
  5. test_spread_threshold_per_pair
  6. test_spread_ohlcv_proxy_basic
  7. test_spread_jpy_pip_detection
  8. test_spread_fail_open_no_data_returns_hard
  9. test_spread_audit_metadata_present
 10. test_spread_serialization_json
+ 6 bonus invariants.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from datetime import datetime, timezone, timedelta

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.v10.v10_spread_guard import (  # noqa: E402
    SpreadState,
    SpreadSource,
    DEFAULT_SPREAD_THRESHOLDS_PIPS,
    DEFAULT_DOWNGRADE_RATIO_MEDIUM,
    DEFAULT_DOWNGRADE_RATIO_HARD,
    ROLLOVER_GUARD_START,
    ROLLOVER_GUARD_END,
    check_spread,
    apply_spread_to_signal,
    _threshold_for,
    _spread_from_ohlcv_proxy,
    _detect_pip_size,
    _is_rollover,
    _downgrade_for,
)


# ─────────────────────────────────────────────────────────────────────
# 1. test_spread_clean_pair
# ─────────────────────────────────────────────────────────────────────
def test_spread_clean_pair():
    """spread=1.0 pips sur EURUSD (seuil 1.5) → ratio=0.67 → clean."""
    state = check_spread(
        "EURUSD",
        timestamp="2026-08-04T12:00:00Z",
        mt5_spread_pips=1.0,
    )
    assert state.is_clean is True
    assert state.ratio < DEFAULT_DOWNGRADE_RATIO_MEDIUM
    assert state.downgrade_level == "NONE"
    assert state.source == SpreadSource.MT5_LIVE


# ─────────────────────────────────────────────────────────────────────
# 2. test_spread_upgraded_to_none_when_hard
# ─────────────────────────────────────────────────────────────────────
def test_spread_upgraded_to_none_when_hard():
    """spread=4.0 sur EURUSD (seuil 1.5) → ratio=2.67 → NONE_HARD."""
    state = check_spread(
        "EURUSD",
        timestamp="2026-08-04T12:00:00Z",
        mt5_spread_pips=4.0,
    )
    assert state.downgrade_level == "NONE_HARD"
    assert state.ratio > DEFAULT_DOWNGRADE_RATIO_HARD
    new_lvl, downgraded, severity = apply_spread_to_signal("A1", state)
    assert new_lvl == "NONE"
    assert downgraded is True
    assert severity == "hard"


# ─────────────────────────────────────────────────────────────────────
# 3. test_spread_downgrades_a1_to_a2_when_medium
# ─────────────────────────────────────────────────────────────────────
def test_spread_downgrades_a1_to_a2_when_medium():
    """spread=2.5 sur EURUSD → ratio=1.67 → DOWNGRADE (medium)."""
    state = check_spread(
        "EURUSD",
        timestamp="2026-08-04T12:00:00Z",
        mt5_spread_pips=2.5,
    )
    assert state.downgrade_level == "DOWNGRADE"
    assert DEFAULT_DOWNGRADE_RATIO_MEDIUM < state.ratio <= DEFAULT_DOWNGRADE_RATIO_HARD
    new_lvl, downgraded, severity = apply_spread_to_signal("A1", state)
    assert new_lvl == "A2"
    assert downgraded is True
    assert severity == "medium"


def test_spread_downgrade_a2_to_a3_when_medium():
    state = check_spread(
        "EURUSD",
        timestamp="2026-08-04T12:00:00Z",
        mt5_spread_pips=2.5,
    )
    new_lvl, _, _ = apply_spread_to_signal("A2", state)
    assert new_lvl == "A3"


def test_spread_no_downgrade_when_clean():
    state = check_spread(
        "EURUSD",
        timestamp="2026-08-04T12:00:00Z",
        mt5_spread_pips=1.0,
    )
    new_lvl, downgraded, _ = apply_spread_to_signal("A1", state)
    assert new_lvl == "A1"
    assert downgraded is False


# ─────────────────────────────────────────────────────────────────────
# 4. test_spread_rollover_guard_blocks
# ─────────────────────────────────────────────────────────────────────
def test_spread_rollover_guard_blocks():
    """Pendant 23:50-00:10 UTC → guard_active=True → NONE_HARD."""
    state = check_spread(
        "EURUSD",
        timestamp="2026-08-04T23:55:00Z",
        mt5_spread_pips=0.5,  # spread petit mais guard doit primer
    )
    assert state.rollover_active is True
    assert state.guard_active is True
    assert state.downgrade_level == "NONE_HARD"


def test_spread_rollover_guard_end_window():
    state = check_spread(
        "EURUSD",
        timestamp="2026-08-04T00:08:00Z",
        mt5_spread_pips=0.5,
    )
    assert state.rollover_active is True


def test_spread_no_rollover_outside_window():
    state = check_spread(
        "EURUSD",
        timestamp="2026-08-04T12:00:00Z",
        mt5_spread_pips=0.5,
    )
    assert state.rollover_active is False


def test_spread_rollover_midnight_exact():
    """00:00 pile = in rollover."""
    state = check_spread(
        "EURUSD",
        timestamp="2026-08-04T00:00:00Z",
        mt5_spread_pips=0.5,
    )
    assert state.rollover_active is True


# ─────────────────────────────────────────────────────────────────────
# 5. test_spread_threshold_per_pair
# ─────────────────────────────────────────────────────────────────────
def test_spread_threshold_per_pair():
    """Vérifie que chaque paire a son seuil."""
    assert _threshold_for("EURUSD") == 1.5
    assert _threshold_for("USDJPY") == 1.5
    assert _threshold_for("USDCHF") == 1.5
    assert _threshold_for("GBPUSD") == 2.0
    assert _threshold_for("AUDUSD") == 2.0
    assert _threshold_for("NZDUSD") == 2.0
    assert _threshold_for("USDCAD") == 1.8
    assert _threshold_for("EURGBP") == 1.8
    assert _threshold_for("XAUUSD") == 3.5  # mineur → OTHER


def test_spread_custom_threshold_override():
    state = check_spread(
        "EURUSD",
        timestamp="2026-08-04T12:00:00Z",
        mt5_spread_pips=2.0,
        thresholds={"EURUSD": 1.0},  # override → seuil=1.0 → ratio=2.0
    )
    assert state.threshold_pips == 1.0
    # ratio = 2.0 → entre 1.5 et 2.5 → DOWNGRADE
    assert state.downgrade_level == "DOWNGRADE"


# ─────────────────────────────────────────────────────────────────────
# 6. test_spread_ohlcv_proxy_basic
# ─────────────────────────────────────────────────────────────────────
def test_spread_ohlcv_proxy_basic():
    """Barres OHLCV : 5 dernières, (high-low) moyen = proxy spread."""
    bars = [
        {"open": 1.100, "high": 1.1030, "low": 1.0995, "close": 1.1005},   # range 35 pips
        {"open": 1.100, "high": 1.1035, "low": 1.0995, "close": 1.1005},
        {"open": 1.100, "high": 1.1040, "low": 1.0995, "close": 1.1005},
        {"open": 1.100, "high": 1.1035, "low": 1.0995, "close": 1.1005},
        {"open": 1.100, "high": 1.1030, "low": 1.0995, "close": 1.1005},
    ]
    proxy = _spread_from_ohlcv_proxy(bars, lookback=5)
    # 4-decimal pip → 0.0001 → range 0.0035 ≈ 35 pips
    assert 30 < proxy < 40


def test_spread_ohlcv_proxy_no_bars():
    proxy = _spread_from_ohlcv_proxy([])
    assert proxy == 0.0


def test_spread_ohlcv_proxy_fallback():
    """Sans MT5 ni bars → fallback FAIL-OPEN ratio=2.0."""
    state = check_spread(
        "EURUSD",
        timestamp="2026-08-04T12:00:00Z",
    )
    assert state.source == SpreadSource.FALLBACK
    assert state.ratio == 2.0
    assert state.downgrade_level == "NONE_HARD"


# ─────────────────────────────────────────────────────────────────────
# 7. test_spread_jpy_pip_detection
# ─────────────────────────────────────────────────────────────────────
def test_spread_jpy_pip_detection():
    """USDJPY : 1 pip = 0.01 → range 0.0200 = 2 pips."""
    bars = [
        {"open": 150.00, "high": 150.0250, "low": 149.9970, "close": 150.0050},
        {"open": 150.00, "high": 150.0300, "low": 149.9970, "close": 150.0050},
        {"open": 150.00, "high": 150.0250, "low": 149.9970, "close": 150.0050},
    ]
    proxy = _spread_from_ohlcv_proxy(bars, lookback=3)
    # Range ~0.028 → ≈ 2.8 pips JPY
    assert 2.0 < proxy < 4.0


def test_spread_pip_size_eur_default():
    """Default pip pour non-JPY = 0.0001."""
    bars = [{"close": 1.10, "high": 1.10, "low": 1.10}]
    assert _detect_pip_size(bars) == 0.0001


def test_spread_pip_size_jpy_detection():
    """Si close > 50 → pip JPY = 0.01."""
    bars = [{"close": 150.0, "high": 150.0, "low": 150.0}]
    assert _detect_pip_size(bars) == 0.01


# ─────────────────────────────────────────────────────────────────────
# 8. test_spread_fail_open_no_data_returns_hard
# ─────────────────────────────────────────────────────────────────────
def test_spread_fail_open_no_data_returns_hard():
    """R6 fail-open : aucun spread → fallback conservateur → NONE_HARD."""
    state = check_spread(
        "EURUSD",
        timestamp="2026-08-04T12:00:00Z",
    )
    assert state.source == SpreadSource.FALLBACK
    assert state.guard_active is True
    assert state.downgrade_level == "NONE_HARD"
    assert state.audit.get("reason") == "no_spread_data"


# ─────────────────────────────────────────────────────────────────────
# 9. test_spread_audit_metadata_present
# ─────────────────────────────────────────────────────────────────────
def test_spread_audit_metadata_present():
    state = check_spread(
        "EURUSD",
        timestamp="2026-08-04T12:00:00Z",
        mt5_spread_pips=1.2,
        seed=42,
    )
    payload = state.as_dict()
    assert "ratio" in payload["audit"]
    assert "threshold" in payload["audit"]
    assert payload["audit"]["threshold"] == 1.5


# ─────────────────────────────────────────────────────────────────────
# 10. test_spread_serialization_json
# ─────────────────────────────────────────────────────────────────────
def test_spread_serialization_json():
    state = check_spread(
        "EURUSD",
        timestamp="2026-08-04T12:00:00Z",
        mt5_spread_pips=2.0,
    )
    j = json.dumps(state.as_dict())
    parsed = json.loads(j)
    assert parsed["symbol"] == "EURUSD"
    assert parsed["source"] == "mt5_live"
    assert parsed["current_spread_pips"] == 2.0


# ─────────────────────────────────────────────────────────────────────
# Bonus invariants
# ─────────────────────────────────────────────────────────────────────
def test_rollover_helper_23_59():
    assert _is_rollover("2026-08-04T23:59:30Z") is True


def test_rollover_helper_outside():
    assert _is_rollover("2026-08-04T12:00:00Z") is False


def test_rollover_helper_invalid_timestamp():
    """Timestamp bidon → fail-safe False."""
    assert _is_rollover("not-a-date") is False


def test_downgrade_levels():
    assert _downgrade_for(1.0) == "NONE"
    assert _downgrade_for(1.5) == "DOWNGRADE"
    assert _downgrade_for(2.0) == "DOWNGRADE"
    assert _downgrade_for(2.6) == "NONE_HARD"
    # Guard prioritaire
    assert _downgrade_for(1.0, guard_active=True) == "NONE_HARD"


def test_spread_state_class_init():
    s = SpreadState("EURUSD", "t")
    assert s.symbol == "EURUSD"
    assert s.ratio == 2.0  # défaut conservateur


def test_spread_r2_additif_no_import_core_v9():
    """R2 : pas d'import core/v9."""
    src = Path(ROOT / "core" / "v10" / "v10_spread_guard.py").read_text(encoding="utf-8")
    forbidden = []
    for line in src.splitlines():
        if "from core.v9" in line or "import core.v9" in line:
            forbidden.append(line)
    assert not forbidden


def test_spread_r10_no_order_transmission():
    src = Path(ROOT / "core" / "v10" / "v10_spread_guard.py").read_text(encoding="utf-8")
    forbidden = ("order_send", "positions_open", "trade_request",
                 "execute_order")
    for f in forbidden:
        assert f not in src, f"R10 violation : {f} dans v10_spread_guard.py"


def test_apply_spread_to_a3_with_hard():
    state = check_spread(
        "EURUSD",
        timestamp="2026-08-04T12:00:00Z",
        mt5_spread_pips=5.0,
    )
    new_lvl, downgraded, severity = apply_spread_to_signal("A3", state)
    assert new_lvl == "NONE"
    assert downgraded is True
    assert severity == "hard"
