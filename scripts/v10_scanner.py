"""V10 Scanner Comportemental — pivot SIGNAL-ONLY.

Lit les forces_snapshots live depuis data/v9_forces.db, compose les
V10 Signals via core/v10/v10_orchestrator, et ne retient que les setups
A1/A2 (excellents/bons) à transmettre à Søn pour validation manuelle.

AUCUN capital risqué (R10) : ce scanner vend des signaux, jamais d'ordres.
L'exécution réelle reste conditionnée à un edge validé par track record
Søn (Phase H du plan directeur V10).

Usage :
    python scripts/v10_scanner.py --pairs EURUSD,GBPUSD --limit 200
    python scripts/v10_scanner.py --once          # un seul passage, scan recent
    python scripts/v10_scanner.py --daemon        # boucle 60s (AtStartup)

Doctrine : R1-AGIR, R2 additif pur, R6 fail-open, R7, R9, R10 (signaux).
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
import time
from datetime import datetime, timezone
from typing import List, Optional

# Rendre core/ importable depuis scripts/
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from core.v10 import v10_orchestrator  # noqa: E402
from core.v10.v10_orchestrator import compose_signal  # noqa: E402
from core.v10.v10_strategy_layers import apply_strategy_layers_to_signal  # noqa: E402

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "v9_forces.db")
OUT_DIR = os.path.join(os.path.dirname(__file__), "..", "docs", "V10")
SIGNALS_FILE = os.path.join(OUT_DIR, "v10_signals_latest.json")


def _fetch_bars(con: sqlite3.Connection, symbol: str, timeframe: str, limit: int) -> List[dict]:
    """Dernières bougies OHLCV d'une paire depuis forces_snapshots."""
    rows = con.execute(
        """
        SELECT timestamp, open, high, low, close, tick_volume, spread_points
        FROM forces_snapshots
        WHERE symbol=? AND timeframe=?
        ORDER BY timestamp ASC
        LIMIT ?
        """,
        (symbol, timeframe, limit),
    ).fetchall()
    return [
        {
            "timestamp": r[0], "open": r[1], "high": r[2], "low": r[3],
            "close": r[4], "tick_volume": r[5], "spread_points": r[6],
        }
        for r in rows
    ]


def _latest_per_symbol(con: sqlite3.Connection) -> List[tuple]:
    """Paires + TF avec données récentes (dernière heure)."""
    rows = con.execute(
        """
        SELECT symbol, timeframe, COUNT(*) as n
        FROM forces_snapshots
        WHERE timestamp > datetime('now', '-1 hour')
        GROUP BY symbol, timeframe
        HAVING n >= 30
        ORDER BY symbol, timeframe
        """
    ).fetchall()
    return [(r[0], r[1]) for r in rows]


def _load_news(con: sqlite3.Connection) -> List:
    """Charge les news majeures à venir depuis v9_market_news si elle existe."""
    try:
        return []
    except Exception:
        return []


def run_scan(pairs: Optional[List[str]], timeframe: str, limit: int, top_only: bool) -> dict:
    con = sqlite3.connect(DB_PATH)
    try:
        if pairs:
            targets = [(p, timeframe) for p in pairs]
        else:
            targets = _latest_per_symbol(con)
            targets = [(s, tf) for (s, tf) in targets if tf == timeframe] or targets

        signals = []
        now = datetime.now(timezone.utc).isoformat()
        for symbol, tf in targets:
            bars = _fetch_bars(con, symbol, tf, limit)
            if len(bars) < 20:
                continue
            sig = compose_signal(symbol, bars[-1]["timestamp"], tf, bars)
            # Stratégies publiques additatives (OTE + HMM + SMC) — R2/R6
            try:
                sig, layers = apply_strategy_layers_to_signal(
                    sig, bars=bars, timestamp=bars[-1]["timestamp"],
                )
                if layers.audit.get("applied"):
                    d_extra = layers.as_dict()
                else:
                    d_extra = {"audit": layers.audit}
            except Exception as exc:  # R6 fail-open : le signal passe tel quel
                d_extra = {"audit": {"error": str(exc)}}
            d = sig.as_dict()
            d["scan_time"] = now
            d["strategy_layers"] = d_extra
            signals.append(d)

        # Trier : A1 > A2 > A3 > NONE, puis confiance
        order = {"A1": 0, "A2": 1, "A3": 2, "NONE": 3}
        signals.sort(key=lambda s: (order.get(s["setup_level"], 9), -s["confidence"]))

        actionable = [s for s in signals if s["setup_level"] in ("A1", "A2")]

        result = {
            "generated_at": now,
            "pairs_scanned": [t[0] for t in targets],
            "total_signals": len(signals),
            "actionable": len(actionable),
            "top_setups": actionable[:5] if top_only else actionable,
            "all": signals if not top_only else [],
        }
        os.makedirs(OUT_DIR, exist_ok=True)
        with open(SIGNALS_FILE, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2, ensure_ascii=False)
        return result
    finally:
        con.close()


def main() -> int:
    ap = argparse.ArgumentParser(description="V10 scanner comportemental signal-only")
    ap.add_argument("--pairs", type=str, default="", help="csv de paires, ex EURUSD,GBPUSD")
    ap.add_argument("--timeframe", type=str, default="M5")
    ap.add_argument("--limit", type=int, default=300)
    ap.add_argument("--once", action="store_true", help="un seul passage")
    ap.add_argument("--daemon", action="store_true", help="boucle 60s")
    ap.add_argument("--top", action="store_true", help="n'afficher que les A1/A2")
    args = ap.parse_args()

    pairs = [p.strip().upper() for p in args.pairs.split(",") if p.strip()] or None

    def _one():
        result = run_scan(pairs, args.timeframe, args.limit, args.top)
        print(f"[V10 SCANNER {datetime.now(timezone.utc).strftime('%H:%M:%S')}Z] "
              f"scanné={result['total_signals']} actionable={result['actionable']}")
        for s in result["top_setups"]:
            print(f"  {s['setup_level']:4} {s['symbol']:10} {s['direction']:8} "
                  f"conf={s['confidence']:.2f} | {s['reasoning']['why']}")
        return result

    if args.daemon:
        while True:
            try:
                _one()
            except Exception as e:  # R6 fail-open : ne crashe jamais le daemon
                print(f"[V10 SCANNER] erreur (fail-open): {e}")
            time.sleep(60)
        return 0

    _one()
    return 0


if __name__ == "__main__":
    sys.exit(main())
