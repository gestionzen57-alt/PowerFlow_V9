"""Tests Chantier 3 — v9_sizing_confidence (Kelly fractionnel continu).

Vérifie : formule de Kelly, bornes dures [0.3,2.0], no-trade (gated / edge≤0),
réduction par drawdown, fallback R6.
"""
from __future__ import annotations

import pytest

from core.v9 import v9_sizing_confidence as sz


# ------------------------------------------------------------------ kelly brut

def test_kelly_raw_positive_edge():
    # p=0.8, R=1 → 0.8 - 0.2/1 = 0.6.
    assert sz.kelly_fraction_raw(0.8, 1.0) == pytest.approx(0.6, abs=0.001)


def test_kelly_raw_negative_edge():
    # p=0.4, R=1 → 0.4 - 0.6 = -0.2.
    assert sz.kelly_fraction_raw(0.4, 1.0) == pytest.approx(-0.2, abs=0.001)


def test_kelly_raw_high_rr():
    # p=0.5, R=2 → 0.5 - 0.5/2 = 0.25.
    assert sz.kelly_fraction_raw(0.5, 2.0) == pytest.approx(0.25, abs=0.001)


def test_kelly_raw_zero_rr():
    assert sz.kelly_fraction_raw(0.8, 0.0) == 0.0


def test_kelly_raw_clamps_p():
    # p>1 clampé à 1 → 1 - 0 = 1.
    assert sz.kelly_fraction_raw(1.5, 1.0) == pytest.approx(1.0, abs=0.001)


def test_kelly_raw_bad_input():
    assert sz.kelly_fraction_raw("x", 1.0) == 0.0  # type: ignore[arg-type]


# ------------------------------------------------------------------ compute_size : bornes

def test_size_within_bounds():
    d = sz.compute_size(0.9, 20, 10)
    assert d.size == 0.0 or sz._SIZING_MIN <= d.size <= sz._SIZING_MAX


def test_size_returns_dataclass():
    d = sz.compute_size(0.8, 20, 10)
    assert isinstance(d, sz.SizingDecision)


def test_size_positive_edge_nonzero():
    d = sz.compute_size(0.9, 20, 10)
    assert d.size > 0


def test_size_negative_edge_no_trade():
    d = sz.compute_size(0.3, 10, 20)  # p faible, RR défavorable
    assert d.size == 0.0
    assert d.rationale == "negative_edge_no_trade"


def test_size_edge_exactly_zero_no_trade():
    # p tel que kelly = 0 : p=(1/(1+R))... p - (1-p)/R = 0 → p = 1/(1+R). R=1 → p=0.5.
    d = sz.compute_size(0.5, 10, 10)
    assert d.size == 0.0


def test_size_never_exceeds_max():
    d = sz.compute_size(0.99, 30, 8, kelly_fraction=5.0)  # K énorme
    assert d.size <= sz._SIZING_MAX


def test_size_floor_min_when_tiny_positive():
    # petit edge positif · petit K → sous le plancher → SIZING_MIN.
    d = sz.compute_size(0.55, 12, 10, kelly_fraction=0.01)
    assert d.size == sz._SIZING_MIN
    assert d.capped is True


# ------------------------------------------------------------------ gated / drawdown

def test_gated_forces_zero():
    d = sz.compute_size(0.95, 25, 8, gated=True)
    assert d.size == 0.0
    assert d.gated is True
    assert d.rationale == "gated_no_trade"


def test_gated_overrides_positive_edge():
    d = sz.compute_size(0.99, 30, 8, gated=True)
    assert d.size == 0.0


def test_drawdown_reduces_size():
    d0 = sz.compute_size(0.85, 20, 10, dd_ratio=0.0)
    d1 = sz.compute_size(0.85, 20, 10, dd_ratio=0.8)
    assert d1.size <= d0.size


def test_drawdown_full_reduces_to_floor_or_zero():
    d = sz.compute_size(0.85, 20, 10, dd_ratio=1.0)
    # (1-dd)=0 → target 0 → clamp remonte au plancher.
    assert d.size in (0.0, sz._SIZING_MIN)


def test_drawdown_clamped():
    d = sz.compute_size(0.85, 20, 10, dd_ratio=5.0)
    assert d.dd_ratio == 1.0


# ------------------------------------------------------------------ formule / champs

def test_edge_formula():
    d = sz.compute_size(0.7, 20, 10)
    assert d.edge == pytest.approx(0.7 * 20 - 0.3 * 10, abs=0.01)


def test_rr_ratio_recorded():
    d = sz.compute_size(0.8, 20, 10)
    assert d.rr_ratio == pytest.approx(2.0, abs=0.001)


def test_kelly_fraction_default_from_config():
    d = sz.compute_size(0.9, 20, 10)
    assert d.kelly_fraction == sz._KELLY_FRACTION


def test_kelly_fraction_override():
    d = sz.compute_size(0.9, 20, 10, kelly_fraction=0.5)
    assert d.kelly_fraction == 0.5


def test_raw_kelly_recorded():
    d = sz.compute_size(0.8, 10, 10)
    assert d.raw_kelly == pytest.approx(0.6, abs=0.01)


def test_to_dict_roundtrip():
    d = sz.compute_size(0.8, 20, 10)
    dd = d.to_dict()
    assert dd["size"] == d.size
    assert set(["size", "edge", "raw_kelly", "gated", "capped"]).issubset(dd.keys())


def test_higher_p_gives_higher_or_equal_size():
    lo = sz.compute_size(0.7, 20, 10)
    hi = sz.compute_size(0.95, 20, 10)
    assert hi.size >= lo.size


def test_higher_rr_gives_higher_or_equal_size():
    lo = sz.compute_size(0.7, 12, 10)
    hi = sz.compute_size(0.7, 25, 10)
    assert hi.size >= lo.size


# ------------------------------------------------------------------ fallback R6

def test_bad_tp_fallback():
    d = sz.compute_size(0.8, "bad", 10)  # type: ignore[arg-type]
    assert d.rationale == "fallback_bad_input"
    assert d.size == sz._SIZING_MIN


def test_bad_p_fallback():
    d = sz.compute_size("bad", 20, 10)  # type: ignore[arg-type]
    assert d.rationale == "fallback_bad_input"


def test_zero_sl_no_crash():
    d = sz.compute_size(0.8, 20, 0)
    assert isinstance(d, sz.SizingDecision)


def test_version_constant():
    assert sz.SIZING_CONFIDENCE_VERSION == "1.0"


def test_size_no_trade_constant():
    assert sz.SIZE_NO_TRADE == 0.0


def test_capped_false_when_interior():
    # taille strictement à l'intérieur → capped False.
    d = sz.compute_size(0.85, 20, 10, kelly_fraction=0.25)
    if sz._SIZING_MIN < d.size < sz._SIZING_MAX:
        assert d.capped is False
