#!/usr/bin/env python3
"""v9_daily_report.py — Rapport journalier agrégé V9 (Phase 9.7+).

Doctrine : lecture seule. Agrège plusieurs sources pour produire un
résumé quotidien en 1 écran — facilite le suivi du pipeline live
sans avoir à lancer 4 scripts différents.

Sources agrégées :
  - DB live (data/v9_forces.db) : snapshots, signaux, décisions,
    paper_trades, WIN/LOSS
  - v9_validate_coherence (intégré ici pour éviter subprocess)
  - v9_scoring (intégré ici pour éviter subprocess)
  - Logs Telegram (telegram_notifier.log) : nb messages envoyés

Usage :
    python scripts/v9_daily_report.py
    python scripts/v9_daily_report.py --json
    python scripts/v9_daily_report.py --no-color   # pour cron/log

Doctrine : aucune écriture en DB, aucune logique d'exécution d'ordre.
"""
from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from core.v9.db_schema import get_connection  # noqa: E402

# ---------- Constantes ----------


WINDOW_24H = timedelta(hours=24)
WINDOW_7D = timedelta(days=7)

# Chemins logs (best-effort — log absent = 0)
LOG_TELEGRAM = ROOT_DIR / "logs" / "telegram_notifier.log"


# ---------- Helpers ----------


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.isoformat()


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (table,),
    ).fetchone()
    return row is not None


def _count_where(conn: sqlite3.Connection, table: str, where: str = "1",
                 params: tuple = ()) -> int:
    if not _table_exists(conn, table):
        return 0
    try:
        r = conn.execute(
            f"SELECT COUNT(*) AS n FROM {table} WHERE {where}", params
        ).fetchone()
        return int(r[0]) if r else 0
    except sqlite3.OperationalError:
        return 0


def _count_since(conn: sqlite3.Connection, table: str, since_iso: str,
                 ts_col: str = "timestamp") -> int:
    if not _table_exists(conn, table):
        return 0
    try:
        r = conn.execute(
            f"SELECT COUNT(*) AS n FROM {table} WHERE {ts_col} >= ?",
            (since_iso,),
        ).fetchone()
        return int(r[0]) if r else 0
    except sqlite3.OperationalError:
        return 0


# ---------- Sections du rapport ----------


def section_snapshots(conn: sqlite3.Connection) -> dict:
    """Snapshots forces + derniers TF actifs."""
    last_ts_row = None
    if _table_exists(conn, "forces_snapshots"):
        try:
            last_ts_row = conn.execute(
                "SELECT MAX(timestamp) AS ts FROM forces_snapshots"
            ).fetchone()
        except sqlite3.OperationalError:
            pass

    total = _count_where(conn, "forces_snapshots")
    last_24h = _count_since(conn, "forces_snapshots",
                            _iso(_now_utc() - WINDOW_24H))

    tfs = []
    if _table_exists(conn, "forces_snapshots"):
        try:
            rows = conn.execute(
                "SELECT DISTINCT timeframe FROM forces_snapshots "
                "WHERE timestamp >= ? ORDER BY timeframe",
                (_iso(_now_utc() - WINDOW_24H),),
            ).fetchall()
            tfs = [r[0] for r in rows if r[0]]
        except sqlite3.OperationalError:
            pass

    return {
        "total_snapshots": total,
        "snapshots_24h": last_24h,
        "last_snapshot": last_ts_row["ts"] if last_ts_row else None,
        "timeframes_actifs_24h": tfs,
    }


def section_signals(conn: sqlite3.Connection) -> dict:
    """Signaux directionnels 24h + lifetime."""
    total_dir = _count_where(
        conn, "signals",
        "direction IS NOT NULL AND direction != 'neutre'",
    )
    total_24h = _count_since(
        conn, "signals", _iso(_now_utc() - WINDOW_24H),
    )
    dir_24h = _count_where(
        conn, "signals",
        "timestamp >= ? AND direction IS NOT NULL AND direction != 'neutre'",
        (_iso(_now_utc() - WINDOW_24H),),
    )
    return {
        "signaux_directionnels_total": total_dir,
        "signaux_24h_total": total_24h,
        "signaux_24h_directionnels": dir_24h,
    }


def section_decisions(conn: sqlite3.Connection) -> dict:
    """Décisions 24h, WIN/LOSS."""
    dec_24h = _count_since(conn, "decisions", _iso(_now_utc() - WINDOW_24H))
    dec_dir_24h = _count_where(
        conn, "decisions",
        "timestamp >= ? AND direction IS NOT NULL AND direction != 'neutre'",
        (_iso(_now_utc() - WINDOW_24H),),
    )
    win = _count_where(conn, "decisions", "is_win = 1")
    loss = _count_where(conn, "decisions", "is_win = 0")
    unresolved = _count_where(conn, "decisions", "is_win IS NULL")
    winrate = (win / (win + loss) * 100) if (win + loss) > 0 else None
    return {
        "decisions_24h": dec_24h,
        "decisions_24h_directionnelles": dec_dir_24h,
        "win_total": win,
        "loss_total": loss,
        "unresolved_total": unresolved,
        "winrate_pct": round(winrate, 1) if winrate is not None else None,
    }


def section_paper_trades(conn: sqlite3.Connection) -> dict:
    """Paper-trades ouverts / fermés."""
    if not _table_exists(conn, "paper_trades"):
        return {"available": False}
    try:
        open_ = conn.execute(
            "SELECT COUNT(*) FROM paper_trades WHERE closed_at IS NULL"
        ).fetchone()[0]
        closed = conn.execute(
            "SELECT COUNT(*) FROM paper_trades WHERE closed_at IS NOT NULL"
        ).fetchone()[0]
    except sqlite3.OperationalError:
        return {"available": False}
    return {
        "available": True,
        "open": int(open_),
        "closed": int(closed),
    }


def section_coherence(conn: sqlite3.Connection) -> dict:
    """Rejoue les 7 checks validate-coherence et résume."""
    # Import via importlib : validate-coherence.py contient un tiret dans
    # son nom, donc non importable comme `scripts.validate_coherence`.
    try:
        import importlib.util
        from pathlib import Path
        vc_path = Path(__file__).resolve().parent / "validate-coherence.py"
        spec = importlib.util.spec_from_file_location("validate_coherence", vc_path)
        vc = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(vc)
        results = vc.run_all_checks(conn)
        return {
            "available": True,
            "summary": vc.summarize(results),
            "details": [
                {
                    "check": r["check"],
                    "status": r["status"],
                    "count": r["count"],
                }
                for r in results
            ],
        }
    except Exception as exc:  # noqa: BLE001
        return {"available": False, "error": str(exc)}


def section_scoring(conn: sqlite3.Connection) -> dict:
    """Win rate par principe — top 5."""
    try:
        import scripts.v9_scoring as sc
        scoring = sc._compute_scoring(conn, min_samples=0)
        total_resolved = sc._total_resolved(conn)
        # Top 5 par win_rate DESC
        top = [r for r in scoring if r["win_rate"] is not None][:5]
        return {
            "available": True,
            "total_decisions_resolues": total_resolved,
            "principes_scores": [
                {
                    "principle_id": r["principle_id"],
                    "nb": r["nb"],
                    "win_rate": round(r["win_rate"] * 100, 1),
                }
                for r in top
            ],
        }
    except Exception as exc:  # noqa: BLE001
        return {"available": False, "error": str(exc)}


def section_telegram_logs() -> dict:
    """Parse logs/telegram_notifier.log pour nb messages envoyés 24h."""
    if not LOG_TELEGRAM.exists():
        return {"available": False}
    try:
        cutoff = _now_utc() - WINDOW_24H
        pattern = re.compile(
            r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}).*Message Telegram envoyé"
        )
        count_24h = 0
        total = 0
        for line in LOG_TELEGRAM.read_text(encoding="utf-8", errors="replace").splitlines():
            m = pattern.match(line)
            if not m:
                continue
            total += 1
            try:
                ts = datetime.strptime(m.group(1), "%Y-%m-%d %H:%M:%S")
                ts = ts.replace(tzinfo=timezone.utc)
                if ts >= cutoff:
                    count_24h += 1
            except ValueError:
                pass
        return {
            "available": True,
            "messages_total": total,
            "messages_24h": count_24h,
            "log_path": str(LOG_TELEGRAM),
        }
    except Exception as exc:  # noqa: BLE001
        return {"available": False, "error": str(exc)}


# ---------- Format console ----------


def format_console(report: dict, use_color: bool = True) -> str:
    """Génère le rapport console 1-écran."""
    today = _now_utc().strftime("%Y-%m-%d %H:%M UTC")
    lines = []
    bar = "═" * 60
    sep = "─" * 60

    lines.append(bar)
    lines.append(f"  V9 Daily Report — {today}")
    lines.append(bar)

    # Snapshots
    s = report["snapshots"]
    lines.append(f"\n[SNAPSHOTS]")
    lines.append(f"  Total            : {s['total_snapshots']:>6}")
    lines.append(f"  24h              : {s['snapshots_24h']:>6}")
    lines.append(f"  Dernier snapshot : {s['last_snapshot'] or 'N/A'}")
    if s["timeframes_actifs_24h"]:
        lines.append(f"  TF actifs (24h)  : {', '.join(s['timeframes_actifs_24h'])}")

    # Signals
    sig = report["signals"]
    lines.append(f"\n[SIGNAUX]")
    lines.append(f"  Total directionnels     : {sig['signaux_directionnels_total']:>6}")
    lines.append(f"  24h (tous)              : {sig['signaux_24h_total']:>6}")
    lines.append(f"  24h directionnels       : {sig['signaux_24h_directionnels']:>6}")

    # Decisions
    dec = report["decisions"]
    lines.append(f"\n[DECISIONS]")
    lines.append(f"  24h (toutes)            : {dec['decisions_24h']:>6}")
    lines.append(f"  24h directionnelles     : {dec['decisions_24h_directionnelles']:>6}")
    lines.append(f"  WIN (lifetime)          : {dec['win_total']:>6}")
    lines.append(f"  LOSS (lifetime)         : {dec['loss_total']:>6}")
    lines.append(f"  Unresolved              : {dec['unresolved_total']:>6}")
    if dec["winrate_pct"] is not None:
        lines.append(f"  Win rate                : {dec['winrate_pct']:>5.1f}%")
    else:
        lines.append(f"  Win rate                :     — (0 résolution)")

    # Paper trades
    pt = report["paper_trades"]
    if pt.get("available"):
        lines.append(f"\n[PAPER TRADES]")
        lines.append(f"  Ouverts                 : {pt['open']:>6}")
        lines.append(f"  Fermés                  : {pt['closed']:>6}")
    else:
        lines.append(f"\n[PAPER TRADES] : table absente")

    # Coherence
    coh = report["coherence"]
    lines.append(f"\n[COHERENCE DB]")
    if coh.get("available"):
        c = coh["summary"]["counts"]
        ec = coh["summary"]["exit_code"]
        ec_str = {0: "OK", 1: "WARNING", 2: "ERROR"}.get(ec, str(ec))
        lines.append(
            f"  7 checks : OK={c['ok']}  WARN={c['warning']}  ERR={c['error']}  → exit {ec_str}"
        )
        for d in coh["details"]:
            icon = {"OK": "  ✓", "WARNING": "  ⚠", "ERROR": "  ✗"}.get(d["status"], "  ?")
            lines.append(f"{icon} {d['check']:<30} ({d['count']} issue(s))")
    else:
        lines.append(f"  (indisponible : {coh.get('error', '?')})")

    # Scoring
    sco = report["scoring"]
    lines.append(f"\n[SCORING PRINCIPES]")
    if sco.get("available"):
        lines.append(f"  Décisions résolues : {sco['total_decisions_resolues']}")
        if sco["principes_scores"]:
            for p in sco["principes_scores"]:
                lines.append(f"    {p['principle_id']:<32} N={p['nb']:>3}  WR={p['win_rate']:.1f}%")
        else:
            lines.append("  (aucun score — pas de décision résolue)")
    else:
        lines.append(f"  (indisponible : {sco.get('error', '?')})")

    # Telegram
    tg = report["telegram_logs"]
    lines.append(f"\n[TELEGRAM]")
    if tg.get("available"):
        lines.append(f"  Messages envoyés 24h : {tg['messages_24h']}")
        lines.append(f"  Messages total       : {tg['messages_total']}")
        lines.append(f"  Log                  : {tg['log_path']}")
    else:
        lines.append(f"  (log absent ou illisible)")

    lines.append("")
    lines.append(sep)
    lines.append(f"  Généré le {today} par v9_daily_report.py")
    lines.append(bar)
    return "\n".join(lines)


# ---------- Main ----------


def build_report(db_path: Path | str | None = None) -> dict:
    """Construit le rapport structuré."""
    conn = get_connection(db_path)
    conn.row_factory = sqlite3.Row  # accès par clé sur les Row
    try:
        report = {
            "generated_at": _iso(_now_utc()),
            "snapshots": section_snapshots(conn),
            "signals": section_signals(conn),
            "decisions": section_decisions(conn),
            "paper_trades": section_paper_trades(conn),
            "coherence": section_coherence(conn),
            "scoring": section_scoring(conn),
            "telegram_logs": section_telegram_logs(),
        }
    finally:
        conn.close()
    return report


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Rapport journalier agrégé V9 (lecture seule).",
    )
    parser.add_argument("--json", action="store_true",
                        help="Sortie JSON structurée.")
    parser.add_argument("--no-color", action="store_true",
                        help="Désactive les couleurs ANSI (pour log/cron).")
    args = parser.parse_args()

    report = build_report()

    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False, default=str))
    else:
        print(format_console(report, use_color=not args.no_color))

    return 0


if __name__ == "__main__":
    sys.exit(main())