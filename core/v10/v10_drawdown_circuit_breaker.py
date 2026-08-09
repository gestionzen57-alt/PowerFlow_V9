"""
v10_drawdown_circuit_breaker.py — CYCLE 12 : Drawdown Circuit Breaker

C12-OPT5 : Déclenche un circuit breaker (halt_trading=True) si :
            - Daily DD   > 3% (SOFT)
            - Weekly DD  > 6% (HARD)
            - Monthly DD > 10% (CRITICAL)

Doctrine : R2 additif pur | R6 fail-open | R9 audit | R10 compute-only
"""
from __future__ import annotations

import warnings
from dataclasses import dataclass, field
from typing import Any


# ── Seuils ────────────────────────────────────────────────────────────────────
DD_DAILY_SOFT: float = 0.03
DD_WEEKLY_HARD: float = 0.06
DD_MONTHLY_CRITICAL: float = 0.10

LEVEL_MAP = {
    "NONE": 0, "SOFT": 1, "HARD": 2, "CRITICAL": 3
}


@dataclass
class CircuitBreakerResult:
    halt_trading: bool = False
    level: str = "NONE"          # NONE | SOFT | HARD | CRITICAL
    trigger: str = ""
    daily_dd: float = 0.0
    weekly_dd: float = 0.0
    monthly_dd: float = 0.0
    resume_conditions: list = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "halt_trading": self.halt_trading,
            "level": self.level,
            "trigger": self.trigger,
            "daily_dd": self.daily_dd,
            "weekly_dd": self.weekly_dd,
            "monthly_dd": self.monthly_dd,
            "resume_conditions": self.resume_conditions,
        }


def check_circuit_breaker(
    daily_dd: float = 0.0,
    weekly_dd: float = 0.0,
    monthly_dd: float = 0.0,
) -> CircuitBreakerResult:
    """
    Évalue si le circuit breaker doit être déclenché.

    Args:
        daily_dd   : drawdown journalier (0-1, ex: 0.04 = 4%)
        weekly_dd  : drawdown hebdo
        monthly_dd : drawdown mensuel

    Returns:
        CircuitBreakerResult avec halt_trading=True si un seuil est dépassé
    """
    result = CircuitBreakerResult(
        daily_dd=daily_dd,
        weekly_dd=weekly_dd,
        monthly_dd=monthly_dd,
    )
    try:
        # CRITICAL — priorité la plus haute
        if monthly_dd >= DD_MONTHLY_CRITICAL:
            result.halt_trading = True
            result.level = "CRITICAL"
            result.trigger = f"MONTHLY_DD={monthly_dd:.1%}>={DD_MONTHLY_CRITICAL:.0%}"
            result.resume_conditions = [
                "Attendre reset mensuel",
                "Revue manuelle obligatoire",
                "WR ≥ 50% sur 20 derniers trades shadow",
            ]
        elif weekly_dd >= DD_WEEKLY_HARD:
            result.halt_trading = True
            result.level = "HARD"
            result.trigger = f"WEEKLY_DD={weekly_dd:.1%}>={DD_WEEKLY_HARD:.0%}"
            result.resume_conditions = [
                "Attendre lundi (reset hebdo)",
                "WR ≥ 48% sur 10 derniers trades shadow",
            ]
        elif daily_dd >= DD_DAILY_SOFT:
            result.halt_trading = True
            result.level = "SOFT"
            result.trigger = f"DAILY_DD={daily_dd:.1%}>={DD_DAILY_SOFT:.0%}"
            result.resume_conditions = [
                "Attendre ouverture session suivante (NY/London/Tokyo)",
                "PnL shadow positif sur 5 trades",
            ]
        else:
            result.level = "NONE"
            result.trigger = "ALL_DD_OK"

    except Exception as e:  # R6 fail-open
        warnings.warn(f"[C12] CircuitBreaker error (fail-open): {e}")
        result.halt_trading = False
        result.trigger = f"ERROR_FAIL_OPEN: {e}"

    return result
