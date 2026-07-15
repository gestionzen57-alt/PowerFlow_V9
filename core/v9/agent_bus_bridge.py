"""Agent Bus Bridge V9 — pont entre le bus d'événements V9 et les assistants IA.

Connecte ZCode, Hermes (Claude Code) et Claude CLI au bus agent V9
(data/v9_agent_bus.db). Permet aux assistants IA de :

1. S'abonner à des types d'événements du pipeline V9
2. Consommer les événements en attente
3. Publier des décisions/actions dans le bus
4. Synchroniser les outcomes entre assistants

Architecture :
  Pipeline V9 → publish(event) → bus → poll(zcode_agent) → ZCode subagent
  ZCode subagent → publish(decision) → bus → poll(hermes_agent) → Hermes

Usage CLI :
  python -m core.v9.agent_bus_bridge subscribe <agent_name> <event_type>
  python -m core.v9.agent_bus_bridge poll <agent_name> [--limit 5]
  python -m core.v9.agent_bus_bridge publish <source> <event_type> <json_payload>
  python -m core.v9.agent_bus_bridge pending [--limit 20]
  python -m core.v9.agent_bus_bridge stats [--hours 24]
  python -m core.v9.agent_bus_bridge sync <from_agent> <to_agent>

Usage Python :
  from core.v9.agent_bus_bridge import BusBridge
  bridge = BusBridge(agent_name="zcode:calib-analyst")
  bridge.subscribe("regime_change")
  events = bridge.poll()
  bridge.publish("calibration_done", {"threshold": 0.15, "win_rate": 0.85})

Subagents IA connectés :
  - zcode:rule-guard        → écoute doctrine_violation, regression_detected
  - zcode:capture-ops       → écoute pipeline_status, snapshot_stale, ea_disconnected
  - zcode:calib-analyst     → écoute threshold_proposed, calibration_requested
  - zcode:data-explorer     → écoute data_anomaly, snapshot_stats
  - zcode:learn-analyst     → écoute pattern_detected, learning_cycle_done
  - zcode:session-writer    → écoute session_closed, commit_pushed
  - hermes:rule-guard       → idem (Claude Code)
  - hermes:capture-ops      → idem
  - hermes:calib-analyst    → idem
  - hermes:data-explorer    → idem
  - hermes:learn-analyst    → idem
  - hermes:session-writer   → idem
  - claude-cli:*            → idem (Claude CLI)

Compatible R18 (aucun LLM dans la boucle cognitive — le pont est code pur).
Compatible R2 (couche additive — n'affecte ni le pipeline ni le bus existant).
"""
from __future__ import annotations

import json
import sys
import time
from typing import Any

from core.v9.agent_bus import (
    cleanup,
    get_agent_stats,
    get_connection,
    get_pending_events,
    init_agent_bus_db,
    poll,
    publish,
    subscribe,
)

# Prefixes pour distinguer les assistants IA
ZCODE_PREFIX = "zcode"
HERMES_PREFIX = "hermes"
CLAUDE_CLI_PREFIX = "claude-cli"

# Abonnements par défaut pour chaque profil subagent
DEFAULT_SUBSCRIPTIONS: dict[str, list[str]] = {
    "rule-guard": [
        "doctrine_violation",
        "regression_detected",
        "assouplissement_triggered",
    ],
    "capture-ops": [
        "pipeline_status",
        "snapshot_stale",
        "ea_disconnected",
        "port_status",
    ],
    "calib-analyst": [
        "threshold_proposed",
        "calibration_requested",
        "benchmark_completed",
    ],
    "data-explorer": [
        "data_anomaly",
        "snapshot_stats",
        "db_mutation",
    ],
    "learn-analyst": [
        "pattern_detected",
        "learning_cycle_done",
        "proposal_emitted",
        "principle_scored",
    ],
    "session-writer": [
        "session_closed",
        "commit_pushed",
        "state_updated",
    ],
}


class BusBridge:
    """Pont entre un assistant IA (ZCode/Hermes/Claude CLI) et le bus V9.

    Chaque instance représente un agent IA qui peut publier et consommer
    des événements sur le bus. Le nom d'agent est préfixé par la source
    (zcode/hermes/claude-cli) pour distinguer les assistants.
    """

    def __init__(self, agent_name: str, source: str = ZCODE_PREFIX) -> None:
        """Initialise le pont pour un agent IA.

        Args:
            agent_name: nom du profil subagent (ex: "calib-analyst")
            source: source de l'assistant ("zcode", "hermes", "claude-cli")
        """
        self.agent_name = f"{source}:{agent_name}"
        self.source = source
        self.raw_name = agent_name
        init_agent_bus_db()

    def auto_subscribe(self) -> list[str]:
        """Abonne l'agent aux événements par défaut de son profil.

        Retourne la liste des event_types auxquels l'agent est maintenant abonné.
        Idempotent — ne crée pas de doublons.
        """
        event_types = DEFAULT_SUBSCRIPTIONS.get(self.raw_name, [])
        subscribed: list[str] = []
        for event_type in event_types:
            callback = f"{self.source}_handler:{event_type}"
            sub_id = subscribe(
                agent_name=self.agent_name,
                event_type=event_type,
                callback=callback,
                provider=self.source,
            )
            subscribed.append(event_type)
        return subscribed

    def poll_events(self, limit: int = 10) -> list[dict[str, Any]]:
        """Consomme jusqu'à `limit` événements en attente pour cet agent.

        Marque les événements comme consommés. Retourne [] si aucun
        abonnement actif ou aucun événement en attente.
        """
        events = poll(agent_name=self.agent_name, limit=limit)
        return events

    def publish_event(
        self,
        event_type: str,
        payload: dict[str, Any],
        severity: str = "info",
    ) -> str:
        """Publie un événement sur le bus au nom de cet agent IA.

        Retourne l'event_id créé.
        """
        enriched_payload = {
            **payload,
            "_ia_source": self.source,
            "_ia_agent": self.raw_name,
            "_ts": time.time(),
        }
        event_id = publish(
            event_type=event_type,
            source=self.agent_name,
            payload=enriched_payload,
            severity=severity,
        )
        return event_id

    def sync_to(self, target_agent: str, event_types: list[str] | None = None) -> int:
        """Synchronise les événements de cet agent vers un autre agent IA.

        Utile pour propager une décision de ZCode vers Hermes ou vice-versa.
        Retourne le nombre d'événements re-propagés.
        """
        if event_types is None:
            event_types = DEFAULT_SUBSCRIPTIONS.get(self.raw_name, [])

        conn = get_connection()
        conn.row_factory = __import__("sqlite3").Row
        try:
            count = 0
            for event_type in event_types:
                # Récupère les événements publiés par cet agent
                rows = conn.execute(
                    "SELECT * FROM events WHERE source = ? AND event_type = ? "
                    "ORDER BY created_at ASC",
                    (self.agent_name, event_type),
                ).fetchall()
                for row in rows:
                    payload = json.loads(row["payload"]) if row["payload"] else {}
                    publish(
                        event_type=f"sync:{event_type}",
                        source=f"{self.agent_name}→{target_agent}",
                        payload={**payload, "_sync_origin": self.agent_name},
                    )
                    count += 1
            return count
        finally:
            conn.close()

    @staticmethod
    def get_pending(limit: int = 20) -> list[dict[str, Any]]:
        """Événements en attente, tous agents confondus (vue globale)."""
        return get_pending_events(limit=limit)

    @staticmethod
    def get_stats(hours: int = 24) -> dict[str, dict[str, Any]]:
        """Statistiques par agent sur les dernières heures."""
        return get_agent_stats(hours=hours)

    @staticmethod
    def cleanup_old(days: int = 7) -> dict[str, int]:
        """Purge les anciens événements et logs."""
        return cleanup(days=days)


def _cmd_subscribe(args: list[str]) -> None:
    """Abonne un agent IA au bus."""
    if len(args) < 2:
        print("Usage: subscribe <agent_name> <event_type> [--source zcode|hermes|claude-cli]")
        sys.exit(1)
    agent_name = args[0]
    event_type = args[1]
    source = ZCODE_PREFIX
    if "--source" in args:
        source = args[args.index("--source") + 1]
    bridge = BusBridge(agent_name=agent_name, source=source)
    sub_id = bridge.auto_subscribe()
    if event_type not in sub_id:
        sub_id = subscribe(
            agent_name=f"{source}:{agent_name}",
            event_type=event_type,
            callback=f"{source}_handler:{event_type}",
            provider=source,
        )
        sub_id = [*sub_id, event_type]
    print(f"Subscribed {source}:{agent_name} to: {', '.join(sub_id)}")


def _cmd_poll(args: list[str]) -> None:
    """Consomme les événements en attente pour un agent."""
    if not args:
        print("Usage: poll <agent_name> [--source zcode|hermes|claude-cli] [--limit 10]")
        sys.exit(1)
    agent_name = args[0]
    source = ZCODE_PREFIX
    limit = 10
    if "--source" in args:
        source = args[args.index("--source") + 1]
    if "--limit" in args:
        limit = int(args[args.index("--limit") + 1])
    bridge = BusBridge(agent_name=agent_name, source=source)
    events = bridge.poll_events(limit=limit)
    if not events:
        print(f"No events for {source}:{agent_name} (no subscriptions or empty queue)")
    else:
        print(f"Polled {len(events)} events for {source}:{agent_name}:")
        for ev in events:
            print(f"  [{ev['event_type']}] {ev['severity']} — {ev['payload']}")


def _cmd_publish(args: list[str]) -> None:
    """Publie un événement sur le bus."""
    if len(args) < 3:
        print("Usage: publish <source> <event_type> <json_payload> [--severity info]")
        sys.exit(1)
    source_raw = args[0]
    event_type = args[1]
    payload = json.loads(args[2])
    severity = "info"
    if "--severity" in args:
        severity = args[args.index("--severity") + 1]

    # source peut être "zcode:calib-analyst" ou juste "calib-analyst"
    if ":" in source_raw:
        source, agent_name = source_raw.split(":", 1)
    else:
        source = ZCODE_PREFIX
        agent_name = source_raw

    bridge = BusBridge(agent_name=agent_name, source=source)
    event_id = bridge.publish_event(event_type, payload, severity=severity)
    print(f"Published event {event_id}: [{event_type}] from {source}:{agent_name}")


def _cmd_pending(args: list[str]) -> None:
    """Liste les événements en attente (tous agents)."""
    limit = 20
    if "--limit" in args:
        limit = int(args[args.index("--limit") + 1])
    events = BusBridge.get_pending(limit=limit)
    if not events:
        print("No pending events")
    else:
        print(f"{len(events)} pending events:")
        for ev in events:
            print(f"  [{ev['event_type']}] from {ev['source']} — {ev['severity']}")
            if ev.get("payload"):
                print(f"    payload: {json.dumps(ev['payload'], ensure_ascii=False)[:200]}")


def _cmd_stats(args: list[str]) -> None:
    """Affiche les statistiques du bus."""
    hours = 24
    if "--hours" in args:
        hours = int(args[args.index("--hours") + 1])
    stats = BusBridge.get_stats(hours=hours)
    if not stats:
        print(f"No agent activity in the last {hours}h")
    else:
        print(f"Agent stats (last {hours}h):")
        for agent, data in sorted(stats.items(), key=lambda x: -x[1]["events_processed"]):
            print(f"  {agent}: {data['events_processed']} events, avg {data['avg_duration_ms']:.1f}ms, {data['errors']} errors")


def _cmd_sync(args: list[str]) -> None:
    """Synchronise les événements d'un agent vers un autre."""
    if len(args) < 2:
        print("Usage: sync <from_agent> <to_agent> [--source zcode|hermes|claude-cli]")
        sys.exit(1)
    from_agent = args[0]
    to_agent = args[1]
    source = ZCODE_PREFIX
    if "--source" in args:
        source = args[args.index("--source") + 1]
    bridge = BusBridge(agent_name=from_agent, source=source)
    count = bridge.sync_to(to_agent)
    print(f"Synced {count} events from {source}:{from_agent} → {to_agent}")


def _cmd_setup_all(args: list[str]) -> None:
    """Abonne tous les 6 profils subagents pour ZCode, Hermes et Claude CLI."""
    sources = [ZCODE_PREFIX, HERMES_PREFIX, CLAUDE_CLI_PREFIX]
    profiles = list(DEFAULT_SUBSCRIPTIONS.keys())
    total = 0
    for source in sources:
        for profile in profiles:
            bridge = BusBridge(agent_name=profile, source=source)
            subs = bridge.auto_subscribe()
            total += len(subs)
            print(f"  {source}:{profile} → subscribed to {len(subs)} event types")
    print(f"\nTotal: {total} subscriptions created across {len(sources)} sources × {len(profiles)} profiles")


# --- CLI entry point ---

COMMANDS = {
    "subscribe": _cmd_subscribe,
    "poll": _cmd_poll,
    "publish": _cmd_publish,
    "pending": _cmd_pending,
    "stats": _cmd_stats,
    "sync": _cmd_sync,
    "setup-all": _cmd_setup_all,
}


def main() -> None:
    if len(sys.argv) < 2 or sys.argv[1] in ("-h", "--help"):
        print(__doc__)
        print("\nCommands:", ", ".join(COMMANDS.keys()))
        sys.exit(0)
    cmd = sys.argv[1]
    handler = COMMANDS.get(cmd)
    if handler is None:
        print(f"Unknown command: {cmd}")
        print("Available:", ", ".join(COMMANDS.keys()))
        sys.exit(1)
    handler(sys.argv[2:])


if __name__ == "__main__":
    main()