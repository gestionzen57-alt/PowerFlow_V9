#!/usr/bin/env python3
"""v9_analyze_ny_after_bias.py — Analyse du biais New York/After (Brief O4).

ANALYSE PURE — lecture seule, aucune écriture DB, aucune modification
core/v9/*. Répond à la question : le WR NY/After défavorable est-il (a) un
biais de période (échantillon haussier 91%), (b) un défaut structurel de
lecture (microstructure NY invalide les principes), ou (c) un mélange des
deux ?

Usage :
    python scripts/v9_analyze_ny_after_bias.py
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

from core.v9.config import DB_PATH  # noqa: E402
from core.v9.exit_simulator import ExitSimulator, infer_session_from_hour  # noqa: E402

HORIZON_HOURS = 4
SPREAD_PIPS = 0.5


def _connect(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path), timeout=60)
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def load_target_rows(conn: sqlite3.Connection) -> list[tuple]:
    """Toutes les décisions preparer_entree en session new_york/after
    (indépendamment de resolution_strategy — analyse pure sur les prix
    bruts, pas sur les labels déjà écrits)."""
    rows = conn.execute(
        """
        SELECT decision_id, snapshot_id, timestamp, symbol, timeframe,
               direction, confiance, principes_json
        FROM decisions
        WHERE action = 'preparer_entree' AND timestamp IS NOT NULL
        ORDER BY timestamp ASC
        """
    ).fetchall()
    out = []
    for r in rows:
        try:
            hour = datetime.fromisoformat(r[2].replace("Z", "+00:00")).hour
        except Exception:
            continue
        if infer_session_from_hour(hour) in ("new_york", "after"):
            out.append(r)
    return out


def load_price_context(conn, rows):
    snap_ids = list({r[1] for r in rows if r[1]})
    entry_mids = {}
    if snap_ids:
        ph = ",".join("?" for _ in snap_ids)
        for sid, mid in conn.execute(
            f"SELECT snapshot_id, mid FROM forces_snapshots WHERE snapshot_id IN ({ph}) AND mid IS NOT NULL",
            snap_ids,
        ):
            entry_mids[sid] = float(mid)

    timestamps = [r[2] for r in rows if r[2]]
    future: dict[str, list[tuple[str, float]]] = {}
    if timestamps:
        min_ts, max_ts = min(timestamps), max(timestamps)
        max_end = (
            datetime.fromisoformat(max_ts.replace("Z", "+00:00")) + timedelta(hours=HORIZON_HOURS)
        ).isoformat()
        for sym, tf, ts, mid in conn.execute(
            """
            SELECT symbol, timeframe, timestamp, mid FROM forces_snapshots
            WHERE timestamp > ? AND timestamp <= ? AND mid IS NOT NULL
            ORDER BY symbol, timeframe, timestamp
            """,
            (min_ts, max_end),
        ):
            future.setdefault(f"{sym}|{tf}", []).append((ts, float(mid)))
    return entry_mids, future


def get_mids(future, sym, tf, ts, end_iso):
    key = f"{sym}|{tf}"
    mids = [p[1] for p in future.get(key, []) if p[0] > ts and p[0] <= end_iso]
    if len(mids) < 3 and tf != "M15":
        fmids = [p[1] for p in future.get(f"{sym}|M15", []) if p[0] > ts and p[0] <= end_iso]
        if len(fmids) > len(mids):
            mids = fmids
    return mids


def main() -> int:
    conn = _connect(DB_PATH)
    rows = load_target_rows(conn)
    entry_mids, future = load_price_context(conn, rows)

    now_dt = datetime.now(timezone.utc)
    sim_mfe = ExitSimulator(strategy="MFE_ONLY", spread_pips=SPREAD_PIPS)
    sim_tp3_sl15 = ExitSimulator(strategy="TP_SL", tp_pips=3.0, sl_pips=15.0, spread_pips=SPREAD_PIPS)
    sim_tp10_sl15 = ExitSimulator(strategy="TP_SL", tp_pips=10.0, sl_pips=15.0, spread_pips=SPREAD_PIPS)

    # 1. Distribution direction x session x résultat (MFE_ONLY, référence directionnelle)
    dir_session: dict[str, dict[str, dict[str, int]]] = defaultdict(lambda: defaultdict(lambda: {"n": 0, "wins": 0}))
    # 2. WR par principe x session
    principle_session: dict[str, dict[str, dict[str, int]]] = defaultdict(lambda: defaultdict(lambda: {"n": 0, "wins": 0}))
    # 3. MFE/MAE
    mfe_mae: dict[str, list[tuple[float, float, int]]] = defaultdict(list)
    # 4. Pattern retournement (WR réel vs WR si direction inversée)
    reversal: dict[str, dict[str, int]] = defaultdict(lambda: {"n": 0, "wins": 0, "wins_if_reversed": 0})
    # 5. Contrefactuel TP3/SL15 vs TP10/SL15
    counterfactual: dict[str, dict[str, dict[str, float]]] = defaultdict(lambda: defaultdict(lambda: {"n": 0, "wins": 0, "pips": 0.0}))
    n_no_data = 0
    n_analyzed = 0

    for did, sid, ts, sym, tf, direc, conf, principes_raw in rows:
        try:
            dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        except Exception:
            continue
        entry = entry_mids.get(sid)
        if entry is None:
            n_no_data += 1
            continue
        session = infer_session_from_hour(dt.hour)
        end_dt = min(dt + timedelta(hours=HORIZON_HOURS), now_dt)
        mids = get_mids(future, sym, tf, ts, end_dt.isoformat())
        if not mids:
            n_no_data += 1
            continue
        n_analyzed += 1

        res_mfe = sim_mfe.simulate(entry, direc, mids)
        res_tp3 = sim_tp3_sl15.simulate(entry, direc, mids)
        res_tp10 = sim_tp10_sl15.simulate(entry, direc, mids)

        dir_session[session][direc]["n"] += 1
        dir_session[session][direc]["wins"] += res_mfe.is_win

        try:
            principes = json.loads(principes_raw) if principes_raw else []
        except (json.JSONDecodeError, TypeError):
            principes = []
        for p in principes:
            principle_session[p][session]["n"] += 1
            principle_session[p][session]["wins"] += res_mfe.is_win

        mfe_mae[session].append((res_mfe.max_favorable, res_mfe.max_adverse, res_mfe.is_win))

        reversal[session]["n"] += 1
        reversal[session]["wins"] += res_mfe.is_win
        # Inversion : gagnant devient perdant et vice-versa (approximation
        # symétrique — le pips exact inversé nécessiterait une resimulation
        # avec direction opposée, ce qui est fait ci-dessous précisément).
        opp_direction = "baissiere" if direc == "haussiere" else "haussiere"
        res_mfe_opp = sim_mfe.simulate(entry, opp_direction, mids)
        reversal[session]["wins_if_reversed"] += res_mfe_opp.is_win

        counterfactual[session]["TP3_SL15"]["n"] += 1
        counterfactual[session]["TP3_SL15"]["wins"] += res_tp3.is_win
        counterfactual[session]["TP3_SL15"]["pips"] += res_tp3.pips
        counterfactual[session]["TP10_SL15"]["n"] += 1
        counterfactual[session]["TP10_SL15"]["wins"] += res_tp10.is_win
        counterfactual[session]["TP10_SL15"]["pips"] += res_tp10.pips

    conn.close()

    report = {
        "timestamp_utc": now_dt.isoformat(),
        "n_target_decisions": len(rows),
        "n_analyzed": n_analyzed,
        "n_no_data": n_no_data,
        "direction_x_session": {
            sess: {
                direc: {
                    "n": v["n"], "wins": v["wins"],
                    "win_rate_pct": round(v["wins"] / max(1, v["n"]) * 100, 1),
                }
                for direc, v in dirs.items()
            }
            for sess, dirs in dir_session.items()
        },
        "principle_x_session": {
            p: {
                sess: {
                    "n": v["n"], "wins": v["wins"],
                    "win_rate_pct": round(v["wins"] / max(1, v["n"]) * 100, 1),
                }
                for sess, v in sessdata.items()
            }
            for p, sessdata in principle_session.items()
        },
        "mfe_mae_by_session": {
            sess: {
                "n": len(vals),
                "avg_mfe": round(sum(v[0] for v in vals) / max(1, len(vals)), 1),
                "avg_mae": round(sum(v[1] for v in vals) / max(1, len(vals)), 1),
                "pct_mfe_gt_10_but_lost": round(
                    sum(1 for v in vals if v[0] > 10 and v[2] == 0) / max(1, len(vals)) * 100, 1
                ),
            }
            for sess, vals in mfe_mae.items()
        },
        "reversal_pattern": {
            sess: {
                "n": v["n"],
                "win_rate_actual_pct": round(v["wins"] / max(1, v["n"]) * 100, 1),
                "win_rate_if_reversed_pct": round(v["wins_if_reversed"] / max(1, v["n"]) * 100, 1),
            }
            for sess, v in reversal.items()
        },
        "counterfactual_exit_strategies": {
            sess: {
                strat: {
                    "n": s["n"],
                    "win_rate_pct": round(s["wins"] / max(1, s["n"]) * 100, 1),
                    "total_pips": round(s["pips"], 1),
                    "avg_pips": round(s["pips"] / max(1, s["n"]), 1),
                }
                for strat, s in strategies.items()
            }
            for sess, strategies in counterfactual.items()
        },
    }

    out_path = ROOT_DIR / "docs" / "reports" / "NY_AFTER_BIAS_RAW_20260712.json"
    out_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"[OK] Rapport brut écrit : {out_path}")
    print(json.dumps(report, indent=2, ensure_ascii=False)[:2000])
    return 0


if __name__ == "__main__":
    sys.exit(main())
