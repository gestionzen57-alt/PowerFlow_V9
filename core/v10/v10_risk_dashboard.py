"""
v10_risk_dashboard.py — Cycle 15
Tableau de bord risque temps réel : exposition nette, drawdown courant,
circuit breakers actifs, score global de santé du portefeuille.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, List, Optional
from datetime import datetime, timezone


@dataclass
class RiskMetric:
    name: str
    value: float
    threshold: float
    status: str  # OK | WARN | ALERT

    def as_dict(self) -> dict:
        return {
            "name": self.name,
            "value": round(self.value, 4),
            "threshold": round(self.threshold, 4),
            "status": self.status,
        }


@dataclass
class DashboardSnapshot:
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    metrics: List[RiskMetric] = field(default_factory=list)
    health_score: float = 100.0  # 0-100
    circuit_breakers_active: List[str] = field(default_factory=list)
    trading_allowed: bool = True

    def as_dict(self) -> dict:
        return {
            "timestamp": self.timestamp,
            "health_score": round(self.health_score, 2),
            "trading_allowed": self.trading_allowed,
            "circuit_breakers": self.circuit_breakers_active,
            "metrics": [m.as_dict() for m in self.metrics],
        }


class RiskDashboard:
    """
    Agrège les métriques de risque et calcule un score de santé global.
    """

    THRESHOLDS = {
        "drawdown_pct": 0.05,      # 5%
        "daily_loss_pct": 0.02,    # 2%
        "open_positions": 5,
        "net_exposure": 0.15,      # 15% du capital
        "consecutive_losses": 4,
    }

    def __init__(self) -> None:
        self._current: Dict[str, float] = {}

    def update(self, key: str, value: float) -> None:
        self._current[key] = value

    def snapshot(self) -> DashboardSnapshot:
        snap = DashboardSnapshot()
        circuit_breakers: List[str] = []
        penalty = 0.0

        for name, threshold in self.THRESHOLDS.items():
            value = self._current.get(name, 0.0)
            if value >= threshold * 1.5:
                status = "ALERT"
                circuit_breakers.append(name)
                penalty += 30.0
            elif value >= threshold:
                status = "WARN"
                penalty += 10.0
            else:
                status = "OK"
            snap.metrics.append(RiskMetric(name=name, value=value, threshold=threshold, status=status))

        snap.health_score = max(0.0, 100.0 - penalty)
        snap.circuit_breakers_active = circuit_breakers
        snap.trading_allowed = len(circuit_breakers) == 0
        return snap

    def reset(self) -> None:
        self._current.clear()
