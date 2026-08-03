"""Phase 157 — Analyse L11v2 par jour de semaine (correction sprint CEO).

Le sprint CEO 03/08 a livré L11 « Mer boost / Mar blacklist » basé sur un
audit qui disait 111 trades mercredi. Vérification SQL live 03/08 20:45 UTC
révèle que la VRAIE distribution GBPUSD all-time est :
  - Vendredi : 77 trades WR 97.4% +383.4p (MEGA)
  - Mercredi : 40 trades WR 45.0% +79.6p  (edge faible, pas top)
  - Mardi    : 21 trades WR 0%   -158.3p (KILL confirmé)
  - Lundi    : 18 trades WR 50%  -62.8p  (drain)
  - Jeudi    : 5  trades WR 20%  -29.4p  (drain)
  - Dimanche : 3  trades WR 67%  -9.5p   (sample nul)

L11 actuel (Mer boost) est probablement faux (audit sprint CEO biaisé).
Vrai signal = Vendredi boost + Mercredi préservation + Mardi blacklist.

Doctrine :
  R2 additif pur (nouveau script, 0 modif core/)
  R6 fail-open
  R14 audit SQL live = vérité
  R31 vérification vocabulaire/échelle (R31 sur les jours de semaine)
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


def get_db_path() -> Path:
    return _ROOT / "data" / "v9_forces.db"


_JOURS = {
    "0": "Dimanche",
    "1": "Lundi",
    "2": "Mardi",
    "3": "Mercredi",
    "4": "Jeudi",
    "5": "Vendredi",
    "6": "Samedi",
}


def analyze_gbpusd_by_day(min_n: int = 5) -> list[dict]:
    """Calcule n, WR, PNL par jour de semaine pour GBPUSD (all-time)."""
    conn = None
    try:
        conn = sqlite3.connect(str(get_db_path()), timeout=15)
        rows = conn.execute(
            """
            SELECT
              strftime('%w', opened_at) jour_num,
              COUNT(*) n,
              SUM(CASE WHEN is_win = 1 THEN 1 ELSE 0 END) wins,
              ROUND(100.0 * SUM(CASE WHEN is_win = 1 THEN 1 ELSE 0 END) / COUNT(*), 1) wr,
              ROUND(SUM(pips_simulated), 1) pnl,
              ROUND(AVG(pips_simulated), 2) avg_pips
            FROM paper_trades
            WHERE substr(snapshot_id, 3, 6) = '-GBPUS'
              AND closed_at IS NOT NULL
            GROUP BY strftime('%w', opened_at)
            ORDER BY pnl DESC
            """,
        ).fetchall()
        out = []
        for j, n, wins, wr, pnl, avg in rows:
            if n < min_n:
                continue
            out.append(
                {
                    "jour_num": int(j),
                    "jour": _JOURS.get(j, f"j{j}"),
                    "n": n,
                    "wins": wins,
                    "wr_pct": wr,
                    "pnl_pips": pnl,
                    "avg_pips": avg,
                }
            )
        return out
    except Exception as e:
        return [{"error": str(e)}]
    finally:
        if conn is not None:
            conn.close()


def recommend_l11v2(by_day: list[dict]) -> dict:
    """Recommandation L11v2 basée sur la distribution par jour.

    Règle :
      - Jour WR >= 70% ET n >= 10 ET PNL > 0 → BOOST (x1.3)
      - Jour WR <= 30% ET n >= 10 → BLACKLIST
      - Sinon → pass-through
    """
    boosts, blacklists, neutrals = [], [], []
    for d in by_day:
        if d.get("error"):
            return {"error": d["error"]}
        if d["wr_pct"] >= 70 and d["n"] >= 10 and d["pnl_pips"] > 0:
            boosts.append(d["jour"])
        elif d["wr_pct"] <= 30 and d["n"] >= 10:
            blacklists.append(d["jour"])
        else:
            neutrals.append(d["jour"])
    return {"boost": boosts, "blacklist": blacklists, "neutral": neutrals}


def main() -> int:
    parser = argparse.ArgumentParser(description="Phase 157 L11v2 audit GBPUSD par jour")
    parser.add_argument("--json", action="store_true", help="Sortie JSON")
    parser.add_argument("--min-n", type=int, default=5, help="min sample size")
    args = parser.parse_args()

    by_day = analyze_gbpusd_by_day(args.min_n)
    reco = recommend_l11v2(by_day) if by_day else {"error": "no data"}
    out = {
        "computed_at": datetime.now(timezone.utc).isoformat(),
        "by_day": by_day,
        "recommendation": reco,
    }

    if args.json:
        print(json.dumps(out, indent=2, default=str))
    else:
        print("=== Phase 157 L11v2 audit GBPUSD par jour (all-time) ===")
        print(f"  Window : all-time  min_n={args.min_n}")
        print()
        print(f"  {'Jour':<10} {'n':>4} {'WR':>6} {'PNL':>9} {'avg':>7}")
        for d in by_day:
            print(f"  {d['jour']:<10} {d['n']:>4} {d['wr_pct']:>5}% {d['pnl_pips']:>+8.1f}p {d['avg_pips']:>+6.2f}")
        print()
        if reco.get("error"):
            print(f"  Recommendation : ERROR ({reco['error']})")
        else:
            print(f"  BOOST     : {', '.join(reco['boost']) or '(none)'}")
            print(f"  BLACKLIST : {', '.join(reco['blacklist']) or '(none)'}")
            print(f"  NEUTRAL   : {', '.join(reco['neutral']) or '(none)'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
