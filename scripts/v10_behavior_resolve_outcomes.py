"""V10 Behavior Outcome Resolution — résout les outcomes des comportements (Phase 10, Cognitive Continuum).

Les 78k comportements interprétés (v10_behaviors) ont is_win=NULL. Ce script
résout leur outcome en mesurant l'IMPACT directionnel du comportement sur le
marché.

⚠️ R9 HONNÊTE : ce n'est PAS un profit de trade. C'est une métrique de
"le comportement a-t-il eu un momentum directionnel réel ?" :
  - Un comportement "réussi" (is_win=1) = le prix a bougé de façon
    SIGNIFICATIVE dans les H barres forward (|Δclose| > seuil momentum).
  - Un comportement "de bruit" (is_win=0) = pas de mouvement significatif.

Cela permet d'activer le drift par comportement : détecter les comportements
qui ont un impact réel vs ceux qui sont du bruit décorrélé.

R6 fail-open. R9 : chaque résolution tracée (proxy momentum, pas profit).
R10 : compute only.
"""
from __future__ import annotations

import argparse
import logging
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

log = logging.getLogger(__name__)

DEFAULT_REG = ROOT / "data" / "v10_behaviors.db"
DEFAULT_FORCES = ROOT / "data" / "v9_forces.db"

# Horizon de résolution par TF (nb de barres forward)
HORIZON_BY_TF = {"M30": 3, "H1": 2, "H4": 1}

# Seuil de momentum (fraction de l'ATR) pour qu'un comportement soit "impactant"
MOMENTUM_ATR_RATIO = 0.5


def _atr(closes: list, period: int = 14) -> float:
    if len(closes) < 2:
        return 0.0
    ranges = [abs(closes[i] - closes[i - 1]) for i in range(1, len(closes))]
    rng = ranges[-period:]
    return (sum(rng) / len(rng)) if rng else 0.0


def resolve_behavior_outcomes(reg_db: Path, forces_db: Path,
                              *, limit: int = 50000) -> dict:
    """Résout les outcomes des comportements non résolus.

    Pour chaque comportement sans is_win :
      1. Récupère close au timestamp du comportement dans forces_snapshots.
      2. Récupère close[H] barres plus tard (H = horizon par TF).
      3. is_win = 1 si |close[H] - close[t]| > MOMENTUM_ATR_RATIO * ATR.
      4. Met à jour le registre (UPDATE batch).

    R6 fail-open : pas de barres forward → reste non résolu (pending légitime).
    """
    if not reg_db.exists() or not forces_db.exists():
        return {"status": "no_db", "n_resolved": 0}

    reg = sqlite3.connect(str(reg_db))
    forces = sqlite3.connect(str(forces_db))

    # Charger tous les comportements non résolus
    rows = reg.execute(
        "SELECT id, pair, timeframe, timestamp FROM v10_behaviors "
        "WHERE is_win IS NULL AND timestamp != '' LIMIT ?", (limit,)
    ).fetchall()
    print(f"Comportements à résoudre: {len(rows)}")

    # Group by (pair, timeframe) → charger UNE SEULE fois la série de prix par groupe
    groups = {}
    for beh_id, pair, tf, ts in rows:
        tf = tf or "H1"
        groups.setdefault((pair, tf), []).append((beh_id, ts))

    updates = []
    n_resolved = 0
    n_pending = 0
    for (pair, tf), items in groups.items():
        horizon = HORIZON_BY_TF.get(tf, 2)
        # Charge la série complète (timestamp, close) triée pour cette paire/tf
        series = forces.execute(
            "SELECT timestamp, close FROM forces_snapshots "
            "WHERE symbol=? AND timeframe=? AND is_closed_bar=1 ORDER BY bar_time",
            (pair, tf),
        ).fetchall()
        if not series:
            n_pending += len(items)
            continue
        # Index timestamp → position
        ts_list = [r[0] for r in series]
        close_list = [r[1] for r in series]
        ts_to_idx = {ts: i for i, ts in enumerate(ts_list)}

        for beh_id, ts in items:
            idx = ts_to_idx.get(ts)
            if idx is None or idx + horizon >= len(close_list):
                n_pending += 1
                continue
            close_t = close_list[idx]
            closes_series = close_list[idx:idx + horizon + 5]
            close_H = close_list[idx + horizon]
            atr = _atr(closes_series)
            if atr <= 0:
                n_pending += 1
                continue
            delta = abs(close_H - close_t)
            is_win = 1 if delta > MOMENTUM_ATR_RATIO * atr else 0
            pnl_pips = (close_H - close_t) / 0.0001
            updates.append((is_win, round(pnl_pips, 2), beh_id))
            n_resolved += 1

    # UPDATE batch (1 commit)
    reg.executemany(
        "UPDATE v10_behaviors SET is_win=?, pnl_pips=? WHERE id=?",
        updates,
    )
    reg.commit()
    reg.close()
    forces.close()

    return {"status": "ok", "n_resolved": n_resolved, "n_pending": n_pending}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--reg", default=str(DEFAULT_REG))
    ap.add_argument("--forces", default=str(DEFAULT_FORCES))
    ap.add_argument("--limit", type=int, default=50000)
    args = ap.parse_args()

    res = resolve_behavior_outcomes(Path(args.reg), Path(args.forces),
                                    limit=args.limit)
    print(res)

    reg = sqlite3.connect(str(args.reg))
    n = reg.execute("SELECT COUNT(*) FROM v10_behaviors WHERE is_win IS NOT NULL").fetchone()[0]
    n_win = reg.execute("SELECT COUNT(*) FROM v10_behaviors WHERE is_win=1").fetchone()[0]
    reg.close()
    print(f"Résolus au total: {n} | wins: {n_win}")
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    sys.exit(main())
