#!/usr/bin/env python
"""v9_health_one_liner.py — État système V9 multi-lignes.

Combine les checks vitaux du système en une sortie lisible multi-lignes :
- Timestamp explicite (Paris + UTC)
- Aujourd'hui vs Hier vs 24h glissantes (split clair)
- Pipeline (port 31685) actif ?
- DB snapshot < 5 min ?
- CVD 6/6 paires vivantes ?
- Crons Ready count ?
- Brier 7j (critère) ?
- Kill switches bayésiens (#43-44-45)
- Edge Walk-Forward (si récent)

Doctrine : R8 (traçabilité), R20' (lecture-first), R22 (CLI lecture seule).

Usage :
    python scripts/v9_health_one_liner.py                  # multi-lignes
    python scripts/v9_health_one_liner.py --json          # dict JSON
    python scripts/v9_health_one_liner.py --exit-code     # exit 0 si tout OK, 1 sinon
    python scripts/v9_health_one_liner.py --oneliner      # format 1 ligne (legacy)
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

# Ajouter le root au path pour les imports core.v9.* AVANT les imports
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.v9._time_windows import (
    get_session_now,
    get_today_yesterday_split,
    get_24h_rolling,
    get_session_full_label,
)
from core.v9.kill_switches import (
    bayesian_calibrator_enabled,
    kelly_fractional_enabled,
    bayesian_predictor_enabled,
    drawdown_protector_enabled,
    risk_parity_enabled,
    cycle_memory_enabled,
)

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
        try:
            last = datetime.fromisoformat(last_str.replace("Z", "+00:00"))
        except ValueError:
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
        return {"n_alive": len(by_sym), "n_total": 6, "details": by_sym}
    except Exception:
        return {"n_alive": 0, "n_total": 6, "details": {}}


def _check_crons() -> dict:
    """Crons V9_* Ready.

    Parse la sortie schtasks /Query /XML par blocs <Task>.
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

        tasks = re.findall(r"<Task\b[^>]*>(.*?)</Task>", text, re.DOTALL)
        seen = {}
        for t in tasks:
            uri_match = re.search(r"<URI>([^<]+)</URI>", t)
            if not uri_match:
                continue
            name = uri_match.group(1).lstrip("\\").strip()
            enabled_match = re.search(r"<Enabled>(true|false)</Enabled>", t)
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
        return {"n": n, "wr": round(100.0 * w / n, 1) if n and n >= 5 else None}
    except Exception:
        return {"n": 0, "wr": None}


def _check_brier_7j() -> dict:
    """Brier score sur fenêtre 7j."""
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


def _check_kill_switches() -> dict:
    """État des kill switches bayésiens et risque."""
    bayesian_count = sum([
        bayesian_calibrator_enabled(),
        kelly_fractional_enabled(),
        bayesian_predictor_enabled(),
    ])
    return {
        "bayesian_on": bayesian_count,
        "bayesian_total": 3,
        "dd_protector": drawdown_protector_enabled(),
        "risk_parity": risk_parity_enabled(),
        "cycle_memory": cycle_memory_enabled(),
    }


def _check_walk_forward_edge() -> dict | None:
    """Edge Walk-Forward si disponible (lecture rapport)."""
    report_path = ROOT / "docs" / "reports" / "walk_forward_20260721.md"
    if not report_path.exists():
        # Essayer date du jour
        today = datetime.now(timezone.utc).strftime("%Y%m%d")
        report_path = ROOT / "docs" / "reports" / f"walk_forward_{today}.md"
        if not report_path.exists():
            return None
    try:
        text = report_path.read_text(encoding="utf-8")
        # Cherche verdict + expectancy
        verdict = None
        expectancy = None
        ratio = None
        for line in text.splitlines():
            if "EDGE_REEL" in line and "verdict" not in (verdict or "").lower():
                verdict = "EDGE_REEL"
            if "expectancy" in line.lower() or "oos_expectancy" in line.lower():
                # Parse nombre
                import re
                m = re.search(r'[-+]?\d+\.?\d*', line)
                if m:
                    expectancy = float(m.group())
            if "ratio" in line.lower():
                import re
                m = re.search(r'\d+\.?\d*', line)
                if m:
                    ratio = float(m.group())
        if verdict:
            return {
                "verdict": verdict,
                "oos_expectancy": expectancy or 0.0,
                "ratio": ratio or 0.0,
            }
    except Exception:
        pass
    return None


def _verdict_reason(health: dict) -> str:
    """Raison courte du verdict."""
    if health["all_ok"]:
        return "OK"
    reasons = []
    brier = health["brier_7j"].get("brier")
    if brier is not None and brier >= 0.40:
        reasons.append(f"Brier {brier:.4f}")
    if not health["pipeline"]["active"]:
        reasons.append("Pipeline KO")
    if not health["snapshot_fresh"]:
        reasons.append("Snapshot stale")
    if not health["cvd_full"]:
        reasons.append(f"CVD {health['cvd']['n_alive']}/6")
    return " | ".join(reasons) if reasons else "OK"


def collect_health() -> dict:
    """Collecte tous les checks."""
    port_ok = _check_port(PIPELINE_PORT)
    snap = _check_db_snapshot()
    cvd = _check_cvd_coverage()
    crons = _check_crons()
    git = _check_git_align()
    wr = _check_paper_trades_wr()
    brier = _check_brier_7j()
    kill_switches = _check_kill_switches()
    walk_forward = _check_walk_forward_edge()

    # Split today/yesterday/24h via _time_windows
    time_split = get_today_yesterday_split(DB_PATH)
    h24 = get_24h_rolling(DB_PATH)

    snap_fresh = (snap.get("age_sec") is not None and snap["age_sec"] < SNAPSHOT_FRESH_SEC)
    cvd_full = cvd["n_alive"] == cvd["n_total"]
    brier_ok = brier["brier"] is None or brier["brier"] < 0.40
    all_ok = port_ok and snap_fresh and cvd_full and brier_ok

    now_utc = datetime.now(timezone.utc)
    now_paris = now_utc.astimezone()

    return {
        "checked_at": now_utc.isoformat(),
        "all_ok": all_ok,
        "local_time": now_paris.strftime("%H:%M"),
        "utc_time": now_utc.strftime("%H:%M"),
        "utc_date": now_utc.strftime("%d/%m"),
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
        "kill_switches": kill_switches,
        "walk_forward": walk_forward,
        "today": time_split["today"],
        "yesterday": time_split["yesterday"],
        "24h_rolling": h24,
    }


def render_health_multi(health: dict) -> str:
    """Génère la sortie multi-lignes structurée."""
    lines = []

    # Ligne 1 : Verdict global + timestamp
    overall = "\u2705 OK" if health["all_ok"] else "\u26a0\ufe0f DEGRADED"
    lines.append(
        f"V9 {overall} ({_verdict_reason(health)}) | "
        f"\U0001f5d3\ufe0f {health['utc_date']} {health['local_time']} Paris ({health['utc_time']} UTC)"
    )

    # Ligne 2 : Aujourd'hui
    today = health["today"]
    if today["n"] > 0:
        lines.append(
            f"\U0001f4c5 Aujourd'hui : n={today['n']} trades, WR={today['wr_pct']:.1f}%, "
            f"{today['pips']:+.1f} pips (session {today.get('session_now', '?')})"
        )
    else:
        lines.append(
            "\U0001f4c5 Aujourd'hui : march\u00e9 pas encore actif / pas de d\u00e9cision"
        )

    # Ligne 3 : Hier
    yesterday = health["yesterday"]
    if yesterday["n"] > 0:
        lines.append(
            f"\U0001f552 Hier ({yesterday['date']}) : n={yesterday['n']}, "
            f"WR={yesterday['wr_pct']:.1f}%, {yesterday['pips']:+.1f} pips"
        )

    # Ligne 4 : 24h rolling
    h24 = health["24h_rolling"]
    if "error" not in h24:
        lines.append(
            f"\U0001f501 24h globales : n={h24['n']}, WR={h24['wr_pct']:.1f}%, "
            f"{h24['pips']:+.1f} pips (mixte aujourd'hui+hier)"
        )
    else:
        lines.append(f"\U0001f501 24h globales : \u26a0\ufe0f {h24.get('error', 'N/A')}")

    # Ligne 5 : Pipeline
    pipe_emoji = "\U0001f7e2" if health["pipeline"]["active"] else "\U0001f534"
    snap_age = health["snapshot"].get("age_sec")
    snap_str = f"{snap_age}s" if snap_age is not None else "N/A"
    cvd_str = f"{health['cvd']['n_alive']}/{health['cvd']['n_total']}"
    lines.append(
        f"{pipe_emoji} Pipeline : snap {snap_str}, CVD {cvd_str}, "
        f"port {health['pipeline']['port']}"
    )

    # Ligne 6 : Kill switches
    ks = health["kill_switches"]
    lines.append(
        f"\u2699\ufe0f Kill switches : {ks['bayesian_on']}/3 bay\u00e9siens ON (#43-44-45), "
        f"DD/RP/cycle {'ON' if ks['dd_protector'] else 'OFF'}/"
        f"{'ON' if ks['risk_parity'] else 'OFF'}/"
        f"{'ON' if ks['cycle_memory'] else 'OFF'}"
    )

    # Ligne 7 : Crons
    crons_n = health["crons"].get("ready", "?")
    lines.append(f"\U0001f916 Crons : {crons_n} Ready")

    # Ligne 8 : Edge (si Walk-Forward récent)
    if health.get("walk_forward"):
        wf = health["walk_forward"]
        lines.append(
            f"\U0001f5af Edge : Walk-Forward {wf['verdict']} "
            f"({wf['oos_expectancy']:+.1f} pips, ratio {wf['ratio']:.2f})"
        )

    # Ligne 9 : Brier + WR (contexte qualité)
    brier = health["brier_7j"].get("brier")
    brier_str = f"{brier:.4f}" if brier is not None else "N/A"
    wr = health["paper_trades_wr"].get("wr")
    wr_str = f"{wr}%" if wr is not None else "N/A"
    lines.append(
        f"\U0001f4c8 Qualit\u00e9 : Brier 7j {brier_str} (cible <0.20) | WR live {wr_str}"
    )

    return "\n".join(lines)


def render_one_liner(health: dict) -> str:
    """Génère la sortie 1 ligne ASCII (format legacy)."""
    port = "\U0001f7e2" if health["pipeline"]["active"] else "\U0001f534"
    snap_age = health["snapshot"].get("age_sec")
    snap = f"\U0001f7e2{snap_age}s" if health["snapshot_fresh"] else (f"\U0001f534{snap_age}s" if snap_age else "\U0001f534N/A")
    cvd = "\U0001f7e26/6" if health["cvd_full"] else f"\U0001f534{health['cvd']['n_alive']}/6"
    crons_n = health["crons"].get("ready", "?")
    git_align = "\U0001f7e2" if health["git"].get("aligned") else "\U0001f534"
    wr = health["paper_trades_wr"].get("wr")
    wr_str = f"{wr}%" if wr is not None else "N/A"
    brier = health["brier_7j"].get("brier")
    brier_str = f"{brier:.4f}" if brier is not None else "N/A"
    git_sha = health["git"].get("local", "?")
    overall = "\u2705 OK" if health["all_ok"] else "\u26a0\ufe0f DEGRADED"
    return (
        f"V9 {overall} | "
        f"pipe:{port} snap:{snap} cvd:{cvd} crons:{crons_n} "
        f"git:{git_align}({git_sha}) "
        f"WR:{wr_str} Brier7j:{brier_str}"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="V9 Health \u2014 multi-lignes")
    parser.add_argument("--json", action="store_true", help="sortie JSON")
    parser.add_argument("--exit-code", action="store_true", help="exit 1 si d\u00e9grad\u00e9")
    parser.add_argument("--oneliner", action="store_true", help="format 1 ligne (legacy)")
    args = parser.parse_args()

    health = collect_health()

    if args.json:
        print(json.dumps(health, indent=2, ensure_ascii=False))
    elif args.oneliner:
        print(render_one_liner(health))
    else:
        print(render_health_multi(health))

    if args.exit_code and not health["all_ok"]:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())