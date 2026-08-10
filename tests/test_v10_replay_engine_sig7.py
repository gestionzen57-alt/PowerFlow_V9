"""P0 — test import fail-open signal_7_pre_wave dans v10_replay_engine.

Vérifie :
  1. _FATMAN_OK=True (import signal_7_pre_wave réussi)
  2. get_fatman_signal absent de l'espace module (plus d'import cassé)
  3. _build_fatman_structure() : pré-vague détectée (compression sigma
     + gap) → fatman_signal BUY/SELL + strength > 0
  4. _build_fatman_structure() : pas de pré-vague → NEUTRAL fail-open
  5. R6 : données absentes → neutre, jamais d'exception
  6. R2 : aucun import core/v9 dans le fichier
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import core.v10.v10_replay_engine as re  # noqa: E402


def _bars(n: int = 40, close: float = 1.1000) -> list:
    """Barres synthétiques OHLCV (compat _build_fatman_structure)."""
    return [
        {
            "open": close, "high": close + 0.001, "low": close - 0.001,
            "close": close, "tick_volume": 100, "spread_points": 5,
            "timestamp": f"2026-08-10T00:{i:02d}:00Z",
        }
        for i in range(n)
    ]


def _compression_series() -> list:
    """Série sigma : compression nette en fin (récent << historique)."""
    return [70.0, 68.0, 72.0, 65.0, 69.0, 66.0, 64.0, 61.0, 58.0,
            55.0, 52.0, 48.0, 42.0, 38.0, 34.0, 30.0, 27.0, 24.0,
            21.0, 18.0, 16.0, 14.0]


def test_import_signal_7_fail_open_ok():
    """L'import signal_7_pre_wave doit réussir (plus de get_fatman_signal)."""
    assert re._FATMAN_OK is True
    assert re.signal_7_pre_wave is not None


def test_get_fatman_signal_absent():
    """L'ancien symbole cassé ne doit plus exister dans le module."""
    assert not hasattr(re, "get_fatman_signal")


def test_fatman_pre_wave_buy():
    """Pré-vague compression + base forte → BUY + strength > 0."""
    structure, fatman = re._build_fatman_structure(
        _bars(), "EURUSD", "M30",
        sigma_history=_compression_series(),
        fatman_scores={"EUR": 90.0, "USD": 30.0},  # base forte → LONG
    )
    assert fatman["ok"] is True
    assert fatman["signal"] == "BUY"
    assert fatman["strength"] > 0
    assert structure is not None
    assert structure["fatman_pattern"] == "PRE_WAVE"


def test_fatman_pre_wave_sell():
    """Pré-vague avec base faible → SELL anticipé."""
    structure, fatman = re._build_fatman_structure(
        _bars(), "EURUSD", "M30",
        sigma_history=_compression_series(),
        fatman_scores={"EUR": 30.0, "USD": 90.0},  # base faible → SHORT
    )
    assert fatman["ok"] is True
    assert fatman["signal"] == "SELL"
    assert fatman["strength"] > 0


def test_fatman_no_pre_wave_neutral():
    """Pas de pré-vague (sigma stable) → NEUTRAL fail-open."""
    structure, fatman = re._build_fatman_structure(
        _bars(), "EURUSD", "M30",
        sigma_history=[40.0] * 22,
        fatman_scores={"EUR": 50.0, "USD": 50.0},
    )
    assert fatman["ok"] is False
    assert fatman["signal"] == "NEUTRAL"
    assert structure is None


def test_fatman_data_absente_failopen():
    """R6 : barres courtes → neutre, jamais d'exception."""
    structure, fatman = re._build_fatman_structure(_bars(3), "EURUSD", "M30")
    assert fatman["ok"] is False
    assert fatman["signal"] == "NEUTRAL"
    assert structure is None


def test_r2_additif_no_core_v9():
    """R2 : v10_replay_engine n'importe aucun core/v9."""
    src = (ROOT / "core/v10/v10_replay_engine.py").read_text(encoding="utf-8")
    assert "core.v9" not in src
    assert "from core.v9" not in src
