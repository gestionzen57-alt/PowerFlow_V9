"""v9_live_candle_ingest.py — P1-1 motion CEO 48h Champ libre.

Ingestion de bougies depuis MT4 bridge (OrderQueue) ou fallback simulation.
Met a jour candles_d, candles_h4, candles_h1 dans la DB.

Auteur : Hermes (P1-1 motion CEO 48h Champ libre, 31/07/2026)
"""
from __future__ import annotations

import argparse
import json
import logging
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

log = logging.getLogger("v9.candle_ingest")

QUEUE_PATH = Path(r"C:\projet\V9\mt4_bridge\OrderQueue.csv")


def init_candles_table(conn: sqlite3.Connection, tf: str) -> None:
    """Cree la table candles_xx si absente."""
    conn.execute(f"""
        CREATE TABLE IF NOT EXISTS candles_{tf.lower()} (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            open REAL, high REAL, low REAL, close REAL,
            volume INTEGER,
            UNIQUE(symbol, timestamp)
        )
    """)
    conn.commit()


def insert_candle(conn: sqlite3.Connection, tf: str, symbol: str,
                    ts: str, o: float, h: float, l: float, c: float,
                    vol: int = 0) -> bool:
    """Insere une bougie (idempotent via UNIQUE)."""
    try:
        conn.execute(f"""
            INSERT OR IGNORE INTO candles_{tf.lower()}
            (symbol, timestamp, open, high, low, close, volume)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (symbol, ts, o, h, l, c, vol))
        conn.commit()
        return True
    except Exception:
        return False


def read_mt4_queue() -> list[dict]:
    """Lit la file MT4 OrderQueue si elle existe."""
    if not QUEUE_PATH.exists():
        return []
    try:
        rows = []
        with open(QUEUE_PATH, encoding="utf-8") as f:
            next(f)  # skip header
            for line in f:
                parts = line.strip().split(",")
                if len(parts) >= 7:
                    rows.append({
                        "symbol": parts[0],
                        "tf": parts[1],
                        "timestamp": parts[2],
                        "open": float(parts[3]),
                        "high": float(parts[4]),
                        "low": float(parts[5]),
                        "close": float(parts[6]),
                        "volume": int(parts[7]) if len(parts) > 7 else 0,
                    })
        return rows
    except Exception:
        return []


def simulate_candles(symbol: str, n: int = 30,
                       base_price: float = 1.30) -> list[dict]:
    """Simule n bougies daily (pour tests sans MT4)."""
    import random
    from datetime import timedelta
    random.seed(42)
    candles = []
    price = base_price
    today = datetime.now(timezone.utc).date()
    for i in range(n):
        date = today - timedelta(days=i)
        ts = date.isoformat() + "T00:00:00"
        change = random.gauss(0, 0.002)
        o = price
        c = price * (1 + change)
        h = max(o, c) * (1 + abs(random.gauss(0, 0.0005)))
        l = min(o, c) * (1 - abs(random.gauss(0, 0.0005)))
        candles.append({
            "symbol": symbol,
            "tf": "D",
            "timestamp": ts,
            "open": round(o, 5),
            "high": round(h, 5),
            "low": round(l, 5),
            "close": round(c, 5),
            "volume": random.randint(500, 2000),
        })
        price = c
    candles.reverse()
    return candles


def ingest(symbol: str, db_path: Path, source: str = "auto",
             simulate: bool = False) -> dict:
    """Ingestion de bougies depuis source."""
    candles = []
    source_used = "unknown"
    if source == "mt4" or (source == "auto" and QUEUE_PATH.exists()
                            and not simulate):
        candles = read_mt4_queue()
        source_used = "mt4_queue"
    if not candles or simulate or source == "simulate":
        candles = simulate_candles(symbol)
        source_used = "simulate"
    # Insertion
    if not db_path.exists():
        return {"error": "db_missing", "source": source_used,
                "n_candles": len(candles), "n_inserted": 0}
    try:
        conn = sqlite3.connect(str(db_path))
        inserted = 0
        try:
            # Init tables
            for tf in ["d", "h4", "h1", "m15", "m5", "m1"]:
                init_candles_table(conn, tf)
            for c in candles:
                if c.get("tf", "D").lower() in ["d", "h4", "h1", "m15",
                                                     "m5", "m1"]:
                    ok = insert_candle(
                        conn, c.get("tf", "D"), c["symbol"],
                        c["timestamp"], c["open"], c["high"],
                        c["low"], c["close"], c["volume"],
                    )
                    if ok:
                        inserted += 1
        finally:
            conn.close()
        return {
            "source": source_used,
            "n_candles": len(candles),
            "n_inserted": inserted,
            "symbol": symbol,
        }
    except (sqlite3.OperationalError, sqlite3.DatabaseError) as e:
        return {"error": str(e), "source": source_used,
                "n_candles": len(candles), "n_inserted": 0}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="V9 live candle ingest (P1-1)",
    )
    parser.add_argument("--symbol", default="GBPUSD")
    parser.add_argument("--source", default="auto",
                        choices=["auto", "mt4", "simulate"])
    args = parser.parse_args(argv)

    from core.v9.config import DB_PATH
    simulate = args.source == "simulate"
    result = ingest(args.symbol, Path(DB_PATH),
                      source=args.source, simulate=simulate)

    print("=" * 70)
    print("P1-1 — LIVE CANDLE INGEST")
    print("=" * 70)
    print(f"Symbol     : {result.get('symbol', 'N/A')}")
    print(f"Source     : {result.get('source', 'unknown')}")
    print(f"N candles  : {result.get('n_candles', 0)}")
    print(f"N inserted : {result.get('n_inserted', 0)}")
    if "error" in result:
        print(f"Erreur     : {result['error']}")
        return 1
    print("=" * 70)
    return 0


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )
    sys.exit(main())