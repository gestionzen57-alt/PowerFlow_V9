"""Tests — v9_kelly_sizing (Axe 1.2 J2, 2026-07-21).

Couvre le câblage du multiplicateur Kelly bayésien-borné :
  - KellySizingEngine.compute_multiplier (posterior, garde-fous n / edge,
    floor / cap, quart-Kelly, fail-safe)
  - KellySizingEngine.is_enabled (kill switch défaut OFF)
  - apply_kelly_to_sizing (composition multiplicative, neutralité)
  - intégration TradeEngine (propriété kelly_sizing_report, hook OFF par défaut)

R7 strict : ≥15 tests. Les posteriors sont injectés via un calibrator stub
(fit_context déterministe) — `kelly_fraction` reste la math pure livrée en J1,
donc aucune DB n'est requise pour les tests unitaires du multiplicateur.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from core.v9 import kill_switches
from core.v9.bayesian_calibrator import BayesianCalibrator, BetaPosterior
from core.v9.v9_kelly_sizing import (
    KellySizingEngine,
    apply_kelly_to_sizing,
)

KELLY_ENV = "V9_KELLY_FRACTIONAL_ENABLED"


class _StubCalibrator(BayesianCalibrator):
    """Calibrator dont `fit_context` renvoie un posterior fixe (pas de DB).

    `kelly_fraction` reste l'implémentation math pure héritée (J1)."""

    def __init__(self, posterior: BetaPosterior) -> None:
        super().__init__(db_path="unused.db")
        self._stub = posterior

    def fit_context(self, context_key):  # type: ignore[override]
        return self._stub


def _engine(posterior: BetaPosterior) -> KellySizingEngine:
    return KellySizingEngine(_StubCalibrator(posterior), db_path="unused.db")


CTX = ("PRICE_LAG_AT_NODE_BIRTH", "GBPUSD", "M15", "asie", "NEUTRE")


# ── init / kill switch ───────────────────────────────────────────────
def test_kelly_engine_init():
    """Construction sans erreur avec un calibrator stub."""
    engine = _engine(BetaPosterior(80.0, 20.0, 98))
    assert isinstance(engine.calibrator, BayesianCalibrator)
    assert engine.db_path == Path("unused.db")


def test_kelly_engine_kill_switch_off(monkeypatch):
    """is_enabled() est False par défaut (R25' strict)."""
    monkeypatch.delenv(KELLY_ENV, raising=False)
    monkeypatch.setattr(kill_switches, "_load", lambda: {})
    assert _engine(BetaPosterior(2.0, 2.0, 2)).is_enabled() is False


def test_kelly_engine_kill_switch_on(monkeypatch):
    """is_enabled() est True quand le switch vaut '1' (env prioritaire)."""
    monkeypatch.setenv(KELLY_ENV, "1")
    assert _engine(BetaPosterior(2.0, 2.0, 2)).is_enabled() is True


# ── compute_multiplier : garde-fous neutres ──────────────────────────
def test_compute_multiplier_no_posterior():
    """Contexte inconnu → prior Beta(1,1), n=0 → neutre (mult=1.0, applied=False)."""
    out = _engine(BetaPosterior(1.0, 1.0, 0)).compute_multiplier(CTX)
    assert out["applied"] is False
    assert out["multiplier"] == 1.0
    assert out["reason"].startswith("n_below_min")
    assert out["posterior"]["n"] == 0


def test_compute_multiplier_n_too_low():
    """n=5 < MIN_N=20 → neutre (échantillon trop court)."""
    out = _engine(BetaPosterior(4.0, 2.0, 5)).compute_multiplier(CTX)
    assert out["applied"] is False
    assert out["multiplier"] == 1.0
    assert out["reason"].startswith("n_below_min")


def test_compute_multiplier_edge_unconfirmed():
    """P(WR>0.5) < 0.6 (Beta symétrique, n suffisant) → edge non confirmé, neutre."""
    out = _engine(BetaPosterior(25.0, 25.0, 48)).compute_multiplier(CTX)
    assert out["applied"] is False
    assert out["multiplier"] == 1.0
    assert out["reason"].startswith("edge_unconfirmed")
    assert out["posterior"]["prob_above_0_5"] < KellySizingEngine.MIN_PROB_ABOVE


def test_compute_multiplier_edge_clearly_negative():
    """Edge franchement négatif (mean<0.5, n suffisant) → edge non confirmé."""
    out = _engine(BetaPosterior(20.0, 30.0, 48)).compute_multiplier(CTX)
    assert out["applied"] is False
    assert out["multiplier"] == 1.0
    assert out["reason"].startswith("edge_unconfirmed")


# ── compute_multiplier : edge confirmé ───────────────────────────────
def test_compute_multiplier_edge_confirmed():
    """Beta(80,20) → edge confirmé, multiplicateur dans [floor, cap]."""
    out = _engine(BetaPosterior(80.0, 20.0, 98)).compute_multiplier(CTX)
    assert out["applied"] is True
    assert out["reason"] == "applied"
    assert KellySizingEngine.DEFAULT_FLOOR <= out["multiplier"] <= KellySizingEngine.DEFAULT_CAP
    assert out["kelly_full"] > 0.0


def test_compute_multiplier_floor_applied():
    """Edge confirmé mais faible (mean≈0.53, n élevé) → Kelly bas clampé au floor 0.3."""
    out = _engine(BetaPosterior(530.0, 470.0, 998)).compute_multiplier(CTX)
    assert out["applied"] is True
    assert out["multiplier"] == pytest.approx(KellySizingEngine.DEFAULT_FLOOR)


def test_compute_multiplier_cap_applied():
    """Beta(99,1) → Kelly extrême clampé au cap 2.0."""
    out = _engine(BetaPosterior(99.0, 1.0, 98)).compute_multiplier(CTX)
    assert out["applied"] is True
    assert out["multiplier"] == pytest.approx(KellySizingEngine.DEFAULT_CAP)


def test_compute_multiplier_quarter_kelly():
    """fraction=0.25 : Beta(70,30) → mult = f_full/0.25 = 1.6, dans le range."""
    out = _engine(BetaPosterior(70.0, 30.0, 98)).compute_multiplier(CTX)
    assert out["applied"] is True
    assert out["multiplier"] == pytest.approx(1.6, abs=1e-6)
    assert out["kelly_fractional"] == pytest.approx(out["kelly_full"] * 0.25, abs=1e-9)


def test_compute_multiplier_custom_fraction():
    """Une fraction plus permissive (0.5) déplace le multiplicateur (demi-Kelly)."""
    out = _engine(BetaPosterior(70.0, 30.0, 98)).compute_multiplier(CTX, fraction=0.5)
    # f_full = 0.4, mult = 0.4/0.5 = 0.8
    assert out["applied"] is True
    assert out["multiplier"] == pytest.approx(0.8, abs=1e-6)


def test_compute_multiplier_failsafe_on_error():
    """fit_context qui lève → neutre + reason=error (R6 fail-safe)."""
    engine = _engine(BetaPosterior(80.0, 20.0, 98))

    def _boom(_key):
        raise RuntimeError("db blew up")

    engine.calibrator.fit_context = _boom  # type: ignore[assignment]
    out = engine.compute_multiplier(CTX)
    assert out["applied"] is False
    assert out["multiplier"] == 1.0
    assert out["reason"].startswith("error")


# ── apply_kelly_to_sizing : composition ──────────────────────────────
def test_apply_kelly_to_sizing_neutral_when_disabled(monkeypatch):
    """Kill switch OFF → kelly_multiplier=1.0, final = base × dynamic."""
    monkeypatch.delenv(KELLY_ENV, raising=False)
    monkeypatch.setattr(kill_switches, "_load", lambda: {})
    engine = _engine(BetaPosterior(80.0, 20.0, 98))
    out = apply_kelly_to_sizing(10.0, engine, CTX, dynamic_risk_multiplier=1.5)
    assert out["kelly_multiplier"] == 1.0
    assert out["applied"] is False
    assert out["final_size"] == pytest.approx(15.0)


def test_apply_kelly_to_sizing_neutral_when_engine_none():
    """Aucun engine → neutre (final = base × dynamic)."""
    out = apply_kelly_to_sizing(10.0, None, CTX, dynamic_risk_multiplier=2.0)
    assert out["kelly_multiplier"] == 1.0
    assert out["applied"] is False
    assert out["final_size"] == pytest.approx(20.0)


def test_apply_kelly_to_sizing_composition(monkeypatch):
    """base × dynamic × kelly = composition multiplicative correcte."""
    monkeypatch.setenv(KELLY_ENV, "1")
    engine = _engine(BetaPosterior(70.0, 30.0, 98))  # mult attendu 1.6
    out = apply_kelly_to_sizing(10.0, engine, CTX, dynamic_risk_multiplier=1.2)
    assert out["applied"] is True
    assert out["kelly_multiplier"] == pytest.approx(1.6, abs=1e-6)
    assert out["final_size"] == pytest.approx(10.0 * 1.2 * 1.6, abs=1e-6)


def test_apply_kelly_to_sizing_floor_enforced(monkeypatch):
    """Edge faible → multiplicateur floorisé (0.3), jamais en-dessous."""
    monkeypatch.setenv(KELLY_ENV, "1")
    engine = _engine(BetaPosterior(530.0, 470.0, 998))
    out = apply_kelly_to_sizing(10.0, engine, CTX)
    assert out["applied"] is True
    assert out["kelly_multiplier"] == pytest.approx(0.3)
    assert out["final_size"] == pytest.approx(3.0)


def test_apply_kelly_to_sizing_cap_enforced(monkeypatch):
    """Edge extrême → multiplicateur capé (2.0), jamais au-dessus."""
    monkeypatch.setenv(KELLY_ENV, "1")
    engine = _engine(BetaPosterior(99.0, 1.0, 98))
    out = apply_kelly_to_sizing(10.0, engine, CTX, dynamic_risk_multiplier=1.0)
    assert out["applied"] is True
    assert out["kelly_multiplier"] == pytest.approx(2.0)
    assert out["final_size"] == pytest.approx(20.0)


# ── intégration TradeEngine ──────────────────────────────────────────
def test_trade_engine_kelly_property_when_disabled(monkeypatch):
    """kelly_sizing_report est None quand le kill switch est OFF (défaut)."""
    monkeypatch.delenv(KELLY_ENV, raising=False)
    monkeypatch.setattr(kill_switches, "_load", lambda: {})
    from core.v9.trade_engine import TradeEngine
    engine = TradeEngine(db_path="unused.db")
    engine._last_snapshot_id = "v9-GBPUSD-M15-xyz"
    assert engine.kelly_sizing_report is None


def test_trade_engine_kelly_property_none_without_snapshot(monkeypatch):
    """kelly_sizing_report est None si aucun snapshot n'a été traité (même ON)."""
    monkeypatch.setenv(KELLY_ENV, "1")
    from core.v9.trade_engine import TradeEngine
    engine = TradeEngine(db_path="unused.db")
    assert engine._last_snapshot_id is None
    assert engine.kelly_sizing_report is None
