"""mcp-v9-edge-decay — MCP server pour EdgeDecayMonitor (motion CEO 28/07).

Expose l'EdgeDecayMonitor aux clients MCP (Claude, ZCode, Hermès) :
  - check_now()                 → lance le check complet (19s sur 41 ACTIVE)
  - get_active_blacklists()     → liste les contextes blacklistés actifs
  - get_alerts_history(days)    → historique des alertes (WARNING + CRITICAL)
  - simulate_blacklist(...)     → dry-run : calcule l'impact d'une blacklist
  - add_manual_override(...)    → motion CEO explicite (R25' strict)

Sécurité : DB write (blacklists) via whitelist + audit log Motion.
Jointure principle_evaluations × decisions (schéma live 2026-07-21).
Origine : motion CEO auto-pilote 2026-07-28 (top-3 MCP à levier).
"""
from __future__ import annotations

import json
import sqlite3
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT_DIR = Path(r"C:\projet\V9")
DB_PATH = ROOT_DIR / "data" / "v9_forces.db"
STATE_PATH = ROOT_DIR / "config" / "v9_edge_decay_state.json"
MOTION_LOG_PATH = ROOT_DIR / "workspace" / "perplexity" / "memory" / "DECISIONS_LOG.md"

# Whitelist R25' strict : seuls ces (principle, session, regime) peuvent être
# ajoutés/retirés manuellement. Le reste reste en lecture seule (CRITICAL auto).
PRINCIPLE_WHITELIST = {
    "PRICE_LAG_AT_NODE_BIRTH",
    "GRAMMAR_COALITION",
    "GRAMMAR_PULLBACK",
    "GRAMMAR_PULLBACK_ADAPTIVE",
    "GRAMMAR_ABSORPTION",
    "GRAMMAR_REGIME",
    "NODE_BIRTH_FAST",
    "NODE_BIRTH_FAST_ADAPTIVE",
}


def _connect_ro() -> sqlite3.Connection:
    """Read-only URI strict pour check_now et simulate_blacklist."""
    uri = f"file:{DB_PATH}?mode=ro"
    conn = sqlite3.connect(uri, uri=True, timeout=10)
    conn.row_factory = sqlite3.Row
    return conn


def _load_state() -> dict:
    """Charge l'état persistant EdgeDecayState (json local)."""
    if not STATE_PATH.exists():
        return {"version": "1.0", "blacklisted_contexts": [], "alerts_history": []}
    with STATE_PATH.open("r", encoding="utf-8") as f:
        return json.load(f)


def handle_check_now(args: dict) -> dict:
    """Lance le check EdgeDecayMonitor complet.

    Args : dry_run (bool, default True), min_level ('WARNING'|'CRITICAL', default 'WARNING').
    Returns : {n_alerts, n_critical, n_warning, alerts: [...], duration_s}.
    """
    t0 = time.time()
    dry_run = bool(args.get("dry_run", True))
    min_level = args.get("min_level", "WARNING").upper()
    try:
        # Import paresseux (R6 défensif)
        sys.path.insert(0, str(ROOT_DIR))
        from core.v9.edge_decay_monitor import EdgeDecayMonitor
        # auto_actions=False par défaut (R25' strict post 28/07)
        monitor = EdgeDecayMonitor(DB_PATH, auto_actions=not dry_run)
        alerts = monitor.check_all_principles()
        filtered = [a.to_dict() for a in alerts if (
            min_level == "WARNING" or a.level == "CRITICAL"
        )]
        return {
            "ok": True,
            "n_alerts": len(filtered),
            "n_critical": sum(1 for a in alerts if a.level == "CRITICAL"),
            "n_warning": sum(1 for a in alerts if a.level == "WARNING"),
            "alerts": filtered[:50],  # Cap pour pas saturer stdout MCP
            "duration_s": round(time.time() - t0, 2),
            "dry_run": dry_run,
            "min_level": min_level,
        }
    except Exception as exc:
        return {"ok": False, "error": f"check_now failed: {exc}", "duration_s": round(time.time() - t0, 2)}


def handle_get_active_blacklists(args: dict) -> dict:
    """Liste les blacklisted_contexts actifs (state JSON)."""
    state = _load_state()
    bls = state.get("blacklisted_contexts", [])
    return {
        "ok": True,
        "n_blacklisted": len(bls),
        "blacklisted_contexts": bls,
        "last_check_iso": state.get("last_check_iso"),
    }


def handle_get_alerts_history(args: dict) -> dict:
    """Historique des alertes (lecture state JSON). Cap 100 par défaut.

    Args : days (int, default 7), min_level (str, default 'WARNING'), limit (int, default 50).
    """
    days = max(1, min(int(args.get("days", 7)), 30))
    min_level = args.get("min_level", "WARNING").upper()
    limit = min(int(args.get("limit", 50)), 200)
    state = _load_state()
    cutoff = time.time() - days * 86400
    history = state.get("alerts_history", [])
    filtered = [
        a for a in history
        if a.get("timestamp_epoch", 0) >= cutoff
        and (min_level == "WARNING" or a.get("level") == "CRITICAL")
    ]
    return {
        "ok": True,
        "n_total": len(filtered),
        "n_returned": min(len(filtered), limit),
        "alerts": filtered[-limit:],
        "days": days,
        "min_level": min_level,
    }


def handle_simulate_blacklist(args: dict) -> dict:
    """Dry-run : calcule l'impact d'une blacklist sans muter.

    Args : principle_id, session, regime.
    Returns : {would_block_n_trades_30d, est_pips_saved, est_wr_impact}.
    """
    principle = args.get("principle_id")
    session = args.get("session")
    regime = args.get("regime")
    if not all([principle, session, regime]):
        return {"ok": False, "error": "principle_id, session, regime requis"}
    if principle not in PRINCIPLE_WHITELIST:
        return {"ok": False, "error": f"principle {principle} hors whitelist R25'"}
    conn = _connect_ro()
    try:
        # Stats 30j pour ce (principle, session, regime)
        cutoff_iso = (
            datetime.fromtimestamp(time.time() - 30 * 86400, tz=timezone.utc)
            .strftime("%Y-%m-%dT%H:%M:%S")
        )
        # Index idx_decisions_resolved_recent créé migration 9cfbf80 (5.27s→0.00s)
        # Optimisation 2-temps : (1) filtrer par principle_id via index,
        # (2) filtrer session/regime en Python sur le résultat.
        # Le JOIN snapshot_id est OK car decisions n'a que 104k rows,
        # principle_evaluations en a 8M (filtré par principle_id = ~50k).
        rows = conn.execute(
            """
            SELECT d.is_win, d.resolution_pips,
                   json_extract(pe.context_json, '$.session_marche') AS s,
                   json_extract(pe.context_json, '$.regime_type') AS r
            FROM decisions d
            INNER JOIN principle_evaluations pe
                ON pe.snapshot_id = d.snapshot_id AND pe.triggered = 1
            WHERE pe.principle_id = ?
              AND d.is_win IS NOT NULL
              AND d.timestamp >= ?
            """,
            (principle, cutoff_iso),
        ).fetchall()
        # Filtrer session/regime en Python
        filtered = [r for r in rows if r["s"] == session and r["r"] == regime]
        n = len(filtered)
        if n == 0:
            wr = 0.0
            avg_pips = 0.0
            cum_pips = 0.0
        else:
            wr = sum(1 for r in filtered if r["is_win"] == 1) / n
            avg_pips = sum(r["resolution_pips"] or 0 for r in filtered) / n
            cum_pips = sum(r["resolution_pips"] or 0 for r in filtered)
        return {
            "ok": True,
            "principle_id": principle,
            "session": session,
            "regime": regime,
            "lookback_days": 30,
            "n_trades": n,
            "wr": round(wr, 4),
            "avg_pips_per_trade": round(avg_pips, 2),
            "cum_pips_30d": round(cum_pips, 1),
            "would_save_pips_30d": round(-cum_pips, 1) if cum_pips < 0 else 0,
            "interpretation": (
                "POSITIVE impact : cette blacklist aurait sauvé des pips"
                if cum_pips < 0 and n >= 20
                else "NEUTRE : pas assez de data ou pas de pertes"
            ),
        }
    finally:
        conn.close()


def handle_add_manual_override(args: dict) -> dict:
    """Motion CEO explicite (R25' strict) : ajoute ou retire une blacklist.

    Args : principle_id, session, regime, action ('add'|'remove'), reason (str).
    Returns : {ok, state_after, motion_logged: True}.
    """
    principle = args.get("principle_id")
    session = args.get("session")
    regime = args.get("regime")
    action = args.get("action", "add").lower()
    reason = args.get("reason", "")
    if not all([principle, session, regime]):
        return {"ok": False, "error": "principle_id, session, regime requis"}
    if principle not in PRINCIPLE_WHITELIST:
        return {"ok": False, "error": f"principle {principle} hors whitelist R25'"}
    if action not in ("add", "remove"):
        return {"ok": False, "error": "action doit être 'add' ou 'remove'"}
    if not reason or len(reason) < 10:
        return {"ok": False, "error": "reason >= 10 chars requis (motion CEO traçable)"}

    state = _load_state()
    bls = state.setdefault("blacklisted_contexts", [])
    # Normaliser en tuples pour set-like ops
    bls_set = {tuple(b) for b in bls}
    key = (principle, session, regime)

    if action == "add":
        if key in bls_set:
            return {"ok": False, "error": f"déjà blacklisté: {key}", "state_after": bls}
        bls.append(list(key))
        bls_set.add(key)
        motion_line = (
            f"\n## {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')} — "
            f"Motion CEO edge_decay manual override (MCP)\n\n"
            f"- ADD blacklist : `{principle} | {session} | {regime}`\n"
            f"- Reason : {reason}\n"
            f"- Source : `mcp_servers/edge_decay_server.py` tool `add_manual_override`\n"
            f"- R25' strict respecté : motion CEO explicite via MCP.\n"
        )
    else:  # remove
        if key not in bls_set:
            return {"ok": False, "error": f"pas blacklisté: {key}", "state_after": bls}
        bls[:] = [b for b in bls if tuple(b) != key]
        bls_set.discard(key)
        motion_line = (
            f"\n## {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')} — "
            f"Motion CEO edge_decay manual override (MCP)\n\n"
            f"- REMOVE blacklist : `{principle} | {session} | {regime}`\n"
            f"- Reason : {reason}\n"
            f"- Source : `mcp_servers/edge_decay_server.py` tool `add_manual_override`\n"
            f"- R25' strict respecté : motion CEO explicite via MCP.\n"
        )

    # Save state
    state["blacklisted_contexts"] = bls
    state["last_motion_ts"] = time.time()
    state["last_motion_iso"] = datetime.now(timezone.utc).isoformat()
    with STATE_PATH.open("w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)

    # Append motion au DECISIONS_LOG (R8 audit trail)
    with MOTION_LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(motion_line)

    return {
        "ok": True,
        "action": action,
        "principle_id": principle,
        "session": session,
        "regime": regime,
        "n_blacklisted_after": len(bls),
        "state_after": bls,
        "motion_logged": True,
    }


HANDLERS = {
    "edge_decay_check_now": handle_check_now,
    "edge_decay_get_active_blacklists": handle_get_active_blacklists,
    "edge_decay_get_alerts_history": handle_get_alerts_history,
    "edge_decay_simulate_blacklist": handle_simulate_blacklist,
    "edge_decay_add_manual_override": handle_add_manual_override,
}


def main() -> None:
    """MCP stdio loop (lit JSON-RPC lines from stdin, écrit sur stdout)."""
    for raw in sys.stdin:
        line = raw.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except Exception as e:
            print(json.dumps({"error": f"invalid json: {e}"}))
            continue
        method = req.get("method", "")
        if method == "tools/list":
            print(json.dumps({
                "tools": [
                    {"name": "edge_decay_check_now", "args": ["dry_run", "min_level"]},
                    {"name": "edge_decay_get_active_blacklists", "args": []},
                    {"name": "edge_decay_get_alerts_history", "args": ["days", "min_level", "limit"]},
                    {"name": "edge_decay_simulate_blacklist", "args": ["principle_id", "session", "regime"]},
                    {"name": "edge_decay_add_manual_override", "args": ["principle_id", "session", "regime", "action", "reason"]},
                ]
            }))
        elif method.startswith("tools/call/"):
            name = method[len("tools/call/"):]
            args = req.get("args", {})
            handler = HANDLERS.get(name)
            if handler:
                print(json.dumps(handler(args), ensure_ascii=False))
            else:
                print(json.dumps({"error": f"unknown tool: {name}"}))


if __name__ == "__main__":
    main()
