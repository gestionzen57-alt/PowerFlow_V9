#!/usr/bin/env python
"""v9_market_brief.py — Brief marché toutes les 4h via Telegram.

Génère et envoie un brief structuré du marché en cours :
- Session active (asia/london/overlap/newyork/after)
- Top 3 paires par expectancy 4h
- Bottes noires (pires paires 4h)
- Stats 24h globales
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
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "data" / "v9_forces.db"
TELEGRAM_CONFIG = ROOT / "config" / "telegram.json"


# ── Sessions forex (heures UTC, simplifiées) ────────────────────────────────

def current_session() -> str:
    """Session forex active selon l'heure UTC courante."""
    h = datetime.now(timezone.utc).hour
    if 0 <= h < 7:
        return "ASIE 🌏 (00-07 UTC)"
    if 7 <= h < 12:
        return "LONDRES 🇬🇧 (07-12 UTC)"
    if 12 <= h < 16:
        return "OVERLAP LONDRES-NY 🇬🇧🇺🇸 (12-16 UTC)"
    if 16 <= h < 21:
        return "NEW YORK 🇺🇸 (16-21 UTC)"
    return "AFTER-HOURS 🌙 (21-24 UTC)"


# ── Lecture DB ─────────────────────────────────────────────────────────────

def fetch_stats(db_path: Path, window_hours: int = 4) -> dict:
    """Lit les stats des décisions résolues sur la fenêtre."""
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

            # Global 24h
            glob = conn.execute(
                """
                SELECT COUNT(*),
                       ROUND(100.0 * SUM(is_win) / COUNT(*), 1),
                       ROUND(AVG(resolution_pips), 2),
                       ROUND(SUM(resolution_pips), 1)
                FROM decisions
                WHERE is_win IS NOT NULL
                  AND resolution_strategy = 'DYNAMIC'
                  AND timestamp > datetime('now', '-24 hours')
                """
            ).fetchone()

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

            # Brier 7j (mêmes stats que le dashboard)
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

            return {
                "by_symbol": by_symbol,
                "global_24h": {
                    "n": glob[0] or 0,
                    "wr_pct": glob[1] or 0,
                    "avg_pips": glob[2] or 0,
                    "total_pips": glob[3] or 0,
                },
                "cvd_alive": sorted(cvd_alive),
                "cvd_total_pairs": 6,
                "brier_7j": round(brier, 4) if brier is not None else None,
            }
    except Exception as e:
        return {"error": str(e)[:200]}


# ── Alertes moments majeurs ────────────────────────────────────────────────

def detect_alerts(stats: dict, window_hours: int) -> list[str]:
    """Génère la liste d'alertes Telegram (emojis)."""
    alerts = []
    if "error" in stats:
        return ["⚠️ DB inaccessible — pas de stats live"]

    # 1. Paires WR < 30% sur la fenêtre
    for sym, d in stats["by_symbol"].items():
        if d["n"] >= 5 and d["wr_pct"] < 30:
            alerts.append(f"🚨 <b>{sym}</b> : WR {d['wr_pct']:.1f}% (n={d['n']}) — DANGER")

    # 2. Paires expectancy < -5 pips
    for sym, d in stats["by_symbol"].items():
        if d["n"] >= 5 and d["avg_pips"] < -5:
            alerts.append(f"🔻 <b>{sym}</b> : expectancy {d['avg_pips']:+.2f} pips — SHORT à éviter")

    # 3. Edge fort (expectancy > 5 pips)
    for sym, d in stats["by_symbol"].items():
        if d["n"] >= 5 and d["avg_pips"] > 5:
            alerts.append(f"🚀 <b>{sym}</b> : expectancy {d['avg_pips']:+.2f} pips — momentum confirmé")

    # 4. CVD KO
    if len(stats["cvd_alive"]) < stats["cvd_total_pairs"]:
        missing = set(["EURUSD", "GBPUSD", "USDJPY", "USDCAD", "USDCHF", "AUDUSD"]) - set(stats["cvd_alive"])
        alerts.append(f"⚠️ CVD KO sur : {', '.join(sorted(missing))}")

    # 5. Brier critique
    if stats["brier_7j"] is not None and stats["brier_7j"] > 0.40:
        alerts.append(f"🔴 Brier 7j = {stats['brier_7j']:.4f} — anti-calibré, sizing actuel dangereux")

    # 6. Global 24h très négatif
    if stats["global_24h"]["n"] >= 20 and stats["global_24h"]["total_pips"] < -100:
        alerts.append(
            f"📉 24h global : {stats['global_24h']['total_pips']:+.1f} pips "
            f"(n={stats['global_24h']['n']}) — jour à surveiller"
        )

    return alerts


# ── Rendu texte Telegram ────────────────────────────────────────────────────

def render_brief(stats: dict, window_hours: int) -> str:
    """Génère le message Telegram (HTML)."""
    now = datetime.now(timezone.utc)
    paris = now.astimezone()  # local TZ
    lines = []

    # Header
    lines.append(f"📊 <b>BRIEF MARCHÉ V9</b>")
    lines.append(f"🕐 {paris.strftime('%H:%M')} Paris ({now.strftime('%H:%M UTC')})")
    lines.append(f"📅 {paris.strftime('%d/%m/%Y')}")
    lines.append(f"")
    lines.append(f"🌐 <b>Session</b> : {current_session()}")
    lines.append(f"📏 Fenêtre stats : {window_hours}h")
    lines.append(f"")

    if "error" in stats:
        lines.append(f"⚠️ {stats['error']}")
        return "\n".join(lines)

    # Stats globales 24h
    g = stats["global_24h"]
    lines.append(f"<b>📈 Global 24h</b>")
    lines.append(f"  Trades : {g['n']} | WR : {g['wr_pct']:.1f}% | Avg : {g['avg_pips']:+.2f} pips")
    pips_emoji = "🟢" if g["total_pips"] >= 0 else "🔴"
    lines.append(f"  {pips_emoji} <b>Total 24h : {g['total_pips']:+.1f} pips</b>")
    lines.append(f"")

    # CVD live
    cvd_ok = len(stats["cvd_alive"])
    cvd_total = stats["cvd_total_pairs"]
    cvd_emoji = "🟢" if cvd_ok == cvd_total else "🔴"
    lines.append(f"{cvd_emoji} <b>CVD live</b> : {cvd_ok}/{cvd_total} paires (15min)")
    lines.append(f"")

    # Top paires par expectancy (window_hours)
    if stats["by_symbol"]:
        sorted_pairs = sorted(stats["by_symbol"].items(), key=lambda x: -x[1]["avg_pips"])
        top = sorted_pairs[:3]
        worst = sorted_pairs[-3:][::-1]  # 3 pires

        lines.append(f"<b>🏆 Top 3 paires ({window_hours}h)</b>")
        for sym, d in top:
            emoji = "🟢" if d["avg_pips"] >= 0 else "🔴"
            lines.append(
                f"  {emoji} <b>{sym}</b> : {d['avg_pips']:+.2f} pips/trade "
                f"(WR {d['wr_pct']:.1f}% · n={d['n']})"
            )
        lines.append(f"")

        lines.append(f"<b>⚠️ Pires 3 paires ({window_hours}h)</b>")
        for sym, d in worst:
            emoji = "🟢" if d["avg_pips"] >= 0 else "🔴"
            lines.append(
                f"  {emoji} <b>{sym}</b> : {d['avg_pips']:+.2f} pips/trade "
                f"(WR {d['wr_pct']:.1f}% · n={d['n']})"
            )
        lines.append(f"")

    # Brier 7j
    if stats["brier_7j"] is not None:
        b = stats["brier_7j"]
        if b < 0.20:
            brier_emoji = "🟢"
        elif b < 0.40:
            brier_emoji = "🟡"
        else:
            brier_emoji = "🔴"
        lines.append(f"{brier_emoji} <b>Brier 7j</b> : {b:.4f} (cible <0.20)")
    lines.append(f"")

    # Alertes
    alerts = detect_alerts(stats, window_hours)
    if alerts:
        lines.append(f"<b>🚨 ALERTES MOMENTS MAJEURS</b>")
        for a in alerts:
            lines.append(f"  {a}")
        lines.append(f"")
    else:
        lines.append(f"✅ Aucune alerte majeure détectée")

    lines.append(f"")
    lines.append(f"<i>Source : data/v9_forces.db (lecture seule, mode=ro)</i>")
    lines.append(f"<i>Généré : {paris.strftime('%Y-%m-%d %H:%M:%S %Z')}</i>")

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
    parser = argparse.ArgumentParser(description="Brief marché V9 → Telegram")
    parser.add_argument("--dry-run", action="store_true", help="Affiche sans envoyer")
    parser.add_argument("--json", action="store_true", help="Sortie JSON")
    parser.add_argument("--window-hours", type=int, default=4, help="Fenêtre stats (défaut 4h)")
    args = parser.parse_args()

    stats = fetch_stats(DB_PATH, args.window_hours)
    text = render_brief(stats, args.window_hours)
    alerts = detect_alerts(stats, args.window_hours)

    if args.json:
        report = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "window_hours": args.window_hours,
            "session": current_session(),
            "stats": stats,
            "alerts": alerts,
            "text_preview": text[:500],
        }
        print(json.dumps(report, indent=2, ensure_ascii=False))
        return 0

    # Affichage
    print(text)
    print()
    print(f"[INFO] {len(alerts)} alerte(s) détectée(s)")

    if args.dry_run:
        print("[DRY-RUN] Pas d'envoi Telegram")
        return 0

    # Envoi
    print("[INFO] Envoi Telegram...")
    ok = send_telegram(text)
    print(f"[INFO] Telegram : {'OK' if ok else 'ÉCHEC'}")
    return 0 if ok else 2


if __name__ == "__main__":
    sys.exit(main())
