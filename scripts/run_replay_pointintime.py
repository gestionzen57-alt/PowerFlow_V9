"""Replay point-in-time (R2 additif) — FALSIFICATION du lookahead H4/fractal.

Problème : `v10_replay_engine._replay_pair_tf` calcule `h4_bias` UNE FOIS sur la
fin de période (lookahead) puis l'applique à CHAQUE décision M15. Idem fractal_conf.
Ce runner refait le replay M15 EURUSD/USDCAD/USDCHF LONDON avec :
  - h4_bias recalé PIT : régression close H4 avec bar_time <= barre i (honnête)
  - fractal neutralisé (None) : élimine la 2e fuite
  - résolution PnL identique (_simulate_pnl : TP/SL sur barres futures)
Si WR/PF s'effondrent vers 50% => l'edge 58.9% était un artefact de lookahead.

Usage : python scripts/run_replay_pointintime.py
"""
from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.v10 import v10_replay_engine as eng  # noqa: E402

PAIRS = ("EURUSD", "USDCAD", "USDCHF")
TF = "M15"
LIMIT = 800
DB = "data/v9_forces.db"


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _load_bars_pit(conn, symbol, tf, limit):
    """Réutilise le monkeypatch honnête de run_replay_c21_validation."""
    rows = conn.execute(
        "SELECT bar_time AS timestamp, open, high, low, close, tick_volume, "
        "force_usd, force_gbp, force_eur, force_jpy, force_cad, force_chf, force_aud, force_nzd "
        "FROM forces_snapshots WHERE symbol=? AND timeframe=? AND is_closed_bar=1 "
        "ORDER BY bar_time DESC LIMIT ?",
        (symbol.upper(), tf.upper(), limit),
    ).fetchall()
    if not rows:
        return []
    bars = []
    for r in reversed(rows):
        b = dict(r)
        for k in ("open", "high", "low", "close"):
            b[k] = float(b.get(k) or 0.0)
        b["tick_volume"] = float(b.get("tick_volume") or 0.0)
        for c in ("force_usd", "force_gbp", "force_eur", "force_jpy",
                  "force_cad", "force_chf", "force_aud", "force_nzd"):
            b[c] = float(b.get(c) or 50.0)
        b["direction"] = b.get("direction", "neutre")
        b["vitesse"] = float(b.get("vitesse") or 0.0)
        bars.append(b)
    return bars


def _h4_bias_pit(conn, symbol, at_bar_time):
    """Pente close H4 avec bar_time <= at_bar_time (point-in-time, pas lookahead)."""
    try:
        rows = conn.execute(
            "SELECT close FROM forces_snapshots WHERE symbol=? AND timeframe='H4' "
            "AND is_closed_bar=1 AND bar_time<=? ORDER BY bar_time DESC LIMIT 30",
            (symbol.upper(), at_bar_time),
        ).fetchall()
        closes = [float(r["close"]) for r in reversed(rows)]
        n = len(closes)
        if n >= 5:
            xs = list(range(n))
            mx = sum(xs) / n
            my = sum(closes) / n
            num = sum((x - mx) * (c - my) for x, c in zip(xs, closes, strict=True))
            den = sum((x - mx) ** 2 for x in xs) or 1e-9
            slope = (num / den) / (my or 1.0)
            return round(max(-1.0, min(1.0, slope * 200)), 4)
    except Exception:
        pass
    return 0.0


def main() -> None:
    print(f"[{_now()}] REPLAY POINT-IN-TIME (sans lookahead H4/fractal) {PAIRS} × {TF} × LONDON × {LIMIT}")
    conn = eng._db_connect(DB)
    if conn is None:
        print("DB inaccessible")
        return
    # monkeypatch _load_bars honnête
    eng._load_bars = _load_bars_pit
    # neutraliser fractal (fuite) : forcer _FRACTAL_OK à False via monkeypatch
    eng._FRACTAL_OK = False

    total_trades = total_wins = 0
    total_pnl = 0.0
    gross_w = gross_l = 0.0
    per_pair = {}
    by_level = {}

    for pair in PAIRS:
        all_bars = eng._load_bars(conn, pair, TF, LIMIT)
        if not all_bars:
            print(f"  {pair}: 0 barres")
            continue
        n_tr = n_w = 0
        pnl = 0.0
        for i in range(30, len(all_bars)):
            bar = all_bars[i]
            bar_time = int(bar.get("timestamp") or 0)
            hb = _h4_bias_pit(conn, pair, bar_time)  # PIT, variable par barre
            window = all_bars[max(0, i - 200): i + 1]
            rec = eng._decide_one(
                pair, TF, eng.TF_ROLE.get(TF, "ENTRY_STRUCTURE"),
                window, hb, None, DB, "LONDON", None,
            )
            if rec is None:
                continue
            if rec.action in ("BUY", "SELL"):
                pnl_i, tp_p, sl_p = eng._simulate_pnl(all_bars, i, rec.action, pair, TF, rec.signal_level)
                pnl += pnl_i
                n_tr += 1
                if pnl_i > 0:
                    n_w += 1
                    gross_w += pnl_i
                else:
                    gross_l += abs(pnl_i)
                lv = rec.signal_level
                bl = by_level.setdefault(lv, {"n": 0, "wins": 0, "pnl": 0.0})
                bl["n"] += 1
                bl["wins"] += 1 if pnl_i > 0 else 0
                bl["pnl"] += pnl_i
        wr = n_w / n_tr if n_tr else 0.0
        per_pair[pair] = {"n": n_tr, "wins": n_w, "wr": round(wr, 4), "pnl_pips": round(pnl, 2)}
        total_trades += n_tr
        total_wins += n_w
        total_pnl += pnl
        print(f"  {pair}: n={n_tr} WR={wr:.4f} PnL={pnl:+.2f}")

    pf = (gross_w / gross_l) if gross_l > 0 else float("inf")
    print("\n=== RÉSULTAT POINT-IN-TIME ===")
    print(f"n_trades={total_trades} WR={total_wins/total_trades:.4f} "
          f"PnL={total_pnl:+.2f} PF={pf:.3f}")
    print("BY_LEVEL:")
    for lv, d in sorted(by_level.items()):
        w = d["wins"]/d["n"] if d["n"] else 0
        print(f"  {lv}: n={d['n']} WR={w:.4f} PnL={d['pnl']:+.2f}")

    report = {
        "ts": _now(), "mode": "point_in_time_no_lookahead",
        "pairs": list(PAIRS), "tf": TF, "limit": LIMIT,
        "n_trades": total_trades, "wr": round(total_wins/total_trades, 4),
        "pnl_pips": round(total_pnl, 2), "pf": round(pf, 4),
        "by_pair": per_pair, "by_level": by_level,
        "audit": {
            "h4_bias": "point_in_time (bar_time<=i) — PAS lookahead",
            "fractal": "neutralisé (fuite éliminée)",
            "resolution": "simulate_pnl TP/SL sur barres futures (légitime replay)",
        },
    }
    out = ROOT / "reports" / "replay_pointintime_20260811.json"
    out.write_text(json.dumps(report, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"\nRapport : {out}")


if __name__ == "__main__":
    main()
