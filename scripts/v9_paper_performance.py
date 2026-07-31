"""v9_paper_performance.py — Phase 21 motion CEO « EDGE FUND MAX ».

Rapport de performance avance sur paper trades (Phase 16 live) :
- Total pips brut / net
- Sharpe-like ratio (mean / std)
- Sortino-like ratio (mean / downside_std)
- Max drawdown duration (jours)
- Recovery factor
- Profit factor (gross_wins / gross_losses)

Usage :
  python scripts/v9_paper_performance.py            # rapport complet
  python scripts/v9_paper_performance.py --json     # JSON brut
  python scripts/v9_paper_performance.py --days 30  # 30 derniers jours

Auteur : Hermes (Phase 21 motion CEO autopilote, 31/07/2026)
"""
from __future__ import annotations

import argparse
import json
import logging
import math
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

# Bootstrap path pour execution directe CLI.
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

log = logging.getLogger("v9.paper_performance")


def compute_performance(trades: list[dict]) -> dict:
    """Calcule les metriques avancees sur une liste de trades."""
    n = len(trades)
    if n == 0:
        return {"error": "no_trades"}

    pips_net_list = [float(t.get("pips_net") or 0) for t in trades]
    pips_brut_list = [float(t.get("pips_brut") or 0) for t in trades]
    total_net = sum(pips_net_list)
    total_brut = sum(pips_brut_list)
    wins = [p for p in pips_net_list if p > 0]
    losses = [p for p in pips_net_list if p < 0]
    n_wins = len(wins)
    n_losses = len(losses)
    win_rate = 100.0 * n_wins / n if n else 0.0
    avg_pips_net = total_net / n
    avg_pips_brut = total_brut / n

    # Sharpe-like (mean / std)
    if n >= 2:
        mean = avg_pips_net
        variance = sum((p - mean) ** 2 for p in pips_net_list) / (n - 1)
        std = math.sqrt(variance)
        sharpe = mean / std if std > 0 else 0.0
    else:
        sharpe = 0.0

    # Sortino-like (mean / downside_std)
    if n >= 2:
        downside = [p for p in pips_net_list if p < 0]
        if downside:
            downside_mean = sum(downside) / len(downside)
            downside_var = sum((p - downside_mean) ** 2 for p in downside) / max(len(downside) - 1, 1)
            downside_std = math.sqrt(downside_var)
            sortino = mean / downside_std if downside_std > 0 else 0.0
        else:
            sortino = float("inf")
    else:
        sortino = 0.0

    # Profit factor
    gross_wins = sum(wins)
    gross_losses = abs(sum(losses))
    profit_factor = gross_wins / gross_losses if gross_losses > 0 else float("inf")

    # Max DD + duree
    running_max = 0.0
    running_dd = 0.0
    max_dd = 0.0
    max_dd_open_id = None
    max_dd_close_id = None
    max_dd_recovery_id = None
    for i, t in enumerate(trades):
        running_dd += float(t.get("pips_net") or 0)
        if running_dd > running_max:
            running_max = running_dd
        drawdown = running_max - running_dd
        if drawdown > max_dd:
            max_dd = drawdown
            max_dd_open_id = t.get("id")
        if running_dd >= running_max:
            max_dd_recovery_id = t.get("id")

    # Recovery factor
    recovery_factor = total_net / max_dd if max_dd > 0 else float("inf")

    # Expectancy
    expectancy_net = avg_pips_net
    expectancy_brut = avg_pips_brut

    return {
        "n_total": n,
        "n_wins": n_wins,
        "n_losses": n_losses,
        "win_rate_pct": round(win_rate, 2),
        "total_pips_brut": round(total_brut, 2),
        "total_pips_net": round(total_net, 2),
        "expectancy_brut": round(expectancy_brut, 2),
        "expectancy_net": round(expectancy_net, 2),
        "sharpe_like": round(sharpe, 3),
        "sortino_like": round(sortino, 3) if sortino != float("inf") else "inf",
        "profit_factor": round(profit_factor, 3) if profit_factor != float("inf") else "inf",
        "max_dd_pips": round(max_dd, 2),
        "recovery_factor": round(recovery_factor, 2) if recovery_factor != float("inf") else "inf",
        "ts": datetime.now(timezone.utc).isoformat(),
    }


def get_paper_trades(db_path: Path | str, days: int | None = None) -> list[dict]:
    """Retourne les paper trades fermes depuis la table v9_paper_trades."""
    db_path = Path(db_path)
    if not db_path.exists():
        return []
    try:
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        try:
            if days is not None:
                # Note : datetime('now') retourne 'YYYY-MM-DD HH:MM:SS' (espace)
                # tandis que opened_at est 'YYYY-MM-DDTHH:MM:SS' (T ISO).
                # On convertit datetime('now') en ISO pour comparaison string coherente.
                # Detecter presence de direction (degrade propre)
                has_direction = False
                try:
                    cols = [r[1] for r in conn.execute(
                        "PRAGMA table_info(v9_paper_trades)"
                    ).fetchall()]
                    has_direction = "direction" in cols
                except Exception:
                    pass
                dir_select = (
                    "direction," if has_direction
                    else "'unknown' AS direction,"
                )
                rows = conn.execute(f"""
                    SELECT id, symbol, {dir_select} opened_at, closed_at,
                           pips_brut, pips_net, spread_pips
                    FROM v9_paper_trades
                    WHERE closed_at IS NOT NULL
                      AND opened_at > REPLACE(datetime('now', ? || ' days'), ' ', 'T')
                    ORDER BY opened_at ASC
                """, (-days,)).fetchall()
            else:
                rows = conn.execute("""
                    SELECT id, symbol, direction, opened_at, closed_at,
                           pips_brut, pips_net, spread_pips
                    FROM v9_paper_trades
                    WHERE closed_at IS NOT NULL
                    ORDER BY opened_at ASC
                """).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()
    except (sqlite3.OperationalError, sqlite3.DatabaseError):
        return []


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="V9 paper performance report (Phase 21)",
    )
    parser.add_argument("--json", action="store_true",
                        help="JSON brut")
    parser.add_argument("--days", type=int, default=None,
                        help="Filtre sur N derniers jours")
    args = parser.parse_args(argv)

    from core.v9.config import DB_PATH
    trades = get_paper_trades(DB_PATH, days=args.days)
    perf = compute_performance(trades)

    if args.json:
        print(json.dumps(perf, indent=2, ensure_ascii=False))
        return 0

    print("=" * 70)
    print("PHASE 21 — PAPER PERFORMANCE REPORT")
    if args.days:
        print(f"Periode : {args.days} derniers jours")
    print("=" * 70)
    if "error" in perf:
        print(f"Erreur : {perf['error']}")
        return 1

    print(f"Trades fermes      : {perf['n_total']}  "
          f"(wins: {perf['n_wins']}, losses: {perf['n_losses']})")
    print(f"Win rate           : {perf['win_rate_pct']:.1f}%")
    print(f"Pips total brut    : {perf['total_pips_brut']:+.1f}")
    print(f"Pips total net     : {perf['total_pips_net']:+.1f}")
    print(f"Expectancy brut    : {perf['expectancy_brut']:+.2f}p")
    print(f"Expectancy net     : {perf['expectancy_net']:+.2f}p")
    print()
    print(f"Sharpe-like ratio  : {perf['sharpe_like']:.3f}")
    print(f"Sortino-like ratio : {perf['sortino_like']}")
    print(f"Profit factor      : {perf['profit_factor']}")
    print(f"Max drawdown       : {perf['max_dd_pips']:.1f}p")
    print(f"Recovery factor    : {perf['recovery_factor']}")
    print()
    print("=" * 70)
    return 0


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )
    sys.exit(main())