"""dedicated_agent_base.py — Base class pour les 4 agents dédiés V9 (Phase 11).

Subscribe au bus agent_bus (core/v9/agent_bus.py) sur un event_type donné,
poll en boucle, appelle on_event() pour chaque event reçu.

Pattern (CEO 2026-07-10) :
- Architecture légère : chaque agent = subprocess indépendant
- Communication inter-MCP = bus agent_bus.db (pub/sub SQLite)
- R25' : les agents LOGGUENT et AGISSENT, ne modifient aucun YAML/seuil
- R8 : 0 modif core/v9/* (consomme l'API publique d'agent_bus.py uniquement)
- Stdlib only, 0 dépendance pip

Usage :
    from core.v9.dedicated_agent_base import DedicatedAgent

    class SignalOpenTracker(DedicatedAgent):
        agent_name = "signal_open_tracker"
        event_type = "signal_open"
        poll_interval_s = 60

        def on_event(self, event: dict) -> None:
            payload = event.get("payload", {})
            self.logger.info("Signal: %s %s%%", payload.get("direction"), payload.get("confiance"))

    if __name__ == "__main__":
        SignalOpenTracker().run_forever()

CLI :
    python agents/signal_open_tracker.py --once    # 1 cycle
    python agents/signal_open_tracker.py --watch   # boucle infinie
"""
from __future__ import annotations

import argparse
import json
import logging
import sqlite3
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core.v9 import agent_bus

ROOT_DIR = Path(__file__).resolve().parent.parent.parent  # core/v9/<file> → root (3 niveaux)
AGENT_BUS_DB = ROOT_DIR / "data" / "v9_agent_bus.db"
LOGS_DIR = ROOT_DIR / "logs" / "agents"


class DedicatedAgent:
    """Base class pour un agent dédié V9.

    Subclasses définissent :
    - agent_name (str) : nom unique (ex: "signal_open_tracker")
    - event_type (str) : event_type à écouter (ex: "signal_open")
    - poll_interval_s (int) : intervalle entre 2 polls (défaut 60s)

    Et implémentent :
    - on_event(event: dict) : callback appelé pour chaque event non consommé
    """
    agent_name: str = "unnamed_agent"
    event_type: str = "unknown"
    poll_interval_s: int = 60
    log_to_file: bool = True

    def __init__(self) -> None:
        if self.agent_name == "unnamed_agent":
            raise ValueError("Subclass must define agent_name")
        if self.event_type == "unknown":
            raise ValueError("Subclass must define event_type")

        # Logger avec fichier dédié
        self.logger = logging.getLogger(f"v9.agent.{self.agent_name}")
        self.logger.setLevel(logging.INFO)
        if not self.logger.handlers:
            if self.log_to_file:
                LOGS_DIR.mkdir(parents=True, exist_ok=True)
                fh = logging.FileHandler(
                    str(LOGS_DIR / f"{self.agent_name}.log"),
                    encoding="utf-8",
                )
                fh.setFormatter(logging.Formatter(
                    "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
                    datefmt="%Y-%m-%d %H:%M:%S",
                ))
                self.logger.addHandler(fh)
            sh = logging.StreamHandler()
            sh.setFormatter(logging.Formatter(
                "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            ))
            self.logger.addHandler(sh)

        self._stopped = False
        self._n_processed = 0
        self._last_event_at: str | None = None

    def on_event(self, event: dict[str, Any]) -> None:
        """Callback appelé pour chaque event non consommé.

        Subclasses DOIVENT implémenter cette méthode.
        Pour logger/alertes Telegram, utiliser self.logger.
        """
        raise NotImplementedError

    def _subscribe(self) -> str:
        """S'abonne au bus sur event_type (idempotent)."""
        return agent_bus.subscribe(
            agent_name=self.agent_name,
            event_type=self.event_type,
            callback=f"{self.agent_name}.on_event",
        )

    def _poll_once(self) -> int:
        """Poll 1 fois le bus, traite les events non consommés. Retourne le nombre traité."""
        try:
            events = agent_bus.poll(self.agent_name, limit=10, db_path=AGENT_BUS_DB)
        except Exception as e:
            self.logger.error("Poll error: %s", e)
            return 0

        n = 0
        for event in events:
            try:
                self.on_event(event)
                self._n_processed += 1
                self._last_event_at = datetime.now(timezone.utc).isoformat()
                n += 1
            except Exception as e:
                self.logger.error("on_event error for %s: %s", event.get("id"), e)
        return n

    def run_once(self) -> int:
        """Exécute 1 cycle de polling. Retourne le nombre d'events traités."""
        self._subscribe()
        n = self._poll_once()
        self.logger.info("Cycle done: %d events processed (total=%d)", n, self._n_processed)
        return n

    def run_forever(self) -> None:
        """Boucle infinie de polling avec gestion propre du KeyboardInterrupt."""
        self.logger.info(
            "Starting %s (event_type=%s, interval=%ds)",
            self.agent_name, self.event_type, self.poll_interval_s,
        )
        self._subscribe()
        try:
            while not self._stopped:
                n = self._poll_once()
                if n > 0:
                    self.logger.info("Processed %d events (total=%d)", n, self._n_processed)
                time.sleep(self.poll_interval_s)
        except KeyboardInterrupt:
            self.logger.info("Stopped by KeyboardInterrupt")

    def stop(self) -> None:
        """Demande l'arrêt de la boucle run_forever."""
        self._stopped = True


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Dedicated agent V9 (base class).")
    p.add_argument("--once", action="store_true", help="1 cycle puis exit.")
    p.add_argument("--watch", action="store_true", help="Boucle infinie.")
    p.add_argument("--interval", type=int, default=None,
                   help="Override poll_interval_s (en secondes).")
    return p.parse_args()


def main() -> int:
    """CLI générique : lance le subclass."""
    raise NotImplementedError("Subclass must implement main() or use this base directly")