#!/usr/bin/env python
"""v9_diagnose_mt4_ea.py — Diagnostic complet MT4 + EA V9_Sonde_M1.

Vérifie l'état du pipeline de capture :
- Process python.exe (capture_server) actif ?
- Port 31685 en écoute ?
- EA V9_Sonde_M1 connecté au port (socket ouvert) ?
- CVD live par paire (15 dernières min) — y a-t-il du flux ?
- Snapshots frais dans la DB (âge < 5 min) ?
- Décisions résolues dans la DB (par jour) ?
- Brier 7j + WR 7j + PnL 24h

Doctrine : R8 (traçabilité), R22 (CLI lecture seule), R13 (observer).

Usage :
    python scripts/v9_diagnose_mt4_ea.py            # diagnostic complet
    python scripts/v9_diagnose_mt4_ea.py --json    # sortie JSON
    python scripts/v9_diagnose_mt4_ea.py --alert   # alerte Telegram si KO
"""
from __future__ import annotations

import argparse
import json
import socket
import sqlite3
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "data" / "v9_forces.db"
PIPELINE_PORT = 31685
EXPECTED_PAIRS = ["EURUSD", "GBPUSD", "USDJPY", "USDCAD", "USDCHF", "AUDUSD"]
SNAPSHOT_FRESH_SEC = 300  # 5 min


def _check_port_listening(port: int, timeout: float = 1.0) -> dict:
    """Le port TCP est-il en écoute ?"""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        result = sock.connect_ex(("127.0.0.1", port))
        sock.close()
        return {
            "listening": result == 0,
            "port": port,
            "error": None if result == 0 else f"connect_ex returned {result}",
        }
    except Exception as e:
        return {"listening": False, "port": port, "error": str(e)}


def _check_capture_server_process() -> dict:
    """Le process python.exe du capture_server tourne-t-il ?"""
    try:
        result = subprocess.run(
            ["tasklist", "/FI", "IMAGENAME eq python.exe", "/FO", "CSV"],
            capture_output=True, text=True, timeout=10,
        )
        lines = [l for l in result.stdout.splitlines() if "python.exe" in l]
        n_python = len(lines)
        # Cherche le PID du capture_server (port 31685)
        netstat = subprocess.run(
            ["netstat", "-ano"], capture_output=True, text=True, timeout=10,
        ).stdout
        # Format : "  TCP    127.0.0.1:31685    ...    LISTENING    PID"
        capture_pid = None
        for line in netstat.splitlines():
            if ":31685" in line and "LISTENING" in line:
                parts = line.split()
                if len(parts) >= 5:
                    try:
                        capture_pid = int(parts[-1])
                    except ValueError:
                        pass
        return {
            "n_python_processes": n_python,
            "capture_pid": capture_pid,
            "capture_in_list": capture_pid is not None,
        }
    except Exception as e:
        return {"error": str(e)}


def _check_active_connections(port: int) -> dict:
    """Connexions TCP actives sur le port (EA MT4 connecté ?)."""
    try:
        result = subprocess.run(
            ["netstat", "-ano"], capture_output=True, text=True, timeout=10,
        ).stdout
        established = 0
        close_wait = 0
        for line in result.splitlines():
            if f":{port}" in line:
                if "ESTABLISHED" in line:
                    established += 1
                elif "CLOSE_WAIT" in line:
                    close_wait += 1
        return {
            "established": established,
            "close_wait": close_wait,
            "verdict": "OK" if established > 0 else ("STALE" if close_wait > 0 else "NO_CONNECTION"),
        }
    except Exception as e:
        return {"error": str(e)}


def _check_cvd_live() -> dict:
    """CVD live par paire (15 dernières min)."""
    if not DB_PATH.exists():
        return {"error": "DB absente"}
    try:
        with sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True) as conn:
            rows = conn.execute(
                """
                SELECT symbol, COUNT(cvd_delta) AS n_cvd, MAX(timestamp) AS last_ts
                FROM forces_snapshots
                WHERE timestamp > datetime('now', '-15 minutes')
                  AND timeframe = 'M1'
                GROUP BY symbol
                """
            ).fetchall()
            by_symbol = {r[0]: {"n_cvd": r[1], "last_ts": r[2]} for r in rows}
            alive = {s for s, d in by_symbol.items() if d["n_cvd"] > 0}
            missing = set(EXPECTED_PAIRS) - alive
        return {
            "by_symbol": by_symbol,
            "alive_count": len(alive),
            "expected_count": len(EXPECTED_PAIRS),
            "missing": sorted(missing),
            "all_alive": len(missing) == 0,
        }
    except Exception as e:
        return {"error": str(e)}


def _check_snapshot_freshness() -> dict:
    """Âge du dernier snapshot (DB)."""
    if not DB_PATH.exists():
        return {"error": "DB absente"}
    try:
        with sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True) as conn:
            row = conn.execute(
                "SELECT MAX(timestamp) FROM forces_snapshots"
            ).fetchone()
        if not row or not row[0]:
            return {"last_ts": None, "age_sec": None}
        last_str = row[0]
        try:
            last = datetime.fromisoformat(last_str.replace("Z", "+00:00"))
        except ValueError:
            last = datetime.fromisoformat(last_str.replace(" ", "T") + "+00:00")
        if last.tzinfo is None:
            last = last.replace(tzinfo=timezone.utc)
        age = (datetime.now(timezone.utc) - last).total_seconds()
        return {
            "last_ts": last_str,
            "age_sec": int(age),
            "fresh": age < SNAPSHOT_FRESH_SEC,
        }
    except Exception as e:
        return {"error": str(e)}


def _check_decisions_recent() -> dict:
    """Décisions résolues par jour (7 derniers jours)."""
    if not DB_PATH.exists():
        return {"error": "DB absente"}
    try:
        with sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True) as conn:
            rows = conn.execute(
                """
                SELECT DATE(timestamp) AS day,
                       COUNT(*) AS n,
                       ROUND(100.0 * SUM(is_win) / COUNT(*), 1) AS wr_pct,
                       ROUND(SUM(resolution_pips), 1) AS total_pips
                FROM decisions
                WHERE is_win IS NOT NULL
                  AND resolution_strategy = 'DYNAMIC'
                  AND timestamp > datetime('now', '-7 days')
                GROUP BY DATE(timestamp)
                ORDER BY day DESC
                """
            ).fetchall()
        return {
            "by_day": [
                {"day": r[0], "n": r[1], "wr_pct": r[2], "total_pips": r[3]}
                for r in rows
            ]
        }
    except Exception as e:
        return {"error": str(e)}


def _check_brier_wr() -> dict:
    """Brier 7j + WR 7j live."""
    if not DB_PATH.exists():
        return {"error": "DB absente"}
    try:
        with sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True) as conn:
            brier_rows = conn.execute(
                """
                SELECT confiance, is_win
                FROM decisions
                WHERE timestamp > datetime('now', '-7 days')
                  AND confiance IS NOT NULL AND is_win IS NOT NULL
                  AND resolution_strategy = 'DYNAMIC'
                """
            ).fetchall()
            brier = None
            if len(brier_rows) >= 5:
                brier = sum(((c / 100.0) - (1 if w else 0)) ** 2 for c, w in brier_rows) / len(brier_rows)

            wr_row = conn.execute(
                """
                SELECT COUNT(*), SUM(is_win)
                FROM paper_trades
                WHERE opened_at >= '2026-07-18' AND is_win IS NOT NULL
                """
            ).fetchone()
            n, w = wr_row[0], wr_row[1] or 0
            wr = (100.0 * w / n) if n and n >= 5 else None
        return {
            "brier_7j": round(brier, 4) if brier is not None else None,
            "wr_7j_pct": round(wr, 1) if wr is not None else None,
            "n_paper_7j": n,
        }
    except Exception as e:
        return {"error": str(e)}


def diagnose() -> dict:
    """Diagnostic complet."""
    now = datetime.now(timezone.utc)
    result = {
        "generated_at": now.isoformat(),
        "pipeline": {},
        "cvd": {},
        "snapshot": {},
        "decisions": {},
        "metrics": {},
    }

    # 1. Process + port
    result["pipeline"]["process"] = _check_capture_server_process()
    result["pipeline"]["port_listening"] = _check_port_listening(PIPELINE_PORT)
    result["pipeline"]["active_connections"] = _check_active_connections(PIPELINE_PORT)

    # 2. CVD live
    result["cvd"] = _check_cvd_live()

    # 3. Snapshot freshness
    result["snapshot"] = _check_snapshot_freshness()

    # 4. Décisions récentes
    result["decisions"] = _check_decisions_recent()

    # 5. Brier + WR
    result["metrics"] = _check_brier_wr()

    # Verdict global
    issues = []
    if not result["pipeline"]["port_listening"].get("listening"):
        issues.append("🔴 Port 31685 fermé")
    if not result["pipeline"]["active_connections"].get("established", 0) > 0:
        if result["pipeline"]["active_connections"].get("close_wait", 0) > 0:
            issues.append("⚠️ Connexions CLOSE_WAIT uniquement (EA peut-être déconnecté)")
        else:
            issues.append("🔴 Aucune connexion TCP active sur 31685")
    if not result["cvd"].get("all_alive"):
        missing = result["cvd"].get("missing", [])
        issues.append(f"⚠️ CVD KO sur {len(missing)} paire(s) : {', '.join(missing)}")
    if not result["snapshot"].get("fresh"):
        age = result["snapshot"].get("age_sec", 0)
        if age and age > 3600:
            issues.append(f"🔴 Snapshot stale de {age//3600}h{age%3600//60}min (>1h)")
        else:
            issues.append(f"⚠️ Snapshot stale de {age}s (>5min)")

    result["verdict"] = "✅ TOUT OK" if not issues else "⚠️ " + " | ".join(issues)
    result["n_issues"] = len(issues)
    return result


def render_text(report: dict) -> str:
    lines = []
    lines.append("=" * 70)
    lines.append("🔧 Diagnostic MT4/EA + pipeline V9")
    lines.append("=" * 70)
    lines.append(f"Généré : {report['generated_at']}")
    lines.append(f"Verdict : {report['verdict']}")
    lines.append("")

    # Pipeline
    lines.append("─" * 70)
    lines.append("🖥️  PIPELINE")
    lines.append("─" * 70)
    p = report["pipeline"]
    pl = p.get("port_listening", {})
    mark = "🟢" if pl.get("listening") else "🔴"
    lines.append(f"{mark} Port {PIPELINE_PORT} : {'EN ÉCOUTE' if pl.get('listening') else 'FERMÉ'}")
    if pl.get("error"):
        lines.append(f"   Error: {pl['error']}")
    proc = p.get("process", {})
    lines.append(f"   Process python.exe actifs : {proc.get('n_python_processes', '?')}")
    lines.append(f"   Capture PID (port 31685) : {proc.get('capture_pid', '?')}")
    ac = p.get("active_connections", {})
    lines.append(f"   Connexions ESTABLISHED : {ac.get('established', 0)}")
    lines.append(f"   Connexions CLOSE_WAIT  : {ac.get('close_wait', 0)}")
    lines.append(f"   Verdict connexions : {ac.get('verdict', '?')}")
    lines.append("")

    # CVD
    lines.append("─" * 70)
    lines.append("📡 CVD LIVE (15min)")
    lines.append("─" * 70)
    cvd = report["cvd"]
    if "error" in cvd:
        lines.append(f"🔴 {cvd['error']}")
    else:
        lines.append(f"CVD vivantes : {cvd['alive_count']}/{cvd['expected_count']}")
        for sym in EXPECTED_PAIRS:
            d = cvd.get("by_symbol", {}).get(sym, {})
            n = d.get("n_cvd", 0)
            mark = "🟢" if n > 0 else "🔴"
            lines.append(f"  {mark} {sym} : n={n:>6} last={d.get('last_ts', 'N/A')}")
        if cvd.get("missing"):
            lines.append(f"⚠️ CVD KO sur : {', '.join(cvd['missing'])}")
    lines.append("")

    # Snapshot
    lines.append("─" * 70)
    lines.append("📸 SNAPSHOT")
    lines.append("─" * 70)
    snap = report["snapshot"]
    if "error" in snap:
        lines.append(f"🔴 {snap['error']}")
    else:
        age = snap.get("age_sec", "?")
        fresh = snap.get("fresh")
        mark = "🟢" if fresh else ("🔴" if isinstance(age, int) and age > 3600 else "⚠️")
        lines.append(f"{mark} Dernier snapshot : {snap.get('last_ts', 'N/A')}")
        lines.append(f"   Âge : {age}s ({'frais' if fresh else 'STALE'})")
    lines.append("")

    # Décisions
    lines.append("─" * 70)
    lines.append("📊 DÉCISIONS (7 derniers jours)")
    lines.append("─" * 70)
    dec = report["decisions"]
    if "error" in dec:
        lines.append(f"🔴 {dec['error']}")
    else:
        by_day = dec.get("by_day", [])
        if not by_day:
            lines.append("⚠️ Aucune décision résolue 7j")
        for d in by_day:
            mark = "🟢" if d["total_pips"] > 0 else "🔴"
            lines.append(f"  {mark} {d['day']} : n={d['n']:>4} WR={d['wr_pct']:>5}% pips={d['total_pips']:+8.1f}")
    lines.append("")

    # Metrics
    lines.append("─" * 70)
    lines.append("📈 MÉTRIQUES LIVE")
    lines.append("─" * 70)
    m = report["metrics"]
    if "error" in m:
        lines.append(f"🔴 {m['error']}")
    else:
        brier = m.get("brier_7j")
        wr = m.get("wr_7j_pct")
        n_paper = m.get("n_paper_7j", 0)
        if brier is not None:
            brier_qual = "🟢" if brier < 0.20 else ("🟡" if brier < 0.40 else "🔴")
            lines.append(f"  {brier_qual} Brier 7j : {brier:.4f} (cible <0.20)")
        if wr is not None:
            wr_qual = "🟢" if wr >= 50 else ("🟡" if wr >= 40 else "🔴")
            lines.append(f"  {wr_qual} WR 7j paper : {wr}% (n={n_paper})")
    lines.append("")

    return "\n".join(lines)


def send_telegram_alert(report: dict) -> bool:
    """Envoie alerte Telegram si verdict dégradé."""
    if report["n_issues"] == 0:
        print("[INFO] Aucun souci détecté, pas d'alerte Telegram.")
        return True
    text = f"🚨 V9 Diagnostic MT4/EA\n\n{report['verdict']}\n\n"
    text += f"Issues : {report['n_issues']}\n"
    text += f"Généré : {report['generated_at']}\n\n"
    text += "Détails dans : python scripts/v9_diagnose_mt4_ea.py"
    try:
        result = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "v9_telegram_notifier.py"),
             "--send-text", text],
            capture_output=True, timeout=15,
        )
        return result.returncode == 0
    except Exception as e:
        print(f"[WARN] Telegram alert failed: {e}", file=sys.stderr)
        return False


def main() -> int:
    parser = argparse.ArgumentParser(description="Diagnostic MT4/EA + pipeline V9")
    parser.add_argument("--json", action="store_true", help="sortie JSON")
    parser.add_argument("--alert", action="store_true", help="alerte Telegram si KO")
    args = parser.parse_args()

    report = diagnose()

    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        print(render_text(report))

    if args.alert:
        send_telegram_alert(report)

    return 0 if report["n_issues"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
