"""
v10_live_connector.py — Cycle 19
Gestionnaire de connexion live : état de connexion, heartbeat, reconnexion auto.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Callable, List, Optional
from datetime import datetime, timezone
import time


@dataclass
class ConnectionState:
    connected: bool = False
    broker: str = ""
    last_heartbeat: Optional[str] = None
    reconnect_attempts: int = 0
    latency_ms: float = 0.0
    error: Optional[str] = None

    def as_dict(self) -> dict:
        return {
            "connected": self.connected,
            "broker": self.broker,
            "last_heartbeat": self.last_heartbeat,
            "reconnect_attempts": self.reconnect_attempts,
            "latency_ms": round(self.latency_ms, 2),
            "error": self.error,
        }


class LiveConnector:
    """
    Abstraction de la connexion broker live.
    Mode simulation : connect() et heartbeat() factices.
    """
    MAX_RECONNECT = 5
    HEARTBEAT_INTERVAL_SEC = 30

    def __init__(self, broker: str = "SIMULATION") -> None:
        self.state = ConnectionState(broker=broker)
        self._on_connect_callbacks: List[Callable] = []
        self._on_disconnect_callbacks: List[Callable] = []

    def on_connect(self, fn: Callable) -> None:
        self._on_connect_callbacks.append(fn)

    def on_disconnect(self, fn: Callable) -> None:
        self._on_disconnect_callbacks.append(fn)

    def connect(self) -> bool:
        t0 = time.monotonic()
        # Simulation : connexion toujours réussie
        latency = (time.monotonic() - t0) * 1000
        self.state.connected = True
        self.state.latency_ms = latency
        self.state.error = None
        self.state.last_heartbeat = datetime.now(timezone.utc).isoformat()
        for cb in self._on_connect_callbacks:
            cb(self.state)
        return True

    def disconnect(self) -> None:
        self.state.connected = False
        for cb in self._on_disconnect_callbacks:
            cb(self.state)

    def heartbeat(self) -> bool:
        if not self.state.connected:
            return False
        self.state.last_heartbeat = datetime.now(timezone.utc).isoformat()
        return True

    def reconnect(self) -> bool:
        if self.state.reconnect_attempts >= self.MAX_RECONNECT:
            self.state.error = "MAX_RECONNECT_REACHED"
            return False
        self.state.reconnect_attempts += 1
        return self.connect()

    def reset(self) -> None:
        self.state = ConnectionState(broker=self.state.broker)
