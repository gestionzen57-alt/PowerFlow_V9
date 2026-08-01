"""Tests unitaires pour les sous-methodes Phase 106-bis de TradeEngine.

Couvre :
- _compute_unified_sizing : 6 sous-couches (PRM, CVaR, Kelly, DD Protector,
  Risk Parity, Unified Sizing) - comportement delegation
- _finalize_decision : idempotence + log_open + transaction_costs

Ces tests sont des tests UNITAIRES isoles : ils n'appellent pas process()
dans son integralite, ils testent la sous-methode directement avec des
mocks leger de l'instance TradeEngine.
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

logging.getLogger("v9.trade_engine").setLevel(logging.WARNING)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _build_engine(tmp_path: Path, **overrides):
    """Construit un stub TradeEngine-like pour les tests unitaires.

    Bypasse l'init de TradeEngine (qui ouvre la DB) en utilisant object.__new__.
    """
    from core.v9 import trade_engine as te_mod

    eng = object.__new__(te_mod.TradeEngine)
    eng.db_path = overrides.get("db_path", tmp_path / "v9_forces.db")
    eng._resolve_symbol_and_decision = overrides.get(
        "resolve_symbol", lambda sid: ("GBPUSD", "haussiere")
    )
    eng._trade_already_open = overrides.get(
        "trade_already_open", lambda sid, d: False,
    )
    eng._current_context_key = overrides.get(
        "current_context_key", lambda sid: None,
    )
    # @property trade_logger/risk_manager/portfolio_risk_manager bloquent
    # l'assignation directe de l'attribut public. On injecte dans __dict__
    # les attributs PRIVES (_logger, _risk_mgr, _prm, _kelly) que les @property
    # vont lire. R6 fail-safe : on initialise aussi _kelly_engine (utilise par
    # _compute_unified_sizing via self.kelly_engine).
    trade_logger = overrides.get("trade_logger", MagicMock())
    trade_logger.log_open = MagicMock(return_value="TRADE-001")
    eng.__dict__["_logger"] = trade_logger
    risk_manager = MagicMock()
    risk_manager.capital = 10000
    eng.__dict__["_risk_mgr"] = risk_manager
    prm = MagicMock()
    prm.evaluate_portfolio = MagicMock(return_value=(True, None, 1.0))
    eng.__dict__["_portfolio_risk"] = prm
    eng.__dict__["_kelly_engine"] = MagicMock()
    return eng


# ---------------------------------------------------------------------------
# Tests _compute_unified_sizing
# ---------------------------------------------------------------------------

def test_unified_sizing_disabled_prm(monkeypatch, tmp_path):
    """PRM OFF → portfolio_risk reste None, pas de skip."""
    eng = _build_engine(tmp_path)
    monkeypatch.setattr(
        "core.v9.trade_engine._portfolio_risk_enabled", lambda: False,
    )
    risk_result = {"position_size": 1.0}
    result = {"action": "go"}
    decision = eng._compute_unified_sizing(
        "SNAP-001",
        {"direction": "haussiere"},
        risk_result,
        result,
        open_trades=[],
        context={"symbol": "GBPUSD"},
    )
    assert decision["early_action"] is None
    assert result["portfolio_risk"] is None


def test_unified_sizing_prm_block(monkeypatch, tmp_path):
    """PRM ON + go=False → early_action=skip + raison remonte."""
    eng = _build_engine(tmp_path)
    monkeypatch.setattr(
        "core.v9.trade_engine._portfolio_risk_enabled", lambda: True,
    )
    eng.portfolio_risk_manager.evaluate_portfolio = MagicMock(
        return_value=(False, "PRM_CIRCUIT_BREAKER", 1.0)
    )
    risk_result = {"position_size": 1.0}
    result = {"action": "go"}
    decision = eng._compute_unified_sizing(
        "SNAP-001",
        {"direction": "haussiere"},
        risk_result,
        result,
        open_trades=[],
        context={"symbol": "GBPUSD"},
    )
    assert decision["early_action"] == "skip"
    assert decision["raison"] == "PRM_CIRCUIT_BREAKER"
    assert result["portfolio_risk"]["go"] is False
    assert result["action"] == "skip"
    assert result["raison_blocage"] == "PRM_CIRCUIT_BREAKER"


def test_unified_sizing_prm_sizing_reduction(monkeypatch, tmp_path):
    """PRM ON + go=True + sizing_mult<1 → position_size reduit (composition multiplicative)."""
    eng = _build_engine(tmp_path)
    monkeypatch.setattr(
        "core.v9.trade_engine._portfolio_risk_enabled", lambda: True,
    )
    monkeypatch.setattr(
        "core.v9.trade_engine._kelly_cvar_enabled", lambda: False,
    )
    monkeypatch.setattr(
        "core.v9.trade_engine._kelly_fractional_enabled", lambda: False,
    )
    monkeypatch.setattr(
        "core.v9.trade_engine._drawdown_protector_enabled", lambda: False,
    )
    monkeypatch.setattr(
        "core.v9.trade_engine._risk_parity_enabled", lambda: False,
    )
    # Override the evaluate_portfolio on the injected mock
    eng.__dict__["_portfolio_risk"].evaluate_portfolio = MagicMock(
        return_value=(True, None, 0.5)
    )
    risk_result = {"position_size": 1.0}
    result = {"action": "go"}
    decision = eng._compute_unified_sizing(
        "SNAP-001",
        {"direction": "haussiere"},
        risk_result,
        result,
        open_trades=[],
        context={"symbol": "GBPUSD"},
    )
    assert decision["early_action"] is None
    # PRM appliquant 0.5 sur 1.0 = 0.5 (composition multiplicative simple)
    assert risk_result["position_size"] == 0.5
    assert result["correlation_sizing_reduction"] == 0.5


def test_unified_sizing_cvar_ceiling(monkeypatch, tmp_path):
    """CVaR ON + cap applique → result['cvar_ceiling'] peuple + position_size cap."""
    eng = _build_engine(tmp_path)
    monkeypatch.setattr(
        "core.v9.trade_engine._portfolio_risk_enabled", lambda: False,
    )
    monkeypatch.setattr(
        "core.v9.trade_engine._kelly_cvar_enabled", lambda: True,
    )

    # Mock recent_returns_pips
    eng._recent_returns_pips = MagicMock(return_value=[-5.0, -8.0, -3.0, -7.0, -6.0, -9.0, -4.0, -7.5, -5.5, -8.5] * 5)

    # Mock cvar_position_cap
    fake_risk_module = MagicMock()
    fake_risk_module.RiskManager.cvar_position_cap = MagicMock(
        return_value={"cvar": 7.0, "cap": 0.5, "size": 0.5, "capped": True}
    )
    monkeypatch.setitem(sys.modules, "core.v9.risk_manager", fake_risk_module)

    risk_result = {"position_size": 1.0}
    result = {"action": "go"}
    decision = eng._compute_unified_sizing(
        "SNAP-001",
        {"direction": "haussiere"},
        risk_result,
        result,
        open_trades=[],
        context={"symbol": "GBPUSD"},
    )
    assert decision["early_action"] is None
    assert result["cvar_ceiling"] is not None
    assert risk_result["position_size"] == 0.5


def test_unified_sizing_kelly_disabled(monkeypatch, tmp_path):
    """Kelly OFF → result['kelly_sizing'] reste None."""
    eng = _build_engine(tmp_path)
    monkeypatch.setattr(
        "core.v9.trade_engine._portfolio_risk_enabled", lambda: False,
    )
    monkeypatch.setattr(
        "core.v9.trade_engine._kelly_cvar_enabled", lambda: False,
    )
    monkeypatch.setattr(
        "core.v9.trade_engine._kelly_fractional_enabled", lambda: False,
    )
    risk_result = {"position_size": 1.0}
    result = {"action": "go"}
    decision = eng._compute_unified_sizing(
        "SNAP-001",
        {"direction": "haussiere"},
        risk_result,
        result,
        open_trades=[],
        context={"symbol": "GBPUSD"},
    )
    assert result.get("kelly_sizing") is None
    # drawdown_protector peut etre absent (jamais initialise) ou None (initialise mais off)
    assert result.get("drawdown_protector") is None


def test_unified_sizing_risk_parity_blacklist(monkeypatch, tmp_path):
    """Risk Parity ON + USDCAD (HARD_BLACKLIST) → pas de plafonnement."""
    eng = _build_engine(tmp_path)
    monkeypatch.setattr(
        "core.v9.trade_engine._portfolio_risk_enabled", lambda: False,
    )
    monkeypatch.setattr(
        "core.v9.trade_engine._kelly_cvar_enabled", lambda: False,
    )
    monkeypatch.setattr(
        "core.v9.trade_engine._kelly_fractional_enabled", lambda: False,
    )
    monkeypatch.setattr(
        "core.v9.trade_engine._risk_parity_enabled", lambda: True,
    )
    # RISK_PARITY_AVAILABLE = True (import successful)
    risk_result = {"position_size": 1.0}
    result = {"action": "go"}
    decision = eng._compute_unified_sizing(
        "SNAP-001",
        {"direction": "haussiere"},
        risk_result,
        result,
        open_trades=[],
        context={"symbol": "USDCAD"},
    )
    assert decision["early_action"] is None
    assert risk_result["position_size"] == 1.0  # pas de cap


def test_unified_sizing_failure_safe(monkeypatch, tmp_path):
    """Si PRM leve, on fail-open (R6) et on continue."""
    eng = _build_engine(tmp_path)
    monkeypatch.setattr(
        "core.v9.trade_engine._portfolio_risk_enabled", lambda: True,
    )
    eng.portfolio_risk_manager.evaluate_portfolio = MagicMock(
        side_effect=RuntimeError("PRM crash")
    )
    risk_result = {"position_size": 1.0}
    result = {"action": "go"}
    decision = eng._compute_unified_sizing(
        "SNAP-001",
        {"direction": "haussiere"},
        risk_result,
        result,
        open_trades=[],
        context={"symbol": "GBPUSD"},
    )
    assert decision["early_action"] is None  # R6 fail-open
    assert risk_result["position_size"] == 1.0  # intact


# ---------------------------------------------------------------------------
# Tests _finalize_decision
# ---------------------------------------------------------------------------

def test_finalize_idempotence_skip(monkeypatch, tmp_path):
    """Idempotence hit → action=skip + raison=snapshot_deja_trade."""
    eng = _build_engine(tmp_path, trade_already_open=lambda sid, d: True)
    result = {"action": "go"}
    decision = eng._finalize_decision(
        "SNAP-001",
        {"direction": "haussiere"},
        {"symbol": "GBPUSD"},
        result,
        tp_pips=10.0,
        sl_pips=5.0,
    )
    assert decision["early_action"] == "skip"
    assert decision["raison"] == "snapshot_deja_trade"
    assert result["action"] == "skip"
    assert result["raison_blocage"] == "snapshot_deja_trade"
    # log_open pas appele
    eng.trade_logger.log_open.assert_not_called()


def test_finalize_log_open_success(monkeypatch, tmp_path):
    """log_open reussi → action=open + trade_id peuple."""
    eng = _build_engine(tmp_path, trade_already_open=lambda sid, d: False)
    result = {"action": "go"}
    decision = eng._finalize_decision(
        "SNAP-001",
        {"direction": "haussiere"},
        {"symbol": "GBPUSD"},
        result,
        tp_pips=10.0,
        sl_pips=5.0,
    )
    assert decision["early_action"] == "open"
    assert result["trade_id"] == "TRADE-001"
    assert result["action"] == "open"
    eng.trade_logger.log_open.assert_called_once()


def test_finalize_log_open_failure(monkeypatch, tmp_path):
    """log_open leve → result.error peuple, pas de crash."""
    eng = _build_engine(tmp_path, trade_already_open=lambda sid, d: False)
    eng.trade_logger.log_open = MagicMock(side_effect=RuntimeError("DB crash"))
    result = {"action": "go"}
    decision = eng._finalize_decision(
        "SNAP-001",
        {"direction": "haussiere"},
        {"symbol": "GBPUSD"},
        result,
        tp_pips=10.0,
        sl_pips=5.0,
    )
    # Pas de early_action, l'error est dans result mais on ne crash pas
    assert result["error"] is not None
    assert "log_open" in result["error"]


def test_finalize_pyramiding_sizing_factor(monkeypatch, tmp_path):
    """Pyramiding > 1 → sizing_factor injecte dans ctx_for_open."""
    captured_ctx = {}

    def capture_log_open(arb_result, ctx):
        captured_ctx.update(ctx)
        return "TRADE-XYZ"

    eng = _build_engine(tmp_path, trade_already_open=lambda sid, d: False)
    eng.trade_logger.log_open = MagicMock(side_effect=capture_log_open)
    result = {"action": "go", "pyramiding": {"multiplier": 1.5}}
    eng._finalize_decision(
        "SNAP-001",
        {"direction": "haussiere"},
        {"symbol": "GBPUSD"},
        result,
        tp_pips=10.0,
        sl_pips=5.0,
    )
    assert captured_ctx.get("sizing_factor") == 1.5


def test_finalize_pyramiding_no_sizing_factor_below_1(monkeypatch, tmp_path):
    """Pyramiding < 1 → pas de sizing_factor (defensif)."""
    captured_ctx = {}

    def capture_log_open(arb_result, ctx):
        captured_ctx.update(ctx)
        return "TRADE-XYZ"

    eng = _build_engine(tmp_path, trade_already_open=lambda sid, d: False)
    eng.trade_logger.log_open = MagicMock(side_effect=capture_log_open)
    result = {"action": "go", "pyramiding": {"multiplier": 0.8}}
    eng._finalize_decision(
        "SNAP-001",
        {"direction": "haussiere"},
        {"symbol": "GBPUSD"},
        result,
        tp_pips=10.0,
        sl_pips=5.0,
    )
    assert "sizing_factor" not in captured_ctx
