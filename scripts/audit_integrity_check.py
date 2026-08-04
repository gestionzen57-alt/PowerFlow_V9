"""
Audit d'intégrité V9 — rejouable.

R2 additif pur : nouveau fichier scripts/. Pas de modif core/.
Reproduit exactement les queries de AUDIT_INTEGRITY_2026_08.md
pour permettre audit continu à chaque exécution.

Doctrine :
- R0 zero-kill : lecture seule
- R6 fail-open : retourne 0 si DB introuvable
- R7 tests : tests/test_audit_integrity_v9.py
- R22 : 1 périmètre = audit chiffres only

Usage :
  .venv/Scripts/python.exe scripts/audit_integrity_check.py
  .venv/Scripts/python.exe scripts/audit_integrity_check.py --json
  .venv/Scripts/python.exe scripts/audit_integrity_check.py --since 2026-07-15
"""

from __future__ import annotations

import argparse
import json
import math
import sqlite3
import statistics
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "data" / "v9_forces.db"

# Couleurs ANSI (R6 fail-open : no-op si pas de TTY)
def _color(text: str, code: str) -> str:
    if not sys.stdout.isatty():
        return text
    return f"\033[{code}m{text}\033[0m"


GREEN = lambda t: _color(t, "32")
RED = lambda t: _color(t, "31")
YELLOW = lambda t: _color(t, "33")
BOLD = lambda t: _color(t, "1")


def compute_metrics(since: str | None = None) -> dict[str, Any]:
    """Calcule les métriques d'intégrité V9 à partir de la DB live.

    Args:
        since: filtre ISO date (ex. '2026-07-15') ou None pour tout l'historique.

    Returns:
        dict avec les VRAIS chiffres. Toutes les queries SQL sont tracables.
    """
    if not DB_PATH.exists():
        return {"error": f"DB introuvable: {DB_PATH}"}

    con = sqlite3.connect(str(DB_PATH), timeout=5)
    try:
        # Filtre WHERE
        where = "WHERE closed_at IS NOT NULL"
        params: tuple[Any, ...] = ()
        if since:
            where += " AND closed_at >= ?"
            params = (since,)

        # V1 — Total rows
        n_total = con.execute(
            f"SELECT COUNT(*) FROM paper_trades {where}", params
        ).fetchone()[0]

        if n_total == 0:
            return {"error": "Aucun trade clôturé", "n_total": 0}

        # V2 — Wins / WR
        n_win = con.execute(
            f"SELECT COUNT(*) FROM paper_trades {where} AND is_win=1", params
        ).fetchone()[0]
        wr = n_win / n_total * 100

        # V3 — PnL
        pnl_brut = con.execute(
            f"SELECT SUM(pips_simulated) FROM paper_trades {where}", params
        ).fetchone()[0] or 0.0
        pnl_net = con.execute(
            f"SELECT SUM(pips_net_of_spread) FROM paper_trades {where}", params
        ).fetchone()[0] or 0.0
        avg_pnl = pnl_net / n_total

        # V4 — Profit Factor
        gw = con.execute(
            f"SELECT SUM(pips_net_of_spread) FROM paper_trades {where} AND pips_net_of_spread > 0",
            params,
        ).fetchone()[0] or 0.0
        gl = abs(
            con.execute(
                f"SELECT SUM(pips_net_of_spread) FROM paper_trades {where} AND pips_net_of_spread < 0",
                params,
            ).fetchone()[0]
            or 0.0
        )
        pf = gw / gl if gl else float("inf")

        # V5 — Max DD
        rows = con.execute(
            f"SELECT closed_at, pips_net_of_spread FROM paper_trades {where} ORDER BY closed_at",
            params,
        ).fetchall()
        running = peak = 0.0
        max_dd = 0.0
        pnls: list[float] = []
        for _, pips in rows:
            if pips is None:
                continue
            pnls.append(pips)
            running += pips
            if running > peak:
                peak = running
            dd = peak - running
            if dd > max_dd:
                max_dd = dd

        # V9 — Sharpe-like (ann. sqrt(252))
        mean = sum(pnls) / len(pnls) if pnls else 0
        std = statistics.stdev(pnls) if len(pnls) > 1 else 0
        sharpe = (mean / std) * math.sqrt(252) if std else 0.0

        # V6 — Distribution par jour
        daily = con.execute(
            f"""
            SELECT DATE(closed_at) d, COUNT(*) n, SUM(is_win) w,
                   ROUND(SUM(is_win)*100.0/COUNT(*),1) wr,
                   ROUND(SUM(pips_net_of_spread),1) pnl
            FROM paper_trades {where}
            GROUP BY DATE(closed_at) ORDER BY d
            """,
            params,
        ).fetchall()
        daily_metrics = [
            {"date": d, "n": n, "wins": w, "wr_pct": wr, "pnl_net": pnl}
            for d, n, w, wr, pnl in daily
        ]

        # V7 — Doublons
        n_dup_id = con.execute(
            f"SELECT COUNT(*) - COUNT(DISTINCT trade_id) FROM paper_trades {where}",
            params,
        ).fetchone()[0]

        # V7bis — Doublons cachés (même closed_at + pnl + direction)
        n_dup_hidden = con.execute(
            f"""
            SELECT COUNT(*) FROM (
                SELECT closed_at, direction, pips_net_of_spread, COUNT(*) c
                FROM paper_trades {where}
                GROUP BY closed_at, direction, pips_net_of_spread
                HAVING c > 1
            )
            """,
            params,
        ).fetchone()[0]

        # V10 — Direction
        by_dir = con.execute(
            f"""
            SELECT direction, COUNT(*) n, SUM(is_win) w,
                   ROUND(SUM(pips_net_of_spread),1) pnl
            FROM paper_trades {where}
            GROUP BY direction
            """,
            params,
        ).fetchall()
        direction_metrics = [
            {"direction": d, "n": n, "wins": w, "wr_pct": round(w / n * 100, 1), "pnl_net": pnl}
            for d, n, w, pnl in by_dir
        ]

        # V12 — Distribution confiance
        by_conf = con.execute(
            f"""
            SELECT confiance, COUNT(*) n, SUM(is_win) w,
                   ROUND(SUM(pips_net_of_spread),1) pnl
            FROM paper_trades {where}
            GROUP BY confiance ORDER BY confiance
            """,
            params,
        ).fetchall()
        confiance_metrics = [
            {"conf": c, "n": n, "wins": w, "wr_pct": round(w / n * 100, 1), "pnl_net": pnl}
            for c, n, w, pnl in by_conf
        ]

        return {
            "db": str(DB_PATH),
            "since": since or "all",
            "queried_at": datetime.now(timezone.utc).isoformat(),
            "v1_total": n_total,
            "v2_wins": n_win,
            "v2_wr_pct": round(wr, 2),
            "v3_pnl_brut": round(pnl_brut, 1),
            "v3_pnl_net": round(pnl_net, 1),
            "v3_avg_pnl": round(avg_pnl, 2),
            "v4_gross_win": round(gw, 1),
            "v4_gross_loss": round(gl, 1),
            "v4_profit_factor": round(pf, 3),
            "v5_max_dd": round(max_dd, 1),
            "v9_sharpe_like_ann": round(sharpe, 3),
            "v6_daily": daily_metrics,
            "v7_dup_trade_id": n_dup_id,
            "v7bis_dup_hidden": n_dup_hidden,
            "v10_direction": direction_metrics,
            "v12_confiance": confiance_metrics,
        }
    finally:
        con.close()


# Seuils d'alerte (R6 fail-open : warning, pas exception)
KILL_CRITERIA = {
    "wr_pct_min": 50.0,  # < 50% = stratégie perdante
    "profit_factor_min": 1.0,  # < 1.0 = pertes > gains
    "max_dd_max": 500.0,  # > 500 pips = risque excessif
    "sharpe_min": 0.0,  # < 0 = Sharpe négatif
    "avg_pnl_min": 0.0,  # < 0 = trade moyen perdant
}


def check_kill_criteria(metrics: dict) -> list[str]:
    """Retourne la liste des critères KILL franchis."""
    alerts: list[str] = []
    if metrics["v2_wr_pct"] < KILL_CRITERIA["wr_pct_min"]:
        alerts.append(
            f"🔴 WR {metrics['v2_wr_pct']}% < {KILL_CRITERIA['wr_pct_min']}% (stratégie perdante)"
        )
    if metrics["v4_profit_factor"] < KILL_CRITERIA["profit_factor_min"]:
        alerts.append(
            f"🔴 PF {metrics['v4_profit_factor']} < {KILL_CRITERIA['profit_factor_min']} (pertes > gains)"
        )
    if abs(metrics["v5_max_dd"]) > KILL_CRITERIA["max_dd_max"]:
        alerts.append(
            f"🔴 Max DD {metrics['v5_max_dd']} > -{KILL_CRITERIA['max_dd_max']} (risque excessif)"
        )
    if metrics["v9_sharpe_like_ann"] < KILL_CRITERIA["sharpe_min"]:
        alerts.append(
            f"🔴 Sharpe {metrics['v9_sharpe_like_ann']} < 0 (Sharpe négatif)"
        )
    if metrics["v3_avg_pnl"] < KILL_CRITERIA["avg_pnl_min"]:
        alerts.append(
            f"🔴 Avg PnL {metrics['v3_avg_pnl']} < 0 (trade moyen perdant)"
        )
    if metrics["v7bis_dup_hidden"] > 0:
        alerts.append(
            f"⚠️  {metrics['v7bis_dup_hidden']} doublons cachés (bug insertion)"
        )
    return alerts


def format_console(metrics: dict) -> str:
    """Formate les métriques pour affichage console."""
    if "error" in metrics:
        return RED(f"❌ ERREUR : {metrics['error']}")

    out = [
        BOLD("=" * 70),
        BOLD(" 🔍 AUDIT INTÉGRITÉ V9 — DB LIVE"),
        BOLD("=" * 70),
        f"DB          : {metrics['db']}",
        f"Filtre      : {metrics['since']}",
        f"Queried at  : {metrics['queried_at']}",
        "",
        BOLD("📊 VRAIS CHIFFRES (DB brute)"),
        f"  V1 Total trades clôturés : {metrics['v1_total']}",
        f"  V2 Wins / WR             : {metrics['v2_wins']} / {metrics['v2_wr_pct']}%",
        f"  V3 PnL brut              : {metrics['v3_pnl_brut']:+} pips",
        f"  V3 PnL net (spread)      : {metrics['v3_pnl_net']:+} pips",
        f"  V3 Avg pnl/trade         : {metrics['v3_avg_pnl']:+.2f} pips",
        f"  V4 Gross win / loss      : {metrics['v4_gross_win']} / {metrics['v4_gross_loss']}",
        f"  V4 Profit Factor         : {metrics['v4_profit_factor']}",
        f"  V5 Max Drawdown          : -{metrics['v5_max_dd']} pips",
        f"  V9 Sharpe-like (ann.)    : {metrics['v9_sharpe_like_ann']}",
        f"  V7 Doublons trade_id     : {metrics['v7_dup_trade_id']}",
        f"  V7bis Doublons cachés    : {metrics['v7bis_dup_hidden']}",
        "",
        BOLD("📅 V6 — Distribution par jour"),
    ]
    for d in metrics["v6_daily"]:
        bar = "█" * int((d["wr_pct"] or 0) / 5)
        wr_display = (str(d["wr_pct"]) + "%") if d["wr_pct"] is not None else "N/A"
        pnl_display = f"{d['pnl_net']:+7.1f}" if d["pnl_net"] is not None else "  N/A  "
        color = GREEN if (d["wr_pct"] or 0) >= 60 else (YELLOW if (d["wr_pct"] or 0) >= 40 else RED)
        out.append(
            f"  {d['date']}  n={d['n']:>3}  WR={color(wr_display):>10}  pnl={pnl_display}  {bar}"
        )
    out.append("")
    out.append(BOLD("📊 V10 — Direction"))
    for d in metrics["v10_direction"]:
        out.append(
            f"  {d['direction']:>10}  n={d['n']:>3}  W={d['wins']:>3}  WR={d['wr_pct']:>5}%  pnl={d['pnl_net']:>+7.1f}"
        )
    out.append("")
    out.append(BOLD("🎯 V12 — WR par confiance"))
    for d in metrics["v12_confiance"]:
        out.append(
            f"  conf={d['conf']:>3}  n={d['n']:>3}  W={d['wins']:>3}  WR={d['wr_pct']:>5}%  pnl={d['pnl_net']:>+7.1f}"
        )

    out.append("")
    out.append(BOLD("🚨 KILL CRITERIA"))
    alerts = check_kill_criteria(metrics)
    if alerts:
        for a in alerts:
            out.append(f"  {a}")
    else:
        out.append(GREEN("  ✅ Aucun kill criteria franchi (système sain)"))

    out.append(BOLD("=" * 70))
    return "\n".join(out)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Audit d'intégrité V9 (rejouable, lecture seule)"
    )
    parser.add_argument(
        "--since", help="Filtre ISO date (ex. 2026-07-15)", default=None
    )
    parser.add_argument(
        "--json", action="store_true", help="Sortie JSON (pour CI/automation)"
    )
    args = parser.parse_args()

    metrics = compute_metrics(since=args.since)

    if args.json:
        print(json.dumps(metrics, indent=2, ensure_ascii=False))
    else:
        print(format_console(metrics))

    # Exit code non-zero si KILL criteria (utile pour CI)
    if "error" not in metrics:
        alerts = check_kill_criteria(metrics)
        if alerts:
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
