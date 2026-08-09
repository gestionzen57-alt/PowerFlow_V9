"""
v10_deployment_validator.py — Cycle 20
Validation finale avant déploiement live : checklist complète de toutes
les pré-conditions système, risque et performance.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, List
from datetime import datetime, timezone


@dataclass
class DeploymentCheck:
    category: str
    name: str
    passed: bool
    value: str
    required: str

    def as_dict(self) -> dict:
        return {
            "category": self.category,
            "name": self.name,
            "passed": self.passed,
            "value": self.value,
            "required": self.required,
        }


@dataclass
class DeploymentReport:
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    checks: List[DeploymentCheck] = field(default_factory=list)
    go_live: bool = False
    score: float = 0.0
    blockers: List[str] = field(default_factory=list)
    recommendation: str = ""

    def as_dict(self) -> dict:
        return {
            "timestamp": self.timestamp,
            "go_live": self.go_live,
            "score": round(self.score, 2),
            "blockers": self.blockers,
            "recommendation": self.recommendation,
            "checks": [c.as_dict() for c in self.checks],
        }


class DeploymentValidator:
    """
    Checklist de déploiement en 4 catégories :
    SYSTEM | RISK | PERFORMANCE | INFRASTRUCTURE
    """

    def validate(self, params: Dict[str, float]) -> DeploymentReport:
        report = DeploymentReport()
        checks_config = [
            # (category, name, key, required_value, operator)
            ("SYSTEM",  "config_loaded",      "config_loaded",   1.0, "gte"),
            ("SYSTEM",  "health_check_ok",    "health_ok",       1.0, "gte"),
            ("SYSTEM",  "simulation_tested",  "sim_trades",     50.0, "gte"),
            ("RISK",    "max_dd_within_limit","max_drawdown",    0.08, "lte"),
            ("RISK",    "ruin_prob_low",       "ruin_prob",       0.05, "lte"),
            ("RISK",    "exposure_capped",     "exposure_ok",     1.0, "gte"),
            ("PERF",    "win_rate_ok",         "win_rate",        0.48, "gte"),
            ("PERF",    "sharpe_ok",           "sharpe",          0.40, "gte"),
            ("PERF",    "profit_factor_ok",    "profit_factor",   1.20, "gte"),
            ("PERF",    "wfa_robust",          "wfa_efficiency",  0.55, "gte"),
            ("INFRA",   "broker_connected",    "broker_ok",       1.0, "gte"),
            ("INFRA",   "feed_active",         "feed_ok",         1.0, "gte"),
        ]
        blockers = []
        passed_count = 0

        for category, name, key, required, op in checks_config:
            value = params.get(key, 0.0)
            passed = value <= required if op == "lte" else value >= required
            if passed:
                passed_count += 1
            else:
                blockers.append(f"{category}/{name}")
            report.checks.append(DeploymentCheck(
                category=category, name=name, passed=passed,
                value=str(round(value, 4)), required=f"{op} {required}",
            ))

        n = len(checks_config)
        report.score = (passed_count / n) * 100
        report.blockers = blockers
        report.go_live = len(blockers) == 0

        if report.go_live:
            report.recommendation = "GO LIVE — Tous les critères validés ✅"
        elif report.score >= 80:
            report.recommendation = f"PRESQUE PRÊT — {len(blockers)} bloqueur(s) à corriger"
        else:
            report.recommendation = f"NOT READY — {len(blockers)} bloqueur(s) critiques"

        return report
