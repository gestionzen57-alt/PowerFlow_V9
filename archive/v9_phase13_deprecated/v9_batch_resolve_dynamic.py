#!/usr/bin/env python3
"""Batch re-resolve DYNAMIC strategy - final version."""
from __future__ import annotations

import hashlib
import json
import sqlite3
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

DB_PATH = ROOT_DIR / "data" / "v9_forces.db"
from core.v9.exit_simulator import ExitSimulator, infer_session_from_hour


def main() -> int:
    backup_dir = ROOT_DIR / "docs" / "calibration" / "backups" / "2026-07-11_resolve_dynamic"
    backup_dir.mkdir(parents=True, exist_ok=True)
    md5 = hashlib.md5(DB_PATH.read_bytes()).hexdigest()
    (backup_dir / "md5_pre.txt").write_text(md5)
    print(f"Backup MD5: {md5}")

    conn = sqlite3.connect(str(DB_PATH), timeout=120)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA cache_size=-80000")
    conn.execute("PRAGMA temp_store=MEMORY")
    cur = conn.cursor()

    rows = cur.execute("""
        SELECT decision_id, snapshot_id, timestamp, symbol, timeframe, direction
        FROM decisions
        WHERE action = 'preparer_entree' AND timestamp IS NOT NULL
        ORDER BY timestamp ASC
    """).fetchall()
    print(f"{len(rows)} decisions")

    snap_ids = list(set(r[1] for r in rows if r[1]))
    ph = ",".join("?" for _ in snap_ids)
    entry_mids = {}
    for m in cur.execute(
        f"SELECT snapshot_id, mid FROM forces_snapshots WHERE snapshot_id IN ({ph}) AND mid IS NOT NULL",
        snap_ids,
    ):
        entry_mids[m[0]] = float(m[1])
    print(f"{len(entry_mids)} mids")

    min_ts = min(r[2] for r in rows if r[2])
    max_ts = max(r[2] for r in rows if r[2])
    max_end = (
        datetime.fromisoformat(max_ts.replace("Z", "+00:00"))
        + timedelta(hours=4)
    ).isoformat()
    future = {}
    for pr in cur.execute(
        """
        SELECT symbol, timeframe, timestamp, mid FROM forces_snapshots
        WHERE timestamp > ? AND timestamp <= ? AND mid IS NOT NULL
        ORDER BY symbol, timeframe, timestamp
    """,
        (min_ts, max_end),
    ):
        key = f"{pr[0]}|{pr[1]}"
        if key not in future:
            future[key] = []
        future[key].append((pr[2], float(pr[3])))
    print(f"{sum(len(v) for v in future.values())} prices")

    # Simulate and UPDATE directly in batches
    print("Simulating and updating decisions in batches...")
    sim = ExitSimulator(strategy="DYNAMIC", spread_pips=0.5)
    conn.execute("BEGIN")
    batch_updates = []
    wins = 0
    losses = 0
    skipped = 0
    total_pips = 0.0
    stats: dict[str, int] = {}
    now_iso = datetime.now(timezone.utc).isoformat()

    for idx, r in enumerate(rows):
        did, sid, ts, sym, tf, direc = r
        entry = entry_mids.get(sid)
        if entry is None:
            continue
        try:
            dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        except Exception:
            continue

        session = infer_session_from_hour(dt.hour)

        if session in ("new_york", "after"):
            skipped += 1
            cur.execute("""
                UPDATE decisions
                SET is_win=0, resolution_pips=0.0, resolution_strategy='SKIPPED',
                    resolution_details=?, resolved_at=?
                WHERE decision_id=?
            """, (json.dumps({"exit_reason": f"skipped_{session}", "session": session}), now_iso, did))
        else:
            end = dt + timedelta(hours=4)
            if end > datetime.now(timezone.utc):
                end = datetime.now(timezone.utc)
            end_iso = end.isoformat()

            key = f"{sym}|{tf}"
            mids = [p[1] for p in future.get(key, []) if p[0] > ts and p[0] <= end_iso]
            if len(mids) < 3 and tf != "M15":
                fkey = f"{sym}|M15"
                fmids = [p[1] for p in future.get(fkey, []) if p[0] > ts and p[0] <= end_iso]
                if len(fmids) > len(mids):
                    mids = fmids
            if not mids:
                skipped += 1
                cur.execute("""
                    UPDATE decisions
                    SET is_win=0, resolution_pips=0.0, resolution_strategy='SKIPPED',
                        resolution_details=?, resolved_at=?
                    WHERE decision_id=?
                """, (json.dumps({"exit_reason": "no_data", "session": session}), now_iso, did))
            else:
                res = sim.simulate(entry, direc, mids, session_marche=session)
                total_pips += res.pips
                if res.is_win:
                    wins += 1
                else:
                    losses += 1
                stats[res.exit_reason] = stats.get(res.exit_reason, 0) + 1

                details = json.dumps({
                    "exit_reason": res.exit_reason,
                    "exit_price": res.exit_price,
                    "entry_price": res.entry_price,
                    "max_favorable": res.max_favorable,
                    "max_adverse": res.max_adverse,
                    "bars_held": res.bars_held,
                    "n_future_prices": len(mids),
                    "strategy": "DYNAMIC",
                    "session": session,
                })
                cur.execute("""
                    UPDATE decisions
                    SET is_win=?, resolution_pips=?, resolution_strategy='DYNAMIC',
                        resolution_details=?, resolved_at=?
                    WHERE decision_id=?
                """, (res.is_win, res.pips, details, now_iso, did))

        # Commit every 200 updates
        if (idx + 1) % 200 == 0:
            conn.commit()
            conn.execute("BEGIN")
            if (idx + 1) % 1000 == 0:
                print(f"  ... {idx+1}/{len(rows)}")

    conn.commit()
    print(f"Simulated and updated: {wins+losses} traded, {skipped} skipped")
    print(f"WR: {wins/max(1,wins+losses)*100:.1f}% ({wins}W/{losses}L)")
    print(f"Pips: {total_pips:+.1f} total, {total_pips/max(1,wins+losses):+.1f}/trade")

    # Update paper trades
    print("Updating paper trades...")
    cur.execute("""
        UPDATE paper_trades
        SET pips_simulated = d.resolution_pips,
            is_win = d.is_win
        FROM (
            SELECT snapshot_id, resolution_pips, is_win
            FROM decisions
            WHERE resolution_strategy = 'DYNAMIC'
        ) d
        WHERE d.snapshot_id = paper_trades.snapshot_id
          AND paper_trades.closed_at IS NOT NULL
    """)
    conn.commit()

    cur.execute("""
        SELECT COUNT(*) as n,
               ROUND(AVG(pips_simulated),1) as avg_pips,
               ROUND(SUM(pips_simulated),1) as total_pips,
               SUM(CASE WHEN is_win=1 THEN 1 ELSE 0 END) as wins,
               SUM(CASE WHEN is_win=0 THEN 1 ELSE 0 END) as losses
        FROM paper_trades WHERE closed_at IS NOT NULL
    """)
    r = cur.fetchone()
    print(f"Paper trades: {r[0]} total, {r[3]}W/{r[4]}L, {r[1]:.1f} avg pips, {r[2]:.1f} total pips")

    # Cleanup
    cur.execute("DROP TABLE IF EXISTS _bdp")
    conn.commit()

    # Report
    n_traded = wins + losses
    report = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "strategy": "DYNAMIC",
        "n_decisions": len(rows),
        "n_traded": n_traded,
        "n_skipped": skipped,
        "n_wins": wins,
        "n_losses": losses,
        "win_rate_pct": round(wins / max(1, n_traded) * 100, 1),
        "total_pips": round(total_pips, 1),
        "avg_pips": round(total_pips / max(1, n_traded), 1),
        "exit_reasons": dict(stats),
    }
    report_path = ROOT_DIR / "docs" / "reports" / "BATCH_RESOLVE_DYNAMIC_20260711.json"
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Report saved: {report_path}")

    conn.close()
    print("[DONE]")
    return 0


if __name__ == "__main__":
    sys.exit(main())
