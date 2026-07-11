#!/usr/bin/env python3
"""Analyse approfondie des stratégies de sortie — Phase 13.2.

Teste 16 combinaisons TP/SL/TRAILING/TIME sur les 9512 décisions.
Analyse la distribution des pips, MFE/MAE, sessions, combinaisons, TF.
"""
from __future__ import annotations

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

# Import after sys.path setup
from core.v9.exit_simulator import ExitSimulator, price_to_pips  # noqa: E402


def main() -> None:
    conn = sqlite3.connect(str(DB_PATH), timeout=120)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=OFF")
    conn.execute("PRAGMA cache_size=-80000")
    conn.execute("PRAGMA temp_store=MEMORY")
    cur = conn.cursor()

    # Load decisions
    rows = cur.execute("""
        SELECT decision_id, snapshot_id, timestamp, symbol, timeframe, direction
        FROM decisions
        WHERE action = 'preparer_entree' AND timestamp IS NOT NULL
        ORDER BY timestamp ASC
    """).fetchall()
    print(f"{len(rows)} decisions loaded")

    # Load entry mids
    snap_ids = list(set(r[1] for r in rows if r[1]))
    ph = ",".join("?" for _ in snap_ids)
    entry_mids = {}
    for m in cur.execute(
        f"SELECT snapshot_id, mid FROM forces_snapshots WHERE snapshot_id IN ({ph}) AND mid IS NOT NULL",
        snap_ids,
    ):
        entry_mids[m[0]] = float(m[1])
    print(f"{len(entry_mids)} entry mids")

    # Load future prices
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
    print(f"{sum(len(v) for v in future.values())} future prices")

    # Load principes for combination analysis
    principe_map = {}
    for pr in cur.execute(
        "SELECT decision_id, principes_json FROM decisions WHERE action = 'preparer_entree'"
    ):
        if pr[1]:
            try:
                p_list = json.loads(pr[1])
                if isinstance(p_list, list) and len(p_list) > 0:
                    principe_map[pr[0]] = "+".join(sorted(p_list))
                else:
                    principe_map[pr[0]] = "unknown"
            except Exception:
                principe_map[pr[0]] = "unknown"
        else:
            principe_map[pr[0]] = "unknown"

    # Strategies to test
    strategies = {
        "TP3_SL10": {"strategy": "TP_SL", "tp_pips": 3, "sl_pips": 10, "spread_pips": 0.5},
        "TP5_SL10": {"strategy": "TP_SL", "tp_pips": 5, "sl_pips": 10, "spread_pips": 0.5},
        "TP8_SL10": {"strategy": "TP_SL", "tp_pips": 8, "sl_pips": 10, "spread_pips": 0.5},
        "TP10_SL10": {"strategy": "TP_SL", "tp_pips": 10, "sl_pips": 10, "spread_pips": 0.5},
        "TP15_SL10": {"strategy": "TP_SL", "tp_pips": 15, "sl_pips": 10, "spread_pips": 0.5},
        "TP20_SL10": {"strategy": "TP_SL", "tp_pips": 20, "sl_pips": 10, "spread_pips": 0.5},
        "TP3_SL15": {"strategy": "TP_SL", "tp_pips": 3, "sl_pips": 15, "spread_pips": 0.5},
        "TP5_SL15": {"strategy": "TP_SL", "tp_pips": 5, "sl_pips": 15, "spread_pips": 0.5},
        "TP8_SL15": {"strategy": "TP_SL", "tp_pips": 8, "sl_pips": 15, "spread_pips": 0.5},
        "TP10_SL15": {"strategy": "TP_SL", "tp_pips": 10, "sl_pips": 15, "spread_pips": 0.5},
        "TP15_SL15": {"strategy": "TP_SL", "tp_pips": 15, "sl_pips": 15, "spread_pips": 0.5},
        "TRAIL10": {"strategy": "TRAILING", "trailing_dist": 10, "spread_pips": 0.5},
        "TRAIL15": {"strategy": "TRAILING", "trailing_dist": 15, "spread_pips": 0.5},
        "TRAIL20": {"strategy": "TRAILING", "trailing_dist": 20, "spread_pips": 0.5},
        "TIME4": {"strategy": "TIME_BASED", "time_bars": 4, "spread_pips": 0.5},
        "TIME8": {"strategy": "TIME_BASED", "time_bars": 8, "spread_pips": 0.5},
    }

    # Results accumulators
    results = {}
    session_results = {}
    combo_results = {}
    tf_results = {}
    for name in strategies:
        results[name] = {"wins": 0, "losses": 0, "total_pips": 0.0, "tp_hit": 0, "sl_hit": 0, "time_end": 0}
        session_results[name] = defaultdict(lambda: {"wins": 0, "losses": 0, "total_pips": 0.0, "n": 0})
        combo_results[name] = defaultdict(lambda: {"wins": 0, "losses": 0, "total_pips": 0.0, "n": 0})
        tf_results[name] = defaultdict(lambda: {"wins": 0, "losses": 0, "total_pips": 0.0, "n": 0})

    # Distribution analysis
    mfe_dist = defaultdict(int)
    mae_dist = defaultdict(int)
    time_to_3pips = []
    time_to_minus10 = []
    max_pips_per_trade = []
    min_pips_per_trade = []

    processed = 0
    for r in rows:
        did, sid, ts, sym, tf, direc = r
        entry = entry_mids.get(sid)
        if entry is None:
            continue
        try:
            dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        except Exception:
            continue
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
            continue

        # Session
        h = dt.hour
        if 0 <= h < 7:
            session = "asie"
        elif 7 <= h < 12:
            session = "london"
        elif 12 <= h < 16:
            session = "overlap"
        elif 16 <= h < 22:
            session = "new_york"
        else:
            session = "after"

        # Principes
        principes = principe_map.get(did, "unknown")

        # Bar-by-bar pips analysis
        bar_pips = []
        for price in mids:
            if direc == "haussiere":
                bp = price_to_pips(price - entry)
            else:
                bp = price_to_pips(entry - price)
            bar_pips.append(bp)

        max_fav = max(bar_pips) if bar_pips else 0
        max_adv = min(bar_pips) if bar_pips else 0
        max_pips_per_trade.append(max_fav)
        min_pips_per_trade.append(max_adv)

        mfe_bucket = int(max_fav / 2) * 2
        mfe_dist[mfe_bucket] += 1
        mae_bucket = int(abs(max_adv) / 2) * 2
        mae_dist[mae_bucket] += 1

        # Time to +3
        for i, bp in enumerate(bar_pips):
            if bp >= 3.0:
                time_to_3pips.append(i + 1)
                break
        # Time to -10
        for i, bp in enumerate(bar_pips):
            if bp <= -10.0:
                time_to_minus10.append(i + 1)
                break

        # Simulate each strategy
        for sname, sparams in strategies.items():
            sim = ExitSimulator(**sparams)
            res = sim.simulate(entry, direc, mids)

            results[sname]["total_pips"] += res.pips
            if res.is_win:
                results[sname]["wins"] += 1
            else:
                results[sname]["losses"] += 1
            results[sname][res.exit_reason] = results[sname].get(res.exit_reason, 0) + 1

            session_results[sname][session]["n"] += 1
            session_results[sname][session]["total_pips"] += res.pips
            if res.is_win:
                session_results[sname][session]["wins"] += 1
            else:
                session_results[sname][session]["losses"] += 1

            combo_results[sname][principes]["n"] += 1
            combo_results[sname][principes]["total_pips"] += res.pips
            if res.is_win:
                combo_results[sname][principes]["wins"] += 1
            else:
                combo_results[sname][principes]["losses"] += 1

            tf_results[sname][tf]["n"] += 1
            tf_results[sname][tf]["total_pips"] += res.pips
            if res.is_win:
                tf_results[sname][tf]["wins"] += 1
            else:
                tf_results[sname][tf]["losses"] += 1

        processed += 1
        if processed % 1000 == 0:
            print(f"  ... {processed}/{len(rows)}")

    # ── RESULTS ──
    print(f"\n{'='*90}")
    print(f"{'STRATÉGIE':<20} {'WR':>8} {'PIPS':>10} {'PIPS/TR':>8} {'TP':>6} {'SL':>6} {'TIME':>6} {'N':>6}")
    print(f"{'='*90}")

    sorted_strats = sorted(results.items(), key=lambda x: x[1]["total_pips"], reverse=True)
    for sname, sres in sorted_strats:
        n = sres["wins"] + sres["losses"]
        wr = sres["wins"] / max(1, n) * 100
        avg = sres["total_pips"] / max(1, n)
        tp = sres.get("tp_hit", 0)
        sl = sres.get("sl_hit", 0)
        te = sres.get("time_end", 0)
        print(f"{sname:<20} {wr:>7.1f}% {sres['total_pips']:>+9.1f} {avg:>+7.1f} {tp:>5} {sl:>5} {te:>5} {n:>5}")

    # ── MFE/MAE Distribution ──
    print(f"\n{'='*90}")
    print(f"DISTRIBUTION MFE (max favorable avant retournement)")
    print(f"{'='*90}")
    for bucket in sorted(mfe_dist.keys()):
        pct = mfe_dist[bucket] / max(1, processed) * 100
        bar = "█" * int(pct)
        print(f"  {bucket:>3}-{bucket+2} pips: {mfe_dist[bucket]:>5} ({pct:>5.1f}%) {bar}")

    print(f"\n{'='*90}")
    print(f"DISTRIBUTION MAE (max adverse / drawdown subi)")
    print(f"{'='*90}")
    for bucket in sorted(mae_dist.keys()):
        pct = mae_dist[bucket] / max(1, processed) * 100
        bar = "█" * int(pct)
        print(f"  {bucket:>3}-{bucket+2} pips: {mae_dist[bucket]:>5} ({pct:>5.1f}%) {bar}")

    # ── Time analysis ──
    if time_to_3pips:
        print(f"\nTemps moyen pour atteindre +3 pips: {sum(time_to_3pips)/len(time_to_3pips):.1f} barres (sur {len(time_to_3pips)}/{processed} trades)")
    if time_to_minus10:
        print(f"Temps moyen pour atteindre -10 pips: {sum(time_to_minus10)/len(time_to_minus10):.1f} barres (sur {len(time_to_minus10)}/{processed} trades)")

    # ── Max/Min pips per trade ──
    max_pips_per_trade.sort()
    min_pips_per_trade.sort()
    print(f"\nDistribution des pips max atteints par trade:")
    for pct in [50, 60, 70, 80, 90, 95, 99]:
        idx = int(len(max_pips_per_trade) * pct / 100)
        print(f"  P{pct}: {max_pips_per_trade[idx]:.1f} pips")
    print(f"\nDistribution des pips min (drawdown) par trade:")
    for pct in [50, 60, 70, 80, 90, 95, 99]:
        idx = int(len(min_pips_per_trade) * pct / 100)
        print(f"  P{pct}: {min_pips_per_trade[idx]:.1f} pips")

    # ── Per-session for best strategy ──
    best = sorted_strats[0][0]
    print(f"\n{'='*90}")
    print(f"ANALYSE PAR SESSION — {best}")
    print(f"{'='*90}")
    for sess in ["asie", "london", "overlap", "new_york", "after"]:
        sd = session_results[best].get(sess, {"n": 0, "wins": 0, "losses": 0, "total_pips": 0.0})
        if sd["n"] > 0:
            wr = sd["wins"] / max(1, sd["n"]) * 100
            avg = sd["total_pips"] / sd["n"]
            print(f"  {sess:<10} n={sd['n']:<5} WR={wr:>6.1f}%  pips={sd['total_pips']:>+8.1f}  avg={avg:>+6.1f}")

    # ── Per-combination for best strategy ──
    print(f"\n{'='*90}")
    print(f"TOP 15 COMBINAISONS — {best} (n>=5)")
    print(f"{'='*90}")
    sorted_combos = sorted(combo_results[best].items(), key=lambda x: x[1]["total_pips"], reverse=True)
    for combo, cd in sorted_combos[:15]:
        if cd["n"] >= 5:
            wr = cd["wins"] / max(1, cd["n"]) * 100
            avg = cd["total_pips"] / cd["n"]
            print(f"  {combo[:55]:<55} n={cd['n']:<4} WR={wr:>5.1f}%  pips={cd['total_pips']:>+8.1f}  avg={avg:>+6.1f}")

    # ── Per-TF for best strategy ──
    print(f"\n{'='*90}")
    print(f"ANALYSE PAR TIMEFRAME — {best}")
    print(f"{'='*90}")
    for tf_name in ["M1", "M5", "M15", "M30", "H1", "H4", "D1"]:
        td = tf_results[best].get(tf_name, {"n": 0, "wins": 0, "losses": 0, "total_pips": 0.0})
        if td["n"] > 0:
            wr = td["wins"] / max(1, td["n"]) * 100
            avg = td["total_pips"] / td["n"]
            print(f"  {tf_name:<5} n={td['n']:<6} WR={wr:>6.1f}%  pips={td['total_pips']:>+8.1f}  avg={avg:>+6.1f}")

    # ── Save report ──
    report = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "n_decisions": processed,
        "strategies": {},
        "mfe_distribution": {str(k): v for k, v in sorted(mfe_dist.items())},
        "mae_distribution": {str(k): v for k, v in sorted(mae_dist.items())},
        "pips_percentiles": {
            "max": {f"P{p}": round(max_pips_per_trade[int(len(max_pips_per_trade) * p / 100)], 1) for p in [50, 60, 70, 80, 90, 95, 99]},
            "min": {f"P{p}": round(min_pips_per_trade[int(len(min_pips_per_trade) * p / 100)], 1) for p in [50, 60, 70, 80, 90, 95, 99]},
        },
    }
    for sname, sres in sorted_strats:
        n = sres["wins"] + sres["losses"]
        report["strategies"][sname] = {
            "n": n,
            "wins": sres["wins"],
            "losses": sres["losses"],
            "win_rate_pct": round(sres["wins"] / max(1, n) * 100, 1),
            "total_pips": round(sres["total_pips"], 1),
            "avg_pips": round(sres["total_pips"] / max(1, n), 1),
            "tp_hit": sres.get("tp_hit", 0),
            "sl_hit": sres.get("sl_hit", 0),
            "time_end": sres.get("time_end", 0),
        }

    report_path = ROOT_DIR / "docs" / "reports" / "EXIT_STRATEGY_ANALYSIS_20260711.json"
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\n[OK] Rapport sauvegardé: {report_path}")

    conn.close()
    print("[DONE]")


if __name__ == "__main__":
    main()
