"""v9_re_resolve_trades.py — Réévalue TOUS les paper_trades clôturés.

2026-07-17 motion CEO « ton papertrade est il realiste verifie tout si v est cohérent ».

Audit CEO : 4212/4772 paper_trades fermés en < 1min (89%) sont des ARTIFACTS
(pips fixes codés en dur). Le WR 90% est sur du backtest artefactuel, pas du
forward-test.

Ce script ré-évalue TOUS les trades avec le nouveau résolveur path-dependent
(ExitSimulator + prix futurs M5 réels) :
  - Win si prix futur touche TP avant SL
  - Loss si prix futur touche SL avant TP
  - MFE (max favorable excursion) si time-end

Stats live (avant fix) :
  - 4772 trades, WR 90.1% (backtest artifact)
  - TP8 fixe 4227, SL15 fixe 474

Stats attendues (après fix) :
  - Forward-test réel via prix M5
  - WR attendu ~ 50-60% (processus aléatoire de marché)
  - P&L plus petit (MFE time-end)
"""
from __future__ import annotations

import argparse
import json
import logging
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.v9.db_schema import get_connection  # noqa: E402
from core.v9.exit_simulator import (  # noqa: E402
    ExitSimulator,
    ExitStrategy,
    infer_session_from_hour,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("v9.re_resolve")


def re_resolve_all(
    db_path: Path | str | None = None,
    *,
    limit: int | None = None,
    batch_size: int = 500,
    dry_run: bool = False,
) -> dict:
    """Réévalue tous les paper_trades clôturés.

    Args:
        db_path: chemin DB (None = défaut).
        limit: limite nombre de trades (None = tous).
        batch_size: taille des batches pour commit.
        dry_run: si True, ne commit pas.

    Returns:
        dict avec stats : n_total, n_re_resolved, n_changed, wr_avant, wr_apres.
    """
    conn = get_connection(db_path)
    conn.row_factory = sqlite3.Row

    # 1. Backup table temporaire pour rollback
    log.info("Création table backup paper_trades_backup...")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS paper_trades_backup_20260717 AS
        SELECT * FROM paper_trades
    """)
    conn.execute("""
        DELETE FROM paper_trades_backup_20260717
    """)
    conn.execute("""
        INSERT INTO paper_trades_backup_20260717 SELECT * FROM paper_trades
    """)
    conn.commit()

    # 2. Stats avant
    row = conn.execute("""
        SELECT COUNT(*) n,
               SUM(CASE WHEN is_win=1 THEN 1 ELSE 0 END) wins,
               ROUND(AVG(pips_simulated), 2) avg_pips
        FROM paper_trades WHERE closed_at IS NOT NULL
    """).fetchone()
    n_before, wins_before, avg_before = row[0], row[1] or 0, row[2] or 0
    wr_before = round(100 * wins_before / max(n_before, 1), 2)
    log.info(f"AVANT: {n_before} trades, WR={wr_before}%, avg_pips={avg_before}")

    # 3. Sélectionne les trades à ré-évaluer
    sql = """
        SELECT pt.trade_id, pt.snapshot_id, pt.direction, pt.opened_at,
               d.is_win AS old_is_win, d.decision_id, d.timestamp, d.symbol,
               d.timeframe, d.regime_type, s.tp_pips_recommended,
               s.sl_pips_recommended, s.exit_strategy_recommended
        FROM paper_trades pt
        JOIN decisions d ON d.snapshot_id = pt.snapshot_id
        LEFT JOIN signals s ON s.snapshot_id = pt.snapshot_id
        WHERE pt.closed_at IS NOT NULL
    """
    if limit:
        sql += f" LIMIT {int(limit)}"
    rows = conn.execute(sql).fetchall()
    log.info(f"Trades à ré-évaluer : {len(rows)}")

    if not rows:
        conn.close()
        return {
            "n_total": 0, "n_re_resolved": 0, "n_changed": 0,
            "wr_before": wr_before, "wr_after": wr_before,
        }

    # 4. Réévaluation par batch
    n_resolved = 0
    n_changed = 0
    n_artifact = 0
    new_wins = 0
    new_pips_total = 0.0
    batch = []

    for i, r in enumerate(rows):
        tp_pips = r["tp_pips_recommended"] or 8.0
        sl_pips = r["sl_pips_recommended"] or 15.0
        strategy_name = r["exit_strategy_recommended"] or "DYNAMIC"
        try:
            strategy = ExitStrategy(strategy_name)
        except ValueError:
            strategy = ExitStrategy.TP_SL

        # 1. Prix d'entrée
        entry_row = conn.execute(
            "SELECT mid FROM forces_snapshots WHERE snapshot_id = ? LIMIT 1",
            (r["snapshot_id"],),
        ).fetchone()

        # 2. Prix futurs M5
        # Note : forces_snapshots.bar_time = epoch secondes (INTEGER),
        # paper_trades.opened_at = ISO text. Convertir opened_at → epoch.
        try:
            opened_dt = datetime.fromisoformat(
                r["opened_at"].replace("Z", "+00:00")
            )
            opened_epoch = int(opened_dt.timestamp())
        except Exception:
            opened_epoch = 0
        future_rows = conn.execute(
            """
            SELECT mid FROM forces_snapshots
            WHERE symbol = ? AND timeframe = 'M5'
              AND bar_time > ?
            ORDER BY bar_time ASC
            LIMIT 200
            """,
            (r["symbol"], opened_epoch),
        ).fetchall()

        is_artifact = False
        if entry_row and future_rows:
            entry_price = float(entry_row[0])
            future_mids = [float(fr[0]) for fr in future_rows]
            # 2026-07-17 audit CEO fix : entry doit être le 1er M5 >= opened_at,
            # PAS le M15 du snapshot_id. Sinon gap M15→M5 hit SL/TP instant.
            entry_price = future_mids[0]
            try:
                sim = ExitSimulator(
                    strategy=strategy.value,
                    tp_pips=tp_pips,
                    sl_pips=sl_pips,
                    symbol=r["symbol"],
                )
                # Session inference depuis le timestamp d'open
                try:
                    open_dt = datetime.fromisoformat(
                        r["opened_at"].replace("Z", "+00:00")
                    )
                    session = infer_session_from_hour(open_dt.hour)
                except Exception:
                    session = None
                result = sim.simulate(
                    entry=entry_price,
                    direction=r["direction"],
                    future_mids=future_mids,
                    session_marche=session,
                )
                pips_new = result.pips
                is_win_new = 1 if pips_new > 0 else 0
            except Exception as exc:
                log.debug("simulate failed for %s: %s", r["trade_id"], exc)
                is_artifact = True
                pips_new = float(tp_pips) if r["old_is_win"] == 1 else -float(sl_pips)
                is_win_new = r["old_is_win"]
        else:
            is_artifact = True
            pips_new = float(tp_pips) if r["old_is_win"] == 1 else -float(sl_pips)
            is_win_new = r["old_is_win"]

        if is_artifact:
            n_artifact += 1

        old_pips = None
        if r["old_is_win"] != is_win_new:
            n_changed += 1

        new_wins += is_win_new
        new_pips_total += pips_new
        n_resolved += 1

        # Update SQL
        if not dry_run:
            batch.append((is_win_new, pips_new, r["trade_id"]))
            if len(batch) >= batch_size:
                conn.executemany(
                    "UPDATE paper_trades SET is_win = ?, pips_simulated = ? WHERE trade_id = ?",
                    batch,
                )
                conn.commit()
                batch = []

        if (i + 1) % 500 == 0:
            log.info(f"  ... {i+1}/{len(rows)} traités")

    # Flush final
    if not dry_run and batch:
        conn.executemany(
            "UPDATE paper_trades SET is_win = ?, pips_simulated = ? WHERE trade_id = ?",
            batch,
        )
        conn.commit()

    # 5. Stats après
    if not dry_run:
        conn.commit()
    row = conn.execute("""
        SELECT COUNT(*) n,
               SUM(CASE WHEN is_win=1 THEN 1 ELSE 0 END) wins,
               ROUND(AVG(pips_simulated), 2) avg_pips,
               ROUND(SUM(pips_simulated), 1) total_pips
        FROM paper_trades WHERE closed_at IS NOT NULL
    """).fetchone()
    n_after, wins_after, avg_after, total_after = (
        row[0], row[1] or 0, row[2] or 0, row[3] or 0,
    )
    wr_after = round(100 * wins_after / max(n_after, 1), 2)
    conn.close()

    log.info("=" * 60)
    log.info(f"APRÈS: {n_after} trades, WR={wr_after}%, avg_pips={avg_after}, total_pips={total_after}")
    log.info(f"Δ WR: {wr_after - wr_before:+.2f} pts")
    log.info(f"Δ Pips: {total_after - (avg_before * n_before):+.1f}")
    log.info(f"N changed: {n_changed}/{n_resolved}")
    log.info(f"N artifact (no future mids): {n_artifact}")
    log.info("=" * 60)

    return {
        "n_total": n_after,
        "n_re_resolved": n_resolved,
        "n_changed": n_changed,
        "n_artifact": n_artifact,
        "wr_before": wr_before,
        "wr_after": wr_after,
        "avg_pips_before": avg_before,
        "avg_pips_after": avg_after,
        "total_pips_before": round(avg_before * n_before, 1),
        "total_pips_after": total_after,
        "dry_run": dry_run,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Re-resolve tous les paper_trades")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--batch-size", type=int, default=500)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args()

    if args.quiet:
        logging.getLogger().setLevel(logging.WARNING)

    result = re_resolve_all(
        limit=args.limit,
        batch_size=args.batch_size,
        dry_run=args.dry_run,
    )
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())