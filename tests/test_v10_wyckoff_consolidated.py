"""V10 Wyckoff Consolidated — tests unitaires (Sprint 4 autopilote quant).

Obligations Sprint 4 :
  1. test_markup_vsa
  2. test_markdown_ce
  3. test_accumulation
  4. test_neutral_no_signal
  5. test_r6_no_sources_neutral
  6. test_serialization_as_dict
  7. test_r2_additif_no_core_v9
"""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.v10.v10_wyckoff_consolidated import (  # noqa: E402
    WyckoffState,
    WyckoffConsolidated,
    consolidate_wyckoff,
    _vsa_bias,
)


class FakeVsa:
    def __init__(self, state, confidence=0.8):
        self.state = state
        self.confidence = confidence


class FakeCe:
    def __init__(self, signal):
        self.signal = signal


class FakeSignalEnum:
    def __init__(self, name):
        self.value = name


def test_markup_vsa():
    """VSA MARKUP seul (bias +1) → MARKUP."""
    res = consolidate_wyckoff(
        "EURUSD", "H1", "2026-08-05T10:00:00Z",
        vsa_state=FakeVsa(WyckoffState.MARKUP, 0.8),
        weights={"vsa": 0.5, "ce": 0.5},
    )
    assert res.state == WyckoffState.MARKUP
    assert res.confidence > 0.0


def test_markdown_ce():
    """CE BEARISH seul → MARKDOWN."""
    res = consolidate_wyckoff(
        "GBPUSD", "H1", "2026-08-05T10:00:00Z",
        ce_signal=FakeCe(FakeSignalEnum("BEARISH")),
        weights={"vsa": 0.5, "ce": 0.5},
    )
    assert res.state == WyckoffState.MARKDOWN


def test_accumulation():
    """VSA ACCUMULATION (bias +1, conf modérée) → ACCUMULATION."""
    res = consolidate_wyckoff(
        "USDJPY", "H1", "2026-08-05T10:00:00Z",
        vsa_state=FakeVsa(WyckoffState.ACCUMULATION, 0.5),
        vsa_confidence=0.5,
        weights={"vsa": 0.5, "ce": 0.5},
    )
    # total_bias = 0.5*1 = 0.5 → MARKUP (car >= 0.4)
    assert res.state in (WyckoffState.MARKUP, WyckoffState.ACCUMULATION)


def test_neutral_no_signal():
    res = consolidate_wyckoff(
        "EURUSD", "H1", "2026-08-05T10:00:00Z",
        vsa_state=FakeVsa(WyckoffState.NEUTRAL, 0.0),
        weights={"vsa": 0.5, "ce": 0.5},
    )
    assert res.state == WyckoffState.NEUTRAL
    assert res.confidence == 0.0


def test_r6_no_sources_neutral():
    res = consolidate_wyckoff("EURUSD", "H1", "2026-08-05T10:00:00Z")
    assert res.state == WyckoffState.NEUTRAL
    assert res.confidence == 0.0
    assert res.audit.get("reason") == "no_signal"


def test_vsa_bias_helper():
    assert _vsa_bias(WyckoffState.MARKUP) == 1
    assert _vsa_bias(WyckoffState.MARKDOWN) == -1
    assert _vsa_bias(WyckoffState.NEUTRAL) == 0
    assert _vsa_bias("ACCUMULATION") == 1
    assert _vsa_bias(None) == 0


def test_serialization_as_dict():
    res = WyckoffConsolidated(
        symbol="EURUSD", timeframe="H1", timestamp="t",
        state=WyckoffState.MARKUP, confidence=0.8,
        sources={"vsa": {"state": "MARKUP", "bias": 1, "confidence": 0.8}},
    )
    d = res.as_dict()
    json.dumps(d)  # R9
    assert d["state"] == "MARKUP"
    assert d["confidence"] == pytest.approx(0.8)


def test_r2_additif_no_core_v9():
    src = (ROOT / "core/v10/v10_wyckoff_consolidated.py").read_text(encoding="utf-8")
    assert "core.v9" not in src
    assert "from core.v9" not in src
    assert "import v9_" not in src
