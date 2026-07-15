#!/usr/bin/env python
"""v9_session_sync.py — synchronisation automatique du contexte V9 au démarrage session.

Appelé par les hooks SessionStart de ZCode et Hermes. Effectue :

1. Régénère AGENT.md (état système auto-généré)
2. Lit les événements en attente sur le bus agent
3. Lit les dernières décisions de DECISIONS_LOG.md
4. Lit l'état courant de STATE.md
5. Publie un événement session_started sur le bus
6. Génère un résumé de contexte compact pour l'IA

Usage :
  python scripts/v9_session_sync.py --source zcode
  python scripts/v9_session_sync.py --source hermes
  python scripts/v9_session_sync.py --source claude-cli

Sortie : JSON compact sur stdout (consommé par le hook)
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

# Root du projet
ROOT = Path(__file__).resolve().parent.parent
os.chdir(ROOT)

# Ajoute le root au path
sys.path.insert(0, str(ROOT))


def run_cmd(cmd: str, timeout: int = 10) -> str:
    """Exécute une commande et retourne stdout, '' si échec."""
    try:
        r = subprocess.run(
            cmd, shell=True, capture_output=True, text=True, timeout=timeout,
            cwd=str(ROOT),
        )
        return r.stdout.strip() if r.returncode == 0 else ""
    except Exception:
        return ""


def sync_agent_md() -> bool:
    """Régénère AGENT.md via v9_sync_state.py."""
    result = run_cmd(
        f'"{ROOT / ".venv" / "Scripts" / "python.exe"}" scripts/v9_sync_state.py',
        timeout=15,
    )
    return bool(result)


def get_git_state() -> dict:
    """État git compact."""
    return {
        "branch": run_cmd("git branch --show-current"),
        "head": run_cmd("git log --oneline -1"),
        "dirty": bool(run_cmd("git status --porcelain")),
        "recent_commits": run_cmd("git log --oneline -5").split("\n") if True else [],
    }


def get_pipeline_status() -> dict:
    """Statut du pipeline de capture."""
    try:
        db = sqlite3.connect(str(ROOT / "data" / "v9_forces.db"))
        db.row_factory = sqlite3.Row
        cur = db.cursor()

        # Dernier snapshot
        cur.execute("SELECT MAX(created_at) as last_ts FROM forces_snapshots")
        row = cur.fetchone()
        last_ts = row["last_ts"] if row else None

        # Compteurs
        cur.execute("SELECT COUNT(*) as n FROM forces_snapshots")
        snapshots = cur.fetchone()[0]

        cur.execute("SELECT COUNT(*) as n FROM decisions")
        decisions = cur.fetchone()[0]

        # Win/loss
        cur.execute("""
            SELECT
                SUM(CASE WHEN is_win = 1 THEN 1 ELSE 0 END) as wins,
                SUM(CASE WHEN is_win = 0 AND closed_at IS NOT NULL THEN 1 ELSE 0 END) as losses,
                SUM(CASE WHEN closed_at IS NULL THEN 1 ELSE 0 END) as opens
            FROM paper_trades
        """)
        wl = cur.fetchone()

        db.close()

        # Age du dernier snapshot
        age_s = None
        if last_ts:
            try:
                # Parse ISO format
                dt = datetime.fromisoformat(last_ts.replace("Z", "+00:00"))
                age_s = int((datetime.now(timezone.utc) - dt).total_seconds())
            except Exception:
                pass

        return {
            "snapshots": snapshots,
            "decisions": decisions,
            "last_snapshot_ts": last_ts,
            "last_snapshot_age_s": age_s,
            "wins": wl["wins"] or 0,
            "losses": wl["losses"] or 0,
            "opens": wl["opens"] or 0,
        }
    except Exception as e:
        return {"error": str(e)}


def get_bus_events() -> dict:
    """Événements en attente sur le bus agent."""
    try:
        db = sqlite3.connect(str(ROOT / "data" / "v9_agent_bus.db"))
        db.row_factory = sqlite3.Row
        cur = db.cursor()

        # Pending events
        cur.execute("SELECT COUNT(*) as n FROM events WHERE consumed_by IS NULL")
        pending = cur.fetchone()[0]

        # Recent events (last 5)
        cur.execute("""
            SELECT event_type, source, severity, created_at
            FROM events ORDER BY created_at DESC LIMIT 5
        """)
        recent = [dict(r) for r in cur.fetchall()]

        # Subscriptions actives
        cur.execute("SELECT COUNT(*) as n FROM subscriptions WHERE enabled = 1")
        subs = cur.fetchone()[0]

        # Agent log recent
        cur.execute("""
            SELECT agent_name, action, created_at
            FROM agent_log ORDER BY created_at DESC LIMIT 5
        """)
        log_recent = [dict(r) for r in cur.fetchall()]

        db.close()
        return {
            "pending_events": pending,
            "active_subscriptions": subs,
            "recent_events": recent,
            "recent_log": log_recent,
        }
    except Exception as e:
        return {"error": str(e)}


def get_state_md_tail() -> str:
    """Lit les dernières lignes de STATE.md."""
    state_file = ROOT / "docs" / "STATE.md"
    if not state_file.exists():
        return ""
    try:
        lines = state_file.read_text(encoding="utf-8").splitlines()
        # Dernières 20 lignes non vides
        non_empty = [l for l in lines if l.strip()]
        return "\n".join(non_empty[-20:]) if non_empty else ""
    except Exception:
        return ""


def get_recent_decisions(limit: int = 3) -> list[str]:
    """Lit les dernières décisions de DECISIONS_LOG.md."""
    decisions_file = ROOT / "workspace" / "perplexity" / "memory" / "DECISIONS_LOG.md"
    if not decisions_file.exists():
        return []
    try:
        content = decisions_file.read_text(encoding="utf-8")
        # Split par sections ## §
        sections = content.split("## §")
        # Garde les dernières `limit` sections
        recent = sections[-(limit + 1):]  # +1 car le premier split est vide
        return ["## §" + s.strip() for s in recent if s.strip()][-limit:]
    except Exception:
        return []


def publish_session_started(source: str) -> str | None:
    """Publie un événement session_started sur le bus."""
    try:
        sys.path.insert(0, str(ROOT))
        from core.v9.agent_bus_bridge import BusBridge
        bridge = BusBridge(agent_name="session-writer", source=source)
        event_id = bridge.publish_event(
            "session_started",
            {
                "source": source,
                "ts": datetime.now(timezone.utc).isoformat(),
                "git_branch": run_cmd("git branch --show-current"),
            },
        )
        return event_id
    except Exception:
        return None


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", default="zcode",
                        choices=["zcode", "hermes", "claude-cli"])
    args = parser.parse_args()

    # 1. Sync AGENT.md
    sync_ok = sync_agent_md()

    # 2. Collecte contexte
    git_state = get_git_state()
    pipeline = get_pipeline_status()
    bus = get_bus_events()
    state_tail = get_state_md_tail()
    decisions = get_recent_decisions()

    # 3. Publie session_started sur le bus
    session_event = publish_session_started(args.source)

    # 4. Output JSON compact
    context = {
        "source": args.source,
        "sync_time": datetime.now(timezone.utc).isoformat(),
        "agent_md_synced": sync_ok,
        "git": git_state,
        "pipeline": pipeline,
        "bus": bus,
        "session_event_published": session_event,
        "state_md_tail": state_tail[:500] if state_tail else "",
        "recent_decisions": decisions,
    }

    print(json.dumps(context, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()