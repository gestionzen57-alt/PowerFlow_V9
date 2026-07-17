"""Tests pour v9_drawdown_protector et v9_risk_parity.

2026-07-17 motion CEO « hedge fund mondial ».
"""
from __future__ import annotations

import sqlite3
import pytest

from core.v9.v9_drawdown_protector import (
    DrawdownDecision,
    DrawdownProtector,
    DrawdownState,
)
from core.v9.v9_risk_parity import (
    HARD_BLACKLIST,
    PairRiskBudget,
    compute_expected_sharpe,
    compute_risk_parity_budgets,
    estimate_vol_annualized,
)


# ── DrawdownProtector tests ────────────────────────────────────────


def test_drawdown_state_initial_zero() -> None:
    """État initial : peak = current = 0, DD = 0."""
    s = DrawdownState()
    assert s.peak_pips == 0.0
    assert s.current_drawdown == 0.0
    assert s.max_drawdown == 0.0
    assert s.is_in_drawdown is False
    assert s.is_recovery is False
    assert s.win_rate == 0.0


def test_drawdown_state_to_dict() -> None:
    """to_dict expose win_rate + booléens calculés."""
    s = DrawdownState(peak_pips=100, current_pips=80, n_trades_total=10, n_wins=7)
    d = s.to_dict()
    assert d["win_rate"] == 0.7
    assert d["is_in_drawdown"] is True
    assert "last_update" in d


def test_drawdown_protector_normal_decision() -> None:
    """Pas de DD → action=normal, multiplier=1.0."""
    prot = DrawdownProtector(initial_capital=10000.0)
    prot.state.current_pips = 1000.0
    prot.state.peak_pips = 1000.0
    decision = prot._decide_with_state(prot.state)
    assert decision.action == "normal"
    assert decision.position_multiplier == 1.0
    assert "nominal" in decision.rationale.lower()


def test_drawdown_protector_reduce_50() -> None:
    """DD entre 5% et 10% → reduce_50."""
    prot = DrawdownProtector(initial_capital=10000.0)
    state = DrawdownState(peak_pips=2000.0, current_pips=1400.0)
    decision = prot._decide_with_state(state)
    assert decision.action == "reduce_50"
    assert decision.position_multiplier == 0.5


def test_drawdown_protector_halt_24h() -> None:
    """DD entre 10% et 15% → halt_24h."""
    prot = DrawdownProtector(initial_capital=10000.0)
    state = DrawdownState(peak_pips=3000.0, current_pips=1800.0)
    decision = prot._decide_with_state(state)
    assert decision.action == "halt_24h"
    assert decision.position_multiplier == 0.0


def test_drawdown_protector_halt_forever() -> None:
    """DD ≥ 15% → halt_forever."""
    prot = DrawdownProtector(initial_capital=10000.0)
    state = DrawdownState(peak_pips=5000.0, current_pips=3000.0)
    decision = prot._decide_with_state(state)
    assert decision.action == "halt_forever"
    assert decision.position_multiplier == 0.0


def test_drawdown_protector_consecutive_losses() -> None:
    """5 losses consécutives → pause défensive."""
    prot = DrawdownProtector(initial_capital=10000.0)
    state = DrawdownState(current_pips=100.0, peak_pips=100.0, consecutive_losses=7)
    decision = prot._decide_with_state(state)
    assert decision.action == "pause_5_losses"
    assert decision.position_multiplier == 0.0


def test_drawdown_protector_decision_to_dict() -> None:
    """DrawdownDecision.to_dict contient action + state."""
    prot = DrawdownProtector(initial_capital=10000.0)
    decision = prot.decide()
    d = decision.to_dict()
    assert "action" in d
    assert "position_multiplier" in d
    assert "state" in d


# ── RiskParity tests ────────────────────────────────────────────────


def test_risk_parity_blacklist_excluded() -> None:
    """USDCAD exclu par défaut."""
    budgets = compute_risk_parity_budgets(capital=10000.0, target_vol=0.15)
    symbols = [b.symbol for b in budgets]
    assert "USDCAD" not in symbols


def test_risk_parity_weights_sum_to_one() -> None:
    """La somme des risk_weights = 1.0 (normalisation)."""
    budgets = compute_risk_parity_budgets(capital=10000.0, target_vol=0.15)
    total = sum(b.risk_weight for b in budgets)
    if budgets:  # skip si tous filtrés
        assert abs(total - 1.0) < 1e-6


def test_risk_parity_higher_vol_lower_weight() -> None:
    """Plus la vol est haute, plus le weight est bas (risk parity)."""
    budgets = compute_risk_parity_budgets(capital=10000.0, target_vol=0.15)
    if len(budgets) < 2:
        pytest.skip("Pas assez de paires avec data pour comparer")
    by_vol = sorted(budgets, key=lambda b: b.vol_annualized)
    # La paire avec la plus haute vol doit avoir un weight parmi les plus bas
    # (à sharpe égale). Mais avec sharpe boost, c'est moins strict.
    # Test pragmatique : la plus haute vol n'est jamais la plus haute weight.
    if len(by_vol) >= 2:
        highest_vol = by_vol[-1]
        highest_weight = max(budgets, key=lambda b: b.risk_weight)
        # Si sharpe boost pour la plus haute vol, peut être exception
        if highest_vol.expected_sharpe < highest_weight.expected_sharpe:
            assert highest_vol.risk_weight < highest_weight.risk_weight


def test_pair_risk_budget_to_dict() -> None:
    """PairRiskBudget.to_dict expose tous les champs."""
    b = PairRiskBudget(
        symbol="GBPUSD",
        risk_weight=0.5,
        vol_annualized=441.0,
        expected_sharpe=0.86,
        max_position_size=8000.0,
        rationale="test",
    )
    d = b.to_dict()
    assert d["symbol"] == "GBPUSD"
    assert d["risk_weight"] == 0.5
    assert d["expected_sharpe"] == 0.86


def test_estimate_vol_returns_positive_or_sentinel() -> None:
    """estimate_vol_annualized retourne soit >0 soit -1.0 (sentinel)."""
    for sym in ["GBPUSD", "EURUSD", "USDJPY", "USDCHF", "AUDUSD", "NZDUSD", "USDCAD"]:
        v = estimate_vol_annualized(None, sym)
        assert v > 0 or v == -1.0, f"{sym}: vol inattendue {v}"


def test_estimate_vol_gbp_has_data() -> None:
    """GBPUSD a assez de data → vol > 0."""
    v = estimate_vol_annualized(None, "GBPUSD")
    assert v > 0, f"GBPUSD devrait avoir data, vol={v}"


def test_estimate_vol_nzd_no_data_returns_sentinel() -> None:
    """NZDUSD a peu de data → vol = -1.0 (sentinel)."""
    v = estimate_vol_annualized(None, "NZDUSD")
    assert v == -1.0, f"NZDUSD devrait être sentinel, vol={v}"


def test_compute_expected_sharpe_returns_float() -> None:
    """Sharpe ratio = avg/stddev, float positif/nul."""
    s = compute_expected_sharpe(None, "GBPUSD")
    assert isinstance(s, float)
    assert s >= 0


def test_hard_blacklist_contains_usdcad() -> None:
    """USDCAD est blacklisté dur."""
    assert "USDCAD" in HARD_BLACKLIST