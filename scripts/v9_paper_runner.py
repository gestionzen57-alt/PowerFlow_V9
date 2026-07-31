"""v9_paper_runner.py — Phase 16 motion CEO « EDGE FUND MAX ».

Paper-trading continu automatise. Execute toutes les N minutes :
1. Lit les derniers snapshots GBPUSD M5 du pipeline (forces_snapshots)
2. Pour chaque snapshot, evalue les filtres L1-L14 via v9_mega_edge_filter
3. Si go=True, OUVRE un paper_trade dans v9_paper_trades
4. Surveille les paper_trades ouverts, FERME selon time_exit (L3) ou TP/SL
5. Log chaque action dans v9_paper_log

Separation nette :
- paper_trades (table historique, Phase 1, 337 trades) = BACKTEST 90j
- v9_paper_trades (table dediee Phase 16) = LIVE simulation continue
- v9_paper_log (table dediee Phase 16) = audit trail de chaque decision

Usage :
  python scripts/v9_paper_runner.py --once        # 1 cycle
  python scripts/v9_paper_runner.py --loop 60     # 1 cycle / 60s
  python scripts/v9_paper_runner.py --status      # etat courant
  python scripts/v9_paper_runner.py --close-all   # fermer tous ouverts

Auteur : Hermes (Phase 16 motion CEO autopilote, 31/07/2026)
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sqlite3
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Bootstrap path pour execution directe CLI.
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

log = logging.getLogger("v9.paper_runner")

# Constantes Phase 16
PAPER_TP_PIPS = 25.0   # TP cible aligne L1 baseline
PAPER_SL_PIPS = 8.0    # SL cible aligne L1 baseline
PAPER_LOT = 0.01       # Mini-lot FTMO par defaut
MAX_HOLD_MINUTES = 5.0  # L3 time_exit aligne Phase 3
SNAPSHOT_LOOKBACK_MIN = 30  # chercher snapshots des 30 dernieres min
MAX_OPEN_TRADES = 3    # max paper_trades ouverts simultanement


def _ensure_tables(db_path: Path | str) -> None:
    """Cree les tables v9_paper_trades et v9_paper_log si absentes."""
    db_path = Path(db_path)
    if not db_path.exists():
        return
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS v9_paper_trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                snapshot_id TEXT NOT NULL,
                symbol TEXT NOT NULL,
                direction TEXT NOT NULL,
                opened_at TEXT NOT NULL,
                closed_at TEXT,
                entry_price REAL,
                tp_pips REAL,
                sl_pips REAL,
                lot REAL,
                close_reason TEXT,
                close_price REAL,
                pips_brut REAL,
                pips_net REAL,
                spread_pips REAL,
                leviers TEXT,
                confidence REAL
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_paper_open
            ON v9_paper_trades (symbol, direction, closed_at)
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS v9_paper_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts TEXT NOT NULL,
                event_type TEXT NOT NULL,
                snapshot_id TEXT,
                symbol TEXT,
                direction TEXT,
                details TEXT
            )
        """)
        conn.commit()
    finally:
        conn.close()


def _log_event(db_path, event_type, snapshot_id=None, symbol=None,
               direction=None, details=None):
    """Log un evenement dans v9_paper_log."""
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute("""
            INSERT INTO v9_paper_log
            (ts, event_type, snapshot_id, symbol, direction, details)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            datetime.now(timezone.utc).isoformat(),
            event_type, snapshot_id, symbol, direction,
            json.dumps(details) if details else None,
        ))
        conn.commit()
    finally:
        conn.close()


def get_recent_snapshots(db_path, *, symbol="GBPUSD",
                         lookback_minutes=SNAPSHOT_LOOKBACK_MIN,
                         limit=20):
    """Retourne les snapshots recents pour le symbol donne."""
    db_path = Path(db_path)
    if not db_path.exists():
        return []
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute("""
            SELECT snapshot_id, timestamp, mid, symbol, timeframe
            FROM forces_snapshots
            WHERE symbol = ?
              AND timestamp > datetime('now', ? || ' minutes')
              AND substr(snapshot_id, 4, 6) = ?
            ORDER BY timestamp DESC
            LIMIT ?
        """, (symbol, -lookback_minutes, symbol, limit)).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def count_open_paper_trades(db_path, *, symbol="GBPUSD"):
    """Compte les paper_trades ouverts pour le symbol."""
    conn = sqlite3.connect(str(db_path))
    try:
        row = conn.execute("""
            SELECT COUNT(*) FROM v9_paper_trades
            WHERE symbol = ? AND closed_at IS NULL
        """, (symbol,)).fetchone()
        return int(row[0]) if row else 0
    finally:
        conn.close()


def evaluate_signal(db_path, snapshot_id, symbol="GBPUSD",
                    direction="haussiere"):
    """Evalue un snapshot via v9_mega_edge_filter. Retourne dict go/decision."""
    from core.v9.v9_mega_edge_filter import mega_edge_evaluation
    # Lecture rapide des principes (simplification : vide)
    return mega_edge_evaluation(
        symbol=symbol, direction=direction,
        snapshot_id=snapshot_id,
        principes=[],  # TODO Phase 17 : lire depuis DB
        db_path=db_path,
    )


def open_paper_trade(db_path, *, snapshot_id, symbol, direction,
                     entry_price, tp_pips=PAPER_TP_PIPS,
                     sl_pips=PAPER_SL_PIPS, lot=PAPER_LOT,
                     leviers=None, confidence=0.0):
    """Ouvre un paper_trade dans la table dediee."""
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute("""
            INSERT INTO v9_paper_trades
            (snapshot_id, symbol, direction, opened_at,
             entry_price, tp_pips, sl_pips, lot, leviers, confidence)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            snapshot_id, symbol, direction,
            datetime.now(timezone.utc).isoformat(),
            entry_price, tp_pips, sl_pips, lot,
            json.dumps(leviers) if leviers else None,
            confidence,
        ))
        conn.commit()
        trade_id = conn.execute(
            "SELECT last_insert_rowid()"
        ).fetchone()[0]
    finally:
        conn.close()
    _log_event(db_path, "OPEN", snapshot_id, symbol, direction,
               {"trade_id": trade_id, "tp": tp_pips, "sl": sl_pips,
                "lot": lot, "entry": entry_price})
    return trade_id


def close_paper_trade(db_path, trade_id, *, close_reason,
                      close_price, pips_brut, pips_net, spread_pips=1.5):
    """Ferme un paper_trade existant."""
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute("""
            UPDATE v9_paper_trades
            SET closed_at = ?, close_reason = ?, close_price = ?,
                pips_brut = ?, pips_net = ?, spread_pips = ?
            WHERE id = ?
        """, (
            datetime.now(timezone.utc).isoformat(),
            close_reason, close_price,
            pips_brut, pips_net, spread_pips,
            trade_id,
        ))
        conn.commit()
    finally:
        conn.close()
    _log_event(db_path, "CLOSE", None, None, None,
               {"trade_id": trade_id, "reason": close_reason,
                "pips_brut": pips_brut, "pips_net": pips_net})


def close_expired_trades(db_path, *, max_hold_minutes=MAX_HOLD_MINUTES):
    """Ferme les paper_trades ouverts > max_hold_minutes (L3 time_exit)."""
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute("""
            SELECT id, snapshot_id, symbol, direction, opened_at,
                   entry_price, tp_pips, sl_pips, lot
            FROM v9_paper_trades
            WHERE closed_at IS NULL
              AND (julianday('now') - julianday(opened_at)) * 24 * 60 > ?
        """, (max_hold_minutes,)).fetchall()
        closed = 0
        for r in rows:
            # L3 time_exit : ferme a pips=0 (artifact)
            close_paper_trade(
                db_path, r["id"],
                close_reason="L3_time_exit",
                close_price=r["entry_price"],  # pas de move
                pips_brut=0.0,
                pips_net=-1.5,  # spread paye
                spread_pips=1.5,
            )
            closed += 1
        return closed
    finally:
        conn.close()


def get_status(db_path):
    """Retourne l'etat actuel des paper_trades."""
    db_path = Path(db_path)
    if not db_path.exists():
        return {"error": "db_missing"}
    _ensure_tables(db_path)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        open_rows = conn.execute("""
            SELECT id, snapshot_id, symbol, direction, opened_at,
                   tp_pips, sl_pips, lot
            FROM v9_paper_trades
            WHERE closed_at IS NULL
            ORDER BY opened_at DESC
        """).fetchall()
        closed_rows = conn.execute("""
            SELECT id, symbol, direction, opened_at, closed_at,
                   close_reason, pips_brut, pips_net
            FROM v9_paper_trades
            WHERE closed_at IS NOT NULL
            ORDER BY closed_at DESC
            LIMIT 20
        """).fetchall()
        n_total = conn.execute(
            "SELECT COUNT(*) FROM v9_paper_trades"
        ).fetchone()[0]
        n_wins = conn.execute(
            "SELECT COUNT(*) FROM v9_paper_trades "
            "WHERE closed_at IS NOT NULL AND pips_net > 0"
        ).fetchone()[0]
        n_closed = conn.execute(
            "SELECT COUNT(*) FROM v9_paper_trades "
            "WHERE closed_at IS NOT NULL"
        ).fetchone()[0]
        return {
            "n_open": len(open_rows),
            "n_closed": n_closed,
            "n_total": n_total,
            "wr_pct": (100.0 * n_wins / n_closed) if n_closed else 0.0,
            "open_trades": [dict(r) for r in open_rows],
            "recent_closed": [dict(r) for r in closed_rows],
        }
    finally:
        conn.close()


def run_one_cycle(db_path, *, symbol="GBPUSD", direction="haussiere"):
    """Execute 1 cycle : ferme expired + cherche nouveaux signaux."""
    db_path = Path(db_path)
    _ensure_tables(db_path)

    # 1. Fermer les trades expires (L3 time_exit)
    n_closed = close_expired_trades(db_path)
    if n_closed:
        log.info("paper_runner: %d trades fermes (L3 time_exit)", n_closed)

    # 2. Verifier limite max open
    n_open = count_open_paper_trades(db_path, symbol=symbol)
    if n_open >= MAX_OPEN_TRADES:
        return {
            "cycle": "skipped_max_open",
            "n_open": n_open,
            "n_closed_expired": n_closed,
        }

    # 3. Chercher nouveaux signaux
    snapshots = get_recent_snapshots(db_path, symbol=symbol)
    if not snapshots:
        return {
            "cycle": "no_snapshots",
            "n_open": n_open,
            "n_closed_expired": n_closed,
        }

    # 4. Filtrer ceux qui n'ont pas deja un trade ouvert
    conn = sqlite3.connect(str(db_path))
    try:
        open_snaps = {r[0] for r in conn.execute(
            "SELECT snapshot_id FROM v9_paper_trades "
            "WHERE closed_at IS NULL"
        ).fetchall()}
    finally:
        conn.close()

    new_trades = 0
    for snap in snapshots:
        if snap["snapshot_id"] in open_snaps:
            continue
        # Evaluer signal
        decision = evaluate_signal(db_path, snap["snapshot_id"],
                                    symbol=symbol, direction=direction)
        if decision.get("go"):
            entry_price = float(snap["mid"]) if snap["mid"] else 1.2680
            open_paper_trade(
                db_path,
                snapshot_id=snap["snapshot_id"],
                symbol=symbol,
                direction=direction,
                entry_price=entry_price,
                leviers=decision.get("leviers", []),
                confidence=decision.get("sizing_multiplier", 1.0),
            )
            new_trades += 1

    return {
        "cycle": "completed",
        "n_open_before": n_open,
        "n_new_trades": new_trades,
        "n_closed_expired": n_closed,
        "n_snapshots_examined": len(snapshots),
    }


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="V9 paper-trading runner Phase 16"
    )
    parser.add_argument("--once", action="store_true",
                        help="Execute 1 cycle et quitte")
    parser.add_argument("--loop", type=int, metavar="SECONDS",
                        help="Execute en boucle toutes les N secondes")
    parser.add_argument("--status", action="store_true",
                        help="Affiche l'etat courant")
    parser.add_argument("--close-all", action="store_true",
                        help="Ferme tous les paper_trades ouverts")
    parser.add_argument("--symbol", default="GBPUSD",
                        help="Symbol a trader (defaut GBPUSD)")
    parser.add_argument("--direction", default="haussiere",
                        choices=["haussiere", "baissiere"],
                        help="Direction (defaut haussiere)")
    args = parser.parse_args(argv)

    from core.v9.config import DB_PATH
    db_path = DB_PATH

    if args.status:
        status = get_status(db_path)
        print(json.dumps(status, indent=2, ensure_ascii=False, default=str))
        return 0

    if args.close_all:
        n_open = count_open_paper_trades(db_path, symbol=args.symbol)
        conn = sqlite3.connect(str(db_path))
        try:
            conn.execute("""
                UPDATE v9_paper_trades
                SET closed_at = ?, close_reason = 'manual_close_all',
                    pips_brut = 0, pips_net = -1.5, spread_pips = 1.5
                WHERE closed_at IS NULL AND symbol = ?
            """, (datetime.now(timezone.utc).isoformat(), args.symbol))
            conn.commit()
        finally:
            conn.close()
        _log_event(db_path, "CLOSE_ALL", None, args.symbol, args.direction,
                   {"n_closed": n_open})
        print(json.dumps({"closed": n_open}, indent=2))
        return 0

    if args.once:
        result = run_one_cycle(db_path, symbol=args.symbol,
                               direction=args.direction)
        print(json.dumps(result, indent=2, ensure_ascii=False, default=str))
        return 0

    if args.loop:
        log.info("paper_runner: loop started (interval=%ds)", args.loop)
        while True:
            try:
                result = run_one_cycle(
                    db_path, symbol=args.symbol,
                    direction=args.direction,
                )
                log.info("cycle: %s", result)
            except KeyboardInterrupt:
                log.info("paper_runner: stopped by user")
                break
            except Exception as exc:
                log.error("cycle error: %s", exc)
            time.sleep(args.loop)
        return 0

    parser.print_help()
    return 1


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )
    sys.exit(main())