#!/usr/bin/env python
"""v9_cvd_watchdog.py — Watchdog CVD avec alerte Telegram si stale.

Surveille la fraîcheur des données CVD (Cumulative Volume Delta) par paire.
Si la dernière donnée CVD de TOUTE paire est > N secondes, alerte Telegram
immédiate (l'EA MT4 est probablement déconnectée).

Doctrine : R8 (traçabilité), R22 (CLI lecture seule DB mode=ro),
R6 défensif (try/except).

Usage :
    python scripts/v9_cvd_watchdog.py                       # check une fois
    python scripts/v9_cvd_watchdog.py --threshold-sec 120  # seuil custom (défaut 120s = 2min)
    python scripts/v9_cvd_watchdog.py --alert              # alerte Telegram si KO
    python scripts/v9_cvd_watchdog.py --watch --interval 60  # mode watch (loop)
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "data" / "v9_forces.db"
EXPECTED_PAIRS = ["EURUSD", "GBPUSD", "USDJPY", "USDCAD", "USDCHF", "AUDUSD"]
DEFAULT_THRESHOLD_SEC = 120  # 2 min
ALERT_COOLDOWN_SEC = 600     # 10 min entre 2 alertes (anti-spam)


def _fetch_cvd_state(db_path: Path) -> dict:
    """Lit l'état CVD live par paire (1min)."""
    if not db_path.exists():
        return {"error": "DB absente"}
    try:
        with sqlite3.connect(f"file:{db_path}?mode=ro", uri=True) as conn:
            rows = conn.execute(
                """
                SELECT symbol,
                       COUNT(cvd_delta) AS n_cvd,
                       MAX(timestamp) AS last_ts
                FROM forces_snapshots
                WHERE timestamp > datetime('now', '-1 minute')
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
        return {"error": str(e)[:200]}


def _fetch_oldest_cvd_age(db_path: Path) -> dict:
    """Trouve le plus vieux CVD parmi toutes les paires (le goulot d'étranglement)."""
    if not db_path.exists():
        return {"age_sec": None, "oldest_pair": None, "oldest_ts": None}
    try:
        with sqlite3.connect(f"file:{db_path}?mode=ro", uri=True) as conn:
            row = conn.execute(
                """
                SELECT symbol, MAX(timestamp) AS last_ts
                FROM forces_snapshots
                WHERE timeframe = 'M1'
                  AND cvd_delta IS NOT NULL
                  AND timestamp > datetime('now', '-1 hour')
                GROUP BY symbol
                """
            ).fetchall()
        if not row:
            return {"age_sec": None, "oldest_pair": None, "oldest_ts": None}
        now = datetime.now(timezone.utc)
        oldest_pair = None
        oldest_ts = None
        oldest_age = 0
        for sym, ts in row:
            try:
                last = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            except ValueError:
                last = datetime.fromisoformat(ts.replace(" ", "T") + "+00:00")
            if last.tzinfo is None:
                last = last.replace(tzinfo=timezone.utc)
            age = (now - last).total_seconds()
            if age > oldest_age:
                oldest_age = age
                oldest_pair = sym
                oldest_ts = ts
        return {
            "age_sec": int(oldest_age),
            "oldest_pair": oldest_pair,
            "oldest_ts": oldest_ts,
        }
    except Exception as e:
        return {"age_sec": None, "error": str(e)[:200]}


def _last_alert_file() -> Path:
    """Fichier état pour anti-spam alertes."""
    return ROOT / "logs" / ".cvd_watchdog_last_alert"


def _should_alert() -> bool:
    """True si on peut alerter (cooldown 10 min depuis dernière)."""
    f = _last_alert_file()
    if not f.exists():
        return True
    try:
        last_ts = float(f.read_text().strip())
        return (time.time() - last_ts) > ALERT_COOLDOWN_SEC
    except (ValueError, OSError):
        return True


def _mark_alerted() -> None:
    """Marque l'alerte comme envoyée."""
    f = _last_alert_file()
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(str(time.time()))


def send_telegram(text: str) -> bool:
    """Envoie Telegram via le notifier."""
    try:
        result = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "v9_telegram_notifier.py"),
             "--send-text", text],
            capture_output=True, timeout=15,
        )
        return result.returncode == 0
    except Exception as e:
        print(f"[WARN] Telegram failed: {e}", file=sys.stderr)
        return False


def check_once(threshold_sec: int = DEFAULT_THRESHOLD_SEC, alert: bool = False) -> dict:
    """Check unique de la fraîcheur CVD."""
    state = _fetch_cvd_state(DB_PATH)
    oldest = _fetch_oldest_cvd_age(DB_PATH)

    cvd_age = oldest.get("age_sec")
    stale = cvd_age is not None and cvd_age > threshold_sec
    missing = state.get("missing", [])

    if state.get("all_alive") and not stale:
        verdict = "✅ CVD OK"
        level = "info"
    elif missing and not state.get("all_alive"):
        verdict = f"⚠️ CVD MISSING ({len(missing)} paire(s))"
        level = "warn"
    elif stale:
        verdict = f"🔴 CVD STALE ({cvd_age}s > {threshold_sec}s seuil)"
        level = "critical"
    else:
        verdict = "⚠️ CVD DEGRADED"
        level = "warn"

    report = {
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "verdict": verdict,
        "level": level,
        "threshold_sec": threshold_sec,
        "state": state,
        "oldest": oldest,
        "cvd_age_sec": cvd_age,
        "stale": stale,
        "missing": missing,
    }

    # Alerte Telegram si KO
    if alert and level in ("warn", "critical") and _should_alert():
        text = (
            f"🚨 V9 CVD Watchdog\n\n"
            f"{verdict}\n\n"
            f"Paires vivantes : {state.get('alive_count', 0)}/{state.get('expected_count', 6)}\n"
        )
        if missing:
            text += f"Missing : {', '.join(missing)}\n"
        if cvd_age is not None:
            text += f"Plus vieux CVD : {cvd_age}s ({oldest.get('oldest_pair', '?')})\n"
        text += f"\nAction : reconnecter EA MT4 `V9_Sonde_M1`.\n"
        text += f"Seuil : {threshold_sec}s | Heure : {report['checked_at']}"
        ok = send_telegram(text)
        if ok:
            _mark_alerted()
            report["alert_sent"] = True
        else:
            report["alert_sent"] = False

    return report


def render_text(report: dict) -> str:
    """Génère le rendu texte."""
    lines = []
    lines.append("=" * 70)
    lines.append(f"🐕 CVD Watchdog — seuil {report['threshold_sec']}s")
    lines.append("=" * 70)
    lines.append(f"Check : {report['checked_at']}")
    lines.append(f"Verdict : {report['verdict']}")
    lines.append("")

    if report["stale"]:
        age = report["cvd_age_sec"]
        sym = report["oldest"].get("oldest_pair", "?")
        lines.append(f"🔴 CVD STALE : {age}s (> {report['threshold_sec']}s)")
        lines.append(f"   Plus vieux : {sym} @ {report['oldest'].get('oldest_ts', '?')}")
    else:
        age = report.get("cvd_age_sec")
        if age is not None:
            lines.append(f"🟢 CVD frais : {age}s (max)")

    lines.append("")
    lines.append(f"Paires attendues : {report['state'].get('expected_count', 6)}")
    lines.append(f"Paires vivantes  : {report['state'].get('alive_count', 0)}")
    if report["missing"]:
        lines.append(f"⚠️ Missing : {', '.join(report['missing'])}")
    lines.append("")

    if "alert_sent" in report:
        lines.append(f"📤 Alerte Telegram : {'✅ envoyée' if report['alert_sent'] else '❌ échec'}")

    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Watchdog CVD avec alerte Telegram")
    parser.add_argument("--threshold-sec", type=int, default=DEFAULT_THRESHOLD_SEC,
                        help=f"Seuil stale CVD en secondes (défaut {DEFAULT_THRESHOLD_SEC})")
    parser.add_argument("--alert", action="store_true",
                        help="Envoie alerte Telegram si KO (cooldown 10 min)")
    parser.add_argument("--json", action="store_true", help="Sortie JSON")
    parser.add_argument("--watch", action="store_true", help="Mode watch (loop)")
    parser.add_argument("--interval", type=int, default=60, help="Intervalle watch (sec)")
    args = parser.parse_args()

    if args.watch:
        print(f"[WATCH] Démarrage (seuil {args.threshold_sec}s, intervalle {args.interval}s)")
        while True:
            report = check_once(args.threshold_sec, args.alert)
            if not args.json:
                print(render_text(report))
            else:
                print(json.dumps(report, indent=2, ensure_ascii=False))
            time.sleep(args.interval)
    else:
        report = check_once(args.threshold_sec, args.alert)
        if args.json:
            print(json.dumps(report, indent=2, ensure_ascii=False))
        else:
            print(render_text(report))
        return 1 if report["level"] in ("warn", "critical") else 0


if __name__ == "__main__":
    sys.exit(main())
