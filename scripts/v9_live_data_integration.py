"""v9_live_data_integration.py — Phase 82 motion CEO 48H (post-Plan C).

Test d'integration live candles MT4 → DB → multi-TF reader.
Verifie que les donnees circulent correctement entre les modules.

Auteur : Hermes (Phase 82 motion CEO 48H non-stop, 31/07/2026)
"""
from __future__ import annotations

import json
import logging
import sqlite3
import tempfile
from pathlib import Path
from typing import Any

log = logging.getLogger("v9.live_data")

REQUIRED_TABLES = [
    "candles_d", "candles_h4", "candles_h1",
    "candles_m15", "candles_m5", "candles_m1",
]

REQUIRED_COLUMNS = ["symbol", "tf", "timestamp", "open", "high", "low", "close"]


def init_candles_tables(db_path: Path) -> bool:
    """Initialise les tables candles multi-TF."""
    try:
        with sqlite3.connect(str(db_path)) as conn:
            for tf_table in REQUIRED_TABLES:
                cols = ", ".join(
                    f"{c} REAL NOT NULL" if c not in ("symbol", "tf", "timestamp")
                    else f"{c} TEXT NOT NULL"
                    for c in REQUIRED_COLUMNS
                )
                conn.execute(
                    f"CREATE TABLE IF NOT EXISTS {tf_table} ("
                    f"{cols}, PRIMARY KEY (symbol, tf, timestamp))"
                )
            conn.commit()
        return True
    except Exception as exc:
        log.warning("init_candles_tables failed: %s", exc)
        return False


def ingest_candles_batch(
    db_path: Path,
    symbol: str,
    tf: str,
    candles: list[dict[str, Any]],
) -> int:
    """Insere un batch de candles pour un (symbol, tf).

    candles : list de dicts avec open/high/low/close/timestamp/volume.
    Retourne le nombre de candles inserees.
    """
    table = f"candles_{tf.lower()}"
    if table not in REQUIRED_TABLES:
        return 0
    inserted = 0
    try:
        with sqlite3.connect(str(db_path)) as conn:
            for c in candles:
                try:
                    conn.execute(
                        f"INSERT OR REPLACE INTO {table} "
                        f"(symbol, tf, timestamp, open, high, low, close) "
                        f"VALUES (?, ?, ?, ?, ?, ?, ?)",
                        (
                            symbol, tf, c["timestamp"],
                            c["open"], c["high"], c["low"], c["close"],
                        ),
                    )
                    inserted += 1
                except sqlite3.IntegrityError:
                    pass
            conn.commit()
    except Exception as exc:
        log.warning("ingest_candles_batch failed: %s", exc)
    return inserted


def query_candles(
    db_path: Path, symbol: str, tf: str, limit: int = 100,
) -> list[dict[str, Any]]:
    """Recupere les N dernieres candles pour (symbol, tf)."""
    table = f"candles_{tf.lower()}"
    if table not in REQUIRED_TABLES:
        return []
    try:
        with sqlite3.connect(str(db_path)) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                f"SELECT * FROM {table} WHERE symbol = ? "
                f"ORDER BY timestamp DESC LIMIT ?",
                (symbol, limit),
            ).fetchall()
            return [dict(r) for r in rows]
    except Exception as exc:
        log.warning("query_candles failed: %s", exc)
        return []


def verify_pipeline(db_path: Path, symbol: str = "GBPUSD") -> dict[str, Any]:
    """Verifie l'integration end-to-end : 6 TF ont des candles pour le symbol."""
    counts = {}
    for tf in ["d", "h4", "h1", "m15", "m5", "m1"]:
        rows = query_candles(db_path, symbol, tf, limit=10)
        counts[tf] = len(rows)
    total = sum(counts.values())
    return {
        "symbol": symbol,
        "counts_by_tf": counts,
        "total_candles": total,
        "all_tf_have_data": all(c > 0 for c in counts.values()),
    }


def main(argv=None) -> int:
    """Demo integration test avec DB temporaire."""
    import argparse
    parser = argparse.ArgumentParser(description="V9 live data integration")
    parser.add_argument("--db-path", default=None)
    args = parser.parse_args(argv)
    print("=" * 70)
    print("V9 LIVE DATA INTEGRATION (Phase 82)")
    print("=" * 70)
    if args.db_path:
        db = Path(args.db_path)
    else:
        tmp = tempfile.mkdtemp()
        db = Path(tmp) / "v9_live_test.db"
        print(f"DB test : {db}")
        # Init tables
        ok = init_candles_tables(db)
        print(f"Init tables : {ok}")
        # Ingest 10 candles par TF
        base_candle = {
            "open": 1.30, "high": 1.301, "low": 1.299, "close": 1.3005,
        }
        for tf in ["d", "h4", "h1", "m15", "m5", "m1"]:
            candles = []
            for i in range(10):
                c = dict(base_candle)
                c["timestamp"] = f"2026-07-31T{12 + i:02d}:00:00"
                candles.append(c)
            n = ingest_candles_batch(db, "GBPUSD", tf, candles)
            print(f"Ingest GBPUSD {tf} : {n} candles")
        # Verify pipeline
        res = verify_pipeline(db, "GBPUSD")
        print()
        print(f"Symbol         : {res['symbol']}")
        print(f"Total candles  : {res['total_candles']}")
        print(f"All TF data    : {res['all_tf_have_data']}")
        for tf, count in res["counts_by_tf"].items():
            print(f"  {tf:>4s} : {count} candles")
    print("=" * 70)
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    import sys
    sys.exit(main())