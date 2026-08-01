"""v9_mt4_candle_bridge.py — Phase 58 motion CEO validée.

Bridge MT4 vers DB candles pour live feed.
Lit mt4_bridge/OrderQueue.csv ou un fichier genere par MT4_EA.

Auteur : Hermes (Phase 58 motion CEO validée, 31/07/2026)
"""
from __future__ import annotations

import argparse
import csv
import logging
import re
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

log = logging.getLogger("v9.mt4_bridge")

DEFAULT_BRIDGE_DIR = Path(r"C:\projet\V9\mt4_bridge")
SUPPORTED_TF = {"M1", "M5", "M15", "M30", "H1", "H4", "D1", "D", "W1", "MN"}
TF_TO_DB = {"M1": "m1", "M5": "m5", "M15": "m15", "M30": "m30",
            "H1": "h1", "H4": "h4", "D1": "d", "D": "d", "W1": "w1",
            "MN": "mn"}


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


def parse_candle_line(line: str) -> dict | None:
    """Parse une ligne CSV MT4 : SYMBOL,TF,TIMESTAMP,O,H,L,C,V."""
    if not line.strip():
        return None
    parts = line.strip().split(",")
    if len(parts) < 7:
        return None
    if parts[0].upper() == "SYMBOL":
        return None  # header
    try:
        return {
            "symbol": parts[0].upper(),
            "tf": parts[1].upper(),
            "timestamp": parts[2],
            "open": float(parts[3]),
            "high": float(parts[4]),
            "low": float(parts[5]),
            "close": float(parts[6]),
            "volume": int(parts[7]) if len(parts) > 7 else 0,
        }
    except (ValueError, IndexError):
        return None


def scan_bridge_dir(bridge_dir: Path) -> list[Path]:
    """Liste tous les fichiers CSV du bridge."""
    if not bridge_dir.exists():
        return []
    files = []
    for pattern in ["*.csv", "*.txt"]:
        files.extend(bridge_dir.glob(pattern))
    return sorted(files)


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
    except Exception as e:
        log.warning("Insert failed: %s", e)
        return False


def bridge_ingest(bridge_dir: Path, db_path: Path) -> dict:
    """Ingest tous les CSV du bridge dans la DB."""
    files = scan_bridge_dir(bridge_dir)
    if not files:
        return {"error": "no_files", "bridge_dir": str(bridge_dir)}
    if not db_path.exists():
        return {"error": "db_missing"}
    conn = sqlite3.connect(str(db_path))
    inserted = 0
    parsed = 0
    invalid = 0
    tf_counts: dict = {}
    symbol_counts: dict = {}
    try:
        for f in files:
            try:
                with open(f, encoding="utf-8") as fp:
                    for line in fp:
                        c = parse_candle_line(line)
                        if not c:
                            continue
                        tf = c["tf"]
                        if tf not in SUPPORTED_TF:
                            invalid += 1
                            continue
                        db_tf = TF_TO_DB.get(tf, tf.lower())
                        # Init table si besoin
                        init_candles_table(conn, db_tf)
                        ok = insert_candle(conn, db_tf, c["symbol"],
                                            c["timestamp"], c["open"],
                                            c["high"], c["low"],
                                            c["close"], c["volume"])
                        if ok:
                            inserted += 1
                            tf_counts[db_tf] = tf_counts.get(db_tf, 0) + 1
                            symbol_counts[c["symbol"]] = (
                                symbol_counts.get(c["symbol"], 0) + 1
                            )
                        parsed += 1
            except OSError as e:
                log.warning("Cannot read %s: %s", f, e)
        return {
            "files_read": len(files),
            "parsed": parsed,
            "inserted": inserted,
            "invalid": invalid,
            "by_tf": tf_counts,
            "by_symbol": symbol_counts,
        }
    except (sqlite3.OperationalError, sqlite3.DatabaseError) as e:
        return {"error": str(e)}
    finally:
        conn.close()


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="V9 MT4 candle bridge (Phase 58)",
    )
    parser.add_argument("--bridge-dir", default=str(DEFAULT_BRIDGE_DIR))
    parser.add_argument("--watch", action="store_true",
                        help="Mode watch (poll toutes les 5min)")
    args = parser.parse_args(argv)

    from core.v9.config import DB_PATH
    bridge_dir = Path(args.bridge_dir)
    result = bridge_ingest(bridge_dir, Path(DB_PATH))

    print("=" * 70)
    print("PHASE 58 — MT4 CANDLE BRIDGE")
    print("=" * 70)
    if "error" in result:
        print(f"Erreur : {result['error']}")
        if "bridge_dir" in result:
            print(f"Bridge dir : {result['bridge_dir']}")
        return 1
    print(f"Files read   : {result['files_read']}")
    print(f"Parsed       : {result['parsed']}")
    print(f"Inserted     : {result['inserted']}")
    print(f"Invalid      : {result['invalid']}")
    if result["by_tf"]:
        print("By TF :")
        for tf, n in sorted(result["by_tf"].items()):
            print(f"  {tf:5s} : {n}")
    if result["by_symbol"]:
        print("By symbol :")
        for sym, n in sorted(result["by_symbol"].items()):
            print(f"  {sym:7s} : {n}")
    print("=" * 70)
    return 0


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )
    sys.exit(main())