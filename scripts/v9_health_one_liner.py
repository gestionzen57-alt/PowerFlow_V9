#!/usr/bin/env python
"""v9_health_one_liner.py — État système V9 en une ligne.

Combine les checks vitaux du système en une seule ligne lisible :
- Pipeline (port 31685) actif ?
- DB snapshot < 5 min ?
- CVD 6/6 paires vivantes ?
- Crons Ready count ?
- Brier 7j (critère) ?
- Paper trades WR live ?
- HEAD git aligné origin ?

Doctrine : R8 (traçabilité), R20' (lecture-first), R22 (CLI lecture seule).

Usage :
    python scripts/v9_health_one_liner.py                  # 1 ligne ASCII
    python scripts/v9_health_one_liner.py --json          # dict JSON
    python scripts/v9_health_one_liner.py --exit-code     # exit 0 si tout OK, 1 sinon
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
CVD_WINDOW_MIN = 15
SNAPSHOT_FRESH_SEC = 300  # 5 min


def _check_port(port: int, timeout: float = 1.0) -> bool:
    """Port TCP ouvert ?"""
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=timeout):
            return True
    except (ConnectionRefusedError, TimeoutError, OSError):
        return False


def _check_db_snapshot() -> dict:
    """Dernier snapshot DB + âge."""
    if not DB_PATH.exists():
        return {"exists": False, "age_sec": None, "last_ts": None}
    try:
        with sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True) as conn:
            row = conn.execute(
                "SELECT timestamp FROM forces_snapshots ORDER BY id DESC LIMIT 1"
            ).fetchone()
        if not row:
            return {"exists": True, "age_sec": None, "last_ts": None}
        last_str = row[0]
        # Format SQLite peut être "2026-07-21 05:34:49" (naive) ou ISO avec timezone
        try:
            last = datetime.fromisoformat(last_str.replace("Z", "+00:00"))
        except ValueError:
            # Format SQLite natif sans timezone → assume UTC
            last = datetime.fromisoformat(last_str.replace(" ", "T") + "+00:00")
        if last.tzinfo is None:
            last = last.replace(tzinfo=timezone.utc)
        age = (datetime.now(timezone.utc) - last).total_seconds()
        return {"exists": True, "age_sec": int(age), "last_ts": last_str}
    except Exception as e:
        return {"exists": True, "error": str(e)}


def _check_cvd_coverage() -> dict:
    """Couverture CVD M1 par paire (15 dernières min)."""
    if not DB_PATH.exists():
        return {"n_alive": 0, "n_total": 6, "details": {}}
    try:
        with sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True) as conn:
            rows = conn.execute(
                """
                SELECT symbol, COUNT(cvd_delta) AS n_cvd
                FROM forces_snapshots
                WHERE timestamp > datetime('now', '-15 minutes')
                  AND timeframe = 'M1'
                GROUP BY symbol
                """
            ).fetchall()
        by_sym = {r[0]: r[1] for r in rows if r[1] > 0}
        return {
            "n_alive": len(by_sym),
            "n_total": 6,
            "details": by_sym,
        }
    except Exception:
        return {"n_alive": 0, "n_total": 6, "details": {}}


def _check_crons() -> dict:
    """Crons V9_* Ready.

    Parse la sortie schtasks /Query /XML par blocs <Task>.
    NOTE Windows : le header annonce UTF-16 mais le contenu réel est ASCII/UTF-8.
    On autodétecte via BOM.

    Le format XML contient UN tag <URI> et UN tag <Enabled> PAR tâche dans
    le même bloc <Task>, mais on parse par bloc pour fiabiliser l'association
    (les tâches désactivées peuvent omettre <Enabled>).
    """
    import re
    try:
        raw = subprocess.run(
            ["schtasks", "/Query", "/XML"],
            capture_output=True, timeout=10,
        ).stdout
        if raw[:2] == b"\xff\xfe":
            text = raw.decode("utf-16-le", errors="replace")
        elif raw[:3] == b"\xef\xbb\xbf":
            text = raw[3:].decode("utf-8", errors="replace")
        else:
            text = raw.decode("utf-8", errors="replace")

        # Découpage par blocs <Task ...>...</Task>
        tasks = re.findall(r"<Task\b[^>]*>(.*?)</Task>", text, re.DOTALL)
        seen = {}
        for t in tasks:
            uri_match = re.search(r"<URI>([^<]+)</URI>", t)
            if not uri_match:
                continue
            name = uri_match.group(1).lstrip("\\").strip()
            enabled_match = re.search(r"<Enabled>(true|false)</Enabled>", t)
            # Si <Enabled> absent → par défaut true (Windows default)
            is_ready = enabled_match.group(1) == "true" if enabled_match else True
            seen[name] = is_ready

        v9_total = sum(1 for n in seen if n.startswith("V9_"))
        v9_ready = sum(1 for n, ready in seen.items() if n.startswith("V9_") and ready)
        return {"ready": v9_ready, "total": v9_total}
    except Exception as e:
        return {"ready": -1, "error": str(e)[:100]}


def _check_git_align() -> dict:
    """HEAD local == origin/HEAD ?"""
    try:
        local = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=str(ROOT),
            capture_output=True, text=True, timeout=5,
        ).stdout.strip()
        origin = subprocess.run(
            ["git", "rev-parse", "origin/feat/v9-foundation-clean"], cwd=str(ROOT),
            capture_output=True, text=True, timeout=5,
        ).stdout.strip()
        return {
            "local": local[:8] if local else None,
            "origin": origin[:8] if origin else None,
            "aligned": local == origin and bool(local),
        }
    except Exception as e:
        return {"aligned": None, "error": str(e)}


def _check_paper_trades_wr() -> dict:
    """WR paper trades post-DROP (18/07+)."""
    if not DB_PATH.exists():
        return {"n": 0, "wr": None}
    try:
        with sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True) as conn:
            row = conn.execute(
                """
                SELECT COUNT(*), SUM(is_win)
                FROM paper_trades
                WHERE opened_at >= '2026-07-18' AND is_win IS NOT NULL
                """
            ).fetchone()
        n, w = row[0], row[1] or 0
        return {
            "n": n,
            "wr": round(100.0 * w / n, 1) if n and n >= 5 else None,
        }
    except Exception:
        return {"n": 0, "wr": None}


def _check_brier_7j() -> dict:
    """Brier score sur fenêtre 7j (réutilise logique v9_brier_dashboard)."""
    if not DB_PATH.exists():
        return {"n": 0, "brier": None}
    try:
        with sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True) as conn:
            rows = conn.execute(
                """
                SELECT confiance, is_win FROM decisions
                WHERE timestamp > datetime('now', '-7 days')
                  AND confiance IS NOT NULL AND is_win IS NOT NULL
                  AND resolution_strategy = 'DYNAMIC'
                """
            ).fetchall()
        if len(rows) < 5:
            return {"n": len(rows), "brier": None}
        s = sum(((c / 100.0) - (1 if w else 0)) ** 2 for c, w in rows)
        return {"n": len(rows), "brier": round(s / len(rows), 4)}
    except Exception:
        return {"n": 0, "brier": None}


def collect_health() -> dict:
    """Collecte tous les checks."""
    port_ok = _check_port(PIPELINE_PORT)
    snap = _check_db_snapshot()
    cvd = _check_cvd_coverage()
    crons = _check_crons()
    git = _check_git_align()
    wr = _check_paper_trades_wr()
    brier = _check_brier_7j()

    snap_fresh = (snap.get("age_sec") is not None and snap["age_sec"] < SNAPSHOT_FRESH_SEC)
    cvd_full = cvd["n_alive"] == cvd["n_total"]
    brier_ok = brier["brier"] is None or brier["brier"] < 0.40
    all_ok = port_ok and snap_fresh and cvd_full and brier_ok

    return {
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "all_ok": all_ok,
        "pipeline": {"port": PIPELINE_PORT, "active": port_ok},
        "snapshot": snap,
        "snapshot_fresh": snap_fresh,
        "cvd": cvd,
        "cvd_full": cvd_full,
        "crons": crons,
        "git": git,
        "paper_trades_wr": wr,
        "brier_7j": brier,
        "brier_ok": brier_ok,
    }


def render_one_liner(health: dict) -> str:
    """Génère la sortie 1 ligne ASCII."""
    port = "🟢" if health["pipeline"]["active"] else "🔴"
    snap_age = health["snapshot"].get("age_sec")
    snap = f"🟢{snap_age}s" if health["snapshot_fresh"] else (f"🔴{snap_age}s" if snap_age else "🔴N/A")
    cvd = "🟢6/6" if health["cvd_full"] else f"🔴{health['cvd']['n_alive']}/6"
    crons_n = health["crons"].get("ready", "?")
    git_align = "🟢" if health["git"].get("aligned") else "🔴"
    wr = health["paper_trades_wr"].get("wr")
    wr_str = f"{wr}%" if wr is not None else "N/A"
    brier = health["brier_7j"].get("brier")
    brier_str = f"{brier:.4f}" if brier is not None else "N/A"
    git_sha = health["git"].get("local", "?")
    overall = "✅ OK" if health["all_ok"] else "⚠️ DEGRADED"
    return (
        f"V9 {overall} | "
        f"pipe:{port} snap:{snap} cvd:{cvd} crons:{crons_n} "
        f"git:{git_align}({git_sha}) "
        f"WR:{wr_str} Brier7j:{brier_str}"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="V9 Health — 1 ligne")
    parser.add_argument("--json", action="store_true", help="sortie JSON")
    parser.add_argument("--exit-code", action="store_true", help="exit 1 si dégradé")
    args = parser.parse_args()

    health = collect_health()

    if args.json:
        print(json.dumps(health, indent=2, ensure_ascii=False))
    else:
        print(render_one_liner(health))

    if args.exit_code and not health["all_ok"]:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
