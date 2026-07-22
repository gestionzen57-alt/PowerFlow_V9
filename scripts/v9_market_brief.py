#!/usr/bin/env python
"""v9_market_brief.py — Brief marché toutes les 4h via Telegram.

Génère et envoie un brief structuré du marché en cours :
- Date/heure explicite (Paris + UTC)
- Session active (ASIE/LONDRES/OVERLAP/NEW_YORK/AFTER_HOURS)
- Section AUJOURD'HUI (depuis 00:00 UTC)
- Section HIER (jour entier)
- Section 24H GLISSANTES (fenêtre rolling, contexte mixte)
- Top 3 paires par expectancy 4h
- Bottes noires (pires paires 4h)
- Alertes moments majeurs (WR<30%, edge>10pts, CVD KO, Brier > 0.40)

Doctrine : R8 (traçabilité), R13 (observer), R22 (lecture seule DB mode=ro),
R25' (kill switch pour envoi Telegram).

Usage :
    python scripts/v9_market_brief.py                    # génère + envoie Telegram
    python scripts/v9_market_brief.py --dry-run         # affiche seulement
    python scripts/v9_market_brief.py --json            # sortie JSON
    python scripts/v9_market_brief.py --window-hours 4 # fenêtre stats (défaut 4)
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import subprocess
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

from core.v9._time_windows import (
    get_session_now,
    get_session_full_label,
    get_today_yesterday_split,
    get_24h_rolling,
)

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "data" / "v9_forces.db"
TELEGRAM_CONFIG = ROOT / "config" / "telegram.json"


# ── Lecture DB ─────────────────────────────────────────────────────────────

def fetch_stats(db_path: Path, window_hours: int = 4) -> dict:
    """Lit les stats des décisions résolues sur la fenêtre + split jour/hier/24h."""
    if not db_path.exists():
        return {"error": "DB absente"}
    try:
        with sqlite3.connect(f"file:{db_path}?mode=ro", uri=True) as conn:
            # Par paire (fenêtre window_hours)
            rows = conn.execute(
                f"""
                SELECT symbol,
                       COUNT(*) AS n,
                       ROUND(100.0 * SUM(is_win) / COUNT(*), 1) AS wr_pct,
                       ROUND(AVG(resolution_pips), 2) AS avg_pips,
                       ROUND(SUM(resolution_pips), 1) AS total_pips
                FROM decisions
                WHERE is_win IS NOT NULL
                  AND resolution_strategy = 'DYNAMIC'
                  AND timestamp > datetime('now', '-{window_hours} hours')
                GROUP BY symbol
                HAVING n >= 3
                ORDER BY total_pips DESC
                """
            ).fetchall()
            by_symbol = {
                r[0]: {"n": r[1], "wr_pct": r[2], "avg_pips": r[3], "total_pips": r[4]}
                for r in rows
            }

            # CVD 15min par paire
            cvd_rows = conn.execute(
                """
                SELECT symbol,
                       COUNT(cvd_delta) AS n_cvd
                FROM forces_snapshots
                WHERE timestamp > datetime('now', '-15 minutes')
                  AND timeframe = 'M1'
                GROUP BY symbol
                """
            ).fetchall()
            cvd_alive = {r[0] for r in cvd_rows if r[1] > 0}

            # Brier 7j
            brier_rows = conn.execute(
                """
                SELECT confiance, is_win
                FROM decisions
                WHERE timestamp > datetime('now', '-7 days')
                  AND confiance IS NOT NULL AND is_win IS NOT NULL
                  AND resolution_strategy = 'DYNAMIC'
                """
            ).fetchall()
            if len(brier_rows) >= 5:
                brier = sum(((c / 100.0) - (1 if w else 0)) ** 2 for c, w in brier_rows) / len(brier_rows)
            else:
                brier = None

        # Split today/yesterday/24h via _time_windows
        time_split = get_today_yesterday_split(db_path)
        h24 = get_24h_rolling(db_path)

        return {
            "by_symbol": by_symbol,
            "today": time_split["today"],
            "yesterday": time_split["yesterday"],
            "24h_rolling": h24,
            "cvd_alive": sorted(cvd_alive),
            "cvd_total_pairs": 6,
            "brier_7j": round(brier, 4) if brier is not None else None,
            "brier_n": len(brier_rows),
        }
    except Exception as e:
        return {"error": str(e)[:200]}


# ── Alertes moments majeurs ────────────────────────────────────────────────

def detect_alerts(stats: dict, window_hours: int) -> list[str]:
    """Génère la liste d'alertes Telegram (emojis)."""
    alerts = []
    if "error" in stats:
        return ["\u26a0\ufe0f DB inaccessible \u2014 pas de stats live"]

    # 1. Paires WR < 30% sur la fenêtre
    for sym, d in stats["by_symbol"].items():
        if d["n"] >= 5 and d["wr_pct"] < 30:
            alerts.append(f"\U0001f6a8 <b>{sym}</b> : WR {d['wr_pct']:.1f}% (n={d['n']}) \u2014 DANGER")

    # 2. Paires expectancy < -5 pips
    for sym, d in stats["by_symbol"].items():
        if d["n"] >= 5 and d["avg_pips"] < -5:
            alerts.append(f"\U0001f53b <b>{sym}</b> : expectancy {d['avg_pips']:+.2f} pips \u2014 SHORT \u00e0 \u00e9viter")

    # 3. Edge fort (expectancy > 5 pips)
    for sym, d in stats["by_symbol"].items():
        if d["n"] >= 5 and d["avg_pips"] > 5:
            alerts.append(f"\U0001f680 <b>{sym}</b> : expectancy {d['avg_pips']:+.2f} pips \u2014 momentum confirm\u00e9")

    # 4. CVD KO
    if len(stats["cvd_alive"]) < stats["cvd_total_pairs"]:
        missing = set(["EURUSD", "GBPUSD", "USDJPY", "USDCAD", "USDCHF", "AUDUSD"]) - set(stats["cvd_alive"])
        alerts.append(f"\u26a0\ufe0f CVD KO sur : {', '.join(sorted(missing))}")

    # 5. Brier critique
    if stats.get("brier_7j") is not None and stats["brier_7j"] > 0.40:
        alerts.append(f"\U0001f534 Brier 7j = {stats['brier_7j']:.4f} \u2014 anti-calibr\u00e9, sizing actuel dangereux")

    # 6. 24h très négatif
    h24 = stats.get("24h_rolling", {})
    if "error" not in h24 and h24.get("n", 0) >= 20 and h24.get("pips", 0) < -100:
        alerts.append(
            f"\U0001f4c9 Pertes 24h : {h24['pips']:+.1f} pips (mixte hier+aujourd'hui)"
        )

    return alerts


# ── Rendu texte Telegram ────────────────────────────────────────────────────

def render_brief(stats: dict, window_hours: int) -> str:
    """Génère le message Telegram (HTML) avec sections explicites."""
    now = datetime.now(timezone.utc)
    paris = now.astimezone()
    session = get_session_now(now)
    lines = []

    # Header
    lines.append("\U0001f4ca <b>BRIEF MARCHÉ V9</b>")
    lines.append(f"\U0001f550 {paris.strftime('%d/%m %H:%M')} Paris ({now.strftime('%H:%M UTC')})")
    lines.append(f"\U0001f310 <b>Session</b> : {get_session_full_label(session)}")
    lines.append("")

    if "error" in stats:
        lines.append(f"\u26a0\ufe0f {stats['error']}")
        return "\n".join(lines)

    # Section AUJOURD'HUI
    today = stats.get("today", {})
    sep = "\u2550" * 40
    lines.append(sep)
    today_date = today.get("date", now.strftime("%Y-%m-%d"))
    lines.append(f"\U0001f4c5 <b>AUJOURD'HUI ({today_date}, depuis 00:00 UTC)</b>")
    lines.append(sep)
    if today.get("n", 0) > 0:
        lines.append(f"Trades aujourd'hui : {today['n']}")
        lines.append(f"WR aujourd'hui     : {today['wr_pct']:.1f}%")
        pips_emoji = "\U0001f7e2" if today["pips"] >= 0 else "\U0001f534"
        lines.append(f"P&L aujourd'hui    : {pips_emoji} {today['pips']:+.1f} pips")
        lines.append(f"Session actuelle   : {session}")
    else:
        lines.append("<i>March\u00e9 pas encore actif / pas de d\u00e9cision aujourd'hui</i>")
    lines.append("")

    # Section HIER
    yesterday = stats.get("yesterday", {})
    if yesterday.get("n", 0) > 0:
        lines.append(sep)
        lines.append(f"\U0001f552 <b>HIER ({yesterday['date']}, jour entier)</b>")
        lines.append(sep)
        lines.append(f"Trades hier : {yesterday['n']}")
        lines.append(f"WR hier     : {yesterday['wr_pct']:.1f}%")
        pips_emoji = "\U0001f7e2" if yesterday["pips"] >= 0 else "\U0001f534"
        lines.append(f"P&L hier    : {pips_emoji} {yesterday['pips']:+.1f} pips")
        lines.append("")

    # Section 24H GLISSANTES
    h24 = stats.get("24h_rolling", {})
    lines.append(sep)
    rolling_start = (now - timedelta(hours=24)).strftime("%d/%m %H:%M")
    lines.append(f"\U0001f501 <b>24H GLISSANTES ({rolling_start} \u2192 {now.strftime('%d/%m %H:%M')} UTC)</b>")
    lines.append(sep)
    if "error" not in h24 and h24.get("n", 0) > 0:
        lines.append(f"Trades 24h : {h24['n']}")
        lines.append(f"WR 24h     : {h24['wr_pct']:.1f}%")
        pips_emoji = "\U0001f7e2" if h24["pips"] >= 0 else "\U0001f534"
        lines.append(f"P&L 24h    : {pips_emoji} {h24['pips']:+.1f} pips")
        lines.append("<i>Note : m\u00e9lange aujourd'hui + hier</i>")
    else:
        lines.append("<i>Donn\u00e9es 24h indisponibles</i>")
    lines.append("")

    # Top paires par expectancy (window_hours)
    if stats.get("by_symbol"):
        sorted_pairs = sorted(stats["by_symbol"].items(), key=lambda x: -x[1]["avg_pips"])
        top = sorted_pairs[:3]
        worst = sorted_pairs[-3:][::-1]

        lines.append(sep)
        lines.append(f"\U0001f3c6 <b>TOP 3 PAIRES (fen\u00eatre {window_hours}h)</b>")
        lines.append(sep)
        for sym, d in top:
            emoji = "\U0001f7e2" if d["avg_pips"] >= 0 else "\U0001f534"
            lines.append(
                f"{emoji} <b>{sym}</b> : {d['avg_pips']:+.2f} pips/trade "
                f"(WR {d['wr_pct']:.1f}% \u00b7 n={d['n']})"
            )
        lines.append("")

        lines.append(sep)
        lines.append(f"\u26a0\ufe0f <b>PIRES 3 PAIRES (fen\u00eatre {window_hours}h)</b>")
        lines.append(sep)
        for sym, d in worst:
            emoji = "\U0001f7e2" if d["avg_pips"] >= 0 else "\U0001f534"
            lines.append(
                f"{emoji} <b>{sym}</b> : {d['avg_pips']:+.2f} pips/trade "
                f"(WR {d['wr_pct']:.1f}% \u00b7 n={d['n']})"
            )
        lines.append("")

    # CVD live
    cvd_ok = len(stats.get("cvd_alive", []))
    cvd_total = stats.get("cvd_total_pairs", 6)
    cvd_emoji = "\U0001f7e2" if cvd_ok == cvd_total else "\U0001f534"
    lines.append(f"{cvd_emoji} <b>CVD live</b> : {cvd_ok}/{cvd_total} paires (15min)")
    lines.append("")

    # Brier 7j
    if stats.get("brier_7j") is not None:
        b = stats["brier_7j"]
        if b < 0.20:
            brier_emoji = "\U0001f7e2"
        elif b < 0.40:
            brier_emoji = "\U0001f7e1"
        else:
            brier_emoji = "\U0001f534"
        lines.append(f"{brier_emoji} <b>Brier 7j</b> : {b:.4f} (cible <0.20)")
        if stats.get("brier_n", 0) < 5:
            lines.append("<i>Brier: N/A (donn\u00e9es insuffisantes, <5 observations)</i>")
    else:
        lines.append("<i>Brier 7j: N/A (donn\u00e9es insuffisantes, <5 observations)</i>")
    lines.append("")

    # Alertes
    alerts = detect_alerts(stats, window_hours)
    if alerts:
        lines.append(f"<b>\U0001f6a8 ALERTES MOMENTS MAJEURS</b>")
        for a in alerts:
            lines.append(f"  {a}")
        lines.append("")
    else:
        lines.append(f"\u2705 Aucune alerte majeure d\u00e9tect\u00e9e")

    lines.append("")
    lines.append(f"<i>Source : data/v9_forces.db (lecture seule, mode=ro)</i>")
    lines.append(f"<i>G\u00e9n\u00e9r\u00e9 : {paris.strftime('%Y-%m-%d %H:%M:%S %Z')}</i>")

    return "\n".join(lines)


# ── Envoi Telegram ──────────────────────────────────────────────────────────

def send_telegram(text: str) -> bool:
    """Envoie via le notifier existant."""
    try:
        result = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "v9_telegram_notifier.py"),
             "--send-text", text],
            capture_output=True, timeout=15,
        )
        return result.returncode == 0
    except Exception as e:
        print(f"[WARN] Telegram envoi failed: {e}", file=sys.stderr)
        return False


# ── Main ───────────────────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(description="Brief march\u00e9 V9 \u2192 Telegram")
    parser.add_argument("--dry-run", action="store_true", help="Affiche sans envoyer")
    parser.add_argument("--json", action="store_true", help="Sortie JSON")
    parser.add_argument("--window-hours", type=int, default=4, help="Fen\u00eatre stats (d\u00e9faut 4h)")
    args = parser.parse_args()

    stats = fetch_stats(DB_PATH, args.window_hours)
    text = render_brief(stats, args.window_hours)
    alerts = detect_alerts(stats, args.window_hours)

    if args.json:
        report = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "window_hours": args.window_hours,
            "session": get_session_full_label(get_session_now()),
            "stats": stats,
            "alerts": alerts,
            "text_preview": text[:500],
        }
        print(json.dumps(report, indent=2, ensure_ascii=False))
        return 0

    # Affichage
    print(text)
    print()
    print(f"[INFO] {len(alerts)} alerte(s) d\u00e9tect\u00e9e(s)")

    if args.dry_run:
        print("[DRY-RUN] Pas d'envoi Telegram")
        return 0

    # Envoi
    print("[INFO] Envoi Telegram...")
    ok = send_telegram(text)
    echec = "ÉCHEC" if not ok else "OK"
    print(f"[INFO] Telegram : {echec}")
    return 0 if ok else 2


if __name__ == "__main__":
    sys.exit(main())