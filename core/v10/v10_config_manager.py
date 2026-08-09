"""
v10_config_manager.py — Cycle 20
Gestion centralisée de la configuration du système PowerFlow V10.
Chargement, validation, hot-reload et snapshots versio nnés.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from datetime import datetime, timezone
import copy


DEFAULT_CONFIG: Dict[str, Any] = {
    "capital": 10_000.0,
    "max_risk_per_trade": 0.01,
    "max_total_exposure": 0.20,
    "max_daily_loss": 0.02,
    "max_drawdown_stop": 0.08,
    "pairs": ["EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCAD",
              "NZDUSD", "USDCHF", "EURGBP", "EURJPY", "GBPJPY",
              "EURCAD", "AUDCAD", "AUDNZD", "CADJPY", "EURNZD"],
    "timeframes": ["M5", "M15", "H1", "H4"],
    "sessions": ["LONDON", "NEWYORK", "OVERLAP"],
    "sharpe_window": 50,
    "kelly_cap": 0.25,
    "min_confluence_score": 65.0,
    "min_signal_score": 60.0,
    "broker": "SIMULATION",
    "simulation_mode": True,
    "log_level": "INFO",
    "version": "10.0.0",
}


@dataclass
class ConfigSnapshot:
    version: str
    timestamp: str
    config: Dict[str, Any]

    def as_dict(self) -> dict:
        return {
            "version": self.version,
            "timestamp": self.timestamp,
            "config": self.config,
        }


class ConfigManager:
    """
    Gestionnaire de configuration avec validation, historique et hot-reload.
    """

    REQUIRED_KEYS = [
        "capital", "max_risk_per_trade", "max_total_exposure",
        "pairs", "timeframes", "broker",
    ]

    def __init__(self) -> None:
        self._config: Dict[str, Any] = copy.deepcopy(DEFAULT_CONFIG)
        self._history: List[ConfigSnapshot] = []
        self._save_snapshot("init")

    def get(self, key: str, default: Any = None) -> Any:
        return self._config.get(key, default)

    def set(self, key: str, value: Any) -> None:
        self._config[key] = value

    def update(self, updates: Dict[str, Any]) -> List[str]:
        errors = self._validate(updates)
        if errors:
            return errors
        self._config.update(updates)
        self._save_snapshot("update")
        return []

    def _validate(self, cfg: Dict[str, Any]) -> List[str]:
        errors = []
        if "capital" in cfg and cfg["capital"] <= 0:
            errors.append("capital must be > 0")
        if "max_risk_per_trade" in cfg and not 0 < cfg["max_risk_per_trade"] <= 0.05:
            errors.append("max_risk_per_trade must be in (0, 0.05]")
        if "max_total_exposure" in cfg and not 0 < cfg["max_total_exposure"] <= 0.50:
            errors.append("max_total_exposure must be in (0, 0.50]")
        return errors

    def validate_required(self) -> List[str]:
        return [k for k in self.REQUIRED_KEYS if k not in self._config]

    def _save_snapshot(self, tag: str) -> None:
        v = f"{self._config.get('version', '?')}-{tag}-{len(self._history)}"
        self._history.append(ConfigSnapshot(
            version=v,
            timestamp=datetime.now(timezone.utc).isoformat(),
            config=copy.deepcopy(self._config),
        ))

    def rollback(self, steps: int = 1) -> bool:
        if len(self._history) <= steps:
            return False
        snap = self._history[-(steps + 1)]
        self._config = copy.deepcopy(snap.config)
        return True

    def snapshot(self) -> dict:
        return copy.deepcopy(self._config)

    def reset(self) -> None:
        self._config = copy.deepcopy(DEFAULT_CONFIG)
        self._history.clear()
        self._save_snapshot("reset")
