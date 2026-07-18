"""Tests d'intégration — câblage PortfolioRiskManager dans TradeEngine (P0).

Vérifie que :
  - le kill switch env pilote l'appel du PRM (V9_PORTFOLIO_RISK_ENABLED)
  - le PRM est bien appelé dans process() après le gate risk_manager
  - le PRM peut BLOQUER un trade (result["action"]=="skip" + raison)
  - le PRM peut RÉDUIRE le sizing (corrélation → position_size * mult)
  - une erreur du PRM ne casse jamais le pipeline (R6) et reste additive (R2)

Le pattern de stubbing suit tests/test_trade_engine_dynamic_risk.py :
on injecte des faux arbiter / risk_manager / cascade / logger pour isoler
le bloc PRM de la DB réelle.
"""
from __future__ import annotations

import pytest

from core.v9.trade_engine import TradeEngine, _portfolio_risk_enabled


# ---------- Kill switch ----------


def test_portfolio_risk_enabled_default_on(monkeypatch):
    monkeypatch.delenv("V9_PORTFOLIO_RISK_ENABLED", raising=False)
    assert _portfolio_risk_enabled() is True


def test_portfolio_risk_disabled_by_env(monkeypatch):
    monkeypatch.setenv("V9_PORTFOLIO_RISK_ENABLED", "0")
    assert _portfolio_risk_enabled() is False


def test_portfolio_risk_enabled_explicit_on(monkeypatch):
    monkeypatch.setenv("V9_PORTFOLIO_RISK_ENABLED", "1")
    assert _portfolio_risk_enabled() is True


# ---------- Fixtures de stubbing ----------


class _ArbiterStub:
    def __init__(self, direction="haussiere"):
        self._direction = direction

    def consolidate(self, _sid):
        return {
            "direction": self._direction,
            "confiance_arbitree": 80,
            "confiance_arbitree_boosted": 80,
            "principes_source": [],
            "regime_type": "NEUTRE",
        }


class _RiskStub:
    capital = 10000.0  # comme PaperRiskManager.capital (lu par le bloc PRM)

    def __init__(self, risk_amount=100.0, position_size=1.0):
        self._risk_amount = risk_amount
        self._position_size = position_size

    def evaluate(self, _arb, _ctx, _open):
        return {
            "go": True,
            "raison_blocage": None,
            "risk_amount": self._risk_amount,
            "position_size": self._position_size,
        }


class _CascadesStub:
    def get_active_cascades(self):
        return []

    def get_cascade_for_snapshot(self, *_a, **_kw):
        return []

    def apply_cascade_confidence_boost(self, arb, _casc):
        return arb


class _LoggerStub:
    def log_open(self, *args, **kwargs):
        return "trade-test-stub"

    def log_close(self, *args, **kwargs):
        return None


def _make_engine(monkeypatch, arbiter=None, risk=None):
    """Construit un TradeEngine isolé de la DB (session=london stubbée)."""
    import core.v9.trade_engine as _te_mod
    monkeypatch.setattr(_te_mod, "infer_session_from_hour", lambda _h: "london")

    eng = TradeEngine(db_path=":memory:")
    eng._arbiter = arbiter or _ArbiterStub()
    eng._risk_mgr = risk or _RiskStub()
    eng._cascade = _CascadesStub()
    eng._logger = _LoggerStub()
    eng._get_open_trades = lambda: []
    eng._build_context = lambda _sid, _sess: {"symbol": "GBPUSD"}
    eng._resolve_symbol_and_decision = lambda _sid: ("GBPUSD", None)
    eng._fetch_signal_recommendation = lambda _sid: {
        "tp_pips_recommended": None,
        "sl_pips_recommended": None,
        "exit_strategy_recommended": "DYNAMIC",
    }
    eng._load_full_context = lambda _sid: None  # DRM fallback (pas d'apply)
    eng._attach_bear_perception_shadow = lambda *a, **k: None
    eng._trade_already_open = lambda *_a, **_kw: False
    # DRM inerte pour ne pas interférer avec le test PRM.
    monkeypatch.setenv("V9_DYNAMIC_RISK_ENABLED", "0")
    return eng


class _PRMBlockStub:
    """PRM qui refuse toujours (circuit breaker simulé)."""

    def evaluate_portfolio(self, _open, _new):
        return False, "circuit_breaker (5 pertes consécutives)", 0.0


class _PRMReduceStub:
    """PRM qui accepte mais réduit le sizing (corrélation)."""

    def evaluate_portfolio(self, _open, _new):
        return True, None, 0.5


class _PRMBoomStub:
    """PRM qui lève une exception (test R6)."""

    def evaluate_portfolio(self, _open, _new):
        raise RuntimeError("simulated PRM crash")


# ---------- Comportement ----------


def test_prm_is_called_and_recorded(monkeypatch):
    """Le PRM est appelé et son verdict est attaché à result."""
    monkeypatch.setenv("V9_PORTFOLIO_RISK_ENABLED", "1")
    eng = _make_engine(monkeypatch)

    called = {}

    class _PRMTrace:
        def evaluate_portfolio(self, open_trades, new_trade):
            called["new_trade"] = new_trade
            return True, None, 1.0

    eng._portfolio_risk = _PRMTrace()
    result = eng.process("v9-GBPUSD-M15-test")

    assert result["portfolio_risk"] is not None
    assert result["portfolio_risk"]["go"] is True
    # new_trade context bien construit depuis arbiter + risk + capital
    assert called["new_trade"]["symbol"] == "GBPUSD"
    assert called["new_trade"]["direction"] == "haussiere"
    assert called["new_trade"]["risk_amount"] == 100.0
    assert "capital" in called["new_trade"]


def test_prm_blocks_trade(monkeypatch):
    """Un refus PRM force action=skip avec la raison de blocage."""
    monkeypatch.setenv("V9_PORTFOLIO_RISK_ENABLED", "1")
    eng = _make_engine(monkeypatch)
    eng._portfolio_risk = _PRMBlockStub()

    result = eng.process("v9-GBPUSD-M15-test")

    assert result["action"] == "skip"
    assert result["raison_blocage"] == "circuit_breaker (5 pertes consécutives)"
    assert result["trade_id"] is None
    assert result["portfolio_risk"]["go"] is False


def test_prm_reduces_sizing(monkeypatch):
    """Un sizing_mult < 1.0 réduit position_size et est tracé."""
    monkeypatch.setenv("V9_PORTFOLIO_RISK_ENABLED", "1")
    risk = _RiskStub(position_size=2.0)
    eng = _make_engine(monkeypatch, risk=risk)
    eng._portfolio_risk = _PRMReduceStub()

    result = eng.process("v9-GBPUSD-M15-test")

    # Le trade passe (réduction, pas refus)
    assert result["action"] == "open"
    assert result["correlation_sizing_reduction"] == 0.5


def test_prm_disabled_by_killswitch(monkeypatch):
    """Kill switch OFF : le PRM n'est jamais appelé."""
    monkeypatch.setenv("V9_PORTFOLIO_RISK_ENABLED", "0")
    eng = _make_engine(monkeypatch)

    class _PRMShouldNotRun:
        def evaluate_portfolio(self, *_a, **_kw):
            raise AssertionError("PRM ne doit pas être appelé quand OFF")

    eng._portfolio_risk = _PRMShouldNotRun()
    result = eng.process("v9-GBPUSD-M15-test")

    assert result["portfolio_risk"] is None
    assert result["action"] == "open"


def test_prm_error_never_breaks_pipeline(monkeypatch):
    """R6 : une exception du PRM ne casse pas le pipeline (fail-open)."""
    monkeypatch.setenv("V9_PORTFOLIO_RISK_ENABLED", "1")
    eng = _make_engine(monkeypatch)
    eng._portfolio_risk = _PRMBoomStub()

    result = eng.process("v9-GBPUSD-M15-test")

    # Le trade continue son chemin (le PRM en erreur ne bloque pas — R6).
    assert result["error"] is None
    assert result["action"] == "open"
