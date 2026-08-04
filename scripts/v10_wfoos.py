"""
V10 — Walk-Forward Out-of-Sample (WFOOS) analysis.

R2 additif pur : nouveau fichier scripts/. Pas de modif core/.
Phase A prerequisite pour edge fund readiness (Bailey 2014 deflated Sharpe).

Méthodologie :
  1. Découpe la série temporelle en N fenêtres glissantes
     (default: 7j in-sample, 7j out-of-sample, roll 1j)
  2. Pour chaque fold OOS :
     - Calcule Sharpe, WR, PF, MaxDD OOS
     - Compare au IS (in-sample)
     - Edge decay = (IS_sharpe - OOS_sharpe) / IS_sharpe
  3. Synthèse : % folds Sharpe > 1.0, % folds WR > 50%, edge decay moyen

Doctrine :
  R1-AGIR (CEO mandate Go max)
  R6-EXPLIQUER (chaque métrique SQL traçable)
  R7-MESURER (KPIs auto-archivés)
  R9-AUDITABLE (bit-pour-bit reproductible)
  R10-PROTÉGER CAPITAL (zéro kill, lecture seule)

Usage :
  .venv/Scripts/python.exe scripts/v10_wfoos.py
  .venv/Scripts/python.exe scripts/v10_wfoos.py --window 14 --oos 7 --json
"""

from __future__ import annotations

import argparse
import json
import math
import sqlite3
import statistics
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "data" / "v9_forces.db"


def _color(text: str, code: str) -> str:
    return f"\033[{code}m{text}\033[0m" if sys.stdout.isatty() else text


GREEN = lambda t: _color(t, "32")
RED = lambda t: _color(t, "31")
YELLOW = lambda t: _color(t, "33")
BOLD = lambda t: _color(t, "1")


def fetch_trades(con: sqlite3.Connection, since: str | None = None) -> list[dict]:
    """Récupère tous les trades clôturés triés par closed_at."""
    where = "WHERE closed_at IS NOT NULL AND pips_net_of_spread IS NOT NULL"
    params: tuple[Any, ...] = ()
    if since:
        where += " AND closed_at >= ?"
        params = (since,)
    rows = con.execute(
        f"""
        SELECT closed_at, pips_net_of_spread, is_win, confiance
        FROM paper_trades {where}
        ORDER BY closed_at
        """,
        params,
    ).fetchall()
    return [
        {"ts": ts, "pnl": pnl, "win": bool(win), "conf": conf}
        for ts, pnl, win, conf in rows
    ]


def compute_fold_metrics(pnls: list[float]) -> dict[str, float]:
    """Calcule Sharpe-like, WR, PF, MaxDD sur une liste de PnL."""
    if not pnls:
        return {"sharpe": 0.0, "wr": 0.0, "pf": 0.0, "max_dd": 0.0, "n": 0}
    n = len(pnls)
    wins = sum(1 for p in pnls if p > 0)
    wr = wins / n * 100
    gw = sum(p for p in pnls if p > 0)
    gl = abs(sum(p for p in pnls if p < 0))
    pf = gw / gl if gl else float("inf")
    mean = sum(pnls) / n
    std = statistics.stdev(pnls) if n > 1 else 0
    sharpe = (mean / std) * math.sqrt(252) if std else 0.0
    # Max DD
    running = peak = 0.0
    max_dd = 0.0
    for p in pnls:
        running += p
        if running > peak:
            peak = running
        dd = peak - running
        if dd > max_dd:
            max_dd = dd
    return {"sharpe": round(sharpe, 3), "wr": round(wr, 2), "pf": round(pf, 3),
            "max_dd": round(max_dd, 2), "n": n}


def run_wfoos(
    trades: list[dict], window_days: int = 7, oos_days: int = 7
) -> dict[str, Any]:
    """Walk-Forward Out-of-Sample analysis glissant.

    Args:
        trades: liste de trades triés par ts
        window_days: taille fenêtre in-sample (jours)
        oos_days: taille fenêtre out-of-sample (jours)

    Returns:
        dict avec folds, synthèse, edge_decay, kill_criteria
    """
    if not trades:
        return {"error": "Aucun trade", "n_total": 0}

    # Parse timestamps + filter NaN
    parsed: list[tuple[datetime, float]] = []
    for t in trades:
        try:
            ts = datetime.fromisoformat(t["ts"].replace("Z", "+00:00"))
            pnl = t["pnl"]
            if pnl is None:
                continue
            parsed.append((ts, float(pnl)))
        except (ValueError, TypeError):
            continue

    if not parsed:
        return {"error": "Aucun trade valide", "n_total": 0}

    start = parsed[0][0]
    end = parsed[-1][0]
    total_days = (end - start).days

    if total_days < window_days + oos_days:
        return {
            "error": f"Données insuffisantes ({total_days}j < {window_days + oos_days}j)",
            "n_total": len(parsed),
        }

    # Sliding windows: 1 day step
    folds: list[dict[str, Any]] = []
    cursor = start
    step = timedelta(days=1)

    while cursor + timedelta(days=window_days + oos_days) <= end:
        is_start = cursor
        is_end = cursor + timedelta(days=window_days)
        oos_start = is_end
        oos_end = oos_start + timedelta(days=oos_days)

        # In-sample PnL
        is_pnls = [p for ts, p in parsed if is_start <= ts < is_end]
        # Out-of-sample PnL
        oos_pnls = [p for ts, p in parsed if oos_start <= ts < oos_end]

        if not is_pnls or not oos_pnls:
            cursor += step
            continue

        is_m = compute_fold_metrics(is_pnls)
        oos_m = compute_fold_metrics(oos_pnls)

        edge_decay = (
            ((is_m["sharpe"] - oos_m["sharpe"]) / abs(is_m["sharpe"]) * 100)
            if is_m["sharpe"] != 0
            else 0.0
        )

        folds.append({
            "fold_id": len(folds) + 1,
            "is_start": is_start.isoformat(),
            "is_end": is_end.isoformat(),
            "oos_start": oos_start.isoformat(),
            "oos_end": oos_end.isoformat(),
            "is": is_m,
            "oos": oos_m,
            "edge_decay_pct": round(edge_decay, 1),
        })

        cursor += step

    if not folds:
        return {"error": "Aucun fold généré", "n_total": len(parsed)}

    # Synthèse
    n_folds = len(folds)
    pct_oos_positive = sum(1 for f in folds if f["oos"]["sharpe"] > 0) / n_folds * 100
    pct_oos_sharpe_gt_1 = sum(1 for f in folds if f["oos"]["sharpe"] > 1.0) / n_folds * 100
    pct_oos_wr_gt_50 = sum(1 for f in folds if f["oos"]["wr"] > 50) / n_folds * 100
    avg_edge_decay = statistics.mean(f["edge_decay_pct"] for f in folds)
    avg_oos_sharpe = statistics.mean(f["oos"]["sharpe"] for f in folds)
    avg_oos_wr = statistics.mean(f["oos"]["wr"] for f in folds)

    # Kill criteria
    alerts: list[str] = []
    if avg_oos_sharpe < 0.5:
        alerts.append(f"🔴 Sharpe OOS moyen {avg_oos_sharpe} < 0.5 (edge détruit)")
    if pct_oos_sharpe_gt_1 < 30:
        alerts.append(f"🔴 {pct_oos_sharpe_gt_1:.0f}% folds Sharpe>1 (cible >30%)")
    if avg_edge_decay > 50:
        alerts.append(f"🔴 Edge decay moyen {avg_edge_decay:.0f}% > 50% (overfitting)")
    if pct_oos_wr_gt_50 < 50:
        alerts.append(f"🔴 {pct_oos_wr_gt_50:.0f}% folds WR>50 (cible >50%)")

    return {
        "n_total_trades": len(parsed),
        "n_folds": n_folds,
        "window_days": window_days,
        "oos_days": oos_days,
        "period_start": start.isoformat(),
        "period_end": end.isoformat(),
        "synthese": {
            "avg_oos_sharpe": round(avg_oos_sharpe, 3),
            "avg_oos_wr_pct": round(avg_oos_wr, 2),
            "pct_oos_positive": round(pct_oos_positive, 1),
            "pct_oos_sharpe_gt_1": round(pct_oos_sharpe_gt_1, 1),
            "pct_oos_wr_gt_50": round(pct_oos_wr_gt_50, 1),
            "avg_edge_decay_pct": round(avg_edge_decay, 1),
        },
        "folds": folds,
        "kill_criteria": alerts,
        "verdict": "GO" if not alerts else "NO-GO",
    }


def format_console(result: dict) -> str:
    if "error" in result:
        return RED(f"❌ {result['error']}")
    out = [
        BOLD("=" * 70),
        BOLD(" 🔬 V10 WFOOS — Walk-Forward Out-of-Sample Analysis"),
        BOLD("=" * 70),
        f"Trades totaux    : {result['n_total_trades']}",
        f"Folds générés    : {result['n_folds']}",
        f"Window IS/OOS    : {result['window_days']}j / {result['oos_days']}j",
        f"Période          : {result['period_start'][:10]} → {result['period_end'][:10]}",
        "",
        BOLD("📊 Synthèse OOS (out-of-sample)"),
        f"  Sharpe moyen OOS      : {result['synthese']['avg_oos_sharpe']}",
        f"  WR moyen OOS          : {result['synthese']['avg_oos_wr_pct']}%",
        f"  % folds Sharpe > 0    : {result['synthese']['pct_oos_positive']}%",
        f"  % folds Sharpe > 1.0  : {result['synthese']['pct_oos_sharpe_gt_1']}%",
        f"  % folds WR > 50%      : {result['synthese']['pct_oos_wr_gt_50']}%",
        f"  Edge decay moyen      : {result['synthese']['avg_edge_decay_pct']}%",
        "",
        BOLD("🚨 KILL CRITERIA"),
    ]
    if result["kill_criteria"]:
        for a in result["kill_criteria"]:
            out.append(f"  {a}")
        out.append("")
        out.append(RED(f"  ❌ VERDICT : {result['verdict']}"))
    else:
        out.append(GREEN("  ✅ Aucun kill criteria franchi"))
        out.append(GREEN(f"  ✅ VERDICT : {result['verdict']}"))
    out.append(BOLD("=" * 70))
    return "\n".join(out)


def main() -> int:
    parser = argparse.ArgumentParser(description="V10 WFOOS analysis")
    parser.add_argument("--window", type=int, default=7, help="In-sample window (jours)")
    parser.add_argument("--oos", type=int, default=7, help="Out-of-sample window (jours)")
    parser.add_argument("--since", default=None, help="Filtre ISO date")
    parser.add_argument("--json", action="store_true", help="Sortie JSON")
    parser.add_argument("--auto", action="store_true", help="Auto-ajuster window si données insuffisantes")
    args = parser.parse_args()

    if not DB_PATH.exists():
        print(RED(f"❌ DB introuvable: {DB_PATH}"))
        return 1

    con = sqlite3.connect(str(DB_PATH), timeout=5)
    try:
        trades = fetch_trades(con, since=args.since)
    finally:
        con.close()

    result = run_wfoos(trades, window_days=args.window, oos_days=args.oos)

    # Auto-retry si données insuffisantes et --auto
    if "error" in result and "Données insuffisantes" in result["error"] and args.auto:
        # Retry avec window=3, oos=3
        result = run_wfoos(trades, window_days=3, oos_days=3)
        if "error" not in result:
            result["auto_adjusted"] = True

    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print(format_console(result))

    return 0 if result.get("verdict") == "GO" else 1


if __name__ == "__main__":
    raise SystemExit(main())