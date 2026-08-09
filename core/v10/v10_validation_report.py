"""
v10_validation_report.py — Cycle 18
Rapport de validation : gates live-readiness, score global.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, List
from datetime import datetime, timezone


@dataclass
class ValidationGate:
    name: str
    passed: bool
    value: float
    threshold: float
    message: str

    def as_dict(self) -> dict:
        return {
            "name": self.name, "passed": self.passed,
            "value": round(self.value, 4), "threshold": round(self.threshold, 4),
            "message": self.message,
        }


@dataclass
class ValidationReport:
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    gates: List[ValidationGate] = field(default_factory=list)
    live_ready: bool = False
    overall_score: float = 0.0
    recommendation: str = ""

    def as_dict(self) -> dict:
        return {
            "timestamp": self.timestamp, "live_ready": self.live_ready,
            "score": round(self.overall_score, 2),
            "recommendation": self.recommendation,
            "gates": [g.as_dict() for g in self.gates],
        }


class ValidationReportBuilder:
    GATES_CONFIG = [
        ("win_rate",       0.48, "WR >= 48%",             False),
        ("sharpe",         0.40, "Sharpe >= 0.40",         False),
        ("max_drawdown",   0.08, "MaxDD <= 8%",            True),
        ("profit_factor",  1.20, "PF >= 1.20",             False),
        ("wfa_efficiency", 0.55, "WFA efficiency >= 55%",  False),
        ("ruin_prob",      0.05, "Ruin prob <= 5%",        True),
    ]

    def build(self, metrics: Dict[str, float]) -> ValidationReport:
        report = ValidationReport()
        passed_count = 0
        for name, threshold, msg, inverted in self.GATES_CONFIG:
            value = metrics.get(name, 0.0)
            passed = (value <= threshold) if inverted else (value >= threshold)
            if passed:
                passed_count += 1
            report.gates.append(ValidationGate(
                name=name, passed=passed, value=value,
                threshold=threshold, message=msg,
            ))
        n = len(self.GATES_CONFIG)
        report.overall_score = (passed_count / n) * 100
        report.live_ready = passed_count >= n - 1
        if report.live_ready:
            report.recommendation = "LIVE_READY — Déploiement autorisé"
        elif report.overall_score >= 60:
            report.recommendation = "PAPER_TRADE — Optimisation complémentaire conseillée"
        else:
            report.recommendation = "NOT_READY — Backtesting additionnel requis"
        return report
