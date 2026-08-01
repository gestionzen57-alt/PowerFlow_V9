"""tests/test_v9_phase75.py — Phase 75 motion CEO 48H (P2.1 audit Perplexity).

Tests pour circuit_breaker.
"""
import time
import pytest


def test_circuit_breaker_default():
    from scripts.v9_circuit_breaker import CircuitBreaker
    cb = CircuitBreaker()
    assert cb.max_errors == 10
    assert cb.pause_seconds == 300


def test_circuit_breaker_success_resets():
    from scripts.v9_circuit_breaker import CircuitBreaker
    cb = CircuitBreaker(max_errors=3, pause_seconds=0)
    cb.record_error("e1")
    cb.record_error("e2")
    assert cb._error_streak == 2
    cb.record_success()
    assert cb._error_streak == 0


def test_circuit_breaker_trips_at_max():
    from scripts.v9_circuit_breaker import CircuitBreaker
    cb = CircuitBreaker(max_errors=3, pause_seconds=0)
    assert cb.record_error("e1") is False
    assert cb.record_error("e2") is False
    assert cb.record_error("e3") is True  # trip


def test_circuit_breaker_trip_calls_on_trip():
    from scripts.v9_circuit_breaker import CircuitBreaker
    tripped = []

    def cb_alert(msg: str) -> None:
        tripped.append(msg)

    cb = CircuitBreaker(max_errors=2, pause_seconds=0, on_trip=cb_alert)
    cb.record_error("e1")
    cb.record_error("e2")
    assert len(tripped) == 1
    assert "2 erreurs consecutives" in tripped[0]


def test_circuit_breaker_status():
    from scripts.v9_circuit_breaker import CircuitBreaker
    cb = CircuitBreaker(max_errors=5, pause_seconds=0)
    cb.record_error("e1")
    cb.record_error("e2")
    s = cb.status()
    assert s["error_streak"] == 2
    assert s["total_errors"] == 2
    assert s["max_errors"] == 5
    assert s["last_error"] == "e2"


def test_circuit_breaker_on_trip_failure():
    """Si on_trip leve une exception, pas de crash (R6)."""
    from scripts.v9_circuit_breaker import CircuitBreaker

    def broken_alert(msg: str) -> None:
        raise RuntimeError("telegram API down")

    cb = CircuitBreaker(max_errors=2, pause_seconds=0, on_trip=broken_alert)
    cb.record_error("e1")
    # Ne doit pas lever malgré on_trip qui crash
    cb.record_error("e2")


def test_make_db_circuit_breaker():
    from scripts.v9_circuit_breaker import make_db_circuit_breaker
    cb = make_db_circuit_breaker()
    assert cb.max_errors == 10
    assert cb.pause_seconds == 300


def test_circuit_breaker_trip_resets_streak():
    """Apres trip, le streak doit etre reset (sinon re-trip immediat)."""
    from scripts.v9_circuit_breaker import CircuitBreaker
    cb = CircuitBreaker(max_errors=2, pause_seconds=0)
    cb.record_error("e1")
    cb.record_error("e2")  # trip, streak reset
    assert cb._error_streak == 0


def test_circuit_breaker_main_demo(capsys):
    from scripts.v9_circuit_breaker import main
    exit_code = main([])
    captured = capsys.readouterr()
    assert exit_code == 0
    assert "CIRCUIT BREAKER" in captured.out
    assert "[TRIP]" in captured.out


def test_circuit_breaker_pause_actually_pauses():
    """Test que pause_seconds est applique (utilise 0.05s pour test rapide)."""
    from scripts.v9_circuit_breaker import CircuitBreaker
    cb = CircuitBreaker(max_errors=1, pause_seconds=0.05)
    t0 = time.time()
    cb.record_error("e1")  # trip + pause
    elapsed = time.time() - t0
    assert elapsed >= 0.04  # marge 10ms