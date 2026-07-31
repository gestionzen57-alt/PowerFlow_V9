"""human_trades_db.py — Schema + helpers pour la table v9_human_trades (J3 28/07).

Motion CEO « GO MAX » : table miroir qui stocke les trades faits à la main par
Søn avec son indicateur, pour que v9_human_mirror puisse apprendre son fingerprint.

Additif (R2) — table purement additive, n'écrase aucune table existante.
- id (autoincrement)
- timestamp (ISO UTC)
- symbol (ex: GBPUSD)
- direction (haussiere|baissiere)
- timeframe (M1|M5|M15|M30|H1|H4|D1)
- entry_price (float)
- sl_price (float)
- tp_price (float)
- confiance (0-100, déclaré par Søn)
- session (asie|sydney|london|overlap|new_york|inconnu)
- principes (JSON list of principle names)
- snapshot_id (optionnel, lier au snapshot live si connu)
- notes (texte libre)
"""
from __future__ import annotations

import json
import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

log = logging.getLogger("v9.human_trades_db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS v9_human_trades (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    symbol TEXT NOT NULL,
    direction TEXT NOT NULL,
    timeframe TEXT NOT NULL,
    entry_price REAL NOT NULL,
    sl_price REAL,
    tp_price REAL,
    confiance INTEGER,
    session TEXT,
    principes TEXT,
    snapshot_id TEXT,
    notes TEXT
)
"""

INDEX_TS = "CREATE INDEX IF NOT EXISTS idx_ht_ts ON v9_human_trades(timestamp DESC)"
INDEX_SYM = "CREATE INDEX IF NOT EXISTS idx_ht_sym ON v9_human_trades(symbol, direction)"


def init_human_trades_db(db_path: Path | str | None = None) -> bool:
    """Crée la table + 2 index si nécessaire. Idempotent (IF NOT EXISTS).

    Returns True si schéma OK, False si erreur (R6).
    """
    from core.v9.config import DB_PATH

    path = Path(db_path) if db_path else DB_PATH
    try:
        with sqlite3.connect(str(path)) as conn:
            conn.execute(SCHEMA)
            conn.execute(INDEX_TS)
            conn.execute(INDEX_SYM)
            conn.commit()
        log.info("human_trades_db: schema OK at %s", path)
        return True
    except Exception as exc:
        log.warning("human_trades_db: init failed (R6): %s", exc)
        return False


def insert_human_trade(
    db_path: Path | str | None,
    symbol: str,
    direction: str,
    timeframe: str,
    entry_price: float,
    sl_price: float | None = None,
    tp_price: float | None = None,
    confiance: int | None = None,
    session: str | None = None,
    principes: list[str] | None = None,
    snapshot_id: str | None = None,
    notes: str | None = None,
) -> int | None:
    """Insère un trade humain. Retourne l'id ou None si erreur (R6)."""
    from core.v9.config import DB_PATH

    path = Path(db_path) if db_path else DB_PATH
    init_human_trades_db(path)  # idempotent
    ts = datetime.now(timezone.utc).isoformat()
    try:
        with sqlite3.connect(str(path)) as conn:
            cur = conn.execute(
                "INSERT INTO v9_human_trades "
                "(timestamp, symbol, direction, timeframe, entry_price, "
                "sl_price, tp_price, confiance, session, principes, "
                "snapshot_id, notes) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (ts, symbol.upper(), direction.lower(), timeframe,
                 float(entry_price), sl_price, tp_price, confiance, session,
                 json.dumps(principes or []), snapshot_id, notes),
            )
            conn.commit()
            return cur.lastrowid
    except Exception as exc:
        log.warning("insert_human_trade failed (R6): %s", exc)
        return None
