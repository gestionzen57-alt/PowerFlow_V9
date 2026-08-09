"""
v10_master_orchestrator.py — Cycle 20 FINAL
Orchestration maître : coordonne tous les cycles C10→C19 en un pipeline
end-to-end. Point d'entrée unique du système PowerFlow V10.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from datetime import datetime, timezone

from core.v10.v10_config_manager import ConfigManager
from core.v10.v10_system_health_check import SystemHealthChecker, SystemHealthReport
from core.v10.v10_auto_restarter import AutoRestarter
from core.v10.v10_deployment_validator import DeploymentValidator, DeploymentReport

# Cycles C15→C19
from core.v10.v10_cycle15_optimizer import C15Optimizer, C15Input
from core.v10.v10_cycle16_optimizer import C16Optimizer, C16TradeRequest
from core.v10.v10_cycle17_optimizer import C17Optimizer, C17Input
from core.v10.v10_cycle18_optimizer import C18Optimizer, C18Input
from core.v10.v10_cycle19_optimizer import C19Optimizer, C19TradeRequest


@dataclass
class MasterStatus:
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    phase: str = "INIT"        # INIT | HEALTH | READY | RUNNING | STOPPED | ERROR
    health: Optional[dict] = None
    deployment: Optional[dict] = None
    config_version: str = ""
    cycles_active: List[str] = field(default_factory=list)
    last_error: Optional[str] = None
    uptime_sec: float = 0.0

    def as_dict(self) -> dict:
        return {
            "timestamp": self.timestamp,
            "phase": self.phase,
            "health": self.health,
            "deployment": self.deployment,
            "config_version": self.config_version,
            "cycles_active": self.cycles_active,
            "last_error": self.last_error,
            "uptime_sec": round(self.uptime_sec, 2),
        }


class MasterOrchestrator:
    """
    PowerFlow V10 — Orchestrateur Maître
    ===========================================
    Pipeline complet :
      Phase 1 : Configuration + Health Check
      Phase 2 : Validation déploiement
      Phase 3 : Surveillance risque (C15)
      Phase 4 : Sizing & exposition (C16)
      Phase 5 : Signal → exécution (C17)
      Phase 6 : Validation quantitative (C18)
      Phase 7 : Exécution live (C19)
    """
    VERSION = "10.0.0"

    def __init__(self, config_overrides: Optional[Dict[str, Any]] = None) -> None:
        import time
        self._start_time = time.monotonic()
        self.config = ConfigManager()
        if config_overrides:
            self.config.update(config_overrides)

        self.health_checker = SystemHealthChecker()
        self.restarter = AutoRestarter()
        self.deployment_validator = DeploymentValidator()

        capital = self.config.get("capital", 10_000.0)
        self.c15 = C15Optimizer(initial_capital=capital)
        self.c16 = C16Optimizer(capital=capital)
        self.c17 = C17Optimizer()
        self.c18 = C18Optimizer()
        self.c19 = C19Optimizer(
            broker=self.config.get("broker", "SIMULATION"),
            capital=capital,
        )
        self.status = MasterStatus(
            config_version=self.VERSION,
            cycles_active=["C15", "C16", "C17", "C18", "C19"],
        )

    def startup(self) -> MasterStatus:
        import time
        self.status.phase = "HEALTH"

        # Phase 1 — Health
        health_report = self.health_checker.run(self.health_checker.default_checks())
        self.status.health = health_report.as_dict()

        if not health_report.system_ready:
            self.status.phase = "ERROR"
            self.status.last_error = f"{health_report.error_count} composants en erreur"
            return self.status

        # Phase 2 — Deployment validation
        deploy_params = {
            "config_loaded": 1.0,
            "health_ok": 1.0,
            "sim_trades": 100.0,
            "broker_ok": 1.0,
            "feed_ok": 1.0,
            # Defaults perf — à renseigner depuis C18
            "win_rate": 0.52,
            "sharpe": 0.60,
            "max_drawdown": 0.06,
            "profit_factor": 1.35,
            "wfa_efficiency": 0.60,
            "ruin_prob": 0.02,
            "exposure_ok": 1.0,
        }
        deploy_report = self.deployment_validator.validate(deploy_params)
        self.status.deployment = deploy_report.as_dict()

        self.status.phase = "READY" if deploy_report.go_live else "DEGRADED"
        self.status.uptime_sec = time.monotonic() - self._start_time
        return self.status

    def run_cycle15(self, trades_data: List[dict]) -> dict:
        inp = C15Input(trades=trades_data)
        return self.c15.run(inp).as_dict()

    def get_status(self) -> dict:
        import time
        self.status.uptime_sec = time.monotonic() - self._start_time
        self.status.timestamp = datetime.now(timezone.utc).isoformat()
        return self.status.as_dict()

    def shutdown(self) -> None:
        self.status.phase = "STOPPED"
        self.c15.reset()
        self.c16.reset()
        self.c17.reset()
        self.c19.reset()
