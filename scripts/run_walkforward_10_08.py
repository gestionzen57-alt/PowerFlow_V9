"""V10 WalkForward C18 — BacktestEngine + WalkForward sur forces_snapshots (R2 additif).

Mission ORCHESTRATION_STATE 3474d36 — Chantier 2.
Cible : wfa_robust = True dans DeploymentValidator (efficiency ≥ 0.55).

Charge les snapshots live 7j (TF M15/M30/H1), construit des trades directionnels,
lance BacktestEngine pour calculer la métrique (WR), puis WalkForward pour mesurer
la robustesse out-of-sample.

R6 fail-open : chaque étape isolée en try/except.
R9 : rapport JSON dans reports/.
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone

DB = "C:/projet/V9/data/v9_forces.db"  # vraie DB (worktree principal)
SINCE = "2026-08-05T00:00:00Z"  # 7 jours
TFS = ("M15", "M30", "H1")


def _load_snapshots(db_path: str, since: str) -> list:
    """Charge les snapshots live (symbol, tf, close, direction, timestamp)."""
    try:
        conn = sqlite3.connect(db_path, timeout=10)
        rows = conn.execute(
            "SELECT symbol, timeframe, close, direction, timestamp "
            "FROM forces_snapshots WHERE timestamp > ? "
            "AND timeframe IN ('M15','M30','H1') "
            "ORDER BY timestamp",
            (since,),
        ).fetchall()
        conn.close()
        return [dict(zip(("symbol", "timeframe", "close", "direction", "timestamp"), r)) for r in rows]
    except Exception as e:
        print(f"[WARN] _load_snapshots: {e}")
        return []


def _decide_direction(snap: dict) -> str:
    d = str(snap.get("direction", "neutre")).lower()
    if d in ("haussiere", "bullish", "buy", "long"):
        return "BUY"
    if d in ("baissiere", "bearish", "sell", "short"):
        return "SELL"
    return "NEUTRAL"


def _build_trades(snaps: list) -> list:
    """Construit des BacktestTrade depuis les snapshots directionnels.

    NB : BacktestTrade (C18) n'est PAS un @dataclass (bug module) — on
    l'instancie via __new__ + assignation d'attributs (R2 : 0 modif module).
    """
    try:
        from core.v10.v10_backtest_engine import BacktestTrade
    except ImportError as e:
        print(f"[WARN] BacktestTrade import: {e}")
        return []
    trades = []
    for snap in snaps:
        direction = _decide_direction(snap)
        if direction == "NEUTRAL" or not snap.get("close"):
            continue
        entry = float(snap["close"])
        if entry <= 0:
            continue
        if direction == "BUY":
            sl, tp = entry * 0.99, entry * 1.02
        else:
            sl, tp = entry * 1.01, entry * 0.98
        t = BacktestTrade.__new__(BacktestTrade)
        t.pair = snap["symbol"]
        t.direction = direction
        t.entry = entry
        t.sl = sl
        t.tp = tp
        t.lot = 0.01
        t.commission = 0.0
        t.slippage_pips = 0.5
        trades.append(t)
    return trades


def _win_rate_metric(trades: list) -> float:
    """Métrique : win rate d'un sous-ensemble de trades (via BacktestEngine)."""
    if not trades:
        return 0.0
    try:
        import math
        import core.v10.v10_backtest_engine as be
        # Workaround R2 : le module C18 utilise `math` sans l'importer (bug).
        # On l'injecte dans son namespace (0 modification du fichier module).
        if not hasattr(be, "math"):
            be.math = math
        from core.v10.v10_backtest_engine import BacktestEngine
        engine = BacktestEngine()
        summary, _ = engine.run(trades)
        return summary.win_rate
    except Exception as e:
        print(f"[WARN] _win_rate_metric: {e}")
        return 0.0


def main() -> None:
    now = datetime.now(timezone.utc)
    print(f"[{now.isoformat()}] WalkForward C18 — BacktestEngine sur forces_snapshots...")

    snaps = _load_snapshots(DB, SINCE)
    print(f"Snapshots live chargés : {len(snaps)}")

    trades = _build_trades(snaps)
    print(f"Trades construits : {len(trades)}")

    results: dict = {"ts": now.isoformat(), "n_snapshots": len(snaps), "n_trades": len(trades)}

    # 1. BacktestEngine — métrique globale
    try:
        import math
        import core.v10.v10_backtest_engine as be
        if not hasattr(be, "math"):
            be.math = math
        from core.v10.v10_backtest_engine import BacktestEngine
        engine = BacktestEngine()
        summary, _ = engine.run(trades)
        results["backtest"] = summary.as_dict()
        print(f"BacktestEngine : WR={summary.win_rate:.4f} sharpe={summary.sharpe:.4f} PF={summary.profit_factor:.4f}")
    except Exception as e:
        results["backtest"] = f"ERROR:{e}"
        print(f"[WARN] BacktestEngine : {e}")

    # 2. WalkForward — robustesse out-of-sample
    try:
        from core.v10.v10_walk_forward import WalkForward
        wf = WalkForward()
        wf_result = wf.run(trades, _win_rate_metric)
        results["walkforward"] = {
            "avg_efficiency": round(wf_result.avg_efficiency, 4),
            "robust": wf_result.robust,
            "n_windows": len(wf_result.windows),
            "threshold": WalkForward.ROBUST_THRESHOLD,
        }
        print(f"WalkForward : avg_efficiency={wf_result.avg_efficiency:.4f} robust={wf_result.robust}")
    except Exception as e:
        results["walkforward"] = f"ERROR:{e}"
        print(f"[WARN] WalkForward : {e}")

    out = "reports/walkforward_2026_08_10.json"
    with open(out, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, default=str)
    print(f"Rapport : {out}")


if __name__ == "__main__":
    main()
