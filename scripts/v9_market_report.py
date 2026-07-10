#!/usr/bin/env python3
"""v9_market_report.py — Rapport marché quantitatif toutes les 4h (Phase 11).

Génère un rapport structuré Telegram-ready pour Søn :
- État live du pipeline (port, dernier snapshot, TF counts)
- Forces 8 devises (mean/std sur 1h) + dominante direction
- Top 5 signaux 24h (direction, confiance, hit_rate résolu)
- WIN/LOSS résolu + biais structurel (moyenne pips)
- Paper trades ouverts/récents
- Propositions meta-agent en attente
- Moments clés à venir (London/NY/Asie open)

CLI :
    python scripts/v9_market_report.py --once
    python scripts/v9_market_report.py --send     # envoie aussi via Telegram MCP
    python scripts/v9_market_report.py --output docs/reports/H24_MARKET_<date>.md

Doctrine :
- R18 : 0 LLM, calcul stdlib pur.
- Lecture seule sur v9_forces.db + v9_agent_bus.db.
- Idempotent : safe à appeler plusieurs fois.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import subprocess
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

ROOT_DIR = Path(r"C:\projet\V9")
DB_PATH = ROOT_DIR / "data" / "v9_forces.db"
AGENT_BUS_DB = ROOT_DIR / "data" / "v9_agent_bus.db"

DEVISES = ["USD", "GBP", "EUR", "JPY", "CAD", "CHF", "AUD", "NZD"]

# Sessions forex (UTC). cf core/v9/market_calendar.py
def _session_for_hour_utc(h: int) -> str:
    if 22 <= h or h < 7:
        return "asia"
    if 7 <= h < 12:
        return "london"
    if 12 <= h < 17:
        return "ny"
    return "off"


def _next_key_session(now_utc: datetime) -> tuple[str, datetime]:
    """Retourne (label, datetime UTC) du prochain moment clé marché.

    Moments clés : London open 07:00 UTC, NY open 13:00 UTC, NY close 17:00 UTC,
    Asia open 22:00 UTC.
    """
    candidates = []
    base_date = now_utc.date()
    for day_offset in range(3):
        d = base_date + timedelta(days=day_offset)
        for h, m, label in [(7, 0, "London open"), (13, 0, "NY open"),
                            (17, 0, "NY close"), (22, 0, "Asia open")]:
            dt = datetime(d.year, d.month, d.day, h, m, tzinfo=timezone.utc)
            if dt > now_utc:
                candidates.append((label, dt))
    if not candidates:
        return ("n/a", now_utc)
    candidates.sort(key=lambda x: x[1])
    return candidates[0]


def _build_forces_block(conn: sqlite3.Connection) -> str:
    """Mean/std forces 8 devises sur la dernière heure, TF M15."""
    lines = ["💪 **Forces 8 devises (1h, M15)**\n"]
    try:
        rows = conn.execute(f"""
            SELECT {", ".join(f"AVG(force_{d.lower()})" for d in DEVISES)},
                   {", ".join(f"MIN(force_{d.lower()})" for d in DEVISES)},
                   {", ".join(f"MAX(force_{d.lower()})" for d in DEVISES)}
            FROM forces_snapshots
            WHERE timeframe = 'M15'
              AND timestamp > datetime('now', '-1 hour', 'utc')
              AND stale = 0
        """).fetchone()
        if not rows or not rows[0]:
            return "💪 Pas de données forces 1h (marché calme ?)."
        means = rows[:8]
        mins = rows[8:16]
        maxs = rows[16:24]
        # Trouver dominante (max mean) et weakest (min mean)
        dom_idx = max(range(8), key=lambda i: means[i] or 0)
        weak_idx = min(range(8), key=lambda i: means[i] or 100)
        for i, d in enumerate(DEVISES):
            m = means[i] or 0
            mn = mins[i] or 0
            mx = maxs[i] or 0
            mark = ""
            if i == dom_idx:
                mark = " 🟢 DOMINANTE"
            elif i == weak_idx:
                mark = " 🔴 FAIBLE"
            lines.append(f"  {d}: mean={m:.1f} range=[{mn:.0f}, {mx:.0f}]{mark}")
        return "\n".join(lines)
    except Exception as e:
        return f"💪 Erreur forces : {e}"


def _build_signals_block(conn: sqlite3.Connection) -> str:
    """Top 5 signaux directionnels 24h + WIN/LOSS résolu."""
    lines = ["📡 **Top 5 signaux (24h)**\n"]
    try:
        rows = conn.execute("""
            SELECT timestamp, direction, confiance, action,
                   is_win, resolution_pips
            FROM decisions
            WHERE direction IS NOT NULL AND direction != 'neutre'
              AND timestamp > datetime('now', '-24 hours', 'utc')
            ORDER BY confiance DESC LIMIT 5
        """).fetchall()
        if not rows:
            return "📡 Aucun signal directionnel 24h."
        for r in rows:
            ts = r[0].replace("T", " ").split(".")[0]
            emoji = "🟢" if r[1] == "haussiere" else "🔴"
            wr_part = ""
            if r[4] is not None:
                wr_part = f" {'WIN' if r[4] else 'LOSS'} {r[5]:+.1f}p"
            lines.append(f"  {emoji} {ts} {r[1]:<10} {r[2]:>3}% {r[3]}{wr_part}")
        return "\n".join(lines)
    except Exception as e:
        return f"📡 Erreur signaux : {e}"


def _build_win_loss_block(conn: sqlite3.Connection) -> str:
    """Stats WIN/LOSS + biais structurel."""
    try:
        r = conn.execute("""
            SELECT
                SUM(CASE WHEN is_win = 1 THEN 1 ELSE 0 END),
                SUM(CASE WHEN is_win = 0 THEN 1 ELSE 0 END),
                SUM(CASE WHEN is_win IS NULL AND action='preparer_entree' THEN 1 ELSE 0 END),
                AVG(resolution_pips) FILTER (WHERE is_win IS NOT NULL)
            FROM decisions
        """).fetchone()
        wins, losses, open_dec, mean_pips = r[0] or 0, r[1] or 0, r[2] or 0, r[3] or 0
        wr = wins / (wins + losses) * 100 if (wins + losses) > 0 else 0
        bias_note = ""
        if wr > 95:
            bias_note = "\n  ⚠ Biais structurel : WR>95% = artefact MFE>0 fenêtre 4h"
        return (
            f"🎯 **WIN/LOSS**\n"
            f"  Wins={wins} Losses={losses} Open={open_dec}\n"
            f"  WR résolu = {wr:.2f}%, pips moyen = {mean_pips:+.2f}{bias_note}"
        )
    except Exception as e:
        return f"🎯 Erreur WIN/LOSS : {e}"


def _build_paper_block(conn: sqlite3.Connection) -> str:
    """Paper trades ouverts + récents."""
    try:
        n_open = conn.execute("SELECT COUNT(*) FROM paper_trades WHERE closed_at IS NULL").fetchone()[0]
        rows = conn.execute("""
            SELECT trade_id, direction, confiance, opened_at, is_win
            FROM paper_trades
            ORDER BY opened_at DESC LIMIT 3
        """).fetchall()
        lines = [f"📝 **Paper trades** : {n_open} ouvert(s)"]
        for r in rows:
            ts = r[3].replace("T", " ").split(".")[0] if r[3] else "?"
            status = "WIN" if r[4] == 1 else ("LOSS" if r[4] == 0 else "OPEN")
            lines.append(f"  {status:<5} {r[1]:<10} {r[2]:>3}% {ts}")
        return "\n".join(lines)
    except Exception as e:
        return f"📝 Erreur paper : {e}"


def _build_proposals_block() -> str:
    """Propositions meta-agent en attente."""
    try:
        result = subprocess.run(
            [sys.executable, "scripts/v9_meta_agent.py", "--proposals", "--limit", "3"],
            capture_output=True, text=True, cwd=str(ROOT_DIR), timeout=10,
        )
        return "🧠 **Propositions meta-agent**\n" + result.stdout[-500:]
    except Exception as e:
        return f"🧠 Erreur meta-agent : {e}"


def _build_session_block(conn: sqlite3.Connection) -> str:
    """Régime actuel + prochain moment clé."""
    try:
        row = conn.execute("""
            SELECT regime_type FROM regime_snapshots
            WHERE symbol = 'GBPUSD' AND stale = 0
            ORDER BY timestamp DESC LIMIT 1
        """).fetchone()
        regime = row[0] if row else "N/A"
    except Exception:
        regime = "N/A"

    now_utc = datetime.now(timezone.utc)
    sess = _session_for_hour_utc(now_utc.hour)
    next_label, next_dt = _next_key_session(now_utc)
    delta = next_dt - now_utc
    h = delta.total_seconds() / 3600
    return (
        f"🌀 **Session & moments clés**\n"
        f"  Maintenant : {sess} (UTC {now_utc.strftime('%H:%M')})\n"
        f"  Régime : {regime}\n"
        f"  Prochain : {next_label} dans {h:.1f}h ({next_dt.strftime('%H:%M UTC')})"
    )


def _build_pipeline_block(conn: sqlite3.Connection) -> str:
    """État pipeline live : port + DB freshness + TF counts."""
    try:
        rows = conn.execute("""
            SELECT timeframe, COUNT(*), MAX(timestamp)
            FROM forces_snapshots
            WHERE stale = 0 AND timestamp > datetime('now', '-2 hours', 'utc')
            GROUP BY timeframe
        """).fetchall()
        lines = ["🟢 **Pipeline** : UP"]
        for tf, n, last_ts in rows:
            age = "?"
            if last_ts:
                dt = datetime.fromisoformat(last_ts.replace("Z", "+00:00"))
                age = f"{int((datetime.now(timezone.utc) - dt).total_seconds())}s"
            lines.append(f"  {tf:<5}: {n:>4} snapshots (last {age})")
        return "\n".join(lines)
    except Exception as e:
        return f"🟢 Pipeline : erreur {e}"


def build_report() -> str:
    """Construit le rapport complet (texte brut Telegram-ready, < 4000 chars)."""
    now_utc = datetime.now(timezone.utc)
    header = (
        f"📊 **V9 RAPPORT MARCHÉ** — {now_utc.strftime('%Y-%m-%d %H:%M UTC')}\n"
        f"   (Paris {now_utc.astimezone().strftime('%H:%M')})"
    )

    if not DB_PATH.exists():
        return f"{header}\n\n❌ DB absente à {DB_PATH}"

    conn = sqlite3.connect(str(DB_PATH), timeout=10)
    try:
        blocks = [
            header,
            _build_pipeline_block(conn),
            _build_forces_block(conn),
            _build_signals_block(conn),
            _build_win_loss_block(conn),
            _build_paper_block(conn),
            _build_proposals_block(),
            _build_session_block(conn),
        ]
    finally:
        conn.close()

    return "\n\n".join(blocks)


def _send_telegram(text: str) -> bool:
    """Envoie via MCP telegram (subprocess, env complet)."""
    import os
    try:
        payload = (json.dumps({"tool": "send_message", "args": {"text": text}}) + "\n").encode("utf-8")
        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"
        proc = subprocess.Popen(
            [sys.executable, "mcp_servers/telegram_server.py"],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            env=env,
            cwd=str(ROOT_DIR),
        )
        stdout, stderr = proc.communicate(input=payload, timeout=30)
        out = stdout.decode("utf-8", errors="replace").strip()
        err = stderr.decode("utf-8", errors="replace").strip()
        if err:
            print(f"  [telegram stderr] {err[-300:]}", file=sys.stderr)
        return '"sent": true' in out
    except Exception as e:
        print(f"send_telegram error: {e}", file=sys.stderr)
        return False


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Rapport marché V9 toutes les 4h.")
    p.add_argument("--once", action="store_true", required=True)
    p.add_argument("--send", action="store_true",
                   help="Envoie aussi via MCP telegram.")
    p.add_argument("--output", type=Path, default=None,
                   help="Fichier sortie (rapport complet).")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    report = build_report()
    print(report)

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(report, encoding="utf-8")
        print(f"\n[output] → {args.output}", file=sys.stderr)

    if args.send:
        ok = _send_telegram(report)
        print(f"\n[telegram] sent={ok}", file=sys.stderr)
        return 0 if ok else 1

    return 0


if __name__ == "__main__":
    sys.exit(main())