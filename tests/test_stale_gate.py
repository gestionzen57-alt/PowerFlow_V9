"""Tests unitaires — core.v9.stale_gate.StaleGate."""

from __future__ import annotations

from core.v9.stale_gate import StaleGate


def test_freshness_ok_when_age_below_threshold():
    gate = StaleGate({"M5": 35_000})
    now_ms = 1_800_000_000_000
    timestamp_ms = now_ms - 10_000  # 10s < 35s

    result = gate.check_freshness(timestamp_ms, "M5", now_ms=now_ms)

    assert result["age_ms"] == 10_000
    assert result["stale"] is False
    assert result["stale_threshold_ms"] == 35_000


def test_stale_detected_when_age_above_threshold():
    gate = StaleGate({"M5": 35_000})
    now_ms = 1_800_000_000_000
    timestamp_ms = now_ms - 40_000  # 40s > 35s

    result = gate.check_freshness(timestamp_ms, "M5", now_ms=now_ms)

    assert result["stale"] is True
    assert result["age_ms"] == 40_000


def test_different_thresholds_per_timeframe():
    gate = StaleGate({"M1": 5_000, "D1": 9_000_000})
    now_ms = 1_800_000_000_000

    m1_result = gate.check_freshness(now_ms - 6_000, "M1", now_ms=now_ms)
    d1_result = gate.check_freshness(now_ms - 6_000, "D1", now_ms=now_ms)

    assert m1_result["stale"] is True   # 6s > 5s seuil M1
    assert d1_result["stale"] is False  # 6s << 9000s seuil D1
    assert m1_result["stale_threshold_ms"] == 5_000
    assert d1_result["stale_threshold_ms"] == 9_000_000


def test_stale_never_blocks_insertion():
    """STALE_GATE marque, ne supprime jamais (doctrine FREE-FIRST)."""
    gate = StaleGate({"H1": 365_000})
    now_ms = 1_800_000_000_000

    result = gate.check_freshness(now_ms - 1_000_000, "H1", now_ms=now_ms)

    assert result["stale"] is True
    # Le champ stale est un simple indicateur du dict retourné : rien dans
    # StaleGate ne lève d'exception ni ne renvoie None pour bloquer l'appelant.
    assert isinstance(result, dict)
    assert set(result.keys()) == {"age_ms", "stale", "stale_threshold_ms"}


def test_stale_stats_counts_per_timeframe():
    gate = StaleGate({"M5": 35_000, "H1": 365_000})
    now_ms = 1_800_000_000_000

    gate.check_freshness(now_ms - 10_000, "M5", now_ms=now_ms)   # fresh
    gate.check_freshness(now_ms - 40_000, "M5", now_ms=now_ms)   # stale
    gate.check_freshness(now_ms - 1_000, "H1", now_ms=now_ms)    # fresh

    stats = gate.stale_stats()

    assert stats["M5"] == {"stale": 1, "total": 2}
    assert stats["H1"] == {"stale": 0, "total": 1}


def test_unknown_timeframe_raises():
    gate = StaleGate({"M5": 35_000})
    try:
        gate.check_freshness(0, "M99")
        assert False, "devait lever ValueError"
    except ValueError:
        pass


def test_check_freshness_accepts_iso8601_timestamp():
    gate = StaleGate({"M5": 35_000})
    now_ms = 1_751_000_000_000
    from datetime import datetime, timezone

    iso = datetime.fromtimestamp((now_ms - 5_000) / 1000.0, tz=timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%S.%f"
    )[:-3] + "Z"

    result = gate.check_freshness(iso, "M5", now_ms=now_ms)

    assert result["stale"] is False
    assert abs(result["age_ms"] - 5_000) < 5
