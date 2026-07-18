"""v9_strategy_compare.py — Compare 4 stratégies de gestion alternatives.

2026-07-17 motion CEO « test different strategie de gestion ».

Le CEO a identifié que les baissiers perdent à cause d'un biais haussier
intrinsèque du prix. Il faut tester des stratégies qui résistent à ce biais.

4 stratégies de gestion testées :
  1. BASELINE : TP=8, SL=15, TP_SL classique
  2. ASYMMETRIC : TP=6, SL=30, ratio 1:5 (small win, big risk)
  3. TIME_EXIT : exit après 5 barres M5 = 25 min peu importe P&L
  4. TRAILING_TIGHT : trailing stop serré 3 pips
  5. TREND_FILTER : ne pas shorter si tendance haussière (MA20 > MA50)

Pour chaque stratégie × tous les trades baissiers GBPUSD, on calcule :
  - WR
  - avg_pips
  - total_pips
  - max_drawdown
  - sharpe_like
"""
from __future__ import annotations

import json
import logging
import sqlite3
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.v9.db_schema import get_connection  # noqa: E402
from core.v9.exit_simulator import (  # noqa: E402
    ExitSimulator,
    ExitStrategy,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("v9.strat_compare")


def load_baissier_trades(db_path: Path | str) -> list[dict]:
    """Charge tous les trades baissiers GBPUSD avec M5 futures."""
    conn = get_connection(db_path)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        """
        SELECT pt.trade_id, pt.opened_at, d.symbol
        FROM paper_trades pt
        JOIN decisions d ON d.snapshot_id=pt.snapshot_id
        WHERE pt.closed_at IS NOT NULL
          AND d.symbol='GBPUSD' AND pt.direction='baissiere'
        ORDER BY pt.opened_at
        """
    ).fetchall()
    conn.close()

    trades = []
    for r in rows:
        try:
            odt = datetime.fromisoformat(r["opened_at"].replace("Z", "+00:00"))
            epoch = int(odt.timestamp())
        except Exception:
            continue
        conn = get_connection(db_path)
        fr = conn.execute(
            """
            SELECT mid FROM forces_snapshots
            WHERE symbol = ? AND timeframe = 'M5'
              AND bar_time > ?
            ORDER BY bar_time ASC
            LIMIT 200
            """,
            (r["symbol"], epoch),
        ).fetchall()
        conn.close()
        if not fr:
            continue
        future_mids = [float(f[0]) for f in fr]
        trades.append({
            "trade_id": r["trade_id"],
            "opened_at": r["opened_at"],
            "entry_price": future_mids[0],
            "future_mids": future_mids,
            "n_bars": len(future_mids),
        })
    return trades


def strat_baseline(trade: dict) -> float:
    """TP=8, SL=15, TP_SL classique."""
    sim = ExitSimulator(strategy="TP_SL", tp_pips=8, sl_pips=15, symbol="GBPUSD")
    res = sim.simulate(
        entry=trade["entry_price"], direction="baissiere",
        future_mids=trade["future_mids"],
    )
    return res.pips


def strat_asymmetric(trade: dict) -> float:
    """TP=6, SL=30, ratio 1:5 (small win, big risk)."""
    sim = ExitSimulator(strategy="TP_SL", tp_pips=6, sl_pips=30, symbol="GBPUSD")
    res = sim.simulate(
        entry=trade["entry_price"], direction="baissiere",
        future_mids=trade["future_mids"],
    )
    return res.pips


def strat_time_exit(trade: dict) -> float:
    """Exit après 5 barres M5 = 25min peu importe P&L."""
    sim = ExitSimulator(strategy="TIME_BASED", time_bars=5, symbol="GBPUSD")
    res = sim.simulate(
        entry=trade["entry_price"], direction="baissiere",
        future_mids=trade["future_mids"],
    )
    return res.pips


def strat_trailing_tight(trade: dict) -> float:
    """Trailing stop serré 3 pips."""
    sim = ExitSimulator(strategy="TRAILING", trailing_dist=3.0, symbol="GBPUSD")
    res = sim.simulate(
        entry=trade["entry_price"], direction="baissiere",
        future_mids=trade["future_mids"],
    )
    return res.pips


def strat_trend_filter(trade: dict) -> float:
    """Trade baissier MAIS avec TP=4 SL=12 (small tight)."""
    # On filtre par tendance en M15
    try:
        odt = datetime.fromisoformat(trade["opened_at"].replace("Z", "+00:00"))
        epoch = int(odt.timestamp())
    except Exception:
        return strat_baseline(trade)
    conn = get_connection(ROOT / "data" / "v9_forces.db")
    conn.row_factory = sqlite3.Row
    # Récupère 20 M15 mid pour calculer MA20
    try:
        rows = conn.execute(
            """
            SELECT mid FROM forces_snapshots
            WHERE symbol='GBPUSD' AND timeframe='M15'
              AND bar_time < ?
            ORDER BY bar_time DESC LIMIT 20
            """,
            (epoch,),
        ).fetchall()
    finally:
        conn.close()
    if len(rows) < 20:
        return strat_baseline(trade)
    prices = [float(r["mid"]) for r in rows][::-1]
    ma20 = sum(prices) / 20
    # Si prix > MA20, tendance haussière → SKIP (return 0 = no trade)
    if trade["entry_price"] > ma20:
        return 0.0
    # Sinon trend baissière → trade avec paramètres
    sim = ExitSimulator(strategy="TP_SL", tp_pips=6, sl_pips=15, symbol="GBPUSD")
    res = sim.simulate(
        entry=trade["entry_price"], direction="baissiere",
        future_mids=trade["future_mids"],
    )
    return res.pips


def strat_combo_asym_time(trade: dict) -> float:
    """Combo : ASYM (TP=6, SL=20) + time exit court 8 barres."""
    sim = ExitSimulator(
        strategy="TP_SL", tp_pips=6, sl_pips=20, time_bars=8, symbol="GBPUSD",
    )
    res = sim.simulate(
        entry=trade["entry_price"], direction="baissiere",
        future_mids=trade["future_mids"],
    )
    # Override : si pas de TP/SL hit, time exit forcé
    if res.exit_reason not in ("tp_hit", "sl_hit"):
        # Time exit
        n = min(8, len(trade["future_mids"]))
        last = trade["future_mids"][n - 1]
        entry = trade["entry_price"]
        return (entry - last) * 10000
    return res.pips


def evaluate_strategy(
    trades: list[dict], strategy_fn, name: str
) -> dict[str, Any]:
    """Évalue une stratégie sur tous les trades."""
    wins = 0
    losses = 0
    skipped = 0
    total_pips = 0.0
    cum = 0.0
    peak = 0.0
    max_dd = 0.0
    pips_list = []

    for trade in trades:
        pips = strategy_fn(trade)
        if pips == 0 and strategy_fn == strat_trend_filter:
            # Trend filter skip
            skipped += 1
            continue
        pips_list.append(pips)
        if pips > 0:
            wins += 1
        else:
            losses += 1
        total_pips += pips
        cum += pips
        if cum > peak:
            peak = cum
        dd = peak - cum
        if dd > max_dd:
            max_dd = dd

    n_traded = wins + losses
    n_total = len(trades)
    wr = round(100 * wins / n_traded, 2) if n_traded else 0
    avg = round(total_pips / n_traded, 2) if n_traded else 0
    # Sharpe-like
    if len(pips_list) > 1:
        import statistics
        std = statistics.pstdev(pips_list) or 1
        sharpe = round(avg / std, 3)
    else:
        sharpe = 0

    return {
        "strategy": name,
        "n_total": n_total,
        "n_traded": n_traded,
        "n_skipped": skipped,
        "wins": wins,
        "losses": losses,
        "wr_pct": wr,
        "avg_pips": avg,
        "total_pips": round(total_pips, 1),
        "max_dd": round(max_dd, 1),
        "sharpe_like": sharpe,
    }


def main() -> int:
    log.info("=" * 60)
    log.info("COMPARAISON STRATÉGIES DE GESTION — baissier GBPUSD")
    log.info("=" * 60)

    trades = load_baissier_trades(ROOT / "data" / "v9_forces.db")
    log.info(f"Trades baissier GBPUSD chargés : {len(trades)}")

    if not trades:
        log.error("Aucun trade")
        return 1

    strategies = [
        (strat_baseline, "BASELINE TP=8/SL=15"),
        (strat_asymmetric, "ASYMMETRIC TP=6/SL=30 (1:5)"),
        (strat_time_exit, "TIME_EXIT 5 barres M5"),
        (strat_trailing_tight, "TRAILING_TIGHT 3pips"),
        (strat_trend_filter, "TREND_FILTER (skip haussière) TP=6/SL=15"),
        (strat_combo_asym_time, "COMBO ASYM TP=6/SL=20+time8"),
    ]

    results = []
    for fn, name in strategies:
        log.info(f"  Testing {name}...")
        r = evaluate_strategy(trades, fn, name)
        results.append(r)

    log.info("\n" + "=" * 60)
    log.info("RÉSULTATS (triés par total_pips)")
    log.info("=" * 60)
    print(f"{'Strategy':>40s} | {'Traded':>7} {'Wins':>5} {'WR%':>6} {'Avg':>8} {'Total':>10} {'MaxDD':>8} {'Sharpe':>8}")
    for r in sorted(results, key=lambda x: -x["total_pips"]):
        print(
            f"  {r['strategy']:>40s} | {r['n_traded']:>7} {r['wins']:>5} {r['wr_pct']:>5.1f}% "
            f"{r['avg_pips']:>+7.2f} {r['total_pips']:>+9.1f} {r['max_dd']:>7.1f} {r['sharpe_like']:>7.3f}"
        )

    # Export
    out = ROOT / "data" / "strategy_pole" / "strategy_comparison.json"
    with open(out, "w", encoding="utf-8") as f:
        json.dump({
            "generated_at": datetime.now().isoformat(),
            "n_trades_baissier_gbpusd": len(trades),
            "results": results,
        }, f, indent=2, ensure_ascii=False)
    log.info(f"\nExporté dans {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())