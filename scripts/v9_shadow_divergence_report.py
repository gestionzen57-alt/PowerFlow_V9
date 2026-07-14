"""v9_shadow_divergence_report.py — P2 Shadow mode, volet alerte (2026-07-13).

Compare les décisions `source_type='shadow'` (core/v9/shadow_evaluator.py,
hook orchestrator gated par V9_SHADOW_MODE_ENABLED) à leur pendant
`source_type='live'` pour le même snapshot_id, et rapporte les
divergences d'action (ex: live='preparer_entree' vs shadow='aucune_action'
— le kill switch expérimental aurait bloqué un trade que le live a pris,
ou l'inverse).

R18 : ce script est le SEUL endroit du chantier P2 qui parle au réseau
(Telegram). Jamais dans core/v9/orchestrator.py ni core/v9/shadow_evaluator.py
— aucun appel réseau dans le chemin cognitif live. Ce script tourne en
dehors du pipeline (manuel ou cron), jamais appelé par run_chain().

Usage :
    # Rapport seul (aucun envoi Telegram) — défaut
    python scripts/v9_shadow_divergence_report.py

    # Envoi Telegram si au moins une divergence dans la fenêtre
    python scripts/v9_shadow_divergence_report.py --send

    # Fenêtre de lookback personnalisée (défaut 24h)
    python scripts/v9_shadow_divergence_report.py --hours 6
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from core.v9.config import DB_PATH  # noqa: E402

DEFAULT_HOURS = 24.0
CONFIG_PATH = ROOT_DIR / "config" / "telegram.json"


def _ensure_utf8_stdout() -> None:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")


def _connect(db_path: Path) -> sqlite3.Connection:
    if not db_path.exists():
        raise FileNotFoundError(f"DB introuvable : {db_path}")
    conn = sqlite3.connect(str(db_path), timeout=60)
    conn.row_factory = sqlite3.Row
    return conn


def find_divergences(
    conn: sqlite3.Connection, *, since: datetime
) -> list[dict[str, Any]]:
    """Paires (live, shadow) pour un même snapshot_id où l'action diffère.

    Ne compare que les snapshots ayant les deux source_type présents —
    un snapshot sans passage shadow (hook désactivé ou en échec) n'est
    jamais rapporté comme divergent."""
    rows = conn.execute(
        "SELECT snapshot_id, source_type, action, direction, confiance, "
        "       symbol, timeframe, timestamp "
        "FROM decisions "
        "WHERE source_type IN ('live', 'shadow') AND timestamp >= ? "
        "ORDER BY snapshot_id, source_type",
        (since.isoformat(),),
    ).fetchall()

    by_snapshot: dict[str, dict[str, sqlite3.Row]] = {}
    for row in rows:
        by_snapshot.setdefault(row["snapshot_id"], {})[row["source_type"]] = row

    divergences = []
    for snapshot_id, pair in by_snapshot.items():
        live = pair.get("live")
        shadow = pair.get("shadow")
        if live is None or shadow is None:
            continue
        if live["action"] == shadow["action"]:
            continue
        divergences.append({
            "snapshot_id": snapshot_id,
            "symbol": live["symbol"],
            "timeframe": live["timeframe"],
            "timestamp": live["timestamp"],
            "live_action": live["action"],
            "live_direction": live["direction"],
            "live_confiance": live["confiance"],
            "shadow_action": shadow["action"],
            "shadow_direction": shadow["direction"],
            "shadow_confiance": shadow["confiance"],
        })
    return divergences


def _format_report(divergences: list[dict[str, Any]], hours: float) -> str:
    if not divergences:
        return f"[SHADOW] Aucune divergence live/shadow sur les {hours:.0f}h dernières."
    lines = [f"[SHADOW] {len(divergences)} divergence(s) live/shadow sur les {hours:.0f}h dernières :"]
    for d in divergences:
        lines.append(
            f"  - {d['symbol']} {d['timeframe']} {d['timestamp']} "
            f"live={d['live_action']}({d['live_direction']},conf={d['live_confiance']}) "
            f"shadow={d['shadow_action']}({d['shadow_direction']},conf={d['shadow_confiance']})"
        )
    return "\n".join(lines)


def _load_telegram_config_safe() -> dict[str, str] | None:
    """Best-effort — jamais de sys.exit (ce script n'est pas interactif)."""
    try:
        if not CONFIG_PATH.exists():
            return None
        cfg = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        token = str(cfg.get("BOT_TOKEN", "")).strip()
        chat_id = str(cfg.get("CHAT_ID", "")).strip()
        if not token or not chat_id or token == "TON_TOKEN_ICI":
            return None
        return {"token": token, "chat_id": chat_id}
    except Exception:
        return None


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--hours", type=float, default=DEFAULT_HOURS)
    parser.add_argument("--send", action="store_true", help="Envoie le rapport via Telegram (défaut: rapport seul)")
    parser.add_argument("--db-path", type=Path, default=None)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    _ensure_utf8_stdout()
    args = _parse_args(argv)
    db_path = args.db_path or DB_PATH
    since = datetime.now(timezone.utc) - timedelta(hours=args.hours)

    conn = _connect(db_path)
    try:
        divergences = find_divergences(conn, since=since)
    finally:
        conn.close()

    report = _format_report(divergences, args.hours)
    print(report)

    if args.send and divergences:
        cfg = _load_telegram_config_safe()
        if cfg is None:
            print("\n[SEND] config/telegram.json absent ou invalide — envoi ignoré.")
            return 0
        from scripts.v9_telegram_notifier import send_telegram  # noqa: PLC0415
        ok = send_telegram(report, cfg, timeout=15)
        print(f"\n[SEND] {'OK' if ok else 'ECHEC'}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
