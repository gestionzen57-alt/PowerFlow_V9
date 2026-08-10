"""V10 Health Dashboard — monitoring live lisible en 10 secondes (R2 additif).

Chantier 4 / HERMES_PROMPT_MAX_V2 (Perplexity CEO 10/08 10:23 CEST).

Affiche : fraîcheur par (paire, TF), 10 derniers paper trades, alertes stale.
Adapté au schéma réel de data/v9_forces.db (colonne symbol, bar_time epoch int).

R6 fail-open : chaque section isolée en try/except.
"""
from __future__ import annotations

import sqlite3
import time
from datetime import datetime, timezone

DB = "data/v9_forces.db"


def _lag_minutes(last_ts_iso) -> float:
    """Lag en minutes depuis un timestamp ISO UTC (colonne `timestamp`)."""
    if not last_ts_iso:
        return 9999.0
    try:
        s = str(last_ts_iso).replace("Z", "+00:00")
        last = datetime.fromisoformat(s)
        if last.tzinfo is None:
            last = last.replace(tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - last).total_seconds() / 60.0
    except Exception:
        return 9999.0


def main() -> None:
    now = datetime.now(timezone.utc)
    print("\n" + "=" * 60)
    print("  PowerFlow V10 — Health Dashboard")
    print(f"  {now.strftime('%Y-%m-%d %H:%M:%S UTC')}")
    print("=" * 60)

    try:
        conn = sqlite3.connect(DB, timeout=10)
    except Exception as e:
        print(f"[FATAL] Connexion DB {DB} : {e}")
        return

    # 1. Fraîcheur par (paire, TF) — basé sur colonne `timestamp` (ISO UTC)
    try:
        # filtre relatif : dernières 2h (les timestamps sont ≤ now, pas > now)
        cutoff = (datetime.now(timezone.utc).timestamp() - 2 * 3600)
        cutoff_iso = datetime.fromtimestamp(cutoff, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        rows = conn.execute(
            "SELECT symbol, timeframe, MAX(timestamp) as last_ts "
            "FROM forces_snapshots "
            "WHERE timestamp > ? "
            "GROUP BY symbol, timeframe ORDER BY symbol, timeframe",
            (cutoff_iso,),
        ).fetchall()
        print("\n📊 FRESHNESS (lag en minutes)")
        # pivot symbol x timeframe
        pivot: dict = {}
        for sym, tf, last_ts in rows:
            pivot.setdefault(sym, {})[tf] = round(_lag_minutes(last_ts), 0)
        if not pivot:
            print("  (aucune donnée récente)")
        else:
            tfs = sorted({tf for d in pivot.values() for tf in d})
            header = "  pair      " + "".join(f"{tf:>7}" for tf in tfs)
            print(header)
            for sym in sorted(pivot):
                line = f"  {sym:<9}" + "".join(
                    f"{pivot[sym].get(tf, '—'):>7}" for tf in tfs
                )
                print(line)
    except Exception as e:
        print(f"[freshness] {e}")

    # 2. 10 derniers paper trades
    try:
        trades = conn.execute(
            "SELECT symbol, direction, pips_net_of_spread, closed_at "
            "FROM paper_trades ORDER BY closed_at DESC LIMIT 10"
        ).fetchall()
        print("\n📈 10 DERNIERS PAPER TRADES")
        if not trades:
            print("  (aucun paper trade)")
        else:
            for sym, direction, pnl, closed in trades:
                sign = "+" if (pnl or 0) > 0 else ""
                print(f"  {sym:<8} {str(direction):<8} {sign}{pnl or 0:>8}  {closed}")
            wins = sum(1 for t in trades if (t[2] or 0) > 0)
            print(f"  WR 10 derniers : {wins/len(trades):.1%}")
    except Exception as e:
        print(f"[paper_trades] {e}")

    # 3. Alertes stale (> 90 min)
    try:
        stale = [
            (sym, tf, round(_lag_minutes(last_ts), 0))
            for sym, tf, last_ts in rows
            if _lag_minutes(last_ts) > 90
        ]
        if stale:
            print(f"\n🔴 STALE ALERTS ({len(stale)} combos > 90 min)")
            for sym, tf, lag in stale:
                print(f"  {sym:<8} {tf:<5} lag={lag:.0f} min")
        else:
            print("\n✅ Tous les combos sont frais (< 90 min)")
    except Exception as e:
        print(f"[stale] {e}")

    conn.close()
    print("\n" + "=" * 60 + "\n")


if __name__ == "__main__":
    main()
