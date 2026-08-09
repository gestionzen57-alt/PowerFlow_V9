"""
v10_cycle11_planner.py — CYCLE 11 : Live-Readiness Gate & Shadow Trading

Objectifs C11 :
  C11-OPT1 : ShadowTrader — exécution papier live en parallèle du replay
  C11-OPT2 : LiveReadiness audit complet (Sharpe ≥ 0.4, MaxDD ≤ 8%, WR ≥ 0.48, PnL ≥ 0)
  C11-OPT3 : Confidence bands sur WR (Wilson interval à 95%)
  C11-OPT4 : Alerting Telegram/webhook sur LiveGate OPEN
  C11-OPT5 : Multi-pair portfolio balancer (net exposure cap)
  C11-OPT6 : Cycle tag + c11_features dans ReplayReport

Règles doctrine :
  R2  — additif pur, zéro import core/v9/
  R6  — fail-open sur tous les sous-modules
  R9  — audit traçable dans summary
  R10 — compute-only jusqu'à validation LiveGate C11

Statut : STUB — À implémenter en Cycle 11
"""

from __future__ import annotations

import warnings
from dataclasses import dataclass, field
from typing import Any


# ─── Seuils C11 ───────────────────────────────────────────────────────────────
C11_SHARPE_MIN: float = 0.40
C11_MAX_DD_MAX: float = 0.08       # 8 %
C11_WR_MIN: float = 0.48
C11_PNL_MIN: float = 0.0
C11_CONFIDENCE_LEVEL: float = 0.95  # Wilson interval
C11_TRADES_MIN: int = 30            # min trades pour bande de confiance


@dataclass
class C11LiveReadinessResult:
    """Résultat de l'audit Live-Readiness C11."""
    live_ready: bool = False
    live_ready_reason: str = "NOT_EVALUATED"
    sharpe: float = 0.0
    max_dd: float = 0.0
    wr: float = 0.0
    pnl: float = 0.0
    wr_lower_bound: float = 0.0     # Wilson lower bound 95%
    wr_upper_bound: float = 0.0     # Wilson upper bound 95%
    shadow_trades: int = 0
    c11_features: list = field(default_factory=list)
    cycle: str = "11"

    def as_dict(self) -> dict[str, Any]:
        return {
            "cycle": self.cycle,
            "live_ready": self.live_ready,
            "live_ready_reason": self.live_ready_reason,
            "sharpe": self.sharpe,
            "max_dd": self.max_dd,
            "wr": self.wr,
            "pnl": self.pnl,
            "wr_lower_bound": self.wr_lower_bound,
            "wr_upper_bound": self.wr_upper_bound,
            "shadow_trades": self.shadow_trades,
            "c11_features": self.c11_features,
        }


def run_cycle11_live_readiness(
    report_dict: dict[str, Any],
    *,
    enable_shadow: bool = True,
    enable_alerting: bool = False,
) -> C11LiveReadinessResult:
    """
    Point d'entrée C11 — audit Live-Readiness complet.

    Args:
        report_dict : dict issu de ReplayReport.as_dict() ou run_all()
        enable_shadow : active le shadow trader (compute-only, R10)
        enable_alerting : active les alertes Telegram/webhook

    Returns:
        C11LiveReadinessResult
    """
    result = C11LiveReadinessResult()
    result.c11_features = [
        "C11-OPT1:ShadowTrader",
        "C11-OPT2:LiveReadinessAudit",
        "C11-OPT3:WilsonConfidenceBands",
        "C11-OPT4:Alerting",
        "C11-OPT5:PortfolioBalancer",
        "C11-OPT6:CycleTag",
    ]

    try:
        # C11-OPT2 : Audit Live-Readiness
        sharpe = float(report_dict.get("sharpe", 0.0))
        max_dd = float(report_dict.get("max_drawdown", 1.0))
        wr = float(report_dict.get("win_rate", 0.0))
        pnl = float(report_dict.get("total_pnl", -1.0))
        n_trades = int(report_dict.get("total_trades", 0))

        result.sharpe = sharpe
        result.max_dd = max_dd
        result.wr = wr
        result.pnl = pnl

        # C11-OPT3 : Wilson confidence interval
        if n_trades >= C11_TRADES_MIN:
            try:
                result.wr_lower_bound, result.wr_upper_bound = _wilson_interval(
                    wr, n_trades, C11_CONFIDENCE_LEVEL
                )
            except Exception as e:  # R6 fail-open
                warnings.warn(f"[C11] Wilson interval error: {e}")

        gates_ok = (
            sharpe >= C11_SHARPE_MIN
            and max_dd <= C11_MAX_DD_MAX
            and wr >= C11_WR_MIN
            and pnl >= C11_PNL_MIN
        )

        if gates_ok:
            result.live_ready = True
            result.live_ready_reason = (
                f"ALL_GATES_PASS Sharpe={sharpe:.2f} MaxDD={max_dd:.1%} "
                f"WR={wr:.1%} PnL={pnl:+.0f}"
            )
        else:
            fails = []
            if sharpe < C11_SHARPE_MIN:
                fails.append(f"Sharpe={sharpe:.2f}<{C11_SHARPE_MIN}")
            if max_dd > C11_MAX_DD_MAX:
                fails.append(f"MaxDD={max_dd:.1%}>{C11_MAX_DD_MAX:.0%}")
            if wr < C11_WR_MIN:
                fails.append(f"WR={wr:.1%}<{C11_WR_MIN:.0%}")
            if pnl < C11_PNL_MIN:
                fails.append(f"PnL={pnl:+.0f}<{C11_PNL_MIN}")
            result.live_ready_reason = "GATES_FAIL: " + ", ".join(fails)

    except Exception as e:  # R6 fail-open global
        warnings.warn(f"[C11] run_cycle11_live_readiness error (fail-open): {e}")
        result.live_ready_reason = f"ERROR_FAIL_OPEN: {e}"

    return result


def _wilson_interval(p: float, n: int, confidence: float = 0.95) -> tuple[float, float]:
    """Wilson score interval pour une proportion p sur n observations."""
    import math
    # z pour 95% → 1.96
    z_map = {0.90: 1.645, 0.95: 1.960, 0.99: 2.576}
    z = z_map.get(confidence, 1.96)
    denominator = 1 + z**2 / n
    centre = (p + z**2 / (2 * n)) / denominator
    margin = (z * math.sqrt(p * (1 - p) / n + z**2 / (4 * n**2))) / denominator
    return max(0.0, centre - margin), min(1.0, centre + margin)
