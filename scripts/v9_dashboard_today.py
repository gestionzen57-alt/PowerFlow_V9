#!/usr/bin/env python
"""v9_dashboard_today.py — Dashboard CLI quotidien focalisé sur la journée en cours.

Affiche une vue complète du jour courant :
- Timestamp explicite (Paris + UTC) + session forex active
- Snapshot du jour (P&L, WR, nombre de trades)
- Performance intraday par session forex traversée
- Positions actives (snapshot dernier)
- État système (pipeline, CVD, crons, kill switches)
- Indicateurs qualité (Brier, WR, Walk-Forward)
- Recommandation générée

Doctrine : R8 (traçabilité), R22 (CLI lecture seule DB mode=ro),
R6 défensif (try/except sur chaque query).

Usage :
    python scripts/v9_dashboard_today.py            # dashboard texte
    python scripts/v9_dashboard_today.py --json    # sortie JSON
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

from core.v9._time_windows import (
    get_session_now,
    get_session_full_label,
    get_today_yesterday_split,
    get_24h_rolling,
    get_intraday_by_session,
)
from core.v9.kill_switches import (
    bayesian_calibrator_enabled,
    kelly_fractional_enabled,
    bayesian_predictor_enabled,
    drawdown_protector_enabled,
    risk_parity_enabled,
    cycle_memory_enabled,
)

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "data" / "v9_forces.db"
PIPELINE_PORT = 31685
EXPECTED_PAIRS = ["EURUSD", "GBPUSD", "USDJPY", "USDCAD", "USDCHF", "AUDUSD"]


def _check_port(port: int, timeout: float = 1.0) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=timeout):
            return True
    except (ConnectionRefusedError, TimeoutError, OSError):
        return False


def _check_cvd() -> dict:
    if not DB_PATH.exists():
        return {"alive": 0, "total": 6, "missing": EXPECTED_PAIRS[:]}
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
        alive = {r[0] for r in rows if r[1] > 0}
        missing = [s for s in EXPECTED_PAIRS if s not in alive]
        return {"alive": len(alive), "total": 6, "missing": missing}
    except Exception:
        return {"alive": 0, "total": 6, "missing": EXPECTED_PAIRS[:]}


def _check_crons() -> int:
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
        count = 0
        for t in tasks:
            uri_match = re.search(r"<URI>([^<]+)</URI>", t)
            if not uri_match:
                continue
            name = uri_match.group(1).lstrip("\\").strip()
            if name.startswith("V9_"):
                enabled_match = re.search(r"<Enabled>(true|false)</Enabled>", t)
                if enabled_match is None or enabled_match.group(1) == "true":
                    count += 1
        return count
    except Exception:
        return -1


def _check_brier_7j() -> dict:
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


def _check_wr_live() -> dict:
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


def _check_walk_forward() -> dict | None:
    report_path = ROOT / "docs" / "reports" / "walk_forward_20260721.md"
    if not report_path.exists():
        today = datetime.now(timezone.utc).strftime("%Y%m%d")
        report_path = ROOT / "docs" / "reports" / f"walk_forward_{today}.md"
        if not report_path.exists():
            return None
    try:
        text = report_path.read_text(encoding="utf-8")
        verdict = None
        expectancy = None
        ratio = None
        import re
        for line in text.splitlines():
            if "EDGE_REEL" in line:
                verdict = "EDGE_REEL"
            if "expectancy" in line.lower() or "oos_expectancy" in line.lower():
                m = re.search(r'[-+]?\d+\.?\d*', line)
                if m:
                    expectancy = float(m.group())
            if "ratio" in line.lower():
                m = re.search(r'\d+\.?\d*', line)
                if m:
                    ratio = float(m.group())
        if verdict:
            return {"verdict": verdict, "oos_expectancy": expectancy or 0.0, "ratio": ratio or 0.0}
    except Exception:
        pass
    return None


def _fetch_positions_actives() -> list[dict]:
    """Positions actives depuis le dernier snapshot par paire."""
    if not DB_PATH.exists():
        return []
    try:
        with sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True) as conn:
            rows = conn.execute(
                """
                SELECT symbol, direction, timeframe
                FROM forces_snapshots
                WHERE timestamp > datetime('now', '-5 minutes')
                  AND timeframe = 'M1'
                GROUP BY symbol
                """
            ).fetchall()
        return [{"symbol": r[0], "direction": r[1], "timeframe": r[2]} for r in rows]
    except Exception:
        return []


def _generate_recommendation(health: dict) -> str:
    """Génère une recommandation basée sur l'état du système."""
    brier = health.get("brier_7j", {}).get("brier")
    today_pips = health.get("today", {}).get("pips", 0)
    ks = health.get("kill_switches", {})

    if brier is not None and brier > 0.40:
        return (
            "Le système est anti-calibré (Brier > 0.40). Les motions #43-44-45 bayésiennes "
            "sont activées mais nécessitent T+30j pour effet complet. Patience + motions CEO "
            "successives (#46 Kelly 0.15, #47 DD Protector) recommandées."
        )
    if today_pips < -100:
        return (
            f"Pertes significatives aujourd'hui ({today_pips:+.1f} pips). "
            "Surveiller les sessions suivantes. Éviter toute sur-exposition."
        )
    if ks.get("bayesian_on", 0) < 3:
        return (
            f"Kill switches bayésiens partiels ({ks.get('bayesian_on', 0)}/3). "
            "Activer les motions #43-44-45 pour calibration complète."
        )
    if today_pips > 0:
        return (
            f"Journée positive ({today_pips:+.1f} pips). Système stable, "
            "continuer le monitoring. Promouvoir les SHADOW si WR sain confirmé."
        )
    return (
        "Système en mode observation. Continuer le paper-trade et surveiller "
        "l'évolution du Brier et du WR sur les prochaines sessions."
    )


def collect_dashboard() -> dict:
    """Collecte toutes les données du dashboard."""
    now_utc = datetime.now(timezone.utc)
    now_paris = now_utc.astimezone()
    session = get_session_now(now_utc)

    time_split = get_today_yesterday_split(DB_PATH)
    h24 = get_24h_rolling(DB_PATH)
    intraday = get_intraday_by_session(DB_PATH)
    cvd = _check_cvd()
    crons = _check_crons()
    brier = _check_brier_7j()
    wr = _check_wr_live()
    walk_forward = _check_walk_forward()
    positions = _fetch_positions_actives()
    port_ok = _check_port(PIPELINE_PORT)

    bayesian_count = sum([
        bayesian_calibrator_enabled(),
        kelly_fractional_enabled(),
        bayesian_predictor_enabled(),
    ])
    kill_switches = {
        "bayesian_on": bayesian_count,
        "bayesian_total": 3,
        "dd_protector": drawdown_protector_enabled(),
        "risk_parity": risk_parity_enabled(),
        "cycle_memory": cycle_memory_enabled(),
    }

    health = {
        "today": time_split["today"],
        "brier_7j": brier,
        "kill_switches": kill_switches,
    }

    return {
        "generated_at": now_utc.isoformat(),
        "paris_time": now_paris.strftime("%H:%M"),
        "utc_time": now_utc.strftime("%H:%M"),
        "utc_date": now_utc.strftime("%d/%m/%Y"),
        "session": session,
        "today": time_split["today"],
        "yesterday": time_split["yesterday"],
        "24h_rolling": h24,
        "intraday": intraday,
        "cvd": cvd,
        "crons_ready": crons,
        "brier_7j": brier,
        "wr_live": wr,
        "walk_forward": walk_forward,
        "positions": positions,
        "pipeline": {"port": PIPELINE_PORT, "active": port_ok},
        "kill_switches": kill_switches,
        "recommendation": _generate_recommendation(health),
    }


def render_dashboard(dash: dict) -> str:
    """Génère le dashboard texte."""
    lines = []
    sep = "=" * 60
    sub = "-" * 60

    # Header
    lines.append(sep)
    lines.append(f"\U0001f4cb V9 DASHBOARD AUJOURD'HUI — {dash['utc_date']}")
    lines.append(sep)
    lines.append(f"\U0001f550 {dash['paris_time']} Paris ({dash['utc_time']} UTC) · Session : {dash['session']}")
    lines.append("")

    # Snapshot du jour
    lines.append(f"\U0001f4f8 SNAPSHOT DU JOUR")
    lines.append(sub)
    today = dash["today"]
    if today.get("n", 0) > 0:
        pips_emoji = "\U0001f7e2" if today["pips"] >= 0 else "\U0001f534"
        lines.append(f"P&L aujourd'hui         : {today['pips']:+.1f} pips  {pips_emoji}")
        lines.append(f"WR aujourd'hui          : {today['wr_pct']:.1f}%      ({today['n']} trades)")
        lines.append(f"P&L depuis 00:00 UTC     : démarré 00:01, marché actif")
    else:
        lines.append("P&L aujourd'hui         : marché pas encore actif / pas de décision")
    lines.append(f"Session actuelle        : {dash['session']}")
    lines.append("")

    # Performance intraday par session
    lines.append(f"\U0001f4ca PERFORMANCE INTRADAY (par session)")
    lines.append(sub)
    intraday = dash.get("intraday", [])
    if intraday:
        for s in intraday:
            pips_emoji = "\U0001f7e2" if s["pips"] >= 0 else "\U0001f534"
            current = "  (en cours)" if s["session"] == dash["session"] else ""
            lines.append(
                f"{s['session']:<20s} : n={s['n']:<4d} WR={s['wr_pct']:.1f}%  "
                f"{s['pips']:+.1f} pips  {pips_emoji}{current}"
            )
    else:
        lines.append("Aucune donnée intraday disponible")
    lines.append("")

    # Positions actives
    lines.append(f"\U0001f4cd POSITIONS ACTIVES (snapshot dernier)")
    lines.append(sub)
    positions = dash.get("positions", [])
    if positions:
        for p in positions:
            direction = p.get("direction", "?")
            sym = p.get("symbol", "?")
            tf = p.get("timeframe", "?")
            lines.append(f"  {sym} {tf} {direction}")
    else:
        lines.append("  Aucune position active détectée")
    lines.append("")

    # État système
    lines.append(f"\u2699\ufe0f ÉTAT SYSTÈME")
    lines.append(sub)
    pipe_emoji = "\U0001f7e2" if dash["pipeline"]["active"] else "\U0001f534"
    lines.append(f"Pipeline        : {pipe_emoji} port {dash['pipeline']['port']} {'OK' if dash['pipeline']['active'] else 'KO'}")
    cvd_emoji = "\U0001f7e2" if dash["cvd"]["alive"] == dash["cvd"]["total"] else "\U0001f534"
    lines.append(f"CVD live        : {cvd_emoji} {dash['cvd']['alive']}/{dash['cvd']['total']} paires")
    crons_n = dash.get("crons_ready", "?")
    lines.append(f"Crons Ready     : {crons_n}")
    ks = dash["kill_switches"]
    lines.append(
        f"Kill switches   : {ks['bayesian_on']}/3 bayésiens ON (#43-44-45), "
        f"DD/RP/cycle {'ON' if ks['dd_protector'] else 'OFF'}/"
        f"{'ON' if ks['risk_parity'] else 'OFF'}/"
        f"{'ON' if ks['cycle_memory'] else 'OFF'}"
    )
    lines.append("")

    # Indicateurs qualité
    lines.append(f"\U0001f4c8 INDICATEURS DE QUALITÉ")
    lines.append(sub)
    brier = dash.get("brier_7j", {}).get("brier")
    if brier is not None:
        brier_emoji = "\U0001f7e2" if brier < 0.20 else ("\U0001f7e1" if brier < 0.40 else "\U0001f534")
        lines.append(f"Brier 7j          : {brier:.4f} {brier_emoji}  (cible <0.20)")
    else:
        lines.append(f"Brier 7j          : N/A (données insuffisantes, <5 obs)")
    wr = dash.get("wr_live", {}).get("wr")
    wr_str = f"{wr}%" if wr is not None else "N/A"
    lines.append(f"WR live 7j         : {wr_str}")
    wf = dash.get("walk_forward")
    if wf:
        lines.append(f"Walk-Forward live  : {wf['verdict']} (+{wf['oos_expectancy']:.3f} pips, ratio {wf['ratio']:.2f})")
    else:
        lines.append(f"Walk-Forward live  : N/A (pas de rapport récent)")
    lines.append("")

    # Recommandation
    lines.append(f"\U0001f3af RECOMMANDATION (générée)")
    lines.append(sub)
    lines.append(dash.get("recommendation", "N/A"))
    lines.append("")
    lines.append(sep)

    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Dashboard quotidien V9")
    parser.add_argument("--json", action="store_true", help="sortie JSON")
    args = parser.parse_args()

    dash = collect_dashboard()

    if args.json:
        print(json.dumps(dash, indent=2, ensure_ascii=False))
    else:
        print(render_dashboard(dash))

    return 0


if __name__ == "__main__":
    sys.exit(main())