"""
v10_auto_restarter.py — Cycle 20
Redémarrage automatique des composants en cas d'erreur critique.
Politique : backoff exponentiel, max retries, circuit breaker.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional
from datetime import datetime, timezone
import time


@dataclass
class RestartEvent:
    component: str
    attempt: int
    success: bool
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    error: Optional[str] = None

    def as_dict(self) -> dict:
        return {
            "component": self.component,
            "attempt": self.attempt,
            "success": self.success,
            "timestamp": self.timestamp,
            "error": self.error,
        }


class AutoRestarter:
    """
    Gère le redémarrage des composants avec backoff exponentiel.
    Circuit breaker après MAX_RETRIES échecs consécutifs.
    """
    MAX_RETRIES = 5
    BASE_DELAY_SEC = 1.0
    MAX_DELAY_SEC = 30.0

    def __init__(self) -> None:
        self._attempts: Dict[str, int] = {}
        self._circuit_open: Dict[str, bool] = {}
        self._history: List[RestartEvent] = []

    def restart(self, component: str, restart_fn: Callable[[], bool]) -> RestartEvent:
        if self._circuit_open.get(component, False):
            evt = RestartEvent(
                component=component,
                attempt=self._attempts.get(component, 0),
                success=False,
                error="CIRCUIT_OPEN",
            )
            self._history.append(evt)
            return evt

        attempt = self._attempts.get(component, 0) + 1
        self._attempts[component] = attempt

        # Backoff exponentiel
        delay = min(self.BASE_DELAY_SEC * (2 ** (attempt - 1)), self.MAX_DELAY_SEC)
        if attempt > 1:
            time.sleep(min(delay, 0.1))  # capé à 100ms en simulation

        try:
            success = restart_fn()
            error = None
        except Exception as e:
            success = False
            error = str(e)

        if success:
            self._attempts[component] = 0
            self._circuit_open[component] = False
        elif attempt >= self.MAX_RETRIES:
            self._circuit_open[component] = True
            error = f"CIRCUIT_OPEN after {attempt} attempts"

        evt = RestartEvent(
            component=component, attempt=attempt,
            success=success, error=error,
        )
        self._history.append(evt)
        return evt

    def is_circuit_open(self, component: str) -> bool:
        return self._circuit_open.get(component, False)

    def reset_circuit(self, component: str) -> None:
        self._circuit_open[component] = False
        self._attempts[component] = 0

    def history(self) -> List[dict]:
        return [e.as_dict() for e in self._history]

    def reset(self) -> None:
        self._attempts.clear()
        self._circuit_open.clear()
        self._history.clear()
