"""
v10_cycle12_optimizer.py — CYCLE 12 : Orchestrateur principal

C12-OPT6 : Intègre AdaptiveRisk + DynamicSizing + RegimeSwitcher
             + CorrelationGuard + CircuitBreaker dans un pipeline
             post-replay unifié.

Doctrine : R2 | R6 fail-open | R9 audit | R10 compute-only
"""
from __future__ import annotations

import warnings
from dataclasses import dataclass, field
from typing import Any

from .v10_adaptive_risk_engine import compute_adaptive_risk, AdaptiveRiskResult
from .v10_dynamic_sizing import compute_lot_size, SizingResult
from .v10_regime_switcher import detect_regime, RegimeResult
from .v10_correlation_guard import check_correlation, CorrelationGuardResult
from .v10_drawdown_circuit_breaker import check_circuit_breaker, CircuitBreakerResult


# ── Cycle tag ──────────────────────────────────────────────────────────────────
CYCLE_TAG = "12"
C12_FEATURES = [
    "C12-OPT1:AdaptiveRiskEngine",
    "C12-OPT2:DynamicSizing",
    "C12-OPT3:RegimeSwitcher",
    "C12-OPT4:CorrelationGuard",
    "C12-OPT5:DrawdownCircuitBreaker",
    "C12-OPT6:C12Orchestrator",
]


@dataclass
class C12PostprocessResult:
    cycle: str = CYCLE_TAG
    halt_trading: bool = False
    circuit_level: str = "NONE"
    regime: str = "unknown"
    risk_pct: float = 0.01
    lot_size: float = 0.10
    correlation_ok: bool = True
    c12_features: list = field(default_factory=list)
    regime_result: dict = field(default_factory=dict)
    risk_result: dict = field(default_factory=dict)
    sizing_result: dict = field(default_factory=dict)
    corr_result: dict = field(default_factory=dict)
    circuit_result: dict = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "cycle": self.cycle,
            "halt_trading": self.halt_trading,
            "circuit_level": self.circuit_level,
            "regime": self.regime,
            "risk_pct": self.risk_pct,
            "lot_size": self.lot_size,
            "correlation_ok": self.correlation_ok,
            "c12_features": self.c12_features,
            "regime_result": self.regime_result,
            "risk_result": self.risk_result,
            "sizing_result": self.sizing_result,
            "corr_result": self.corr_result,
            "circuit_result": self.circuit_result,
        }


def run_cycle12_postprocess(
    report_dict: dict[str, Any],
    open_positions: dict[str, float] | None = None,
    new_pair: str = "EURUSD",
    account_balance: float = 10_000.0,
    *,
    adx: float = 0.0,
    atr: float = 0.0,
    atr_baseline: float = 0.0,
    spread: float = 0.0,
    spread_baseline: float = 0.0,
) -> C12PostprocessResult:
    """
    Pipeline C12 complet post-replay.

    Args:
        report_dict     : dict issu de ReplayReport / run_all()
        open_positions  : {pair: lots} positions ouvertes
        new_pair        : paire candidate
        account_balance : capital disponible
        adx/atr/...     : indicateurs de marché courants
    """
    result = C12PostprocessResult(c12_features=C12_FEATURES)
    if open_positions is None:
        open_positions = {}

    # ── C12-OPT3 : Détection de régime ─────────────────────────────────────
    try:
        reg: RegimeResult = detect_regime(
            adx=adx, atr=atr, atr_baseline=atr_baseline,
            spread=spread, spread_baseline=spread_baseline,
        )
        result.regime = reg.regime
        result.regime_result = reg.as_dict()
    except Exception as e:
        warnings.warn(f"[C12] RegimeSwitcher fail-open: {e}")
        result.regime = "unknown"

    # ── C12-OPT5 : Circuit breaker ─────────────────────────────────────────
    try:
        cb: CircuitBreakerResult = check_circuit_breaker(
            daily_dd=float(report_dict.get("daily_drawdown", 0.0)),
            weekly_dd=float(report_dict.get("weekly_drawdown", 0.0)),
            monthly_dd=float(report_dict.get("monthly_drawdown", 0.0)),
        )
        result.halt_trading = cb.halt_trading
        result.circuit_level = cb.level
        result.circuit_result = cb.as_dict()
    except Exception as e:
        warnings.warn(f"[C12] CircuitBreaker fail-open: {e}")

    # ── C12-OPT1 : Risk adaptatif ───────────────────────────────────────────
    try:
        risk: AdaptiveRiskResult = compute_adaptive_risk(
            regime=result.regime,
            recent_wr=float(report_dict.get("win_rate", 0.50)),
            current_dd=float(report_dict.get("daily_drawdown", 0.0)),
        )
        result.risk_pct = risk.risk_pct
        result.risk_result = risk.as_dict()
    except Exception as e:
        warnings.warn(f"[C12] AdaptiveRisk fail-open: {e}")

    # ── C12-OPT2 : Dynamic sizing ──────────────────────────────────────────
    try:
        sizing: SizingResult = compute_lot_size(
            account_balance=account_balance,
            risk_pct=result.risk_pct,
            stop_loss_pips=float(report_dict.get("avg_sl_pips", 20.0)),
            win_rate=float(report_dict.get("win_rate", 0.50)),
            atr_pips=atr if atr > 0 else None,
        )
        result.lot_size = sizing.lot_size
        result.sizing_result = sizing.as_dict()
    except Exception as e:
        warnings.warn(f"[C12] DynamicSizing fail-open: {e}")

    # ── C12-OPT4 : Correlation guard ──────────────────────────────────────
    try:
        corr: CorrelationGuardResult = check_correlation(
            new_pair=new_pair,
            new_lots=result.lot_size,
            open_positions=open_positions,
        )
        result.correlation_ok = corr.allowed
        result.corr_result = corr.as_dict()
    except Exception as e:
        warnings.warn(f"[C12] CorrelationGuard fail-open: {e}")

    # ── Log C12 ──────────────────────────────────────────────────────────────────
    import logging
    logging.getLogger("powerflow.c12").info(
        "[C12] regime=%s risk=%.3f%% lot=%.2f CB=%s corr=%s halt=%s",
        result.regime, result.risk_pct * 100, result.lot_size,
        result.circuit_level, result.correlation_ok, result.halt_trading,
    )

    return result
