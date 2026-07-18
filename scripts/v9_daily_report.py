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


# ---------- Sections « morning brief » (P4 quantique 2026-07-18) ----------


def _prev_utc_day_bounds() -> tuple[str, str, str]:
    """Bornes ISO du jour UTC précédent (00:00 → 24:00) + libellé date."""
    now = _now_utc()
    start_today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    start_yest = start_today - timedelta(days=1)
    return _iso(start_yest), _iso(start_today), start_yest.strftime("%Y-%m-%d")


def section_pnl_veille(conn: sqlite3.Connection) -> dict:
    """P&L réalisé de la veille (paper_trades clôturés hier, UTC)."""
    if not _table_exists(conn, "paper_trades"):
        return {"available": False}
    start, end, label = _prev_utc_day_bounds()
    try:
        row = conn.execute(
            "SELECT COUNT(*) AS n, "
            "COALESCE(SUM(pips_simulated), 0) AS pips, "
            "COALESCE(SUM(CASE WHEN is_win=1 THEN 1 ELSE 0 END), 0) AS wins "
            "FROM paper_trades "
            "WHERE closed_at IS NOT NULL AND closed_at >= ? AND closed_at < ?",
            (start, end),
        ).fetchone()
    except sqlite3.OperationalError:
        return {"available": False}
    n = int(row["n"]) if row else 0
    wins = int(row["wins"]) if row else 0
    pips = float(row["pips"]) if row else 0.0
    losses = n - wins
    return {
        "available": True,
        "date": label,
        "trades_closed": n,
        "wins": wins,
        "losses": losses,
        "wr_pct": round(wins / n * 100, 1) if n else None,
        "pips_net": round(pips, 1),
        "avg_pips": round(pips / n, 2) if n else None,
    }


def section_wr_par_dimension(conn: sqlite3.Connection, window_days: int = 7) -> dict:
    """WR + expectancy par dimension (symbole, direction, session) sur N jours.

    Source : paper_trades clôturés JOIN decisions (symbol/direction). La
    session est inférée depuis l'heure d'ouverture (infer_session_from_hour).
    """
    if not (_table_exists(conn, "paper_trades") and _table_exists(conn, "decisions")):
        return {"available": False}
    since = _iso(_now_utc() - timedelta(days=window_days))
    try:
        rows = conn.execute(
            "SELECT pt.pips_simulated AS pips, pt.is_win AS is_win, "
            "       pt.opened_at AS opened_at, d.symbol AS symbol, "
            "       pt.direction AS direction "
            "FROM paper_trades pt "
            "LEFT JOIN decisions d ON d.snapshot_id = pt.snapshot_id "
            "WHERE pt.closed_at IS NOT NULL AND pt.closed_at >= ? "
            "GROUP BY pt.trade_id",
            (since,),
        ).fetchall()
    except sqlite3.OperationalError:
        return {"available": False}

    from core.v9.exit_simulator import infer_session_from_hour  # noqa: PLC0415

    dims: dict[str, dict[str, dict]] = {"symbol": {}, "direction": {}, "session": {}}

    def _bucket(dim: str, key: str, is_win: int, pips: float) -> None:
        if key is None:
            key = "?"
        b = dims[dim].setdefault(key, {"n": 0, "wins": 0, "pips": 0.0})
        b["n"] += 1
        b["wins"] += 1 if is_win == 1 else 0
        b["pips"] += pips

    for r in rows:
        pips = float(r["pips"]) if r["pips"] is not None else 0.0
        is_win = int(r["is_win"]) if r["is_win"] is not None else 0
        _bucket("symbol", r["symbol"], is_win, pips)
        _bucket("direction", r["direction"], is_win, pips)
        session = "?"
        if r["opened_at"]:
            try:
                dt = datetime.fromisoformat(r["opened_at"].replace("Z", "+00:00"))
                session = infer_session_from_hour(dt.hour)
            except (ValueError, AttributeError):
                session = "?"
        _bucket("session", session, is_win, pips)

    def _finalize(buckets: dict) -> list[dict]:
        out = []
        for key, b in buckets.items():
            n = b["n"]
            out.append({
                "value": key,
                "n": n,
                "wr_pct": round(b["wins"] / n * 100, 1) if n else None,
                "avg_pips": round(b["pips"] / n, 2) if n else None,
            })
        return sorted(out, key=lambda x: x["n"], reverse=True)

    return {
        "available": True,
        "window_days": window_days,
        "by_symbol": _finalize(dims["symbol"]),
        "by_direction": _finalize(dims["direction"]),
        "by_session": _finalize(dims["session"]),
    }


def _window_stats(conn: sqlite3.Connection, since_iso: str | None) -> dict:
    """WR + expectancy des décisions résolues depuis since (None = lifetime)."""
    where = "is_win IS NOT NULL AND resolution_pips IS NOT NULL"
    params: tuple = ()
    if since_iso is not None:
        where += " AND timestamp >= ?"
        params = (since_iso,)
    try:
        row = conn.execute(
            f"SELECT COUNT(*) AS n, "
            f"COALESCE(SUM(CASE WHEN is_win=1 THEN 1 ELSE 0 END),0) AS wins, "
            f"COALESCE(AVG(resolution_pips),0) AS exp "
            f"FROM decisions WHERE {where}",
            params,
        ).fetchone()
    except sqlite3.OperationalError:
        return {"n": 0, "wr_pct": None, "expectancy": None}
    n = int(row["n"]) if row else 0
    return {
        "n": n,
        "wr_pct": round(int(row["wins"]) / n * 100, 1) if n else None,
        "expectancy": round(float(row["exp"]), 3) if n else None,
    }


def section_edge_decay(conn: sqlite3.Connection) -> dict:
    """Décroissance d'edge : compare 24h vs 7j vs lifetime.

    Un edge qui décroît est le premier signe qu'un régime a changé. On mesure
    l'expectancy (pips/trade) sur 3 fenêtres et on flague une chute.
    """
    if not _table_exists(conn, "decisions"):
        return {"available": False}
    now = _now_utc()
    last_24h = _window_stats(conn, _iso(now - WINDOW_24H))
    last_7d = _window_stats(conn, _iso(now - WINDOW_7D))
    lifetime = _window_stats(conn, None)

    decay = None
    e24 = last_24h.get("expectancy")
    e7 = last_7d.get("expectancy")
    if e24 is not None and e7 is not None and last_24h["n"] >= 10:
        if e7 > 0:
            ratio = e24 / e7
            if ratio < 0.5:
                decay = "SEVERE"
            elif ratio < 0.8:
                decay = "MODEREE"
            else:
                decay = "STABLE"
        else:
            decay = "STABLE" if e24 >= e7 else "SEVERE"
    return {
        "available": True,
        "last_24h": last_24h,
        "last_7d": last_7d,
        "lifetime": lifetime,
        "decay": decay,
    }


def section_promotions(conn: sqlite3.Connection) -> dict:
    """Statut des principes (ACTIVE/SHADOW/...) + principes récents (24h).

    Note honnêteté : V9 ne journalise pas les transitions SHADOW→ACTIVE
    (le statut effectif est piloté par config.PRINCIPLE_ACTIVE_IDS, pas la
    table). On rapporte donc la distribution actuelle des v9_status et les
    principes synchronisés dans les dernières 24h comme proxy.
    """
    if not _table_exists(conn, "principles"):
        return {"available": False}
    try:
        status_rows = conn.execute(
            "SELECT v9_status, COUNT(*) AS n FROM principles GROUP BY v9_status"
        ).fetchall()
        by_status = {(r["v9_status"] or "?"): int(r["n"]) for r in status_rows}
        recent = 0
        try:
            recent = conn.execute(
                "SELECT COUNT(*) FROM principles WHERE synced_at >= ?",
                (_iso(_now_utc() - WINDOW_24H),),
            ).fetchone()[0]
        except sqlite3.OperationalError:
            recent = 0
    except sqlite3.OperationalError:
        return {"available": False}
    return {
        "available": True,
        "by_status": by_status,
        "synced_24h": int(recent),
    }


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


# ---------- Format « morning brief » Telegram (P4 quantique) ----------


def format_morning_brief(report: dict) -> str:
    """Brief matinal compact (HTML Telegram) : P&L veille + WR/dim + edge + promos."""
    today = _now_utc().strftime("%Y-%m-%d %H:%M UTC")
    lines: list[str] = [f"<b>V9 Morning Brief — {today}</b>", ""]

    # P&L veille
    pnl = report.get("pnl_veille", {})
    if pnl.get("available") and pnl.get("trades_closed"):
        sign = "📈" if pnl["pips_net"] >= 0 else "📉"
        wr = f"{pnl['wr_pct']:.0f}%" if pnl["wr_pct"] is not None else "—"
        lines.append(
            f"{sign} <b>P&amp;L veille ({pnl['date']})</b> : "
            f"{pnl['pips_net']:+.1f} pips | {pnl['trades_closed']} trades | WR {wr}"
        )
    else:
        lines.append("• <b>P&amp;L veille</b> : aucun trade clôturé")

    # Edge decay
    ed = report.get("edge_decay", {})
    if ed.get("available"):
        d24, d7 = ed["last_24h"], ed["last_7d"]
        decay = ed.get("decay") or "n/a"
        icon = {"SEVERE": "🔴", "MODEREE": "🟡", "STABLE": "🟢"}.get(decay, "⚪")
        e24 = d24["expectancy"] if d24["expectancy"] is not None else "—"
        e7 = d7["expectancy"] if d7["expectancy"] is not None else "—"
        lines.append(
            f"{icon} <b>Edge</b> : 24h {e24} vs 7j {e7} pips/trade → {decay}"
        )

    # WR par dimension (top symbole + direction)
    wrd = report.get("wr_par_dimension", {})
    if wrd.get("available"):
        top_sym = wrd["by_symbol"][:3]
        if top_sym:
            frag = " · ".join(
                f"{s['value']} {s['wr_pct']:.0f}%({s['n']})"
                for s in top_sym if s["wr_pct"] is not None
            )
            if frag:
                lines.append(f"• <b>WR/symbole (7j)</b> : {frag}")
        dirs = {d["value"]: d for d in wrd["by_direction"]}
        frag_d = " · ".join(
            f"{k} {v['wr_pct']:.0f}%({v['n']})"
            for k, v in dirs.items() if v["wr_pct"] is not None
        )
        if frag_d:
            lines.append(f"• <b>WR/direction</b> : {frag_d}")

    # Promotions / statut principes
    promo = report.get("promotions", {})
    if promo.get("available"):
        by = promo["by_status"]
        frag = " · ".join(f"{k}:{v}" for k, v in sorted(by.items()))
        lines.append(f"• <b>Principes</b> : {frag} (synced 24h: {promo['synced_24h']})")

    lines.append("")
    lines.append("<i>v9_daily_report — lecture seule</i>")
    return "\n".join(lines)


def send_brief_telegram(report: dict) -> bool:
    """Envoie le brief matinal via Telegram. Best-effort (R6).

    Réutilise le channel du notifier (config/telegram.json). Retourne False
    en cas d'échec sans lever — le rapport reste imprimé sur stdout.
    """
    try:
        from scripts.v9_telegram_notifier import (  # noqa: PLC0415
            load_telegram_config,
            send_telegram,
        )
        cfg = load_telegram_config()
        return bool(send_telegram(format_morning_brief(report), cfg))
    except SystemExit:
        # load_telegram_config() fait sys.exit(1) si config absente.
        print("[KO] config/telegram.json absente ou incomplète — envoi ignoré.")
        return False
    except Exception as exc:  # noqa: BLE001 — R6, best-effort
        print(f"[KO] envoi Telegram échoué : {exc}")
        return False


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
            # Sections « morning brief » (P4 quantique)
            "pnl_veille": section_pnl_veille(conn),
            "wr_par_dimension": section_wr_par_dimension(conn),
            "edge_decay": section_edge_decay(conn),
            "promotions": section_promotions(conn),
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
    parser.add_argument("--db-path", type=str, default=None,
                        help="Chemin DB override (défaut: config.DB_PATH). "
                             "Utile pour tests + runs parallèles.")
    parser.add_argument("--brief", action="store_true",
                        help="Affiche le brief matinal compact (P&L veille, "
                             "WR/dimension, edge decay, promotions).")
    parser.add_argument("--telegram", action="store_true",
                        help="Envoie le brief matinal via Telegram "
                             "(config/telegram.json).")
    args = parser.parse_args()

    db_path = Path(args.db_path) if args.db_path else None
    report = build_report(db_path)

    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False, default=str))
    elif args.brief:
        print(format_morning_brief(report))
    else:
        print(format_console(report, use_color=not args.no_color))

    if args.telegram:
        ok = send_brief_telegram(report)
        print("[OK] Brief Telegram envoyé." if ok else "[KO] Brief Telegram non envoyé.")

    return 0


if __name__ == "__main__":
    sys.exit(main())