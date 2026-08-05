"""V10 Metrics Watchdog — détecte les anomalies de métriques avant qu'elles ne polluent l'apprentissage.

R9 : les bugs de facteur (ex. pip JPY 100×) faussent les PnL sans bruit
visible. Ce watchdog vérifie à chaque run :
  1. PnL par trade absurde (> seuil par TF — un move de 100+ pips sur H1
     en 2 barres est physiquement improbable).
  2. PnL JPY cohérent (facteur 100, pas 10000).
  3. Doublons dans le journal (contrainte UNIQUE contournée).
  4. WR global dans une plage plausible (30-70% — hors plage = données fausses).

R10 : compute only, zéro ordre. Sortie JSON + exit code (0 = sain, 1 = anomalie).

Usage :
    python scripts/v10_metrics_watchdog.py [--decisions-db data/v10_decisions.db]
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# Seuils de plausibilité par TF (pips max par trade résolu sur horizon court)
MAX_PIPS_BY_TF = {"M30": 60.0, "H1": 80.0, "H4": 120.0, "D1": 200.0}
DEFAULT_TF = "H1"

# Plage plausible de WR global (hors plage = données fausses ou bug)
WR_MIN = 0.30
WR_MAX = 0.70


def check_metrics(dec_db: Path) -> dict:
    """Analyse le journal de décisions et retourne les anomalies détectées."""
    if not dec_db.exists():
        return {"healthy": True, "anomalies": [], "reason": "db_missing"}

    conn = sqlite3.connect(str(dec_db))
    anomalies = []
    stats = {}

    try:
        # 1. Doublons (contrainte UNIQUE contournée)
        dups = conn.execute(
            "SELECT pair, timeframe, timestamp, action, COUNT(*) as c "
            "FROM v10_decisions GROUP BY pair, timeframe, timestamp, action HAVING c > 1"
        ).fetchall()
        if dups:
            anomalies.append({
                "type": "duplicates",
                "detail": [f"{d[0]}|{d[1]}|{d[2]}|{d[3]} x{d[4]}" for d in dups[:5]],
            })

        # 2. PnL absurde par trade résolu
        rows = conn.execute(
            "SELECT id, pair, timeframe, action, pnl_pips FROM v10_decisions "
            "WHERE is_win IS NOT NULL AND pnl_pips IS NOT NULL"
        ).fetchall()
        stats["n_resolved"] = len(rows)
        bad_pnl = []
        for dec_id, pair, tf, action, pnl in rows:
            max_pips = MAX_PIPS_BY_TF.get(tf or DEFAULT_TF, MAX_PIPS_BY_TF[DEFAULT_TF])
            if abs(pnl or 0.0) > max_pips:
                bad_pnl.append({
                    "id": dec_id, "pair": pair, "tf": tf, "action": action,
                    "pnl_pips": pnl, "max_plausible": max_pips,
                })
        if bad_pnl:
            anomalies.append({"type": "absurd_pnl", "detail": bad_pnl[:10]})

        # 3. Cohérence JPY (facteur 100, pas 10000)
        jpy_rows = conn.execute(
            "SELECT id, pair, pnl_pips FROM v10_decisions "
            "WHERE pair LIKE '%JPY' AND is_win IS NOT NULL AND pnl_pips IS NOT NULL"
        ).fetchall()
        jpy_absurd = [r for r in jpy_rows if abs(r[2] or 0.0) > MAX_PIPS_BY_TF[DEFAULT_TF]]
        if jpy_absurd:
            anomalies.append({
                "type": "jpy_pip_factor",
                "detail": [{"id": r[0], "pair": r[1], "pnl_pips": r[2]} for r in jpy_absurd[:5]],
            })

        # 4. WR global dans la plage plausible
        wins = conn.execute(
            "SELECT COUNT(*) FROM v10_decisions WHERE is_win = 1"
        ).fetchone()[0]
        if stats["n_resolved"] >= 10:
            wr = wins / stats["n_resolved"]
            stats["wr"] = round(wr, 3)
            if not (WR_MIN <= wr <= WR_MAX):
                anomalies.append({
                    "type": "wr_out_of_range",
                    "detail": {"wr": wr, "n": stats["n_resolved"], "range": [WR_MIN, WR_MAX]},
                })

        stats["n_total"] = conn.execute("SELECT COUNT(*) FROM v10_decisions").fetchone()[0]
        stats["n_wins"] = wins
    finally:
        conn.close()

    return {
        "healthy": len(anomalies) == 0,
        "anomalies": anomalies,
        "stats": stats,
        "checked_at": datetime.now(timezone.utc).isoformat(),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="V10 metrics watchdog (R9)")
    ap.add_argument("--decisions-db", default=str(ROOT / "data" / "v10_decisions.db"))
    ap.add_argument("--output", default="")
    args = ap.parse_args()

    result = check_metrics(Path(args.decisions_db))

    out_path = Path(args.output) if args.output else \
        ROOT / "reports" / f"v10_metrics_watchdog_{datetime.now(timezone.utc).strftime('%Y%m%d')}.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")

    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result["healthy"] else 1


if __name__ == "__main__":
    sys.exit(main())
