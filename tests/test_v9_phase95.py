"""tests/test_v9_phase95.py — Phase 95 motion CEO 48H (Plan C).

Tests pour alternative_data_sentiment.
"""
import pytest


def test_clean_text_basic():
    from scripts.v9_alternative_data_sentiment import clean_text
    text = clean_text("GBPUSD rallies on strong NFP!")
    assert text == text.lower()


def test_clean_text_no_special_chars():
    from scripts.v9_alternative_data_sentiment import clean_text
    text = clean_text("Hello, World! 2026.")
    assert "," not in text
    assert "!" not in text
    assert "." not in text


def test_sentiment_score_positive():
    from scripts.v9_alternative_data_sentiment import (
        compute_sentiment_score,
    )
    # bullish = positif
    s = compute_sentiment_score(["GBPUSD rallies breakout strong bullish"])
    assert s > 0


def test_sentiment_score_negative():
    from scripts.v9_alternative_data_sentiment import (
        compute_sentiment_score,
    )
    s = compute_sentiment_score(["crash selloff bear weak panic"])
    assert s < 0


def test_sentiment_score_neutral():
    from scripts.v9_alternative_data_sentiment import (
        compute_sentiment_score,
    )
    s = compute_sentiment_score(["the and or but"])
    assert s == 0


def test_sentiment_score_bounded():
    from scripts.v9_alternative_data_sentiment import (
        compute_sentiment_score,
    )
    s = compute_sentiment_score(["rally breakout strong bullish"] * 100)
    assert -1.0 <= s <= 1.0


def test_label_sentiment_bullish():
    from scripts.v9_alternative_data_sentiment import label_sentiment
    assert label_sentiment(0.5) == "BULLISH"
    assert label_sentiment(0.3) == "BULLISH"


def test_label_sentiment_bearish():
    from scripts.v9_alternative_data_sentiment import label_sentiment
    assert label_sentiment(-0.5) == "BEARISH"
    assert label_sentiment(-0.3) == "BEARISH"


def test_label_sentiment_neutral():
    from scripts.v9_alternative_data_sentiment import label_sentiment
    assert label_sentiment(0.0) == "NEUTRAL"
    assert label_sentiment(0.1) == "NEUTRAL"
    assert label_sentiment(-0.1) == "NEUTRAL"


def test_aggregate_sources():
    from scripts.v9_alternative_data_sentiment import (
        aggregate_sources, compute_sentiment_score,
    )
    sources = {
        "twitter": compute_sentiment_score(["bullish breakout strong"]),
        "reddit": compute_sentiment_score(["bearish selloff weak"]),
        "news": compute_sentiment_score(["stable calm neutral"]),
    }
    agg = aggregate_sources(sources)
    assert "average" in agg
    assert "consensus" in agg
    assert -1.0 <= agg["average"] <= 1.0


def test_main_demo(capsys):
    from scripts.v9_alternative_data_sentiment import main
    exit_code = main([])
    captured = capsys.readouterr()
    assert exit_code == 0
    assert "ALTERNATIVE DATA" in captured.out


def test_sentiment_score_with_symbol():
    from scripts.v9_alternative_data_sentiment import (
        compute_sentiment_score,
    )
    # Mixed GBPUSD-specific
    s = compute_sentiment_score(
        ["GBPUSD bullish breakout", "EURUSD weak bearish",
         "USDJPY stable neutral"],
    )
    assert -1.0 <= s <= 1.0