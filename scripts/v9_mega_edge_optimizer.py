"""v9_mega_edge_optimizer.py — Phase 21 motion CEO « EDGE FUND MAX ».

Calibration runtime des seuils L1-L14 basee sur les paper trades live.
Apres chaque batch de trades fermes (Phase 16), recalcule les seuils
optimaux (window_hour, blacklists) pour maximiser expectancy.

Output : config/calibration_overrides_runtime.json (calibration live).

Note : la calibration de production reste dans config/calibration_overrides.json
(generee par auto_calibrator Phase E, recalibrage 27/07). Ce script ajoute
une couche RUNTIME qui peut etre rollback instantanement.

Auteur : Hermes (Phase 21 motion CEO autopilote, 31/07/2026)
"""
from __future__ import annotations

import json
import logging
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

# Bootstrap path pour execution directe CLI.
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

log = logging.getLogger("v9.mega_edge_optimizer")

# Cibles Phase 15
TARGET_WR = 60.0
TARGET_EXP_NET = 3.0
MIN_SAMPLE = 20

RUNTIME_OVERRIDES_FILE = Path(r"C:\projet\V9\config\calibration_overrides_runtime.json")


def get_paper_trades_closed(db_path: Path | str) -> list[dict]:
    """Retourne les paper trades fermes depuis la table v9_paper_trades."""
    db_path = Path(db_path)
    if not db_path.exists():
        return []
    try:
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        try:
            # Detecter presence de direction (degrade propre)
            has_direction = False
            try:
                cols = [r[1] for r in conn.execute(
                    "PRAGMA table_info(v9_paper_trades)"
                ).fetchall()]
                has_direction = "direction" in cols
            except Exception:
                pass

            dir_select = (
                "direction," if has_direction
                else "'unknown' AS direction,"
            )
            rows = conn.execute(f"""
                SELECT id, symbol, {dir_select}
                       opened_at, closed_at,
                       pips_brut, pips_net, spread_pips, close_reason,
                       strftime('%H', opened_at) AS hour_utc
                FROM v9_paper_trades
                WHERE closed_at IS NOT NULL
                ORDER BY closed_at DESC
            """).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()
    except (sqlite3.OperationalError, sqlite3.DatabaseError):
        return []


def compute_hour_wr(trades: list[dict]) -> dict:
    """Calcule WR par heure UTC (L1 hour tuning)."""
    wr_by_hour = {}
    for t in trades:
        h = t.get("hour_utc", "00")
        if h not in wr_by_hour:
            wr_by_hour[h] = {"n": 0, "wins": 0, "pips_net": 0.0}
        wr_by_hour[h]["n"] += 1
        if (t.get("pips_net") or 0) > 0:
            wr_by_hour[h]["wins"] += 1
        wr_by_hour[h]["pips_net"] += float(t.get("pips_net") or 0)
    for h in wr_by_hour:
        n = wr_by_hour[h]["n"]
        wr_by_hour[h]["wr_pct"] = (100.0 * wr_by_hour[h]["wins"] / n) if n else 0.0
    return wr_by_hour


def compute_symbol_blacklist(trades: list[dict], min_n=5) -> list[str]:
    """Detecte symbols avec WR < 50% (L7 tuning live)."""
    by_symbol = {}
    for t in trades:
        s = t.get("symbol", "unknown")
        if s not in by_symbol:
            by_symbol[s] = {"n": 0, "wins": 0}
        by_symbol[s]["n"] += 1
        if (t.get("pips_net") or 0) > 0:
            by_symbol[s]["wins"] += 1
    blacklist = []
    for s, v in by_symbol.items():
        if v["n"] >= min_n:
            wr = 100.0 * v["wins"] / v["n"]
            if wr < 50.0:
                blacklist.append(s)
    return sorted(blacklist)


def compute_day_blacklist(trades: list[dict], min_n=3) -> list[str]:
    """Detecte jour de semaine avec WR < 50% (L14 tuning live)."""
    by_day = {}
    for t in trades:
        day = t.get("opened_at", "")[:10]
        if not day:
            continue
        wd = datetime.fromisoformat(day).strftime("%A")
        if wd not in by_day:
            by_day[wd] = {"n": 0, "wins": 0}
        by_day[wd]["n"] += 1
        if (t.get("pips_net") or 0) > 0:
            by_day[wd]["wins"] += 1
    blacklist = []
    for d, v in by_day.items():
        if v["n"] >= min_n:
            wr = 100.0 * v["wins"] / v["n"]
            if wr < 50.0:
                blacklist.append(d)
    return sorted(blacklist)


def optimize_runtime(db_path: Path | str) -> dict:
    """Optimise les seuils runtime L1/L7/L14 selon paper trades fermes."""
    trades = get_paper_trades_closed(db_path)
    n_closed = len(trades)

    if n_closed < MIN_SAMPLE:
        return {
            "recommendation": "WAIT_MORE_DATA",
            "n_closed": n_closed,
            "min_required": MIN_SAMPLE,
        }

    wr_by_hour = compute_hour_wr(trades)
    symbol_blacklist = compute_symbol_blacklist(trades)
    day_blacklist = compute_day_blacklist(trades)

    # Optimisation window_hour : heures avec WR >= TARGET_WR
    optimal_hours = sorted(
        h for h, v in wr_by_hour.items()
        if v["wr_pct"] >= TARGET_WR and v["n"] >= 3
    )

    return {
        "recommendation": (
            "APPLY_OVERRIDES" if optimal_hours else "NO_OPTIMAL_HOURS"
        ),
        "n_closed": n_closed,
        "optimal_hours_utc": optimal_hours,
        "wr_by_hour": wr_by_hour,
        "symbol_blacklist_runtime": symbol_blacklist,
        "day_blacklist_runtime": day_blacklist,
        "ts": datetime.now(timezone.utc).isoformat(),
    }


def apply_runtime_overrides(optimization: dict) -> bool:
    """Applique les overrides runtime dans calibration_overrides_runtime.json."""
    if optimization.get("recommendation") != "APPLY_OVERRIDES":
        return False
    RUNTIME_OVERRIDES_FILE.parent.mkdir(parents=True, exist_ok=True)
    overrides = {
        "ts": optimization["ts"],
        "source": "v9_mega_edge_optimizer",
        "phase": 21,
        "window_hour_utc": optimization["optimal_hours_utc"],
        "blacklist_symbols_runtime": optimization["symbol_blacklist_runtime"],
        "blacklist_days_runtime": optimization["day_blacklist_runtime"],
        "wr_by_hour": optimization["wr_by_hour"],
    }
    RUNTIME_OVERRIDES_FILE.write_text(
        json.dumps(overrides, indent=2, ensure_ascii=False), encoding="utf-8",
    )
    return True


def main(argv=None) -> int:
    import argparse
    parser = argparse.ArgumentParser(
        description="V9 mega edge live optimizer (Phase 21)",
    )
    parser.add_argument("--check", action="store_true",
                        help="Verifie sans appliquer")
    parser.add_argument("--apply", action="store_true",
                        help="Applique les overrides")
    args = parser.parse_args(argv)

    from core.v9.config import DB_PATH
    db_path = DB_PATH

    print("=" * 70)
    print("PHASE 21 — MEGA EDGE LIVE OPTIMIZER")
    print("=" * 70)

    optimization = optimize_runtime(db_path)
    print(f"n_closed : {optimization.get('n_closed', 0)} / "
          f"{optimization.get('min_required', MIN_SAMPLE)}")
    print(f"Recommendation : {optimization.get('recommendation', 'unknown')}")

    if "wr_by_hour" in optimization:
        print()
        print("WR par heure UTC :")
        for h in sorted(optimization["wr_by_hour"].keys()):
            d = optimization["wr_by_hour"][h]
            print(f"  {h}h : n={d['n']:3d}  WR={d['wr_pct']:5.1f}%  "
                  f"pips_net={d['pips_net']:+.1f}")
        if optimization.get("optimal_hours_utc"):
            print(f"\nOptimal hours : {optimization['optimal_hours_utc']}")

    if optimization.get("symbol_blacklist_runtime"):
        print(f"\nSymboles a blacklister (WR<50%): "
              f"{optimization['symbol_blacklist_runtime']}")
    if optimization.get("day_blacklist_runtime"):
        print(f"Jours a blacklister (WR<50%): "
              f"{optimization['day_blacklist_runtime']}")

    if args.check or optimization.get("recommendation") != "APPLY_OVERRIDES":
        return 0 if optimization.get("recommendation") != "WAIT_MORE_DATA" else 1

    if args.apply:
        ok = apply_runtime_overrides(optimization)
        if ok:
            print(f"\n>>> Runtime overrides ecrits : {RUNTIME_OVERRIDES_FILE}")
            return 0
        print("\n>>> Apply echoue")
        return 1

    return 0


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )
    sys.exit(main())