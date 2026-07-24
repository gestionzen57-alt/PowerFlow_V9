"""tests/test_v9_axes_3_4_killswitches.py — Tests kill switches Axes 3+4.

Axe 3 : DD protector, Risk parity, CVaR
Axe 4 : Cycle Memory, Meta Strategy Optimizer

Doctrine : R7 (tests verts), R25' (kill switch OFF par défaut).
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


# ── Axe 3 — DD Protector ─────────────────────────────────────────────

def test_drawdown_protector_kill_switch_default_off():
    """V9_DRAWDOWN_PROTECTOR_ENABLED=0 → kill switch OFF par défaut."""
    from core.v9.kill_switches import drawdown_protector_enabled
    assert drawdown_protector_enabled() is False


def test_drawdown_protector_module_exists():
    """v9_drawdown_protector.DrawdownProtector existe."""
    from core.v9 import v9_drawdown_protector
    assert hasattr(v9_drawdown_protector, "DrawdownProtector")
    assert hasattr(v9_drawdown_protector, "DrawdownState")
    assert hasattr(v9_drawdown_protector, "DrawdownDecision")


def test_drawdown_protector_docstring():
    """La fonction kill switch a la docstring R25'."""
    from core.v9.kill_switches import drawdown_protector_enabled
    func = drawdown_protector_enabled
    assert func.__doc__ is not None
    assert "R25'" in func.__doc__
    assert "motion CEO" in func.__doc__


# ── Axe 3 — Risk Parity ─────────────────────────────────────────────

def test_risk_parity_kill_switch_state():
    """V9_RISK_PARITY_ENABLED=1 (CEO motion 2026-07-23)."""
    from core.v9.kill_switches import risk_parity_enabled
    assert risk_parity_enabled() is True


def test_risk_parity_module_exists():
    """v9_risk_parity contient PairRiskBudget + fonctions Risk Parity."""
    from core.v9 import v9_risk_parity
    assert hasattr(v9_risk_parity, "PairRiskBudget")


def test_risk_parity_docstring():
    """La fonction kill switch a la docstring R25'."""
    from core.v9.kill_switches import risk_parity_enabled
    func = risk_parity_enabled
    assert func.__doc__ is not None
    assert "R25'" in func.__doc__


# ── Axe 3 — CVaR (test_kelly_cvar.py existe) ────────────────────────

def test_cvar_module_via_risk_manager():
    """RiskManager.cvar_95() existe (Chantier B 18/07)."""
    from core.v9.risk_manager import RiskManager
    assert hasattr(RiskManager, "cvar_95")
    assert hasattr(RiskManager, "cvar_position_cap")
    assert callable(RiskManager.cvar_95)


def test_cvar_kill_switch_default_off():
    """V9_KELLY_CVAR_ENABLED=0 → kill switch OFF par défaut."""
    from core.v9.kill_switches import kelly_cvar_enabled
    assert kelly_cvar_enabled() is False


def test_cvar_95_basic():
    """cvar_95([5, -3, 2, -8, 1, -2, 4, -1, 3, -5]) → 8.0 (pire perte)."""
    from core.v9.risk_manager import RiskManager
    cvar = RiskManager.cvar_95([5, -3, 2, -8, 1, -2, 4, -1, 3, -5], 0.95)
    assert cvar == 8.0


# ── Axe 4 — Cycle Memory ────────────────────────────────────────────

def test_cycle_memory_kill_switch_state():
    """V9_CYCLE_MEMORY_ENABLED=1 (CEO motion 2026-07-23)."""
    from core.v9.kill_switches import cycle_memory_enabled
    assert cycle_memory_enabled() is True


def test_cycle_memory_module_exists():
    """v9_cycle_memory contient CyclePattern + TransitionPattern."""
    from core.v9 import v9_cycle_memory
    assert hasattr(v9_cycle_memory, "CyclePattern")
    assert hasattr(v9_cycle_memory, "TransitionPattern")


def test_cycle_memory_docstring():
    """La fonction kill switch a la docstring R25'."""
    from core.v9.kill_switches import cycle_memory_enabled
    func = cycle_memory_enabled
    assert func.__doc__ is not None
    assert "R25'" in func.__doc__


# ── Axe 4 — Meta Strategy Optimizer ─────────────────────────────────

def test_meta_strategy_optimizer_kill_switch_state():
    """V9_META_STRATEGY_OPTIMIZER_ENABLED=1 (motion CEO 04h58 21/07)."""
    from core.v9.kill_switches import meta_strategy_optimizer_enabled
    # Motion CEO 04h58 du 21/07 l'a activé
    assert meta_strategy_optimizer_enabled() is True


def test_meta_strategy_optimizer_module_exists():
    """v9_meta_strategy_optimizer contient ContextScore + MetaStrategyDecision."""
    from core.v9 import v9_meta_strategy_optimizer
    assert hasattr(v9_meta_strategy_optimizer, "ContextScore")
    assert hasattr(v9_meta_strategy_optimizer, "MetaStrategyDecision")


def test_meta_strategy_optimizer_docstring():
    """La fonction kill switch documente son activation par motion CEO."""
    from core.v9.kill_switches import meta_strategy_optimizer_enabled
    func = meta_strategy_optimizer_enabled
    assert func.__doc__ is not None
    assert "motion CEO" in func.__doc__
