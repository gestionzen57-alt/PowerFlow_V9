"""
v10_live_readiness.py — C11-OPT2/OPT3 : Audit LiveReadiness + Wilson Confidence Bands

Audit complet en 4 gates :
  - Sharpe ≥ C11_SHARPE_MIN
  - MaxDD   ≤ C11_MAX_DD_MAX
  - WR      ≥ C11_WR_MIN  (+ Wilson lower bound 95%)
  - PnL     ≥ C11_PNL_MIN

Fail-open R6 sur toutes les opérations.
"""
from __future__ import annotations

import math
import warnings
from dataclasses import dataclass, field
from typing import Any

C11_SHARPE_MIN: float = 0.40
C11_MAX_DD_MAX: float = 0.08
C11_WR_MIN: float = 0.48
C11_PNL_MIN: float = 0.0
C11_TRADES_MIN: int = 30
C11_CONFIDENCE: float = 0.95


def _wilson(p: float, n: int, z: float = 1.96) -> tuple[float, float]:
    denom = 1 + z ** 2 / n
    centre = (p + z ** 2 / (2 * n)) / denom
    margin = (z * math.sqrt(p * (1 - p) / n + z ** 2 / (4 * n ** 2))) / denom
    return max(0.0, centre - margin), min(1.0, centre + margin)


@dataclass
class LiveReadinessReport:
    live_ready: bool = False
    reason: str = "NOT_EVALUATED"
    sharpe: float = 0.0
    max_dd: float = 0.0
    wr: float = 0.0
    pnl: float = 0.0
    n_trades: int = 0
    wr_lower: float = 0.0
    wr_upper: float = 0.0
    gates: dict = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "live_ready": self.live_ready,
            "live_ready_reason": self.reason,
            "sharpe": self.sharpe,
            "max_dd": self.max_dd,
            "wr": self.wr,
            "pnl": self.pnl,
            "n_trades": self.n_trades,
            "wr_lower_95": self.wr_lower,
            "wr_upper_95": self.wr_upper,
            "gates": self.gates,
        }


def audit_live_readiness(report_dict: dict[str, Any]) -> LiveReadinessReport:
    """C11-OPT2/OPT3 — Audit complet LiveReadiness."""
    r = LiveReadinessReport()
    try:
        r.sharpe = float(report_dict.get("sharpe", 0.0))
        r.max_dd = float(report_dict.get("max_drawdown", 1.0))
        r.wr = float(report_dict.get("win_rate", 0.0))
        r.pnl = float(report_dict.get("total_pnl", -1.0))
        r.n_trades = int(report_dict.get("total_trades", 0))

        # C11-OPT3 : Wilson confidence band
        if r.n_trades >= C11_TRADES_MIN:
            try:
                r.wr_lower, r.wr_upper = _wilson(r.wr, r.n_trades)
            except Exception as e:
                warnings.warn(f"[C11-OPT3] Wilson error (fail-open): {e}")

        r.gates = {
            "sharpe_ok": r.sharpe >= C11_SHARPE_MIN,
            "maxdd_ok": r.max_dd <= C11_MAX_DD_MAX,
            "wr_ok": r.wr >= C11_WR_MIN,
            "pnl_ok": r.pnl >= C11_PNL_MIN,
        }
        r.live_ready = all(r.gates.values())

        if r.live_ready:
            r.reason = (f"ALL_GATES_PASS Sharpe={r.sharpe:.2f} MaxDD={r.max_dd:.1%} "
                        f"WR={r.wr:.1%}[{r.wr_lower:.1%}-{r.wr_upper:.1%}] PnL={r.pnl:+.0f}")
        else:
            fails = [k for k, v in r.gates.items() if not v]
            r.reason = "GATES_FAIL: " + ", ".join(fails)
    except Exception as e:
        warnings.warn(f"[C11-OPT2] audit_live_readiness error (fail-open): {e}")
        r.reason = f"ERROR_FAIL_OPEN: {e}"
    return r
