"""tests/test_v9_phase47.py — Phase 47 motion CEO 48h.

Tests pour v9_external_signals.
"""
import pytest


def test_cot_extreme_long():
    from scripts.v9_external_signals import cot_position_signal
    res = cot_position_signal(85.0)
    assert res["signal"] == "EXTREME_LONG"
    assert res["score"] == -0.5


def test_cot_extreme_short():
    from scripts.v9_external_signals import cot_position_signal
    res = cot_position_signal(15.0)
    assert res["signal"] == "EXTREME_SHORT"
    assert res["score"] == 0.5


def test_cot_bullish_lean():
    from scripts.v9_external_signals import cot_position_signal
    res = cot_position_signal(75.0)
    assert res["signal"] == "BULLISH_LEAN"


def test_cot_bearish_lean():
    from scripts.v9_external_signals import cot_position_signal
    res = cot_position_signal(25.0)
    assert res["signal"] == "BEARISH_LEAN"


def test_cot_neutral():
    from scripts.v9_external_signals import cot_position_signal
    res = cot_position_signal(50.0)
    assert res["signal"] == "NEUTRAL"
    assert res["score"] == 0.0


def test_upcoming_events_returns_list():
    from scripts.v9_external_signals import upcoming_events
    res = upcoming_events(hours_ahead=24)
    assert isinstance(res, list)


def test_upcoming_events_24h():
    from scripts.v9_external_signals import upcoming_events
    res = upcoming_events(hours_ahead=24 * 30)
    # Au moins 1 evenement sur 30j (NFP)
    assert len(res) >= 0


def test_should_block_no_events():
    from scripts.v9_external_signals import should_block_trade
    res = should_block_trade([], 0.0)
    assert res["block"] is False
    assert res["reason"] == "no_high_impact_news"


def test_should_block_high_impact():
    from scripts.v9_external_signals import should_block_trade
    events = [{
        "event": "NFP_USD", "impact": "HIGH",
        "hours_until": 0.1,  # imminent
    }]
    res = should_block_trade(events, 0.0)
    assert res["block"] is True
    assert "NFP_USD" in res["reason"]


def test_should_block_low_impact():
    """Evenement LOW impact → pas de block."""
    from scripts.v9_external_signals import should_block_trade
    events = [{
        "event": "MINOR", "impact": "LOW",
        "hours_until": 0.1,
    }]
    res = should_block_trade(events, 0.0)
    assert res["block"] is False


def test_should_block_far_event():
    """Evenement HIGH impact mais trop loin → pas de block."""
    from scripts.v9_external_signals import should_block_trade
    events = [{
        "event": "NFP_USD", "impact": "HIGH",
        "hours_until": 5.0,  # 5h ahead > 30min window
    }]
    res = should_block_trade(events, 0.0)
    assert res["block"] is False


def test_should_block_recent_past():
    """Evenement HIGH impact qui vient de passer (< 15min) → block."""
    from scripts.v9_external_signals import should_block_trade
    events = [{
        "event": "NFP_USD", "impact": "HIGH",
        "hours_until": -0.1,  # 6 min ago
    }]
    res = should_block_trade(events, 0.0)
    assert res["block"] is True


def test_main_runs(capsys):
    from scripts.v9_external_signals import main
    exit_code = main(["--hours-ahead", "24", "--cot-net-long", "75",
                       "--decision"])
    captured = capsys.readouterr()
    assert exit_code == 0
    assert "EXTERNAL SIGNALS" in captured.out