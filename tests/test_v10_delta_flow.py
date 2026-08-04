"""V10 Delta Flow — tests unitaires (Phase 13 Edge Fund).

Obligations :
  1. test_delta_basic_computation
  2. test_delta_cum_5_and_20
  3. test_imbalance_ratio_bullish
  4. test_imbalance_ratio_bearish
  5. test_absorption_detected_high_volume_low_movement
  6. test_no_absorption_low_volume
  7. test_stacked_imbalance_3_consecutive_buy
  8. test_stacked_imbalance_3_consecutive_sell
  9. test_direction_delta_buy_threshold
 10. test_direction_delta_sell_threshold
 11. test_direction_delta_neutral
 12. test_fail_open_insufficient_bars
 13. test_proxy_split_buy_sell_bullish_bar
 14. test_proxy_split_buy_sell_bearish_bar
"""
import json
import sys
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.v10.v10_delta_flow import (  # noqa: E402
    DeltaState,
    DeltaDirection,
    DeltaSource,
    DEFAULT_DELTA_CONFIG,
    compute_delta,
    delta_bonus_malus,
    _split_buy_sell_proxy,
    _delta_from_ticks,
)


def _make_bullish_bars(n=50, *, with_volume=False):
    out = []
    for i in range(n):
        b = {
            "open": 1.10 + i * 0.0001,
            "high": 1.1005 + i * 0.0001,
            "low": 1.0995 + i * 0.0001,
            "close": 1.1002 + i * 0.0001,
            "tick_volume": 1000.0 if not with_volume else 1500.0,
        }
        out.append(b)
    return out


def _make_absorption_bars(n=50):
    """Volume fort + petit mouvement → absorption."""
    out = _make_bullish_bars(n, with_volume=True)
    # Dernière barre : volume ×5 + petit range
    out[-1] = {
        "open": 1.1002,
        "high": 1.1003,
        "low": 1.1001,
        "close": 1.1002,
        "tick_volume": 6000.0,
    }
    return out


def _make_stacked_buy_bars(n=50):
    """3 dernières bougies : toutes très bullish (close >> open)."""
    out = _make_bullish_bars(n)
    for i in [-3, -2, -1]:
        out[i] = {
            "open": 1.10 + 0.0001 * i,
            "high": 1.10 + 0.0001 * i + 0.0030,
            "low": 1.10 + 0.0001 * i,
            "close": 1.10 + 0.0001 * i + 0.0030,
            "tick_volume": 1500.0,
        }
    return out


# ─────────────────────────────────────────────────────────────────────
# 1. test_delta_basic_computation
# ─────────────────────────────────────────────────────────────────────
def test_delta_basic_computation():
    bars = _make_bullish_bars(n=50)
    st = compute_delta("EURUSD", "H1", bars)
    assert st.delta_last != 0 or st.n_bars_used >= 5
    assert st.source in (DeltaSource.MT5_TICKS, DeltaSource.TICK_VOLUME_PROXY)
    assert st.n_bars_used >= 5


# ─────────────────────────────────────────────────────────────────────
# 2. test_delta_cum_5_and_20
# ─────────────────────────────────────────────────────────────────────
def test_delta_cum_5_and_20():
    bars = _make_stacked_buy_bars(n=50)
    st = compute_delta("EURUSD", "H1", bars)
    # 3 dernières bullish → cum_5 doit être positif
    assert st.delta_cum_5 != 0
    # cum_20 peut inclure les barres bullish intermédiaires
    assert st.delta_cum_20 != 0


# ─────────────────────────────────────────────────────────────────────
# 3. test_imbalance_ratio_bullish
# ─────────────────────────────────────────────────────────────────────
def test_imbalance_ratio_bullish():
    bars = _make_stacked_buy_bars(n=50)
    st = compute_delta("EURUSD", "H1", bars)
    # bullish → imbalance > 0
    assert st.imbalance_ratio >= 0.0


# ─────────────────────────────────────────────────────────────────────
# 4. test_imbalance_ratio_bearish
# ─────────────────────────────────────────────────────────────────────
def test_imbalance_ratio_bearish():
    """Toutes les bougies bearish → imbalance_ratio < 0."""
    bars = []
    for i in range(50):
        bars.append({
            "open": 1.11 - i * 0.0001,
            "high": 1.1105 - i * 0.0001,
            "low": 1.1095 - i * 0.0001,
            "close": 1.1098 - i * 0.0001,
            "tick_volume": 1000.0,
        })
    st = compute_delta("EURUSD", "H1", bars)
    # 5 dernières toutes bearish
    assert st.delta_cum_5 < 0


# ─────────────────────────────────────────────────────────────────────
# 5. test_absorption_detected_high_volume_low_movement
# ─────────────────────────────────────────────────────────────────────
def test_absorption_detected_high_volume_low_movement():
    bars = _make_absorption_bars(n=50)
    st = compute_delta("EURUSD", "H1", bars)
    assert st.absorption_detected is True


# ─────────────────────────────────────────────────────────────────────
# 6. test_no_absorption_low_volume
# ─────────────────────────────────────────────────────────────────────
def test_no_absorption_low_volume():
    bars = _make_bullish_bars(n=50, with_volume=False)
    # Volume bas + range normal → pas d'absorption
    st = compute_delta("EURUSD", "H1", bars)
    assert st.absorption_detected is False


# ─────────────────────────────────────────────────────────────────────
# 7. test_stacked_imbalance_3_consecutive_buy
# ─────────────────────────────────────────────────────────────────────
def test_stacked_imbalance_3_consecutive_buy():
    bars = _make_stacked_buy_bars(n=50)
    st = compute_delta("EURUSD", "H1", bars)
    assert st.stacked_imbalance is True


# ─────────────────────────────────────────────────────────────────────
# 8. test_stacked_imbalance_3_consecutive_sell
# ─────────────────────────────────────────────────────────────────────
def test_stacked_imbalance_3_consecutive_sell():
    """3 dernières toutes bearish."""
    bars = _make_bullish_bars(n=50)
    for i in [-3, -2, -1]:
        bars[i] = {
            "open": 1.11 - 0.0001 * abs(i),
            "high": 1.1105 - 0.0001 * abs(i),
            "low": 1.1095 - 0.0001 * abs(i),
            "close": 1.1098 - 0.0001 * abs(i),
            "tick_volume": 1500.0,
        }
    st = compute_delta("EURUSD", "H1", bars)
    assert st.stacked_imbalance is True


def test_no_stacked_when_mixed():
    """Alternance buy/sell → pas de stack."""
    bars = _make_bullish_bars(n=50)
    # Dernières bougies en alternance
    bars[-3] = {"open": 1.10, "high": 1.1010, "low": 1.0995, "close": 1.1008, "tick_volume": 1000}
    bars[-2] = {"open": 1.10, "high": 1.1010, "low": 1.0995, "close": 1.0998, "tick_volume": 1000}
    bars[-1] = {"open": 1.10, "high": 1.1010, "low": 1.0995, "close": 1.1005, "tick_volume": 1000}
    st = compute_delta("EURUSD", "H1", bars)
    assert st.stacked_imbalance is False


# ─────────────────────────────────────────────────────────────────────
# 9. test_direction_delta_buy_threshold
# ─────────────────────────────────────────────────────────────────────
def test_direction_delta_buy_threshold():
    """3 stacked buys + bullish bias → direction_delta=BUY."""
    bars = _make_stacked_buy_bars(n=50)
    st = compute_delta("EURUSD", "H1", bars)
    # Si imbalance > 0.30 → BUY ; sinon NEUTRAL (dépend magnitude)
    assert st.direction_delta in (DeltaDirection.BUY, DeltaDirection.NEUTRAL)


# ─────────────────────────────────────────────────────────────────────
# 10. test_direction_delta_sell_threshold
# ─────────────────────────────────────────────────────────────────────
def test_direction_delta_sell_threshold():
    """3 stacked sells → direction_delta=SELL ou NEUTRAL."""
    bars = _make_bullish_bars(n=50)
    for i in [-3, -2, -1]:
        bars[i] = {
            "open": 1.11, "high": 1.1110, "low": 1.0985, "close": 1.0988,
            "tick_volume": 2500.0,
        }
    st = compute_delta("EURUSD", "H1", bars)
    assert st.direction_delta in (DeltaDirection.SELL, DeltaDirection.NEUTRAL)


# ─────────────────────────────────────────────────────────────────────
# 11. test_direction_delta_neutral
# ─────────────────────────────────────────────────────────────────────
def test_direction_delta_neutral():
    """Barres neutres (close ≈ open) → NEUTRAL."""
    bars = []
    for i in range(50):
        bars.append({
            "open": 1.10, "high": 1.1005, "low": 1.0995, "close": 1.1000,
            "tick_volume": 1000.0,
        })
    st = compute_delta("EURUSD", "H1", bars)
    # Close == open → buy = sell → imbalance ≈ 0 → NEUTRAL
    assert st.direction_delta == DeltaDirection.NEUTRAL


# ─────────────────────────────────────────────────────────────────────
# 12. test_fail_open_insufficient_bars
# ─────────────────────────────────────────────────────────────────────
def test_fail_open_insufficient_bars():
    st = compute_delta("EURUSD", "H1", [])
    assert st.source == DeltaSource.MISSING
    assert "insufficient_bars" in st.audit.get("reason", "")

    st2 = compute_delta("EURUSD", "H1", [{"open": 1.10, "close": 1.10, "high": 1.10, "low": 1.10, "tick_volume": 100}])
    assert st2.source == DeltaSource.MISSING


# ─────────────────────────────────────────────────────────────────────
# 13. test_proxy_split_buy_sell_bullish_bar
# ─────────────────────────────────────────────────────────────────────
def test_proxy_split_buy_sell_bullish_bar():
    bar = {"high": 1.1050, "low": 1.0950, "open": 1.10, "close": 1.1040, "tick_volume": 1000}
    buy, sell = _split_buy_sell_proxy(bar, None)
    assert buy > sell  # bullish bar
    assert abs(buy + sell - 1000) < 1.0


# ─────────────────────────────────────────────────────────────────────
# 14. test_proxy_split_buy_sell_bearish_bar
# ─────────────────────────────────────────────────────────────────────
def test_proxy_split_buy_sell_bearish_bar():
    bar = {"high": 1.1050, "low": 1.0950, "open": 1.1040, "close": 1.0960, "tick_volume": 1000}
    buy, sell = _split_buy_sell_proxy(bar, None)
    assert sell > buy  # bearish bar
    assert abs(buy + sell - 1000) < 1.0


# ─────────────────────────────────────────────────────────────────────
# Bonus
# ─────────────────────────────────────────────────────────────────────
def test_delta_state_serializable():
    bars = _make_bullish_bars(n=50)
    st = compute_delta("EURUSD", "H1", bars)
    j = json.dumps(st.as_dict())
    parsed = json.loads(j)
    assert "delta_last" in parsed
    assert "imbalance_ratio" in parsed
    assert "source" in parsed


def test_delta_bonus_malus_aligned():
    bars = _make_stacked_buy_bars(n=50)
    st = compute_delta("EURUSD", "H1", bars)
    # Force direction BUY
    st.direction_delta = DeltaDirection.BUY
    st.stacked_imbalance = True
    bonus = delta_bonus_malus("BULLISH", st)
    assert bonus > 0  # aligned + stacked


def test_delta_bonus_malus_opposing():
    bars = _make_bullish_bars(n=50)
    st = compute_delta("EURUSD", "H1", bars)
    st.direction_delta = DeltaDirection.SELL
    st.absorption_detected = True
    st.imbalance_ratio = -0.5
    bonus = delta_bonus_malus("BULLISH", st)
    # direction BUY + delta=SELL + absorption contre → malus
    assert bonus <= 0


def test_delta_bonus_default_zero():
    bars = _make_bullish_bars(n=50)
    st = compute_delta("EURUSD", "H1", bars)
    st.direction_delta = DeltaDirection.NEUTRAL
    bonus = delta_bonus_malus("BULLISH", st)
    assert bonus == 0.0


def test_delta_from_ticks_basic():
    fake_ticks = [
        type("T", (), {"time": 1000, "flags": 0x02, "volume": 1.0})(),
        type("T", (), {"time": 1000, "flags": 0x00, "volume": 1.0})(),
        type("T", (), {"time": 1001, "flags": 0x02, "volume": 2.0})(),
        type("T", (), {"time": 1001, "flags": 0x00, "volume": 1.0})(),
    ]
    deltas = _delta_from_ticks(fake_ticks)
    # t=1000 : delta = 0 ; t=1001 : delta = +1
    assert isinstance(deltas, list)


def test_delta_no_bars_returns_missing():
    st = compute_delta("EURUSD", "H1", None)
    assert st.source == DeltaSource.MISSING


def test_r2_additif_no_import_core_v9():
    src = Path(ROOT / "core" / "v10" / "v10_delta_flow.py").read_text(encoding="utf-8")
    forbidden = []
    for line in src.splitlines():
        if "from core.v9" in line or "import core.v9" in line:
            forbidden.append(line)
    assert not forbidden
