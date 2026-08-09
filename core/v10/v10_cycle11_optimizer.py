"""
v10_cycle11_optimizer.py — CYCLE 11 : Orchestrateur C11 complet

Chain C11 :
  run_all() → run_cycle11_postprocess() → C11PostprocessResult
    ├ C11-OPT1 : ShadowTrader summary injection
    ├ C11-OPT2 : LiveReadiness audit (4 gates)
    ├ C11-OPT3 : Wilson confidence bands sur WR
    ├ C11-OPT4 : AlertingService.notify_live_gate_open()
    ├ C11-OPT5 : PortfolioBalancer net exposure snapshot
    └ C11-OPT6 : summary["cycle"] = "11" + c11_features

Fail-open R6, compute-only R10, additif pur R2.
"""
from __future__ import annotations

import warnings
from dataclasses import dataclass, field
from typing import Any

# C11-OPT1
try:
    from core.v10.v10_shadow_trader import ShadowTrader
    _HAS_SHADOW = True
except Exception:
    _HAS_SHADOW = False

# C11-OPT2/OPT3
try:
    from core.v10.v10_live_readiness import audit_live_readiness, LiveReadinessReport
    _HAS_READINESS = True
except Exception:
    _HAS_READINESS = False

# C11-OPT4
try:
    from core.v10.v10_alerting import AlertingService, AlertConfig
    _HAS_ALERTING = True
except Exception:
    _HAS_ALERTING = False

# C11-OPT5
try:
    from core.v10.v10_portfolio_balancer import PortfolioBalancer
    _HAS_BALANCER = True
except Exception:
    _HAS_BALANCER = False


C11_FEATURES = [
    "C11-OPT1:ShadowTrader",
    "C11-OPT2:LiveReadinessAudit",
    "C11-OPT3:WilsonConfidenceBands",
    "C11-OPT4:Alerting",
    "C11-OPT5:PortfolioBalancer",
    "C11-OPT6:CycleTag",
]


@dataclass
class C11PostprocessResult:
    cycle: str = "11"
    live_ready: bool = False
    live_ready_reason: str = "NOT_EVALUATED"
    wr: float = 0.0
    pnl: float = 0.0
    sharpe: float = 0.0
    max_dd: float = 0.0
    wr_lower_95: float = 0.0
    wr_upper_95: float = 0.0
    shadow_summary: dict = field(default_factory=dict)
    portfolio_snapshot: dict = field(default_factory=dict)
    alert_sent: bool = False
    gates: dict = field(default_factory=dict)
    c11_features: list = field(default_factory=lambda: list(C11_FEATURES))

    def as_dict(self) -> dict[str, Any]:
        return {
            "cycle": self.cycle,
            "live_ready": self.live_ready,
            "live_ready_reason": self.live_ready_reason,
            "wr": self.wr,
            "pnl": self.pnl,
            "sharpe": self.sharpe,
            "max_dd": self.max_dd,
            "wr_lower_95": self.wr_lower_95,
            "wr_upper_95": self.wr_upper_95,
            "shadow_summary": self.shadow_summary,
            "portfolio_snapshot": self.portfolio_snapshot,
            "alert_sent": self.alert_sent,
            "gates": self.gates,
            "c11_features": self.c11_features,
        }


def run_cycle11_postprocess(
    report_dict: dict[str, Any],
    *,
    shadow_trader: Any = None,
    alert_config: Any = None,
    portfolio_balancer: Any = None,
) -> C11PostprocessResult:
    """
    Point d’entrée C11 — post-traitement complet.

    Args:
        report_dict     : dict issu de ReplayReport.as_dict() / run_all()
        shadow_trader   : instance ShadowTrader optionnelle (C11-OPT1)
        alert_config    : AlertConfig optionnelle (C11-OPT4)
        portfolio_balancer : PortfolioBalancer optionnel (C11-OPT5)

    Returns:
        C11PostprocessResult
    """
    result = C11PostprocessResult()

    # C11-OPT1 : ShadowTrader summary
    if shadow_trader is not None and _HAS_SHADOW:
        try:
            result.shadow_summary = shadow_trader.summary()
        except Exception as e:
            warnings.warn(f"[C11-OPT1] ShadowTrader.summary error (fail-open): {e}")

    # C11-OPT2/OPT3 : LiveReadiness + Wilson
    if _HAS_READINESS:
        try:
            lr: LiveReadinessReport = audit_live_readiness(report_dict)
            result.live_ready = lr.live_ready
            result.live_ready_reason = lr.reason
            result.wr = lr.wr
            result.pnl = lr.pnl
            result.sharpe = lr.sharpe
            result.max_dd = lr.max_dd
            result.wr_lower_95 = lr.wr_lower
            result.wr_upper_95 = lr.wr_upper
            result.gates = lr.gates
        except Exception as e:
            warnings.warn(f"[C11-OPT2] LiveReadiness error (fail-open): {e}")
    else:
        # fallback minimal
        try:
            result.wr = float(report_dict.get("win_rate", 0.0))
            result.pnl = float(report_dict.get("total_pnl", 0.0))
            result.live_ready = result.wr >= 0.48 and result.pnl >= 0
            result.live_ready_reason = "FALLBACK_MINIMAL"
        except Exception:
            pass

    # C11-OPT4 : Alerting
    if result.live_ready and _HAS_ALERTING:
        try:
            cfg = alert_config or AlertConfig(enabled=False)
            svc = AlertingService(cfg)
            enriched = {**report_dict, **result.as_dict()}
            result.alert_sent = svc.notify_live_gate_open(enriched)
        except Exception as e:
            warnings.warn(f"[C11-OPT4] Alerting error (fail-open): {e}")

    # C11-OPT5 : PortfolioBalancer snapshot
    if portfolio_balancer is not None and _HAS_BALANCER:
        try:
            result.portfolio_snapshot = getattr(
                portfolio_balancer, "_open_positions", {}
            )
        except Exception as e:
            warnings.warn(f"[C11-OPT5] PortfolioBalancer snapshot error (fail-open): {e}")

    # C11-OPT6 : Cycle tag
    report_dict["cycle"] = "11"
    report_dict["c11_features"] = C11_FEATURES
    report_dict["c11_result"] = result.as_dict()

    _log_c11(result, report_dict)
    return result


def _log_c11(result: C11PostprocessResult, report_dict: dict[str, Any]) -> None:
    try:
        trades = report_dict.get("total_trades", 0)
        shadow = result.shadow_summary.get("shadow_trades", 0)
        gate = "OPEN" if result.live_ready else "CLOSED"
        print(
            f"[C11] trades={trades} shadow={shadow} "
            f"WR={result.wr:.1%}[{result.wr_lower_95:.1%}-{result.wr_upper_95:.1%}] "
            f"PnL={result.pnl:+.0f} Sharpe={result.sharpe:.2f} "
            f"MaxDD={result.max_dd:.1%} LiveGate={gate} Alert={result.alert_sent}"
        )
    except Exception:
        pass
